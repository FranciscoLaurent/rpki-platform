"""设备配置生成服务。

负责设备配置模板的 CRUD 与配置文本生成。模板内容使用
``{{ var }}`` 形式的变量占位符，生成时按变量字典填充。

支持从数据库加载用户自定义模板，或使用 :mod:`app.core.device_templates`
中的默认模板。
"""

from __future__ import annotations

import difflib
import re
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.device_templates import (
    COMMON_VARIABLES,
    get_default_template,
    get_policy_template,
    list_default_templates,
    list_policies,
    list_policy_templates_for_vendor,
    list_vendors,
)
from app.core.logging import get_logger
from app.models.rtr import DeviceConfigTemplate
from app.schemas.rtr import (
    DeviceConfigBatchItem,
    DeviceConfigBatchResult,
    DeviceConfigBatchResultItem,
    DeviceConfigDiffEntry,
    DeviceConfigDiffResult,
    DeviceConfigPolicyRequest,
    DeviceConfigPolicyResult,
    DeviceConfigRequest,
    DeviceConfigResult,
    DeviceConfigTemplateCreate,
    DeviceConfigTemplateUpdate,
    DeviceConfigValidationIssue,
    DeviceConfigValidationResult,
    PolicyInfo,
    VendorInfo,
)

logger = get_logger("app.device_config_service")


# ──────────────────────────────────────────────
# 模板 CRUD
# ──────────────────────────────────────────────


async def create_template(
    db: AsyncSession, template_create: DeviceConfigTemplateCreate
) -> DeviceConfigTemplate:
    """创建设备配置模板。

    Args:
        db: 异步数据库会话
        template_create: 模板创建数据

    Returns:
        创建后的 DeviceConfigTemplate 对象

    Raises:
        ValueError: 同名模板已存在
    """
    existing = await get_template_by_name(db, template_create.name)
    if existing is not None:
        raise ValueError(f"模板名称 '{template_create.name}' 已存在")

    template = DeviceConfigTemplate(
        name=template_create.name,
        vendor=template_create.vendor,
        template_type=template_create.template_type,
        content=template_create.content,
        variables=template_create.variables,
        description=template_create.description,
        enabled=template_create.enabled,
    )
    db.add(template)
    await db.flush()
    await db.commit()
    await db.refresh(template)

    logger.info(
        "设备配置模板已创建",
        template_id=template.id,
        name=template.name,
        vendor=template.vendor,
        type=template.template_type,
    )
    return template


async def get_template(db: AsyncSession, template_id: int) -> DeviceConfigTemplate | None:
    """根据 ID 获取模板。"""
    stmt = select(DeviceConfigTemplate).where(DeviceConfigTemplate.id == template_id)
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def get_template_by_name(db: AsyncSession, name: str) -> DeviceConfigTemplate | None:
    """根据名称获取模板。"""
    stmt = select(DeviceConfigTemplate).where(DeviceConfigTemplate.name == name)
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def get_templates(
    db: AsyncSession,
    vendor: str | None = None,
    template_type: str | None = None,
    enabled: bool | None = None,
    skip: int = 0,
    limit: int = 50,
) -> list[DeviceConfigTemplate]:
    """获取模板列表。

    Args:
        db: 异步数据库会话
        vendor: 按厂商过滤
        template_type: 按模板类型过滤
        enabled: 按启用状态过滤
        skip: 跳过记录数
        limit: 返回记录数上限

    Returns:
        模板列表
    """
    stmt = select(DeviceConfigTemplate)
    if vendor is not None:
        stmt = stmt.where(DeviceConfigTemplate.vendor == vendor)
    if template_type is not None:
        stmt = stmt.where(DeviceConfigTemplate.template_type == template_type)
    if enabled is not None:
        stmt = stmt.where(DeviceConfigTemplate.enabled == enabled)
    stmt = stmt.order_by(DeviceConfigTemplate.id).offset(skip).limit(limit)
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def count_templates(
    db: AsyncSession,
    vendor: str | None = None,
    template_type: str | None = None,
    enabled: bool | None = None,
) -> int:
    """统计模板数量。"""
    stmt = select(func.count(DeviceConfigTemplate.id))
    if vendor is not None:
        stmt = stmt.where(DeviceConfigTemplate.vendor == vendor)
    if template_type is not None:
        stmt = stmt.where(DeviceConfigTemplate.template_type == template_type)
    if enabled is not None:
        stmt = stmt.where(DeviceConfigTemplate.enabled == enabled)
    result = await db.execute(stmt)
    return result.scalar_one()


