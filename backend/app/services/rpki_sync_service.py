"""RPKI 仓库同步服务。

负责 TAL 初始化、RRDP/rsync 仓库同步、RPKI 对象解析与签名链验证。
实际的 RRDP/rsync 同步与密码学验证使用占位实现（标注 TODO），
但接口与流程框架完整，便于后续接入真实实现。
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.core.rpki_validator import (
    check_resource_coverage,
    check_revocation,
    check_validity_period,
    parse_certificate,
    parse_crl,
    parse_manifest,
    parse_roa,
)
from app.models.rpki import (
    RPKIObject,
    RPKIRepository,
    TAL,
)
from app.schemas.rpki import TALCreate

logger = get_logger("app.rpki_sync_service")


async def init_tal(db: AsyncSession, tal_create: TALCreate) -> TAL:
    """初始化 TAL（Trust Anchor Locator）。

    创建 TAL 记录，并根据 RRDP URI 自动发现关联的 RPKI 仓库。

    Args:
        db: 异步数据库会话
        tal_create: TAL 创建参数

    Returns:
        创建的 TAL 对象
    """
    tal = TAL(
        name=tal_create.name,
        uri=tal_create.uri,
        rsync_uri=tal_create.rsync_uri,
        raw_tal=tal_create.raw_tal,
        status="active",
        sync_status="pending",
    )
    db.add(tal)
    await db.flush()

    # 根据 TAL 自动创建仓库记录
    # RRDP 仓库优先，rsync 作为回退
    repository = RPKIRepository(
        tal_id=tal.id,
        uri=tal_create.uri,
        protocol="rrdp",
        status="active",
        sync_status="pending",
        object_count=0,
    )
    db.add(repository)
    await db.flush()
    await db.commit()
    await db.refresh(tal)

    logger.info(
        "TAL 初始化完成",
        tal_id=tal.id,
        name=tal.name,
        repository_id=repository.id,
    )
    return tal


async def sync_repository(db: AsyncSession, repository_id: int) -> RPKIRepository:
    """同步单个 RPKI 仓库。

    根据仓库协议（RRDP 或 rsync）执行同步流程：
    1. 标记仓库为同步中
    2. 下载仓库内容（snapshot/delta 或 rsync 文件）
    3. 解析 RPKI 对象
    4. 验证签名链
    5. 更新仓库状态

    Args:
        db: 异步数据库会话
        repository_id: 仓库 ID

    Returns:
        更新后的仓库对象

    Raises:
        ValueError: 仓库不存在
    """
    stmt = select(RPKIRepository).where(RPKIRepository.id == repository_id)
    result = await db.execute(stmt)
    repository = result.scalar_one_or_none()
    if repository is None:
        raise ValueError(f"仓库 ID {repository_id} 不存在")

    # 标记为同步中
    repository.sync_status = "running"
    repository.last_error = None
    await db.flush()

    try:
        if repository.protocol == "rrdp":
            await _sync_rrdp_repository(db, repository)
        elif repository.protocol == "rsync":
            await _sync_rsync_repository(db, repository)
        else:
            raise ValueError(f"不支持的协议: {repository.protocol}")

        repository.sync_status = "success"
        repository.last_synced_at = datetime.now(timezone.utc)
        repository.last_error = None
        logger.info(
            "仓库同步成功",
            repository_id=repository.id,
            protocol=repository.protocol,
            object_count=repository.object_count,
        )
    except Exception as e:
        repository.sync_status = "failed"
        repository.last_error = str(e)
        logger.error(
            "仓库同步失败",
            repository_id=repository.id,
            error=str(e),
            exc_info=True,
        )

    await db.flush()
    await db.commit()
    await db.refresh(repository)
    return repository


async def _sync_rrdp_repository(
    db: AsyncSession, repository: RPKIRepository
) -> None:
    """通过 RRDP 协议同步仓库。

    RRDP（RPKI Repository Delta Protocol，RFC 8182）流程：
    1. 从仓库 URI 获取 notification.xml
    2. 根据 session 与版本号决定下载 snapshot 或 delta
    3. 解析 snapshot/delta XML，获取对象列表
    4. 下载每个对象并解析

    Note:
        TODO: 当前为占位实现，使用 httpx 模拟下载流程。
        实际实现需解析 RRDP XML 并处理 session/version。
    """
    # TODO: 实现完整的 RRDP 同步
    # 1. 下载 notification.xml
    # 2. 解析 snapshot URI 与 delta 列表
    # 3. 下载 snapshot.xml 或 delta.xml
    # 4. 解析 XML 获取对象 URI 与内容
    # 5. 调用 parse_rpki_object 解析每个对象

    logger.info(
        "开始 RRDP 同步（占位）",
        repository_id=repository.id,
        uri=repository.uri,
    )

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            # 占位：尝试访问 notification.xml
            # 实际实现需解析返回的 XML
            response = await client.get(repository.uri)
            if response.status_code != 200:
                logger.warning(
                    "RRDP notification 请求失败",
                    repository_id=repository.id,
                    status_code=response.status_code,
                )
    except Exception as e:
        logger.warning(
            "RRDP 同步网络请求异常（占位实现）",
            repository_id=repository.id,
            error=str(e),
        )

    # 占位：不实际下载对象，仅更新计数
    # 实际实现应在此处解析对象并写入 rpki_objects 表
    repository.object_count = 0


async def _sync_rsync_repository(
    db: AsyncSession, repository: RPKIRepository
) -> None:
    """通过 rsync 协议同步仓库。

    Note:
        TODO: 当前为占位实现，实际需调用 rsync 命令或 rsync 客户端库。
    """
    # TODO: 实现 rsync 同步
    # 1. 调用 rsync 命令下载仓库内容
    # 2. 遍历下载的文件
    # 3. 调用 parse_rpki_object 解析每个对象
    logger.info(
        "开始 rsync 同步（占位）",
        repository_id=repository.id,
        uri=repository.uri,
    )
    repository.object_count = 0


async def sync_all_repositories(db: AsyncSession) -> dict[str, Any]:
    """同步所有活跃仓库。

    Args:
        db: 异步数据库会话

    Returns:
        同步结果摘要，包含成功/失败仓库数与错误信息
    """
    stmt = select(RPKIRepository).where(RPKIRepository.status == "active")
    result = await db.execute(stmt)
    repositories = list(result.scalars().all())

    success_count = 0
    failed_count = 0
    errors: list[dict[str, Any]] = []

    for repo in repositories:
        try:
            await sync_repository(db, repo.id)
            success_count += 1
        except Exception as e:
            failed_count += 1
            errors.append(
                {
                    "repository_id": repo.id,
                    "uri": repo.uri,
                    "error": str(e),
                }
            )

    logger.info(
        "全部仓库同步完成",
        total=len(repositories),
        success=success_count,
        failed=failed_count,
    )

    return {
        "total": len(repositories),
        "success": success_count,
        "failed": failed_count,
        "errors": errors,
    }


async def parse_rpki_object(
    db: AsyncSession,
    object_data: bytes,
    object_type: str,
    repository_id: int | None = None,
    uri: str | None = None,
) -> RPKIObject:
    """解析 RPKI 对象并写入数据库。

    根据对象类型调用对应的解析器，提取元数据并存储原始数据与解析结果。

    Args:
        db: 异步数据库会话
        object_data: 对象的 DER 编码字节数据
        object_type: 对象类型（certificate/roa/manifest/crl/ghostbusters）
        repository_id: 所属仓库 ID
        uri: 对象 URI

    Returns:
        创建的 RPKIObject 对象
    """
    parsed_data: dict[str, Any] = {}
    serial_number: str | None = None
    signing_time: datetime | None = None
    not_before: datetime | None = None
    not_after: datetime | None = None
    status = "valid"

    if object_type == "certificate":
        cert_info = parse_certificate(object_data)
        if cert_info is not None:
            serial_number = cert_info.serial_number
            not_before = cert_info.not_before
            not_after = cert_info.not_after
            parsed_data = {
                "subject": cert_info.subject,
                "issuer": cert_info.issuer,
                "resources": [
                    {
                        "type": r.resource_type,
                        "start": r.start,
                        "end": r.end,
                        "prefix_length": r.prefix_length,
                    }
                    for r in cert_info.resources
                ],
            }
            # 检查有效期
            if not check_validity_period(cert_info.not_before, cert_info.not_after):
                status = "expired"

    elif object_type == "roa":
        vrps = parse_roa(object_data)
        parsed_data = {
            "vrps": [
                {
                    "prefix": v.prefix,
                    "prefix_family": v.prefix_family,
                    "prefix_length": v.prefix_length,
                    "origin_as": v.origin_as,
                    "max_length": v.max_length,
                }
                for v in vrps
            ],
        }

    elif object_type == "manifest":
        entries = parse_manifest(object_data)
        parsed_data = {
            "entries": [
                {
                    "name": e.name,
                    "hash_algorithm": e.hash_algorithm,
                    "hash_value": e.hash_value,
                    "file_size": e.file_size,
                }
                for e in entries
            ],
        }

    elif object_type == "crl":
        revoked_serials = parse_crl(object_data)
        parsed_data = {
            "revoked_serials": revoked_serials,
        }

    elif object_type == "ghostbusters":
        # Ghostbusters 记录无标准结构化解析
        parsed_data = {"raw_size": len(object_data)}

    else:
        logger.warning("未知的 RPKI 对象类型", object_type=object_type)

    obj = RPKIObject(
        repository_id=repository_id,
        object_type=object_type,
        uri=uri or "",
        serial_number=serial_number,
        signing_time=signing_time,
        not_before=not_before,
        not_after=not_after,
        status=status,
        raw_data=object_data,
        parsed_data=parsed_data,
    )
    db.add(obj)
    await db.flush()
    await db.commit()
    await db.refresh(obj)

    logger.debug(
        "RPKI 对象解析完成",
        object_id=obj.id,
        object_type=object_type,
        uri=uri,
    )
    return obj


async def validate_object_chain(db: AsyncSession, object_id: int) -> dict[str, Any]:
    """验证 RPKI 对象的签名链。

    验证流程：
    1. 检查对象有效期
    2. 验证签名（占位）
    3. 检查资源范围覆盖
    4. 检查撤销状态

    Args:
        db: 异步数据库会话
        object_id: RPKI 对象 ID

    Returns:
        验证结果字典，包含 is_valid、errors 列表

    Raises:
        ValueError: 对象不存在
    """
    stmt = select(RPKIObject).where(RPKIObject.id == object_id)
    result = await db.execute(stmt)
    obj = result.scalar_one_or_none()
    if obj is None:
        raise ValueError(f"RPKI 对象 ID {object_id} 不存在")

    errors: list[str] = []
    is_valid = True

    # 1. 检查有效期
    if obj.not_before is not None and obj.not_after is not None:
        if not check_validity_period(obj.not_before, obj.not_after):
            is_valid = False
            errors.append("object_expired")
            # 更新对象状态为过期
            obj.status = "expired"

    # 2. 验证签名（占位）
    # TODO: 实际签名验证需获取签发证书并调用 validate_signature
    if obj.raw_data is not None:
        # 占位：假设签名验证通过
        pass

    # 3. 检查资源范围覆盖（针对 ROA 对象）
    if obj.object_type == "roa" and obj.parsed_data:
        # TODO: 实际需查询签发证书的资源范围
        # cert_resources = [...]
        # roa_resources = [...]
        # if not check_resource_coverage(cert_resources, roa_resources):
        #     is_valid = False
        #     errors.append("resource_chain_error")
        pass

    # 4. 检查撤销状态
    if obj.serial_number is not None:
        # TODO: 查询关联的 CRL 并检查撤销
        # crl_serials = await _get_crl_serials(db, obj.repository_id)
        # if not check_revocation(crl_serials, int(obj.serial_number)):
        #     is_valid = False
        #     errors.append("revoked")
        #     obj.status = "revoked"
        pass

    await db.flush()
    await db.commit()

    logger.info(
        "对象签名链验证完成",
        object_id=object_id,
        is_valid=is_valid,
        errors=errors,
    )

    return {
        "object_id": object_id,
        "is_valid": is_valid,
        "errors": errors,
        "status": obj.status,
    }


async def check_sync_health(db: AsyncSession) -> dict[str, Any]:
    """检查 RPKI 同步健康状态。

    统计各仓库的同步状态，识别长时间未同步或同步失败的仓库。

    Args:
        db: 异步数据库会话

    Returns:
        健康状态字典，包含整体状态、仓库统计与异常列表
    """
    stmt = select(RPKIRepository)
    result = await db.execute(stmt)
    repositories = list(result.scalars().all())

    total = len(repositories)
    success = sum(1 for r in repositories if r.sync_status == "success")
    failed = sum(1 for r in repositories if r.sync_status == "failed")
    running = sum(1 for r in repositories if r.sync_status == "running")
    pending = sum(1 for r in repositories if r.sync_status == "pending")

    now = datetime.now(timezone.utc)
    stale_repos: list[dict[str, Any]] = []
    for repo in repositories:
        if repo.last_synced_at is None:
            continue
        # 检查是否超过 24 小时未同步
        delta = now - repo.last_synced_at
        if delta.total_seconds() > 86400:
            stale_repos.append(
                {
                    "repository_id": repo.id,
                    "uri": repo.uri,
                    "last_synced_at": repo.last_synced_at.isoformat(),
                    "hours_since_sync": delta.total_seconds() / 3600,
                }
            )

    overall_healthy = failed == 0 and len(stale_repos) == 0

    return {
        "overall_healthy": overall_healthy,
        "total_repositories": total,
        "success_count": success,
        "failed_count": failed,
        "running_count": running,
        "pending_count": pending,
        "stale_repositories": stale_repos,
    }


async def get_tal_by_id(db: AsyncSession, tal_id: int) -> TAL | None:
    """根据 ID 获取 TAL。"""
    stmt = select(TAL).where(TAL.id == tal_id)
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def get_repository_by_id(
    db: AsyncSession, repository_id: int
) -> RPKIRepository | None:
    """根据 ID 获取仓库。"""
    stmt = select(RPKIRepository).where(RPKIRepository.id == repository_id)
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def delete_tal(db: AsyncSession, tal_id: int) -> bool:
    """删除 TAL（级联删除关联仓库与对象）。

    Args:
        db: 异步数据库会话
        tal_id: TAL ID

    Returns:
        是否删除成功
    """
    tal = await get_tal_by_id(db, tal_id)
    if tal is None:
        return False

    # 软删除：标记为 disabled
    tal.status = "disabled"
    await db.flush()
    await db.commit()

    logger.info("TAL 已禁用", tal_id=tal_id)
    return True


async def list_tals(
    db: AsyncSession, skip: int = 0, limit: int = 50
) -> list[TAL]:
    """获取 TAL 列表。"""
    stmt = (
        select(TAL)
        .order_by(TAL.id)
        .offset(skip)
        .limit(limit)
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def count_tals(db: AsyncSession) -> int:
    """统计 TAL 总数。"""
    from sqlalchemy import func

    stmt = select(func.count(TAL.id))
    result = await db.execute(stmt)
    return result.scalar_one()


async def list_repositories(
    db: AsyncSession,
    tal_id: int | None = None,
    skip: int = 0,
    limit: int = 50,
) -> list[RPKIRepository]:
    """获取仓库列表。

    Args:
        db: 异步数据库会话
        tal_id: 可选的 TAL ID 过滤
        skip: 跳过记录数
        limit: 返回记录数上限
    """
    stmt = select(RPKIRepository).order_by(RPKIRepository.id)
    if tal_id is not None:
        stmt = stmt.where(RPKIRepository.tal_id == tal_id)
    stmt = stmt.offset(skip).limit(limit)
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def count_repositories(
    db: AsyncSession, tal_id: int | None = None
) -> int:
    """统计仓库总数。"""
    from sqlalchemy import func

    stmt = select(func.count(RPKIRepository.id))
    if tal_id is not None:
        stmt = stmt.where(RPKIRepository.tal_id == tal_id)
    result = await db.execute(stmt)
    return result.scalar_one()
