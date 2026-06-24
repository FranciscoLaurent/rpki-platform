# 真实数据采集 Spec

## Why
当前系统所有数据（TAL、ROA、VRP、BGP 公告、ASN、前缀）均为手工编造的示例数据，不符合"真实场景应用"的要求。需要从权威数据源（RIPEstat API、RIR 官方 TAL）采集真实数据，确保 ROA 覆盖率、BGP 公告、RPKI 验证状态等全部反映真实互联网状况，不重不漏。

## What Changes
- **删除所有示例数据**：清除 `sample_data.py` 中的假 TAL、ROA、VRP、BGP 公告、ASN、前缀
- **下载真实 TAL**：从 APNIC、RIPE、ARIN、LACNIC、AFRINIC 官方 URL 下载真实 TAL 文件内容
- **采集 10 个知名 AS 的真实数据**：
  - AS13335 (Cloudflare)
  - AS15169 (Google)
  - AS16509 (Amazon AWS)
  - AS8075 (Microsoft)
  - AS32934 (Facebook/Meta)
  - AS2906 (Netflix)
  - AS20940 (Akamai)
  - AS14618 (Amazon AES)
  - AS4837 (China Unicom)
  - AS4134 (China Telecom)
- **采集真实 ROA 数据**：通过 RIPEstat `rpki-roas` 接口获取每个 AS 的 ROA 列表
- **采集真实 BGP 公告**：通过 RIPEstat `announced-prefixes` 接口获取每个 AS 公告的前缀
- **采集真实 AS 信息**：通过 RIPEstat `as-overview` 接口获取 AS holder、block 等信息
- **采集真实前缀可见性**：通过 RIPEstat `prefix-overview` 接口获取前缀的 origin AS
- **修复 Dashboard ROA 覆盖率 bug**：复用 `roa_validation_service.get_roa_coverage_stats` 的精确匹配逻辑
- **保留真实的基础数据**：租户、用户、角色、权限、检测规则、RTR 服务、业务服务、客户、路由器（这些是系统配置，不是外部数据）

## Impact
- Affected specs: `build-rpki-platform`（数据层真实化）
- Affected code:
  - `backend/app/core/sample_data.py` — 重写为真实数据采集
  - `backend/scripts/init_sample_data.py` — 重写为真实数据初始化
  - `backend/app/services/dashboard_service.py` — 修复 ROA 覆盖率计算 bug
  - 新增 `backend/app/services/ripestat_client.py` — RIPEstat API 客户端
  - 新增 `backend/app/services/tal_downloader.py` — TAL 文件下载器

## ADDED Requirements

### Requirement: 真实 TAL 数据
系统 SHALL 从 RIR 官方 URL 下载真实的 TAL 文件内容并存储到数据库。

#### Scenario: 下载真实 TAL
- **WHEN** 系统初始化数据
- **THEN** 从 APNIC、RIPE、ARIN、LACNIC、AFRINIC 官方 URL 下载 TAL 文件
- **AND** 存储真实的 TAL 内容（含公钥、URI 等信息）

### Requirement: 真实 ROA/VRP 数据
系统 SHALL 通过 RIPEstat API 采集 10 个知名 AS 的真实 ROA 数据。

#### Scenario: 采集真实 ROA
- **WHEN** 系统初始化数据
- **THEN** 调用 `https://stat.ripe.net/data/rpki-roas/data.json?resource=AS{asn}` 获取每个 AS 的 ROA 列表
- **AND** 存储真实的 prefix、origin_as、max_length、trust_anchor 信息

### Requirement: 真实 BGP 公告数据
系统 SHALL 通过 RIPEstat API 采集 10 个知名 AS 的真实 BGP 公告。

#### Scenario: 采集真实 BGP 公告
- **WHEN** 系统初始化数据
- **THEN** 调用 `https://stat.ripe.net/data/announced-prefixes/data.json?resource=AS{asn}` 获取每个 AS 公告的前缀
- **AND** 调用 `https://stat.ripe.net/data/prefix-overview/data.json?resource={prefix}` 获取前缀的 origin AS
- **AND** 存储真实的 prefix、origin_as、as_path、rpki_validation_status

### Requirement: 真实 AS 信息
系统 SHALL 通过 RIPEstat API 采集 10 个知名 AS 的真实信息。

#### Scenario: 采集真实 AS 信息
- **WHEN** 系统初始化数据
- **THEN** 调用 `https://stat.ripe.net/data/as-overview/data.json?resource=AS{asn}` 获取 AS 信息
- **AND** 存储真实的 holder（名称）、block（AS 号段）、type 等信息

### Requirement: 真实前缀资产
系统 SHALL 基于采集的 BGP 公告自动生成前缀资产记录。

#### Scenario: 自动生成前缀资产
- **WHEN** BGP 公告采集完成
- **THEN** 从公告中提取唯一前缀，创建前缀资产记录
- **AND** 标记 importance、business_service 等业务属性（可后续编辑）

### Requirement: ROA 覆盖率一致性
Dashboard 与 ROA 管理页面的 ROA 覆盖率 SHALL 使用相同的计算逻辑。

#### Scenario: 覆盖率一致
- **WHEN** 用户查看 Dashboard 或 ROA 管理页面
- **THEN** 两个页面显示的 ROA 覆盖率数值一致
- **AND** 使用精确匹配逻辑（前缀在 ROA 表中存在）

## MODIFIED Requirements

### Requirement: 数据初始化脚本
`scripts/init_sample_data.py` SHALL 改为从权威外部数据源采集真实数据，不再生成示例数据。

### Requirement: sample_data.py
`app/core/sample_data.py` SHALL 仅保留系统配置类数据（租户、用户、角色、权限、检测规则、RTR 服务、业务服务、客户、路由器），外部数据（TAL、ROA、VRP、BGP、ASN、前缀）由真实数据采集器生成。