async def update_template(
    db: AsyncSession,
    template_id: int,
    template_update: DeviceConfigTemplateUpdate,
) -> DeviceConfigTemplate | None:
    """更新模板。

    Args:
        db: 异步数据库会话
        template_id: 模板 ID
        template_update: 更新数据

    Returns:
        更新后的模板对象，不存在时返回 None
    """
    template = await get_template(db, template_id)
    if template is None:
        return None

    update_data = template_update.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(template, field, value)

    await db.flush()
    await db.commit()
    await db.refresh(template)

    logger.info("设备配置模板已更新", template_id=template_id)
    return template


async def delete_template(db: AsyncSession, template_id: int) -> bool:
    """删除模板。

    Args:
        db: 异步数据库会话
        template_id: 模板 ID

    Returns:
        是否删除成功
    """
    template = await get_template(db, template_id)
    if template is None:
        return False
    await db.delete(template)
    await db.commit()
    logger.info("设备配置模板已删除", template_id=template_id)
    return True


# ──────────────────────────────────────────────
# 配置生成
# ──────────────────────────────────────────────


async def generate_config(
    db: AsyncSession,
    vendor: str,
    template_type: str,
    variables: dict[str, Any],
) -> DeviceConfigResult:
    """生成设备配置文本。

    优先使用数据库中启用的自定义模板，否则使用默认模板。
    使用简单变量替换：``{{ var }}`` 与 ``{{ var | default value }}``。

    Args:
        db: 异步数据库会话
        vendor: 厂商代码
        template_type: 模板类型
        variables: 变量字典

    Returns:
        设备配置生成结果
    """
    warnings: list[str] = []

    # 自动补充生成时间
    if "generated_at" not in variables:
        variables = {
            **variables,
            "generated_at": datetime.now(UTC).isoformat(),
        }

    # 查找数据库模板
    stmt = (
        select(DeviceConfigTemplate)
        .where(
            DeviceConfigTemplate.vendor == vendor,
            DeviceConfigTemplate.template_type == template_type,
            DeviceConfigTemplate.enabled == True,  # noqa: E712
        )
        .order_by(DeviceConfigTemplate.id.desc())
        .limit(1)
    )
    result = await db.execute(stmt)
    template = result.scalar_one_or_none()

    if template is not None:
        content = template.content
        template_id = template.id
        # 合并模板定义的变量默认值
        if template.variables:
            for var_name, var_def in template.variables.items():
                if var_name not in variables and isinstance(var_def, dict) and "default" in var_def:
                    variables[var_name] = var_def["default"]
    else:
        # 使用默认模板
        content = get_default_template(vendor, template_type)
        template_id = None
        if content is None:
            raise ValueError(f"未找到厂商 {vendor} 类型 {template_type} 的模板")
        # 合并通用变量默认值
        for var_name, var_def in COMMON_VARIABLES.items():
            if var_name not in variables and isinstance(var_def, dict) and "default" in var_def:
                variables[var_name] = var_def["default"]

    # 检查必填变量
    required_vars = _get_required_variables(vendor, template_type, template)
    for var_name in required_vars:
        if var_name not in variables or variables[var_name] is None:
            warnings.append(f"必填变量 '{var_name}' 未提供")

    # 渲染模板
    generated = _render_template(content, variables)

    # 检查未填充的变量占位符
    unfilled = _find_unfilled_variables(generated)
    for var_name in unfilled:
        warnings.append(f"变量 '{var_name}' 未填充")

    return DeviceConfigResult(
        generated_config=generated,
        warnings=warnings,
        vendor=vendor,
        template_type=template_type,
        template_id=template_id,
    )


async def generate_config_from_request(
    db: AsyncSession, request: DeviceConfigRequest
) -> DeviceConfigResult:
    """从请求对象生成设备配置。

    Args:
        db: 异步数据库会话
        request: 设备配置生成请求

    Returns:
        设备配置生成结果
    """
    return await generate_config(
        db,
        vendor=request.vendor,
        template_type=request.template_type,
        variables=request.variables,
    )


# ──────────────────────────────────────────────
# 按策略生成配置
# ──────────────────────────────────────────────


