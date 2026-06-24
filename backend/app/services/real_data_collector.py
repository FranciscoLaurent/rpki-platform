"""真实数据采集服务。

从 RIPEstat API 和 RIR 官方下载真实数据，包括：
- TAL（Trust Anchor Locator）文件：从 5 个 RIR 官方地址下载
- AS 概览信息：从 RIPEstat 获取
- BGP 公告前缀：从 RIPEstat 获取
- ROA（Route Origin Authorization）数据：从 RIPEstat 获取
- VRP（Validated ROA Payload）派生：从 ROA 派生
- 前缀资产生成：从 BGP 公告提取
- RPKI 验证状态计算：基于 ROA 验证 BGP 公告

采集流程在一个数据库事务中执行，失败时回滚。
单个 AS 采集失败不影响其他 AS。
"""

from __future__ import annotations

import ipaddress
from dataclasses import dataclass, field
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.models.asn import ASN
from app.models.bgp import (
    BGPAnnouncement,
    BGPDataSource,
    ObservationPoint,
)
from app.models.prefix import Prefix
from app.models.rpki import ROA, RPKIObject, RPKIRepository, TAL, VRP
from app.services.ripestat_client import RIPEstatClient
from app.services.tal_downloader import TALDownloader

logger = get_logger("app.real_data_collector")


# 目标 AS 列表（10 个知名 AS）
TARGET_ASNS: list[int] = [
    13335,  # Cloudflare
    15169,  # Google
    16509,  # Amazon AWS
    8075,   # Microsoft
    32934,  # Facebook/Meta
    2906,   # Netflix
    20940,  # Akamai
    14618,  # Amazon AES
    4837,   # China Unicom
    4134,   # China Telecom
]


@dataclass
class CollectionReport:
    """采集报告。

    记录采集过程中各类数据的数量、错误信息与总耗时。
    """

    tals_count: int = 0
    asns_count: int = 0
    prefixes_count: int = 0
    roas_count: int = 0
    vrps_count: int = 0
    bgp_announcements_count: int = 0
    bgp_withdraws_count: int = 0
    errors: list[str] = field(default_factory=list)
    duration_seconds: float = 0.0


