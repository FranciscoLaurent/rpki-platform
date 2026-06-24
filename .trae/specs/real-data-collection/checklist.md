# Checklist

## RIPEstat API 客户端
- [ ] `app/services/ripestat_client.py` 已创建
- [ ] `get_as_overview(asn)` 实现，返回 AS holder、block 等信息
- [ ] `get_announced_prefixes(asn)` 实现，返回 AS 公告的前缀列表
- [ ] `get_prefix_overview(prefix)` 实现，返回前缀的 origin AS
- [ ] `get_roas_for_asn(asn)` 实现，返回 AS 的 ROA 列表
- [ ] 错误处理、重试机制、速率限制实现

## TAL 下载器
- [ ] `app/services/tal_downloader.py` 已创建
- [ ] 5 个 RIR 的 TAL 下载实现（APNIC、RIPE、ARIN、LACNIC、AFRINIC）
- [ ] TAL 文件内容解析（URI、公钥指纹）

## 真实数据采集服务
- [ ] `app/services/real_data_collector.py` 已创建
- [ ] 采集 10 个 AS 的真实信息（as-overview）
- [ ] 采集 10 个 AS 的真实 BGP 公告（announced-prefixes）
- [ ] 采集 10 个 AS 的真实 ROA 数据（rpki-roas）
- [ ] 前缀去重与资产自动生成
- [ ] VRP 从 ROA 派生
- [ ] BGP 公告的 RPKI 验证状态计算

## 数据初始化重写
- [ ] `scripts/init_sample_data.py` 重写为调用真实数据采集器
- [ ] 保留系统配置数据（租户、用户、角色、权限、检测规则等）
- [ ] 删除旧的示例数据生成

## sample_data.py 修改
- [ ] 删除 make_tals、make_roas、make_vrps、make_bgp_announcements、make_asns、make_prefixes
- [ ] 保留 make_tenants、make_users、make_roles、make_permissions、make_detection_rules 等
- [ ] 更新 make_all_sample_data 的返回值

## Bug 修复
- [ ] Dashboard ROA 覆盖率计算 bug 已修复
- [ ] Dashboard 与 ROA 管理页面覆盖率一致

## 端到端验证
- [ ] 真实数据采集脚本执行无错误
- [ ] TAL 内容是真实下载的（非 placeholder）
- [ ] ROA 数据与 RIPEstat 返回一致
- [ ] BGP 公告与 RIPEstat 返回一致
- [ ] ROA 覆盖率在 Dashboard 与 ROA 管理页面一致
- [ ] 所有数据无造假（无 65001 等私有 ASN，无 10.0.0.0/8 等私有 IP）