async def generate_config_by_policy(
    db: AsyncSession,
    vendor: str,
    policy: str,
    variables: dict[str, Any],
) -> DeviceConfigPolicyResult:
    """按 ROV 策略生成设备配置。

    使用 :data:`app.core.device_templates.POLICY_TEMPLATES` 中的策略专用
    模板，根据指定的策略（drop_invalid/de_preference_invalid/monitor_only）
    生成对应的 ROV 配置。

    Args:
        db: 异步数据库会话（保留以备未来扩展自定义策略模板）
        vendor: 厂商代码
        policy: ROV 策略
        variables: 变量字典

    Returns:
        按策略生成的配置结果

    Raises:
        ValueError: 厂商或策略不支持
    """
    warnings: list[str] = []

    # 自动补充生成时间与策略
    if "generated_at" not in variables:
        variables = {
            **variables,
            "generated_at": datetime.now(UTC).isoformat(),
        }
    if "policy" not in variables:
        variables = {**variables, "policy": policy}

    # 合并通用变量默认值
    for var_name, var_def in COMMON_VARIABLES.items():
        if var_name not in variables and isinstance(var_def, dict) and "default" in var_def:
            variables[var_name] = var_def["default"]

    # 获取策略模板
    content = get_policy_template(vendor, policy)
    if content is None:
        raise ValueError(f"未找到厂商 {vendor} 策略 {policy} 的模板")

    # 检查必填变量
    for var_name, var_def in COMMON_VARIABLES.items():
        if (
            isinstance(var_def, dict)
            and var_def.get("required")
            and (var_name not in variables or variables[var_name] is None)
        ):
            warnings.append(f"必填变量 '{var_name}' 未提供")

    # 渲染模板
    generated = _render_template(content, variables)

    # 检查未填充的变量占位符
    unfilled = _find_unfilled_variables(generated)
    for var_name in unfilled:
        warnings.append(f"变量 '{var_name}' 未填充")

    return DeviceConfigPolicyResult(
        generated_config=generated,
        warnings=warnings,
        vendor=vendor,
        policy=policy,
    )


async def generate_config_by_policy_request(
    db: AsyncSession, request: DeviceConfigPolicyRequest
) -> DeviceConfigPolicyResult:
    """从策略生成请求对象生成设备配置。

    Args:
        db: 异步数据库会话
        request: 策略生成请求

    Returns:
        按策略生成的配置结果
    """
    return await generate_config_by_policy(
        db,
        vendor=request.vendor,
        policy=request.policy,
        variables=request.variables,
    )


# ──────────────────────────────────────────────
# 批量生成配置
# ──────────────────────────────────────────────


async def generate_batch_configs(
    db: AsyncSession, items: list[DeviceConfigBatchItem]
) -> DeviceConfigBatchResult:
    """批量生成多设备配置。

    逐个调用 :func:`generate_config` 生成配置，单个设备失败不影响其他设备。

    Args:
        db: 异步数据库会话
        items: 设备配置生成请求列表

    Returns:
        批量生成结果，包含每个设备的生成状态
    """
    results: list[DeviceConfigBatchResultItem] = []
    success_count = 0
    failure_count = 0

    for item in items:
        try:
            config_result = await generate_config(
                db,
                vendor=item.vendor,
                template_type=item.template_type,
                variables=item.variables,
            )
            results.append(
                DeviceConfigBatchResultItem(
                    device_name=item.device_name,
                    success=True,
                    generated_config=config_result.generated_config,
                    warnings=config_result.warnings,
                    error=None,
                    vendor=item.vendor,
                    template_type=item.template_type,
                )
            )
            success_count += 1
        except ValueError as e:
            results.append(
                DeviceConfigBatchResultItem(
                    device_name=item.device_name,
                    success=False,
                    generated_config=None,
                    warnings=[],
                    error=str(e),
                    vendor=item.vendor,
                    template_type=item.template_type,
                )
            )
            failure_count += 1
            logger.warning(
                "批量生成配置失败",
                device_name=item.device_name,
                vendor=item.vendor,
                error=str(e),
            )

    return DeviceConfigBatchResult(
        results=results,
        total=len(items),
        success_count=success_count,
        failure_count=failure_count,
    )


# ──────────────────────────────────────────────
# 配置差异对比
# ──────────────────────────────────────────────