class RealDataCollector:
    """真实数据采集器。

    从 RIPEstat API 和 RIR 官方下载真实数据并写入数据库。

    Args:
        db: 异步数据库会话
        tenant_id: 租户 ID，用于多租户数据隔离
    """

    def __init__(self, db: AsyncSession, tenant_id: int) -> None:
        self.db = db
        self.tenant_id = tenant_id
        self.ripestat = RIPEstatClient()
        self.tal_downloader = TALDownloader()
        # 缓存采集过程中的数据，供后续步骤使用
        self._tals_by_name: dict[str, TAL] = {}
        self._tal_object_ids: dict[int, int] = {}  # tal_id → 占位 RPKIObject.id
        self._roas: list[ROA] = []
        self._announcements: list[BGPAnnouncement] = []

    async def collect_all(self) -> CollectionReport:
        """采集所有真实数据。

        执行完整的采集流程：
        1. 下载真实 TAL
        2. 采集 AS 信息
        3. 采集 BGP 公告
        4. 采集 ROA 数据
        5. 派生 VRP
        6. 计算验证状态
        7. 提交事务

        Returns:
            采集报告，包含各类数据数量与错误信息
        """
        start_time = datetime.now(timezone.utc)
        report = CollectionReport()

        try:
            # 1. 下载真实 TAL
            logger.info("开始采集真实数据", step="tals")
            tals = await self.collect_tals()
            report.tals_count = len(tals)

            # 2. 采集 AS 信息
            logger.info("开始采集 AS 信息", step="asns")
            asns = await self.collect_asns()
            report.asns_count = len(asns)

            # 3. 采集 BGP 公告（验证状态稍后计算）
            logger.info("开始采集 BGP 公告", step="bgp")
            announcements = await self.collect_bgp_announcements()
            report.bgp_announcements_count = len(announcements)

            # 4. 采集 ROA 数据
            logger.info("开始采集 ROA 数据", step="roas")
            roas = await self.collect_roas()
            report.roas_count = len(roas)

            # 5. 派生 VRP
            logger.info("开始派生 VRP", step="vrps")
            vrps = await self.derive_vrps_from_roas()
            report.vrps_count = len(vrps)

            # 6. 计算验证状态（基于已采集的 ROA）
            # 单独 try-except：失败时不回滚其他数据
            logger.info("开始计算 RPKI 验证状态", step="validation")
            try:
                self._update_validation_status()
            except Exception as e:
                error_msg = f"RPKI 验证状态计算失败: {e}"
                report.errors.append(error_msg)
                logger.error(
                    "RPKI 验证状态计算失败，继续后续步骤",
                    error=str(e),
                    exc_info=True,
                )

            # 7. 生成前缀资产
            logger.info("开始生成前缀资产", step="prefixes")
            prefixes = await self.generate_prefix_assets()
            report.prefixes_count = len(prefixes)

            # 8. 提交事务
            await self.db.commit()
            logger.info("事务已提交", step="commit")
        except Exception as e:
            await self.db.rollback()
            error_msg = f"采集过程失败: {e}"
            report.errors.append(error_msg)
            logger.error("采集过程失败，已回滚", error=str(e), exc_info=True)

        end_time = datetime.now(timezone.utc)
        report.duration_seconds = (end_time - start_time).total_seconds()

        logger.info(
            "真实数据采集完成",
            tals=report.tals_count,
            asns=report.asns_count,
            prefixes=report.prefixes_count,
            roas=report.roas_count,
            vrps=report.vrps_count,
            bgp_announcements=report.bgp_announcements_count,
            bgp_withdraws=report.bgp_withdraws_count,
            errors=len(report.errors),
            duration_seconds=report.duration_seconds,
        )

        return report

    async def collect_tals(self) -> list[TAL]:
        """下载并存储真实 TAL。

        从 5 个 RIR 官方地址下载 TAL 文件，创建 TAL 记录及关联的
        RPKI 仓库与 RPKI 对象（用于后续 ROA 关联）。

        Returns:
            创建的 TAL 记录列表
        """
        logger.info("开始下载真实 TAL 文件")
        tal_infos = await self.tal_downloader.download_all_tals()
        tals: list[TAL] = []

        for info in tal_infos:
            # 检查是否已存在同名 TAL
            stmt = select(TAL).where(TAL.name == info.name)
            result = await self.db.execute(stmt)
            existing = result.scalar_one_or_none()

            if existing is not None:
                # 更新已有 TAL 的内容
                existing.uri = info.rrdp_uri
                existing.rsync_uri = info.rsync_uri
                existing.raw_tal = info.raw_tal
                existing.status = "active"
                existing.sync_status = "success"
                existing.last_synced_at = info.downloaded_at
                existing.last_error = None
                await self.db.flush()
                tal = existing
                logger.info("更新已有 TAL", name=info.name, tal_id=tal.id)
            else:
                # 创建新 TAL
                tal = TAL(
                    name=info.name,
                    uri=info.rrdp_uri,
                    rsync_uri=info.rsync_uri,
                    raw_tal=info.raw_tal,
                    status="active",
                    sync_status="success",
                    last_synced_at=info.downloaded_at,
                )
                self.db.add(tal)
                await self.db.flush()
                logger.info(
                    "创建 TAL",
                    name=info.name,
                    tal_id=tal.id,
                    size_bytes=info.size_bytes,
                )

            # 创建关联的 RPKI 仓库（如果不存在）
            repo_stmt = select(RPKIRepository).where(
                RPKIRepository.tal_id == tal.id
            )
            repo_result = await self.db.execute(repo_stmt)
            repo = repo_result.scalar_one_or_none()
            if repo is None:
                repo = RPKIRepository(
                    tal_id=tal.id,
                    uri=info.rrdp_uri,
                    protocol="rrdp",
                    status="active",
                    sync_status="success",
                    last_synced_at=info.downloaded_at,
                    object_count=0,
                )
                self.db.add(repo)
                await self.db.flush()
                logger.info(
                    "创建 RPKI 仓库",
                    tal_name=info.name,
                    repository_id=repo.id,
                )

            # 创建占位 RPKI 对象（ROA 的父对象）
            obj_stmt = select(RPKIObject).where(
                RPKIObject.repository_id == repo.id,
                RPKIObject.object_type == "roa",
            )
            obj_result = await self.db.execute(obj_stmt)
            obj = obj_result.scalar_one_or_none()
            if obj is None:
                obj = RPKIObject(
                    repository_id=repo.id,
                    object_type="roa",
                    uri=f"ripestat://roas/{info.name}",
                    status="valid",
                    signing_time=info.downloaded_at,
                )
                self.db.add(obj)
                await self.db.flush()
                logger.info(
                    "创建占位 RPKI 对象",
                    tal_name=info.name,
                    object_id=obj.id,
                )

            self._tals_by_name[info.name] = tal
            self._tal_object_ids[tal.id] = obj.id
            tals.append(tal)

        logger.info("TAL 采集完成", count=len(tals))
        return tals

    async def collect_asns(self) -> list[ASN]:
        """采集 AS 信息。

        对每个目标 AS 调用 RIPEstat 获取概览信息，创建 ASN 记录。
        单个 AS 采集失败不影响其他 AS。

        Returns:
            创建的 ASN 记录列表
        """
        logger.info("开始采集 AS 信息", target_count=len(TARGET_ASNS))
        asns: list[ASN] = []

        for asn in TARGET_ASNS:
            try:
                overview = await self.ripestat.get_as_overview(asn)
                holder = overview.holder or f"AS{asn}"

                # 检查是否已存在
                stmt = select(ASN).where(ASN.asn == asn)
                result = await self.db.execute(stmt)
                existing = result.scalar_one_or_none()

                if existing is not None:
                    existing.name = holder
                    existing.description = holder
                    existing.asn_type = "peer"
                    existing.status = "active"
                    existing.risk_profile = "high"
                    existing.tenant_id = self.tenant_id
                    await self.db.flush()
                    asns.append(existing)
                    logger.info(
                        "更新 ASN",
                        asn=asn,
                        holder=holder,
                        asn_id=existing.id,
                    )
                else:
                    asn_obj = ASN(
                        asn=asn,
                        name=holder,
                        asn_type="peer",
                        status="active",
                        risk_profile="high",
                        description=holder,
                        tenant_id=self.tenant_id,
                    )
                    self.db.add(asn_obj)
                    await self.db.flush()
                    asns.append(asn_obj)
                    logger.info(
                        "创建 ASN",
                        asn=asn,
                        holder=holder,
                        asn_id=asn_obj.id,
                    )
            except Exception as e:
                logger.warning(
                    "采集 AS 信息失败，跳过",
                    asn=asn,
                    error=str(e),
                )

        logger.info("AS 信息采集完成", count=len(asns))
        return asns

    async def collect_bgp_announcements(self) -> list[BGPAnnouncement]:
        """采集 BGP 公告。

        对每个目标 AS 调用 RIPEstat 获取公告前缀，创建 BGP 公告记录。
        RPKI 验证状态将在 ROA 采集完成后统一计算。

        Returns:
            创建的 BGP 公告记录列表
        """
        logger.info("开始采集 BGP 公告")
        announcements: list[BGPAnnouncement] = []

        # 创建或获取 BGP 数据源
        data_source = await self._get_or_create_data_source()
        # 创建或获取观察点
        observation_point = await self._get_or_create_observation_point(
            data_source.id
        )

        for asn in TARGET_ASNS:
            try:
                prefixes = await self.ripestat.get_announced_prefixes(asn)
                logger.info(
                    "获取 AS 公告前缀",
                    asn=asn,
                    prefix_count=len(prefixes),
                )

                for p in prefixes:
                    if not p.prefix:
                        continue
                    try:
                        family, length = self._parse_prefix(p.prefix)
                    except ValueError as e:
                        logger.warning(
                            "前缀解析失败，跳过",
                            asn=asn,
                            prefix=p.prefix,
                            error=str(e),
                        )
                        continue

                    # 解析公告时间
                    announced_at = self._parse_datetime(p.starttime)

                    ann = BGPAnnouncement(
                        prefix=p.prefix,
                        prefix_family=family,
                        prefix_length=length,
                        origin_as=asn,
                        as_path=[asn],
                        observation_point_id=observation_point.id,
                        data_source_id=data_source.id,
                        timestamp=announced_at,
                        address_family=family,
                        rpki_validation_status="not_found",
                        tenant_id=self.tenant_id,
                    )
                    self.db.add(ann)
                    announcements.append(ann)

                await self.db.flush()
            except Exception as e:
                logger.warning(
                    "采集 BGP 公告失败，跳过该 AS",
                    asn=asn,
                    error=str(e),
                )

        logger.info(
            "BGP 公告采集完成",
            count=len(announcements),
        )
        self._announcements = announcements
        return announcements

    async def collect_roas(self) -> list[ROA]:
        """采集 ROA 数据。

        对每个目标 AS 调用 RIPEstat 获取 ROA 列表，创建 ROA 记录。
        根据 ROA 的 trust_anchor 字段匹配对应的 TAL。

        Returns:
            创建的 ROA 记录列表
        """
        logger.info("开始采集 ROA 数据")
        roas: list[ROA] = []

        for asn in TARGET_ASNS:
            try:
                roa_records = await self.ripestat.get_roas_for_asn(asn)
                logger.info(
                    "获取 AS ROA 数据",
                    asn=asn,
                    roa_count=len(roa_records),
                )

                for record in roa_records:
                    if not record.prefix:
                        continue
                    try:
                        family, length = self._parse_prefix(record.prefix)
                    except ValueError as e:
                        logger.warning(
                            "ROA 前缀解析失败，跳过",
                            asn=asn,
                            prefix=record.prefix,
                            error=str(e),
                        )
                        continue

                    # 根据 trust_anchor 匹配 TAL
                    tal_id, object_id = self._match_tal_for_roa(
                        record.trust_anchor
                    )

                    # object_id 是必填字段，未匹配 TAL 时跳过该 ROA
                    if object_id is None:
                        logger.warning(
                            "ROA 未匹配到 TAL，跳过",
                            asn=asn,
                            prefix=record.prefix,
                            trust_anchor=record.trust_anchor,
                        )
                        continue

                    # max_length 处理：0 或 None 时使用前缀长度
                    max_length = record.max_length if record.max_length > 0 else length

                    roa = ROA(
                        object_id=object_id,
                        prefix=record.prefix,
                        prefix_family=family,
                        prefix_length=length,
                        origin_as=record.asn,
                        max_length=max_length,
                        tal_id=tal_id,
                        status="valid",
                    )
                    self.db.add(roa)
                    roas.append(roa)

                await self.db.flush()
            except Exception as e:
                logger.warning(
                    "采集 ROA 数据失败，跳过该 AS",
                    asn=asn,
                    error=str(e),
                )

        logger.info("ROA 数据采集完成", count=len(roas))
        self._roas = roas
        return roas

    async def derive_vrps_from_roas(self) -> list[VRP]:
        """从 ROA 派生 VRP。

        VRP 是 ROA 的验证版本，每个 ROA 对应一个 VRP。

        Returns:
            派生的 VRP 记录列表
        """
        logger.info("开始从 ROA 派生 VRP", roa_count=len(self._roas))
        vrps: list[VRP] = []

        for roa in self._roas:
            # 获取 TAL 名称作为 trust_anchor
            trust_anchor = ""
            if roa.tal_id is not None:
                for name, tal in self._tals_by_name.items():
                    if tal.id == roa.tal_id:
                        trust_anchor = name
                        break

            vrp = VRP(
                prefix=roa.prefix,
                prefix_family=roa.prefix_family,
                prefix_length=roa.prefix_length,
                origin_as=roa.origin_as,
                max_length=roa.max_length,
                tal_id=roa.tal_id,
                roa_id=roa.id,
                trust_anchor=trust_anchor,
                validation_status="valid",
            )
            self.db.add(vrp)
            vrps.append(vrp)

        await self.db.flush()
        logger.info("VRP 派生完成", count=len(vrps))
        return vrps

    async def generate_prefix_assets(self) -> list[Prefix]:
        """从 BGP 公告生成前缀资产。

        从 BGP 公告中提取唯一前缀，创建 Prefix 记录。

        Returns:
            创建的 Prefix 记录列表
        """
        logger.info("开始生成前缀资产")
        prefixes: list[Prefix] = []
        seen: set[str] = set()

        for ann in self._announcements:
            if ann.prefix in seen:
                continue
            seen.add(ann.prefix)

            # 检查是否已存在
            stmt = select(Prefix).where(Prefix.prefix == ann.prefix)
            result = await self.db.execute(stmt)
            existing = result.scalar_one_or_none()

            if existing is not None:
                prefixes.append(existing)
                continue

            try:
                prefix_obj = Prefix(
                    prefix=ann.prefix,
                    prefix_family=ann.prefix_family,
                    prefix_length=ann.prefix_length,
                    status="active",
                    importance="medium",
                    description=f"AS{ann.origin_as} announced prefix",
                    tenant_id=self.tenant_id,
                )
                self.db.add(prefix_obj)
                prefixes.append(prefix_obj)
            except Exception as e:
                logger.warning(
                    "创建前缀资产失败，跳过",
                    prefix=ann.prefix,
                    error=str(e),
                )

        await self.db.flush()
        logger.info("前缀资产生成完成", count=len(prefixes))
        return prefixes

    def compute_rpki_validation_status(
        self, prefix: str, origin_as: int, roas: list[ROA]
    ) -> str:
        """计算 BGP 公告的 RPKI 验证状态。

        验证规则：
        - valid: 存在 ROA 覆盖该前缀，且 origin_as 匹配，且前缀长度 <= max_length
        - invalid: 存在 ROA 覆盖该前缀，但 origin_as 不匹配或前缀长度 > max_length
        - not_found: 无任何 ROA 覆盖该前缀

        Args:
            prefix: BGP 公告前缀
            origin_as: 起源 AS 号
            roas: ROA 记录列表

        Returns:
            验证状态：valid/invalid/not_found
        """
        # 查找覆盖该前缀的 ROA
        covering_roas = [
            r for r in roas if self._prefix_covered_by_roa(prefix, r)
        ]
        if not covering_roas:
            return "not_found"

        # 检查是否有匹配的 ROA
        prefix_length = self._prefix_length(prefix)
        for roa in covering_roas:
            max_len = roa.max_length if roa.max_length else roa.prefix_length
            if roa.origin_as == origin_as and prefix_length <= max_len:
                return "valid"

        # 有覆盖但不匹配 → invalid
        return "invalid"

    def _update_validation_status(self) -> None:
        """更新所有 BGP 公告的 RPKI 验证状态。

        在 ROA 采集完成后调用，基于已采集的 ROA 数据计算每条
        BGP 公告的验证状态。

        使用前缀字典索引加速：按 ROA 前缀字符串建立字典，
        对每条公告通过遍历父前缀查找覆盖的 ROA（最多 32/128 次），
        避免遍历全部 ROA。
        """
        if not self._roas:
            logger.warning("无 ROA 数据，跳过验证状态计算")
            return

        # 按前缀字符串建立 ROA 索引
        roa_by_prefix: dict[str, list[ROA]] = {}
        for roa in self._roas:
            roa_by_prefix.setdefault(roa.prefix, []).append(roa)

        valid_count = 0
        invalid_count = 0
        not_found_count = 0

        for ann in self._announcements:
            covering = self._find_covering_roas(
                ann.prefix, roa_by_prefix
            )
            if not covering:
                ann.rpki_validation_status = "not_found"
                not_found_count += 1
                continue

            prefix_len = self._prefix_length(ann.prefix)
            origin_as = ann.origin_as or 0
            matched = False
            for roa in covering:
                max_len = (
                    roa.max_length if roa.max_length else roa.prefix_length
                )
                if roa.origin_as == origin_as and prefix_len <= max_len:
                    matched = True
                    break

            if matched:
                ann.rpki_validation_status = "valid"
                valid_count += 1
            else:
                ann.rpki_validation_status = "invalid"
                ann.rpki_invalid_reason = (
                    self._compute_invalid_reason_from_list(
                        ann.prefix, origin_as, covering
                    )
                )
                invalid_count += 1

        logger.info(
            "RPKI 验证状态计算完成",
            total=len(self._announcements),
            valid=valid_count,
            invalid=invalid_count,
            not_found=not_found_count,
        )

    def _find_covering_roas(
        self, prefix: str, roa_by_prefix: dict[str, list[ROA]]
    ) -> list[ROA]:
        """通过前缀字典索引查找覆盖给定前缀的 ROA。

        遍历该前缀及其所有父前缀，在字典中查找匹配的 ROA。
        时间复杂度 O(L)，L 为前缀长度（IPv4 最多 32，IPv6 最多 128）。

        Args:
            prefix: BGP 公告前缀
            roa_by_prefix: 按前缀字符串索引的 ROA 字典

        Returns:
            覆盖该前缀的 ROA 列表
        """
        try:
            net = ipaddress.ip_network(prefix, strict=False)
        except ValueError:
            return []

        covering: list[ROA] = []
        addr = net.network_address
        # 遍历该前缀及其所有父前缀（从当前前缀长度到 0）
        for plen in range(net.prefixlen, -1, -1):
            try:
                parent = ipaddress.ip_network(
                    f"{addr}/{plen}", strict=False
                )
            except ValueError:
                continue
            key = str(parent)
            if key in roa_by_prefix:
                covering.extend(roa_by_prefix[key])
            if plen == 0:
                break

        return covering

    def _compute_invalid_reason_from_list(
        self, prefix: str, origin_as: int, covering_roas: list[ROA]
    ) -> str:
        """计算 RPKI 验证失败原因。

        Args:
            prefix: BGP 公告前缀
            origin_as: 起源 AS 号
            covering_roas: 覆盖该前缀的 ROA 列表

        Returns:
            失败原因：origin_as_mismatch/length_exceeded
        """
        prefix_length = self._prefix_length(prefix)
        for roa in covering_roas:
            max_len = roa.max_length if roa.max_length else roa.prefix_length
            if roa.origin_as != origin_as:
                return "origin_as_mismatch"
            if prefix_length > max_len:
                return "length_exceeded"
        return "origin_as_mismatch"

    def _match_tal_for_roa(
        self, trust_anchor: str
    ) -> tuple[int | None, int | None]:
        """根据 trust_anchor 匹配 TAL。

        Args:
            trust_anchor: ROA 的信任锚名称（如 "ARIN", "RIPE"）

        Returns:
            (tal_id, object_id) 元组，未匹配时均为 None
        """
        if not trust_anchor:
            return None, None

        # 标准化信任锚名称
        ta_upper = trust_anchor.upper().strip()
        # 尝试精确匹配
        tal = self._tals_by_name.get(ta_upper)
        if tal is None:
            # 尝试部分匹配（如 "arin-rpki" → "ARIN"）
            for name, t in self._tals_by_name.items():
                if name in ta_upper or ta_upper in name:
                    tal = t
                    break

        if tal is None:
            return None, None

        # 从缓存中获取该 TAL 关联的占位 RPKIObject ID
        object_id = self._tal_object_ids.get(tal.id)
        return tal.id, object_id

    async def _get_or_create_data_source(self) -> BGPDataSource:
        """获取或创建 BGP 数据源。

        创建名为 "RIPEstat RIS" 的数据源（如果不存在）。

        Returns:
            BGP 数据源对象
        """
        stmt = select(BGPDataSource).where(
            BGPDataSource.name == "RIPEstat RIS",
            BGPDataSource.tenant_id == self.tenant_id,
        )
        result = await self.db.execute(stmt)
        ds = result.scalar_one_or_none()

        if ds is not None:
            return ds

        ds = BGPDataSource(
            name="RIPEstat RIS",
            source_type="ripe_ris",
            protocol="bgp_live_stream",
            endpoint="https://stat.ripe.net/data/announced-prefixes",
            status="active",
            trust_level="high",
            tenant_id=self.tenant_id,
        )
        self.db.add(ds)
        await self.db.flush()
        logger.info("创建 BGP 数据源", data_source_id=ds.id)
        return ds

    async def _get_or_create_observation_point(
        self, data_source_id: int
    ) -> ObservationPoint:
        """获取或创建观察点。

        创建名为 "RIPE RIS Global" 的观察点（如果不存在）。

        Args:
            data_source_id: 数据源 ID

        Returns:
            观察点对象
        """
        stmt = select(ObservationPoint).where(
            ObservationPoint.name == "RIPE RIS Global",
            ObservationPoint.data_source_id == data_source_id,
        )
        result = await self.db.execute(stmt)
        op = result.scalar_one_or_none()

        if op is not None:
            return op

        op = ObservationPoint(
            name="RIPE RIS Global",
            data_source_id=data_source_id,
            location="Global",
            collector_id="RIS-GLOBAL",
            ip_version="dual",
            status="active",
        )
        self.db.add(op)
        await self.db.flush()
        logger.info("创建观察点", observation_point_id=op.id)
        return op

    @staticmethod
    def _parse_prefix(prefix: str) -> tuple[int, int]:
        """解析前缀字符串，返回 (family, length)。

        Args:
            prefix: CIDR 前缀字符串

        Returns:
            (family, length) 元组，family 为 4 或 6

        Raises:
            ValueError: 前缀格式无效
        """
        net = ipaddress.ip_network(prefix, strict=False)
        family = 6 if net.version == 6 else 4
        return family, net.prefixlen

    @staticmethod
    def _prefix_length(prefix: str) -> int:
        """获取前缀长度。

        Args:
            prefix: CIDR 前缀字符串

        Returns:
            前缀长度
        """
        return ipaddress.ip_network(prefix, strict=False).prefixlen

    @staticmethod
    def _prefix_covered_by_roa(prefix: str, roa: ROA) -> bool:
        """检查前缀是否被 ROA 覆盖。

        ROA 覆盖前缀的条件：ROA 的前缀包含公告前缀（同族）。

        Args:
            prefix: BGP 公告前缀
            roa: ROA 记录

        Returns:
            是否被覆盖
        """
        try:
            prefix_net = ipaddress.ip_network(prefix, strict=False)
            roa_net = ipaddress.ip_network(roa.prefix, strict=False)
        except ValueError:
            return False

        # 必须同族
        if prefix_net.version != roa_net.version:
            return False

        # ROA 前缀包含公告前缀（相等或公告前缀是 ROA 前缀的子网）
        return prefix_net == roa_net or prefix_net.subnet_of(roa_net)

    @staticmethod
    def _parse_datetime(dt_str: str | None) -> datetime:
        """解析 RIPEstat 返回的时间字符串。

        Args:
            dt_str: ISO 8601 时间字符串

        Returns:
            解析后的 datetime 对象，解析失败时返回当前时间
        """
        if not dt_str:
            return datetime.now(timezone.utc)
        try:
            # RIPEstat 返回 ISO 8601 格式，如 "2024-01-01T00:00:00Z"
            # Python 3.11+ 的 fromisoformat 支持 "Z" 后缀
            cleaned = dt_str.replace("Z", "+00:00")
            dt = datetime.fromisoformat(cleaned)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        except (ValueError, TypeError):
            return datetime.now(timezone.utc)


__all__ = [
    "CollectionReport",
    "RealDataCollector",
    "TARGET_ASNS",
]
