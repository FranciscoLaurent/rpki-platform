"""ROA 良性冲突识别引擎。

包含以下检测器：
- ddos_scrubbing_detector: DDoS 清洗临时宣告识别
- anycast_detector: Anycast 扩容识别
- maintenance_detector: 计划内割接识别
- resource_transfer_detector: 资源迁移/转让识别
- data_source_delay_detector: RPKI 数据源延迟识别
- customer_misconfig_detector: 客户误配置识别

``BenignConflictDetector`` 为统一入口，依次执行所有检测器，
返回置信度最高的良性冲突分析结果。

重要：
    良性冲突识别只降低误报优先级，不能替代安全验证。
    每种检测器返回置信度（0-1）和证据。
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.models.detection import Alert
from app.schemas.benign_conflict import BenignConflictAnalysisResult
from app.services.benign_conflict.anycast_detector import detect_anycast_expansion
from app.services.benign_conflict.customer_misconfig_detector import (
    detect_customer_misconfig,
)
from app.services.benign_conflict.data_source_delay_detector import (
    detect_data_source_delay,
)
from app.services.benign_conflict.ddos_scrubbing_detector import (
    detect_ddos_scrubbing,
)
from app.services.benign_conflict.maintenance_detector import (
    detect_planned_maintenance,
)
from app.services.benign_conflict.resource_transfer_detector import (
    detect_resource_transfer,
)

logger = get_logger("app.benign_conflict")


# 检测器列表（按执行顺序）
_DETECTORS = [
    detect_ddos_scrubbing,
    detect_planned_maintenance,
    detect_anycast_expansion,
    detect_resource_transfer,
    detect_customer_misconfig,
    detect_data_source_delay,
]


class BenignConflictDetector:
    """良性冲突识别引擎统一入口。

    依次执行所有检测器，返回置信度最高的良性冲突分析结果。
    若多个检测器均识别为良性，选择置信度最高的结果；
    若均未识别为良性，返回 ``is_benign=False`` 的默认结果。

    用法::

        detector = BenignConflictDetector()
        result = await detector.analyze(db, alert)
        if result.is_benign:
            # 降低告警优先级，记录良性冲突
            ...
    """

    def __init__(self) -> None:
        """初始化良性冲突识别引擎。"""
        self.detectors = list(_DETECTORS)

    async def analyze(
        self, db: AsyncSession, alert: Alert
    ) -> BenignConflictAnalysisResult:
        """分析告警是否为良性冲突。

        依次执行所有检测器，收集每个检测器的分析结果，
        返回置信度最高的良性冲突分析结果。

        Args:
            db: 异步数据库会话
            alert: 待分析的告警对象

        Returns:
            良性冲突分析结果。``is_benign`` 为 True 表示疑似或确认良性冲突，
            可降低告警优先级；False 表示未识别为良性，需保持原有处置流程。
        """
        all_evidence: dict[str, Any] = {"detector_results": []}
        best_result: BenignConflictAnalysisResult | None = None

        for detector in self.detectors:
            detector_name = detector.__name__
            try:
                result = await detector(db, alert)
                all_evidence["detector_results"].append(
                    {
                        "detector": detector_name,
                        "is_benign": result.is_benign,
                        "conflict_type": result.conflict_type,
                        "confidence": result.confidence,
                        "recommendation": result.recommendation,
                    }
                )

                # 选择置信度最高的良性结果
                if result.is_benign:
                    if best_result is None or result.confidence > best_result.confidence:
                        best_result = result

                logger.debug(
                    "检测器执行完成",
                    detector=detector_name,
                    is_benign=result.is_benign,
                    confidence=result.confidence,
                )
            except Exception as e:
                logger.error(
                    "检测器执行失败",
                    detector=detector_name,
                    error=str(e),
                    exc_info=True,
                )
                all_evidence["detector_results"].append(
                    {
                        "detector": detector_name,
                        "error": str(e),
                        "is_benign": False,
                    }
                )
                continue

        # 若有检测器识别为良性，返回最佳结果（合并证据）
        if best_result is not None:
            # 合并所有检测器的执行记录到证据中
            merged_evidence = dict(best_result.evidence)
            merged_evidence["all_detector_results"] = all_evidence["detector_results"]
            return BenignConflictAnalysisResult(
                conflict_type=best_result.conflict_type,
                confidence=best_result.confidence,
                evidence=merged_evidence,
                recommendation=best_result.recommendation,
                is_benign=True,
            )

        # 所有检测器均未识别为良性
        return BenignConflictAnalysisResult(
            conflict_type=None,
            confidence=0.0,
            evidence=all_evidence,
            recommendation=(
                "所有检测器均未识别为良性冲突，按正常告警处置流程处理。"
                "注意：良性冲突识别只降低误报优先级，不能替代安全验证。"
            ),
            is_benign=False,
        )


__all__ = [
    "BenignConflictDetector",
    "detect_anycast_expansion",
    "detect_customer_misconfig",
    "detect_data_source_delay",
    "detect_ddos_scrubbing",
    "detect_planned_maintenance",
    "detect_resource_transfer",
]
