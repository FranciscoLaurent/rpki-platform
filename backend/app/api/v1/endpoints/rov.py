"""ROV 策略模拟与变更影响评估 API 端点。

提供以下接口：
- POST /rov/simulate：模拟 ROV 策略（drop_invalid/de-preference_invalid/monitor_only）
- POST /rov/simulate-roa-change：模拟 ROA 变更（创建/修改/撤销）影响
- POST /rov/simulate-roa-creation：模拟 ROA 创建影响（细粒度入口）
- POST /rov/simulate-roa-modification：模拟 ROA 修改影响（细粒度入口）
- POST /rov/simulate-roa-revocation：模拟 ROA 撤销影响（细粒度入口）
- GET /rov/deployment-guide：获取通用的分阶段部署指南
- POST /rov/export-results：导出模拟结果为 JSON 或 CSV
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_permissions
from app.core.database import get_db
from app.models.user import User
from app.schemas.rov import (
    ROAChangeSimulationRequest,
    ROAChangeSimulationResult,
    ROACreationSimulationRequest,
    ROAModificationSimulationRequest,
    ROARevocationSimulationRequest,
    ROVExportRequest,
    ROVExportResponse,
    ROVSimulationRequest,
    ROVSimulationResult,
)
from app.services.roa_change_impact_service import (
    simulate_roa_creation,
    simulate_roa_modification,
    simulate_roa_revocation,
)
from app.services.rov_simulation_service import (
    export_simulation_results,
    simulate_roa_change,
    simulate_rov_policy,
)

router = APIRouter()

# ROV 权限码（使用字符串字面量避免修改共享的 rbac.py）
ROV_READ = "rov:read"
# ROA 模拟权限码（使用字符串字面量，与 roa:simulate 等价）
ROA_SIMULATE = "roa:simulate"


# ──────────────────────────────────────────────
# ROV 策略模拟
# ──────────────────────────────────────────────


@router.post("/simulate", response_model=ROVSimulationResult)
async def simulate_rov(
    request: ROVSimulationRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permissions(ROV_READ)),
) -> ROVSimulationResult:
    """模拟 ROV 策略。

    需要 ``rov:read`` 权限。基于当前/历史路由表与 VRP 数据，
    模拟指定 ROV 策略（drop_invalid/de-preference_invalid/monitor_only）
    对网络的影响，返回受影响前缀、业务、客户清单与部署建议。

    支持按路由器、地域、机房、VRF、地址族、业务域、前缀重要度过滤范围。
    可通过 snapshot_time 模拟历史路由表。
    """
    return await simulate_rov_policy(db, request)


# ──────────────────────────────────────────────
# ROA 变更模拟
# ──────────────────────────────────────────────


@router.post(
    "/simulate-roa-change", response_model=ROAChangeSimulationResult
)
async def simulate_roa_change_endpoint(
    request: ROAChangeSimulationRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permissions(ROV_READ)),
) -> ROAChangeSimulationResult:
    """模拟 ROA 变更影响。

    需要 ``rov:read`` 权限。模拟 ROA 创建/修改/撤销对 BGP 公告验证状态的影响，
    返回验证状态变化列表、新增攻击面与风险评估。

    - create：新建 ROA，需提供 new_prefix 和 new_origin_as
    - modify：修改现有 ROA，需提供 roa_id
    - revoke：撤销现有 ROA，需提供 roa_id
    """
    try:
        return await simulate_roa_change(db, request)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        ) from e


# ──────────────────────────────────────────────
# 细粒度 ROA 变更模拟（按变更类型拆分）
# ──────────────────────────────────────────────


@router.post(
    "/simulate-roa-creation", response_model=ROAChangeSimulationResult
)
async def simulate_roa_creation_endpoint(
    request: ROACreationSimulationRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permissions(ROA_SIMULATE)),
) -> ROAChangeSimulationResult:
    """模拟 ROA 创建影响。

    需要 ``roa:simulate`` 权限。模拟新建 ROA 后对所有受影响 BGP 公告
    验证状态的变化，分析新增攻击面（子前缀劫持、未授权 origin、过宽授权），
    评估风险等级。

    输入新前缀、起源 AS 与可选的 maxLength（为空时采用 minimal ROA 原则），
    返回验证状态变化列表、受影响公告清单、攻击面与风险评估。
    """
    try:
        return await simulate_roa_creation(
            db,
            prefix=request.prefix,
            origin_as=request.origin_as,
            max_length=request.max_length,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        ) from e


@router.post(
    "/simulate-roa-modification", response_model=ROAChangeSimulationResult
)
async def simulate_roa_modification_endpoint(
    request: ROAModificationSimulationRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permissions(ROA_SIMULATE)),
) -> ROAChangeSimulationResult:
    """模拟 ROA 修改影响（含调整 maxLength）。

    需要 ``roa:simulate`` 权限。模拟修改现有 ROA 的 prefix、origin AS
    或 maxLength 后对 BGP 公告验证状态的影响，分析新增攻击面与风险评估。

    任意字段为 None 表示保持原值不变。需提供 roa_id 指定待修改的 ROA。
    """
    try:
        return await simulate_roa_modification(
            db,
            roa_id=request.roa_id,
            new_prefix=request.new_prefix,
            new_origin_as=request.new_origin_as,
            new_max_length=request.new_max_length,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        ) from e


@router.post(
    "/simulate-roa-revocation", response_model=ROAChangeSimulationResult
)
async def simulate_roa_revocation_endpoint(
    request: ROARevocationSimulationRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permissions(ROA_SIMULATE)),
) -> ROAChangeSimulationResult:
    """模拟 ROA 撤销影响。

    需要 ``roa:simulate`` 权限。模拟撤销现有 ROA 后所有原本由该 ROA
    覆盖的公告将失去 RPKI 保护，验证状态可能从 Valid/Invalid 变为 NotFound。

    需提供 roa_id 指定待撤销的 ROA。
    """
    try:
        return await simulate_roa_revocation(db, roa_id=request.roa_id)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        ) from e


# ──────────────────────────────────────────────
# 部署指南
# ──────────────────────────────────────────────


@router.get("/deployment-guide")
async def get_deployment_guide(
    current_user: User = Depends(require_permissions(ROV_READ)),
) -> dict[str, Any]:
    """获取 ROV 分阶段部署指南。

    需要 ``rov:read`` 权限。返回通用的分阶段部署建议文档，
    包含监控、降权、拒收三个阶段的目标、前置条件与持续时间，
    以及 NotFound 前缀治理、良性 Invalid 治理与风险控制建议。
    """
    return {
        "title": "ROV 分阶段部署指南",
        "description": "Route Origin Validation 分阶段部署最佳实践",
        "phases": [
            {
                "phase": "monitor",
                "name": "第一阶段：监控模式",
                "description": (
                    "启用 ROV 监控（monitor_only），记录所有 Invalid 路由"
                    "但不影响转发。建立 Invalid 路由的基线数据，观察 2-4 周。"
                ),
                "objectives": [
                    "收集 Invalid 路由的分布、来源与趋势",
                    "识别 ROA 配置错误与路由异常",
                    "建立告警机制",
                ],
                "prerequisites": [
                    "RPKI 验证器正常运行且 VRP 数据已同步",
                    "日志收集系统就绪",
                    "通知相关业务团队",
                ],
                "duration": "2-4 周",
            },
            {
                "phase": "de-preference",
                "name": "第二阶段：降权模式",
                "description": (
                    "对 Invalid 路由降权处理（增大 MED、降低 LOCAL_PREF），"
                    "使其在有多条路径时不会被优选，但仍保持可达性。"
                ),
                "objectives": [
                    "验证 Invalid 路由降权后业务不受影响",
                    "确认所有 Invalid 路由有备用 Valid 路径",
                    "逐步收窄 Invalid 路由影响范围",
                ],
                "prerequisites": [
                    "第一阶段监控无异常",
                    "确认备用路径可用",
                    "核心前缀暂不实施",
                ],
                "duration": "1-2 周",
            },
            {
                "phase": "drop",
                "name": "第三阶段：拒收模式",
                "description": (
                    "完全拒收 Invalid 路由（drop_invalid），实现完整的 ROV 防护。"
                    "先在边缘路由器实施，逐步推广至核心。"
                ),
                "objectives": [
                    "完全阻断 Invalid 路由传播",
                    "实现 RFC 6811 完整 ROV 防护",
                    "建立持续监控与响应机制",
                ],
                "prerequisites": [
                    "第二阶段 de-preference 运行稳定",
                    "所有 Invalid 路由根因已修复",
                    "无核心业务依赖 Invalid 路由",
                    "制定回滚预案",
                ],
                "duration": "持续推进",
            },
        ],
        "governance": {
            "not_found": (
                "对 NotFound 前缀：为合法前缀创建 ROA"
                "（遵循 minimal ROA 原则），对非法前缀加强监控。"
            ),
            "benign_invalid": (
                "对疑似良性 Invalid 前缀：排查 ROA 配置是否正确，"
                "联系相关 AS 管理员确认，必要时临时修改 ROA。"
            ),
            "critical_prefix": (
                "对核心前缀 Invalid：优先排查根因，"
                "在根因解决前不实施 drop 策略。"
            ),
        },
        "risk_control": {
            "approval_required": (
                "核心前缀受影响或大规模合法路由受影响时需审批"
            ),
            "rollback_plan": "可快速切换回 de-preference 或 monitor 模式",
            "monitoring": "持续监控 Invalid 路由数量、业务影响与告警",
        },
    }


# ──────────────────────────────────────────────
# 导出模拟结果
# ──────────────────────────────────────────────


@router.post("/export-results", response_model=ROVExportResponse)
async def export_results(
    request: ROVExportRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permissions(ROV_READ)),
) -> ROVExportResponse:
    """导出模拟结果。

    需要 ``rov:read`` 权限。运行 ROV 策略模拟并将结果导出为 JSON 或 CSV 格式。

    输入模拟请求参数与导出格式，返回导出内容与建议文件名。
    """
    return await export_simulation_results(db, request)
