# Tasks

## 阶段 1：基础设施

- [ ] Task 1: 创建 RIPEstat API 客户端
  - [ ] SubTask 1.1: 创建 `app/services/ripestat_client.py`
  - [ ] SubTask 1.2: 实现 `get_as_overview(asn)` → 调用 as-overview 接口
  - [ ] SubTask 1.3: 实现 `get_announced_prefixes(asn)` → 调用 announced-prefixes 接口
  - [ ] SubTask 1.4: 实现 `get_prefix_overview(prefix)` → 调用 prefix-overview 接口
  - [ ] SubTask 1.5: 实现 `get_roas_for_asn(asn)` → 调用 rpki-roas 接口
  - [ ] SubTask 1.6: 实现错误处理、重试机制、速率限制（RIPEstat 建议 1 请求/秒）

- [ ] Task 2: 创建 TAL 下载器
  - [ ] SubTask 2.1: 创建 `app/services/tal_downloader.py`
  - [ ] SubTask 2.2: 实现 5 个 RIR 的 TAL 下载（APNIC、RIPE、ARIN、LACNIC、AFRINIC）
  - [ ] SubTask 2.3: 解析 TAL 文件内容（URI、公钥指纹）

## 阶段 2：数据采集器

- [ ] Task 3: 创建真实数据采集服务
  - [ ] SubTask 3.1: 创建 `app/services/real_data_collector.py`
  - [ ] SubTask 3.2: 实现采集 10 个 AS 的真实信息（as-overview）
  - [ ] SubTask 3.3: 实现采集 10 个 AS 的真实 BGP 公告（announced-prefixes）
  - [ ] SubTask 3.4: 实现采集 10 个 AS 的真实 ROA 数据（rpki-roas）
  - [ ] SubTask 3.5: 实现前缀去重与资产自动生成
  - [ ] SubTask 3.6: 实现 VRP 从 ROA 派生
  - [ ] SubTask 3.7: 实现 BGP 公告的 RPKI 验证状态计算（基于 ROA 匹配）

## 阶段 3：数据初始化重写

- [ ] Task 4: 重写数据初始化脚本
  - [ ] SubTask 4.1: 重写 `scripts/init_sample_data.py`，调用真实数据采集器
  - [ ] SubTask 4.2: 保留系统配置数据（租户、用户、角色、权限、检测规则等）
  - [ ] SubTask 4.3: 删除旧的示例数据生成（TAL、ROA、VRP、BGP、ASN、前缀）

- [ ] Task 5: 修改 sample_data.py
  - [ ] SubTask 5.1: 删除 make_tals、make_roas、make_vrps、make_bgp_announcements、make_asns、make_prefixes
  - [ ] SubTask 5.2: 保留 make_tenants、make_users、make_roles、make_permissions、make_detection_rules 等
  - [ ] SubTask 5.3: 更新 make_all_sample_data 的返回值

## 阶段 4：Bug 修复

- [ ] Task 6: 修复 Dashboard ROA 覆盖率计算 bug
  - [ ] SubTask 6.1: 复用 `roa_validation_service.get_roa_coverage_stats` 逻辑
  - [ ] SubTask 6.2: 确保 Dashboard 与 ROA 管理页面覆盖率一致

## 阶段 5：验证

- [ ] Task 7: 端到端验证
  - [ ] SubTask 7.1: 执行真实数据采集脚本，确认无错误
  - [ ] SubTask 7.2: 验证 TAL 内容是真实下载的（非 placeholder）
  - [ ] SubTask 7.3: 验证 ROA 数据与 RIPEstat 返回一致
  - [ ] SubTask 7.4: 验证 BGP 公告与 RIPEstat 返回一致
  - [ ] SubTask 7.5: 验证 ROA 覆盖率在 Dashboard 与 ROA 管理页面一致
  - [ ] SubTask 7.6: 验证所有数据无造假（无 65001 等私有 ASN，无 10.0.0.0/8 等私有 IP）

# Task Dependencies
- Task 3 依赖 Task 1、Task 2
- Task 4 依赖 Task 3
- Task 5 与 Task 4 并行
- Task 6 独立（可并行）
- Task 7 依赖 Task 4、Task 5、Task 6