def diff_configs(
    config_a: str,
    config_b: str,
    context_lines: int = 3,
) -> DeviceConfigDiffResult:
    """对比两份配置文本的差异。

    使用 :mod:`difflib` 生成统一 diff 与结构化差异条目。

    Args:
        config_a: 配置文本 A
        config_b: 配置文本 B
        context_lines: 差异上下文行数

    Returns:
        配置差异对比结果
    """
    lines_a = config_a.splitlines(keepends=False)
    lines_b = config_b.splitlines(keepends=False)

    # 生成统一 diff 文本
    diff_lines = list(
        difflib.unified_diff(
            lines_a,
            lines_b,
            fromfile="config_a",
            tofile="config_b",
            n=context_lines,
            lineterm="",
        )
    )
    diff_text = "\n".join(diff_lines)

    # 生成结构化差异条目
    entries: list[DeviceConfigDiffEntry] = []
    added_count = 0
    removed_count = 0
    modified_count = 0

    # 使用 SequenceMatcher 进行行级对比
    matcher = difflib.SequenceMatcher(None, lines_a, lines_b, autojunk=False)
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            continue
        elif tag == "replace":
            # 修改：A 中 [i1, i2) 被替换为 B 中 [j1, j2)
            max_len = max(i2 - i1, j2 - j1)
            for k in range(max_len):
                line_a = lines_a[i1 + k] if i1 + k < i2 else None
                line_b = lines_b[j1 + k] if j1 + k < j2 else None
                entries.append(
                    DeviceConfigDiffEntry(
                        line_number_a=(i1 + k + 1 if line_a is not None else None),
                        line_number_b=(j1 + k + 1 if line_b is not None else None),
                        change_type="modified",
                        content_a=line_a,
                        content_b=line_b,
                    )
                )
            modified_count += max_len
        elif tag == "delete":
            # 删除：A 中 [i1, i2) 被删除
            for k in range(i1, i2):
                entries.append(
                    DeviceConfigDiffEntry(
                        line_number_a=k + 1,
                        line_number_b=None,
                        change_type="removed",
                        content_a=lines_a[k],
                        content_b=None,
                    )
                )
            removed_count += i2 - i1
        elif tag == "insert":
            # 新增：B 中 [j1, j2) 被新增
            for k in range(j1, j2):
                entries.append(
                    DeviceConfigDiffEntry(
                        line_number_a=None,
                        line_number_b=k + 1,
                        change_type="added",
                        content_a=None,
                        content_b=lines_b[k],
                    )
                )
            added_count += j2 - j1

    identical = len(entries) == 0

    return DeviceConfigDiffResult(
        identical=identical,
        added_count=added_count,
        removed_count=removed_count,
        modified_count=modified_count,
        diff_text=diff_text,
        entries=entries,
    )


# ──────────────────────────────────────────────
# 配置验证（语法检查占位）
# ──────────────────────────────────────────────


def validate_config(
    vendor: str,
    config: str,
) -> DeviceConfigValidationResult:
    """验证设备配置语法（占位实现）。

    当前实现为基础语法检查占位，未来可对接各厂商的配置校验工具
    （如 Cisco 的 `show config` 模拟、FRR 的 `vtysh -c` 校验等）。

    检查项：
    - 配置是否为空
    - 是否包含未填充的变量占位符
    - 基本括号/大括号配对检查

    Args:
        vendor: 厂商代码
        config: 待验证的配置文本

    Returns:
        配置验证结果
    """
    issues: list[DeviceConfigValidationIssue] = []

    # 检查空配置
    if not config or not config.strip():
        issues.append(
            DeviceConfigValidationIssue(
                line_number=None,
                severity="error",
                message="配置内容为空",
                line_content=None,
            )
        )
        return DeviceConfigValidationResult(
            valid=False,
            vendor=vendor,
            issues=issues,
            checked_at=datetime.now(UTC),
        )

    lines = config.splitlines()

    # 检查未填充的变量占位符
    for idx, line in enumerate(lines, start=1):
        placeholders = re.findall(r"\{\{[^}]+\}\}", line)
        for ph in placeholders:
            issues.append(
                DeviceConfigValidationIssue(
                    line_number=idx,
                    severity="warning",
                    message=f"存在未填充的变量占位符: {ph}",
                    line_content=line,
                )
            )

    # 检查括号/大括号配对
    brace_pairs: dict[str, str] = {"{": "}", "(": ")", "[": "]"}
    stack: list[tuple[str, int]] = []
    for idx, line in enumerate(lines, start=1):
        for char in line:
            if char in brace_pairs:
                stack.append((char, idx))
            elif char in brace_pairs.values():
                if not stack:
                    issues.append(
                        DeviceConfigValidationIssue(
                            line_number=idx,
                            severity="error",
                            message=f"多余的闭合括号 '{char}'",
                            line_content=line,
                        )
                    )
                else:
                    opening, open_line = stack.pop()
                    if brace_pairs[opening] != char:
                        issues.append(
                            DeviceConfigValidationIssue(
                                line_number=idx,
                                severity="error",
                                message=(
                                    f"括号不匹配：期望 '{brace_pairs[opening]}'"
                                    f"，实际 '{char}'（第 {open_line} 行开启）"
                                ),
                                line_content=line,
                            )
                        )

    # 检查未闭合的括号
    for opening, open_line in stack:
        issues.append(
            DeviceConfigValidationIssue(
                line_number=open_line,
                severity="error",
                message=f"未闭合的括号 '{opening}'",
                line_content=lines[open_line - 1] if open_line <= len(lines) else None,
            )
        )

    # 判断是否通过验证（存在 error 级别问题则不通过）
    has_error = any(issue.severity == "error" for issue in issues)

    return DeviceConfigValidationResult(
        valid=not has_error,
        vendor=vendor,
        issues=issues,
        checked_at=datetime.now(UTC),
    )


