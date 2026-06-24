"""初始化真实数据脚本

从权威数据源采集真实数据：
- TAL: 从 5 个 RIR 官方下载
- AS 信息: 从 RIPEstat API 采集 10 个知名 AS
- BGP 公告: 从 RIPEstat API 采集
- ROA 数据: 从 RIPEstat API 采集
- VRP: 从 ROA 派生
- 前缀资产: 从 BGP 公告自动生成

系统配置数据（租户、用户、角色等）从 sample_data.py 初始化。

用法::

    # 在 backend 目录下执行
    python -m scripts.init_sample_data

注意：
- 本脚本不会自动执行数据库迁移，请先运行 ``alembic upgrade head``。
- 采集过程需要访问外网（RIPEstat API 与 RIR 官方地址）。
- 单个数据源采集失败不影响其他数据源。
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

# 添加项目根目录到 sys.path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.core.database import async_session_factory
from app.core.logging import get_logger
from app.core.sample_data import init_system_config_data
from app.services.real_data_collector import RealDataCollector

logger = get_logger("init_sample_data")


async def main() -> None:
    """主函数：初始化系统配置数据并采集真实数据。"""
    print("=" * 60)
    print("RPKI 平台真实数据初始化")
    print("=" * 60)

    async with async_session_factory() as db:
        try:
            # 1. 初始化系统配置数据
            print("\n[1/2] 初始化系统配置数据...")
            result = await init_system_config_data(db)
            print(f"  租户: {result.get('tenants_count', 0)}")
            print(f"  用户: {result.get('users_count', 0)}")
            print(f"  角色: {result.get('roles_count', 0)}")
            print(f"  权限: {result.get('permissions_count', 0)}")
            print(f"  检测规则: {result.get('detection_rules_count', 0)}")
            print(f"  RTR 服务: {result.get('rtr_servers_count', 0)}")
            print(f"  业务服务: {result.get('business_services_count', 0)}")
            print(f"  客户: {result.get('customers_count', 0)}")
            print(f"  路由器: {result.get('routers_count', 0)}")

            tenant_id = result.get("default_tenant_id")
            if not tenant_id:
                print("\n✗ 未获取到默认租户 ID，终止采集流程")
                return

            # 2. 采集真实数据
            print("\n[2/2] 采集真实数据（从 RIPEstat API 和 RIR 官方）...")
            print("  - TAL: 从 5 个 RIR 官方下载")
            print("  - AS 信息: 从 RIPEstat 采集 10 个知名 AS")
            print("  - BGP 公告 / ROA / VRP / 前缀: 自动派生")
            print()

            collector = RealDataCollector(db, tenant_id)
            report = await collector.collect_all()

            # 打印采集报告
            print("\n" + "=" * 60)
            print("采集报告")
            print("=" * 60)
            print(f"TAL 数量: {report.tals_count}")
            print(f"ASN 数量: {report.asns_count}")
            print(f"前缀数量: {report.prefixes_count}")
            print(f"ROA 数量: {report.roas_count}")
            print(f"VRP 数量: {report.vrps_count}")
            print(f"BGP 公告数量: {report.bgp_announcements_count}")
            print(f"撤路记录数量: {report.bgp_withdraws_count}")
            print(f"采集耗时: {report.duration_seconds:.1f} 秒")

            if report.errors:
                print(f"\n警告（{len(report.errors)} 个错误）:")
                for err in report.errors[:10]:
                    print(f"  - {err}")
                if len(report.errors) > 10:
                    print(f"  ... 还有 {len(report.errors) - 10} 个错误未显示")

            print("\n✓ 真实数据初始化完成")
        except Exception as e:
            await db.rollback()
            logger.error("真实数据初始化失败", error=str(e), exc_info=True)
            print(f"\n✗ 初始化失败: {e}")
            raise


if __name__ == "__main__":
    asyncio.run(main())