# ──────────────────────────────────────────────
# 厂商与默认模板查询
# ──────────────────────────────────────────────


def get_vendors() -> list[VendorInfo]:
    """获取支持的厂商列表。

    Returns:
        厂商信息列表
    """
    return [
        VendorInfo(
            vendor=item["vendor"],
            name=item["name"],
            template_types=item["template_types"],
        )
        for item in list_vendors()
    ]


def get_default_templates_for_vendor(
    vendor: str,
) -> list[dict[str, Any]]:
    """获取指定厂商的默认模板列表。

    Args:
        vendor: 厂商代码

    Returns:
        默认模板信息字典列表
    """
    return list_default_templates(vendor)


def get_policies() -> list[PolicyInfo]:
    """获取支持的 ROV 策略列表。

    Returns:
        策略信息列表
    """
    return [
        PolicyInfo(
            policy=item["policy"],
            name=item["name"],
            description=item["description"],
        )
        for item in list_policies()
    ]


def get_policy_templates_for_vendor(
    vendor: str,
) -> list[dict[str, Any]]:
    """获取指定厂商的策略模板列表。

    Args:
        vendor: 厂商代码

    Returns:
        策略模板信息字典列表，包含 policy、name、content
    """
    return list_policy_templates_for_vendor(vendor)


# ──────────────────────────────────────────────
# 内部辅助函数
# ──────────────────────────────────────────────


def _get_required_variables(
    vendor: str,
    template_type: str,
    template: DeviceConfigTemplate | None,
) -> list[str]:
    """获取模板的必填变量列表。"""
    required: list[str] = []
    if template is not None and template.variables:
        for var_name, var_def in template.variables.items():
            if isinstance(var_def, dict) and var_def.get("required"):
                required.append(var_name)
    else:
        # 使用通用变量定义
        for var_name, var_def in COMMON_VARIABLES.items():
            if isinstance(var_def, dict) and var_def.get("required"):
                required.append(var_name)
    return required


def _render_template(content: str, variables: dict[str, Any]) -> str:
    """渲染模板，替换变量占位符。

    支持两种语法：
    - ``{{ var }}``：直接替换
    - ``{{ var | default value }}``：变量未提供时使用默认值

    Args:
        content: 模板内容
        variables: 变量字典

    Returns:
        渲染后的配置文本
    """
    result = content

    # 先处理带 default 的占位符
    default_pattern = re.compile(r"\{\{\s*(\w+)\s*\|\s*default\s+([^}\s]+)\s*\}\}")

    def _default_replacer(match: re.Match[str]) -> str:
        var_name = match.group(1)
        default_value = match.group(2)
        # 去除可能的引号
        if default_value.startswith('"') and default_value.endswith('"'):
            default_value = default_value[1:-1]
        value = variables.get(var_name, default_value)
        return str(value)

    result = default_pattern.sub(_default_replacer, result)

    # 再处理普通占位符
    simple_pattern = re.compile(r"\{\{\s*(\w+)\s*\}\}")

    def _simple_replacer(match: re.Match[str]) -> str:
        var_name = match.group(1)
        value = variables.get(var_name, "")
        return str(value)

    result = simple_pattern.sub(_simple_replacer, result)

    return result


def _find_unfilled_variables(content: str) -> list[str]:
    """查找内容中未填充的变量占位符。

    Args:
        content: 已渲染的配置文本

    Returns:
        未填充的变量名列表
    """
    pattern = re.compile(r"\{\{\s*(\w+)[^}]*\}\}")
    matches = pattern.findall(content)
    # 去重并保持顺序
    seen: set[str] = set()
    result: list[str] = []
    for m in matches:
        if m not in seen:
            seen.add(m)
            result.append(m)
    return result


__all__ = [
    "count_templates",
    "create_template",
    "delete_template",
    "diff_configs",
    "generate_batch_configs",
    "generate_config",
    "generate_config_by_policy",
    "generate_config_by_policy_request",
    "generate_config_from_request",
    "get_default_templates_for_vendor",
    "get_policies",
    "get_policy_templates_for_vendor",
    "get_template",
    "get_template_by_name",
    "get_templates",
    "get_vendors",
    "update_template",
    "validate_config",
]
