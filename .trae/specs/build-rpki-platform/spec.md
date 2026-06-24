# 企业级 RPKI 网络安全管理平台 Spec

## Why
企业、运营商、IDC、云服务商等大型组织面临 BGP 路由安全威胁（前缀劫持、子前缀劫持、路由泄露、MOAS 异常等），需要一套统一的控制与分析中枢，将资源授权、RPKI 状态、实际路由传播、业务影响和处置过程连接起来，使 RPKI 从合规动作变成真正可运营的路由安全能力。当前阶段遵循"应用先落地"原则，优先交付可部署、可运行、可验证的平台应用。

## What Changes
- 建立资源资产管理模块：统一管理 IPv4/IPv6 前缀、ASN、BGP 邻居及其与业务、ROA、IRR 的关系
- 建立 RPKI 数据同步、验证与 VRP 服务：从全球信任锚同步数据，验证 RPKI 对象，生成 VRP 并提供验证状态查询
- 建立 BGP 数据采集、解析与存储：接入外部 BGP 数据源（RIPE RIS、RouteViews 等）与内部 BMP 数据，解析 BGP 属性
- 建立 BGP 路由安全检测：源 AS 劫持、子前缀劫持、MOAS 异常、路由泄露、路径异常、撤路与震荡、RPKI Invalid 传播检测
- 建立 ROA 生命周期管理：查询、创建建议、变更评估、maxLength 风险检查、审批控制、变更后验证
- 建立 ROA 良性冲突与配置错误识别：区分 DDoS 清洗、Anycast、计划内割接、资源迁移、数据源延迟、客户误配置等场景
- 建立 ROV 策略模拟与变更影响评估：模拟 drop-invalid/de-preference-invalid 策略，评估变更影响
- 建立 RPKI-RTR 服务与设备集成：提供 RTR 服务，支持多厂商设备配置模板
- 建立告警、事件与处置闭环：发现、取证、定级、响应、处置建议、关闭与复盘
- 建立可视化与驾驶舱：总览、前缀详情、ASN 详情、事件详情
- 建立开放接口与集成能力：REST/gRPC API、Webhook、与 IPAM/CMDB/SIEM/SOC 等系统集成
- 建立权限、审计与多租户基础：RBAC/ABAC、SSO/OIDC/SAML/LDAP、审计日志、租户隔离
- **BREAKING**：无（新建项目）

## Impact
- Affected specs: 无（新建项目，无既有 spec）
- Affected code: 全新代码库，包含以下主要模块
  - 后端服务：资产服务、RPKI 验证服务、BGP 采集与检测服务、ROA 服务、ROV 模拟服务、RTR 服务、告警事件服务、API 网关、审计服务
  - 前端应用：Web 控制台、运营大屏、客户门户
  - 数据存储：关系型数据库（PostgreSQL）、时序数据库、列式分析库、缓存（Redis）、消息队列（Kafka）
  - 基础设施：容器化部署、CI/CD、监控、日志、链路追踪
- 外部依赖：RIPE RIS / RouteViews BGP 数据、全球 RPKI 信任锚仓库、IPAM/CMDB（如 NetBox）、SIEM/SOC/ITSM 系统

## ADDED Requirements

### Requirement: 资源资产管理
系统 SHALL 提供企业 IP 前缀、ASN、BGP 邻居的统一管理能力，并建立其与业务、ROA、BGP、IRR、设备、上游、客户和事件的关系。

#### Scenario: IP 前缀管理
- **WHEN** 网络管理员创建或导入 IP 前缀
- **THEN** 系统支持 CIDR 层级、父子前缀、聚合/拆分、标签、业务归属、地域、机房、云区域、客户、重要等级、生命周期状态与批量导入

#### Scenario: ASN 管理
- **WHEN** 管理员维护 ASN 信息
- **THEN** 系统支持自有、客户、供应商、上游、对等、IXP、Route Server、清洗商等类型，并维护联系人、NOC、应急联系方式、关系标签与风险画像

#### Scenario: BGP 邻居管理
- **WHEN** 管理员维护 BGP 邻居
- **THEN** 系统维护 Peer IP、Remote AS、地址族、会话类型、路由策略、最大前缀数、会话状态及关联路由器

#### Scenario: 资产一致性检查
- **WHEN** 系统执行一致性检查
- **THEN** 系统识别 IPAM/CMDB 台账与实际 BGP、ROA、IRR 之间的不一致、重叠、越权、未登记与过期信息

#### Scenario: 关系视图
- **WHEN** 用户查看前缀关系
- **THEN** 系统提供前缀—ASN—ROA—BGP 路由—业务系统—事件的关联视图和拓扑展示

### Requirement: RPKI 数据同步、验证与 VRP 服务
系统 SHALL 从全球 RPKI 信任锚和仓库同步数据，兼容 RRDP 与 rsync，支持 TAL 管理与同步健康检查，并对 RPKI 对象进行验证和 VRP 生成。

#### Scenario: RPKI 仓库同步
- **WHEN** 系统从信任锚同步数据
- **THEN** 系统兼容 RRDP 与 rsync，支持 TAL 管理与同步健康检查

#### Scenario: RPKI 对象验证
- **WHEN** 系统解析 RPKI 对象
- **THEN** 系统校验证书、ROA、Manifest、CRL、Ghostbusters 等对象的签名链、有效期、资源范围与撤销状态

#### Scenario: 多验证器比对
- **WHEN** 多验证器并行运行
- **THEN** 系统比对结果，发现对象、VRP 或状态不一致时触发告警

#### Scenario: VRP 生成与查询
- **WHEN** 系统依据已验证 ROA 生成 VRP
- **THEN** 系统支持按 prefix、origin AS、maxLength、RIR/TAL、时间点进行高性能查询

#### Scenario: BGP 公告验证状态
- **WHEN** 系统对任意 BGP 公告输出验证状态
- **THEN** 系统输出 Valid、Invalid、NotFound，并细分 Invalid 原因（origin AS 不匹配、长度超出 maxLength、ROA 撤销/失效、资源链异常或数据源异常）

#### Scenario: 数据快照与回滚
- **WHEN** 用户查看历史版本
- **THEN** 系统支持 RPKI 数据快照、历史版本差异和稳定版本回滚

### Requirement: BGP 数据采集、解析与存储
系统 SHALL 接入外部与内部 BGP 数据源，解析 BGP 属性，并支持数据治理。

#### Scenario: 外部 BGP 数据源接入
- **WHEN** 系统接入 RIPE RIS、RouteViews、公开 Route Server 或商业数据源
- **THEN** 系统支持实时 update 流和 MRT/RIB 文件

#### Scenario: 内部网络数据源接入
- **WHEN** 系统通过 BMP 采集 RIB/UPDATE
- **THEN** 系统支持通过 SNMP、NETCONF、RESTCONF、gNMI 或 CLI 接入路由器与路由反射器状态

#### Scenario: 多厂商设备适配
- **WHEN** 系统接入不同厂商设备
- **THEN** 系统至少适配 Cisco、Juniper、Huawei、H3C、Arista、Nokia、FRRouting、BIRD、OpenBGPD 等主流环境

#### Scenario: BGP 属性解析
- **WHEN** 系统解析 BGP 消息
- **THEN** 系统实时解析 announce、withdraw、AS_PATH、NEXT_HOP、COMMUNITY、Large Community、MED、LocalPref、时间戳与地址族

#### Scenario: 数据治理
- **WHEN** 系统处理 BGP 数据
- **THEN** 系统支持去重、聚合、归并、数据源可信度、延迟、覆盖范围统计，保留热数据与可追溯历史数据

### Requirement: BGP 路由安全检测
系统 SHALL 实现多种 BGP 路由安全检测能力，识别前缀劫持、子前缀劫持、MOAS 异常、路由泄露、路径异常、撤路与震荡、RPKI Invalid 传播。

#### Scenario: 源 AS 劫持检测
- **WHEN** 非授权 origin AS 对企业前缀发起公告
- **THEN** 系统识别异常并关联 ROA、资产台账、历史基线与传播范围

#### Scenario: 子前缀劫持检测
- **WHEN** 更具体前缀出现异常公告
- **THEN** 系统评估是否存在流量吸引风险与 ROA/maxLength 漏洞

#### Scenario: MOAS 异常检测
- **WHEN** 前缀出现多 origin AS
- **THEN** 系统区分授权多 origin、Anycast、客户托管、清洗业务与未知双 origin

#### Scenario: 路由泄露检测
- **WHEN** 路由出现不合理传播
- **THEN** 系统结合上游/下游/对等关系、AS_PATH 模式与 ASPA 预留关系识别路由泄露

#### Scenario: 路径异常检测
- **WHEN** AS_PATH 出现异常
- **THEN** 系统发现 AS_PATH 突变、异常中转 ASN、异常国家/区域传播、路径异常拉长或黑洞风险

#### Scenario: 撤路与震荡检测
- **WHEN** 关键前缀大范围消失或频繁震荡
- **THEN** 系统识别撤路、频繁 announce/withdraw、前缀数突变和收敛异常

#### Scenario: RPKI Invalid 传播统计
- **WHEN** Invalid 路由被传播
- **THEN** 系统统计 Invalid 路由被哪些观察点接收、传播或拒绝，反映真实影响面

### Requirement: ROA 生命周期管理
系统 SHALL 提供 ROA 查询、创建建议、变更评估、maxLength 风险检查、审批控制与变更后验证能力。

#### Scenario: ROA 查询与关联
- **WHEN** 用户查询 ROA
- **THEN** 系统展示 prefix、origin AS、maxLength、状态、签发机构、有效期、历史版本，并关联实际 BGP 公告和 VRP

#### Scenario: ROA 创建建议
- **WHEN** 系统发现已公告无 ROA、ROA 缺失或不匹配的前缀
- **THEN** 系统提出建议，优先使用 minimal ROA 原则

#### Scenario: ROA 变更评估
- **WHEN** 用户修改 prefix、origin AS、maxLength 或撤销 ROA 前
- **THEN** 系统计算影响的 BGP 公告、业务、客户、观察点和验证状态

#### Scenario: maxLength 风险检查
- **WHEN** 系统检查 maxLength
- **THEN** 系统识别过宽授权、未实际使用的子前缀授权、可能被利用的劫持面，并提出精确化建议

#### Scenario: ROA 审批控制
- **WHEN** 核心前缀、origin AS 变更、maxLength 放宽和撤销操作
- **THEN** 系统要求分级审批，所有动作保留完整审计链

#### Scenario: ROA 变更后验证
- **WHEN** ROA 发布/修改后
- **THEN** 系统自动验证 RPKI 仓库状态、VRP 变化和实际 BGP 状态

### Requirement: ROA 良性冲突与配置错误识别
系统 SHALL 区分"RPKI/BGP 表面不一致"与"真实攻击"，良性冲突识别只能降低误报优先级，不能替代安全验证。

#### Scenario: DDoS 清洗临时宣告
- **WHEN** 清洗商 ASN 宣告客户前缀
- **THEN** 系统结合已登记清洗商 ASN、工单、授权时间窗、已知路径模式，输出疑似/已确认良性冲突并提示临时 ROA 或授权治理

#### Scenario: Anycast 扩容
- **WHEN** Anycast 节点扩容
- **THEN** 系统结合已登记节点 ASN、地域、业务标签、历史多 origin 模式，输出授权多 origin 或需补齐 ROA 的建议

#### Scenario: 计划内割接
- **WHEN** 计划内割接发生
- **THEN** 系统结合变更窗口、审批记录、内部 BMP/RIB、业务变更记录，识别短时配置/变更异常并跟踪是否按窗口恢复

#### Scenario: 资源迁移/转让
- **WHEN** 资源迁移或转让
- **THEN** 系统结合 IPAM/CMDB 状态、组织归属、历史 ROA、IRR 变化，输出资源迁移待治理或高风险异常

#### Scenario: RPKI 数据源延迟
- **WHEN** RPKI 数据源延迟
- **THEN** 系统结合多验证器差异、同步状态、仓库对象时间戳，输出数据源不一致与延迟告警

#### Scenario: 客户误配置
- **WHEN** 客户误配置发生
- **THEN** 系统结合客户 ASN 授权边界、实际客户合同、BGP 记录，输出配置错误并生成修复待办与通知建议

### Requirement: ROV 策略模拟与变更影响评估
系统 SHALL 在启用 ROV 策略前对路由表进行模拟，并在 ROA 变更前评估影响。

#### Scenario: ROV 策略模拟
- **WHEN** 启用 drop-invalid、de-preference-invalid 或其他验证策略前
- **THEN** 系统对当前/历史路由表进行模拟，列出受影响前缀、路径、设备、业务和客户

#### Scenario: ROA 变更影响模拟
- **WHEN** 创建、修改、撤销 ROA 或调整 maxLength 前
- **THEN** 系统模拟 Valid/Invalid/NotFound 状态变化与新增攻击面

#### Scenario: 多维度影响查看
- **WHEN** 用户查看影响范围
- **THEN** 系统支持按路由器、地域、机房、VRF、地址族、业务域和前缀重要性查看

#### Scenario: 分阶段部署建议
- **WHEN** 系统输出部署建议
- **THEN** 系统提供先监控、再降权、后拒收的分阶段建议，对 NotFound 和疑似良性 Invalid 提供治理清单

#### Scenario: 高风险阻断
- **WHEN** 变更会导致核心前缀或大规模合法路由变为 Invalid
- **THEN** 系统强制高风险提示与升级审批

### Requirement: RPKI-RTR 服务与设备集成
系统 SHALL 提供符合 RPKI-RTR 的服务能力，并支持多厂商设备配置生成。

#### Scenario: RTR 服务能力
- **WHEN** RTR 客户端连接
- **THEN** 系统支持 Session ID、Serial Number、增量更新、会话监控、一致性检查、白名单、mTLS/访问控制和快照回滚

#### Scenario: RTR 高可用
- **WHEN** 部署 RTR 服务
- **THEN** 系统支持多实例、高可用、负载均衡、多站点部署和 RTR 客户端连接状态监控

#### Scenario: 多厂商配置生成
- **WHEN** 生成设备配置
- **THEN** 系统提供至少覆盖 Cisco IOS XE/IOS XR、Juniper JunOS、Huawei VRP、H3C、Arista EOS、Nokia SR OS、FRRouting、BIRD、OpenBGPD 的配置生成能力或模板接口

#### Scenario: 设备侧策略模板
- **WHEN** 应用设备策略
- **THEN** 系统提供覆盖 Valid、Invalid、NotFound 匹配、drop-invalid、de-preference-invalid、回滚和风险提示的模板

### Requirement: 告警、事件与处置闭环
系统 SHALL 形成发现、取证、定级、响应、处置建议、关闭与复盘的闭环。

#### Scenario: 告警发现
- **WHEN** 检测到异常
- **THEN** 系统实时告警、规则匹配、事件去重、聚合与同源事件归并

#### Scenario: 自动取证
- **WHEN** 告警生成
- **THEN** 系统自动收集 ROA/VRP、BGP 样本、AS_PATH、传播范围、观察点、资产关系、变更记录和历史基线

#### Scenario: 事件定级
- **WHEN** 系统评估事件
- **THEN** 系统基于前缀重要性、RPKI 状态、传播规模、异常路径、变更窗口和良性冲突证据输出风险等级与置信度

#### Scenario: 事件响应
- **WHEN** 事件需要响应
- **THEN** 系统支持确认、分派、升级、静默、维护窗口、Webhook、邮件、短信、企业协作工具和 ITSM/SOC 集成

#### Scenario: 处置建议
- **WHEN** 事件需要处置
- **THEN** 系统提供联系异常 ASN/上游、修正 ROA、调整策略、发布更具体合法前缀、清洗联动、客户通知等建议

#### Scenario: 关闭与复盘
- **WHEN** 事件关闭
- **THEN** 系统确认恢复、记录根因、保留证据与操作链，沉淀为规则和案例库

### Requirement: 可视化与驾驶舱
系统 SHALL 提供总览、前缀详情、ASN 详情、事件详情等可视化能力。

#### Scenario: 总览驾驶舱
- **WHEN** 用户查看总览
- **THEN** 系统展示企业 IP/ASN 数量、ROA 覆盖率、Valid/Invalid/NotFound 分布、P0/P1 事件、RPKI cache 状态、RTR 会话状态、BGP 数据源状态和风险趋势

#### Scenario: 前缀详情
- **WHEN** 用户查看前缀详情
- **THEN** 系统展示资产属性、合法 origin、当前公告、AS_PATH、ROA/VRP 命中、IRR 信息、历史状态、告警、业务影响与操作建议

#### Scenario: ASN 详情
- **WHEN** 用户查看 ASN 详情
- **THEN** 系统展示关联前缀、上游/下游/对等关系、历史路径、异常记录、与本企业关系和风险画像

#### Scenario: 事件详情时间线
- **WHEN** 用户查看事件详情
- **THEN** 系统提供完整时间线：首次出现、传播变化、告警、人工确认、处置、恢复和关闭

### Requirement: 开放接口与集成能力
系统 SHALL 提供 REST/gRPC API、Webhook 等接口，并支持与外部系统集成。

#### Scenario: API 接口
- **WHEN** 外部系统调用 API
- **THEN** 系统提供 REST API，关键高频能力可提供 gRPC；接口支持版本化、分页、筛选、限流、幂等、审计与权限校验

#### Scenario: 核心 API 能力
- **WHEN** 调用核心 API
- **THEN** 系统提供前缀验证、ROA/VRP 查询、BGP 状态查询、告警事件查询、资产同步、风险评估、报告数据导出和策略模拟接口

#### Scenario: 事件推送
- **WHEN** 事件需要推送
- **THEN** 系统支持 Webhook、Syslog、Kafka 或等价消息通道，用于实时向 SIEM、SOC、ITSM、企业协作工具推送事件

#### Scenario: 认证与授权
- **WHEN** API 调用需要认证
- **THEN** 系统支持服务账号、API Key、OAuth2、mTLS 和细粒度权限控制

#### Scenario: 外部系统集成
- **WHEN** 与外部系统集成
- **THEN** 系统支持与 IPAM/CMDB/NetBox、SIEM/SOC/ITSM、NMS/Prometheus/Grafana、RIR/NIR/IRR/PeeringDB、路由器与配置管理系统、企业协作与通知系统集成

### Requirement: 权限、审计与多租户
系统 SHALL 提供 RBAC/ABAC、SSO/OIDC/SAML/LDAP、MFA、审计日志与多租户隔离能力。

#### Scenario: 身份认证
- **WHEN** 用户登录
- **THEN** 系统支持 SSO、OIDC、SAML、LDAP/AD、MFA、RBAC 与 ABAC，遵循最小权限原则

#### Scenario: 接口安全
- **WHEN** 访问接口和内部服务
- **THEN** 系统支持 TLS、mTLS、密钥轮换、IP 白名单、访问限流、防暴力破解和异常登录检测

#### Scenario: 敏感数据保护
- **WHEN** 存储敏感数据
- **THEN** 系统对敏感资产、联系人、内部拓扑、API 凭据和审计信息加密存储或采用合适的密钥托管机制

#### Scenario: 安全工程
- **WHEN** 构建与部署
- **THEN** 系统支持容器镜像扫描、依赖漏洞扫描、SBOM、代码静态检查、关键操作审计与导出审计

#### Scenario: 多租户隔离
- **WHEN** 多租户环境
- **THEN** 系统在数据、权限、任务、缓存和对象存储层实施隔离

### Requirement: 数据模型与数据治理
系统 SHALL 管理核心实体，并支持关系查询、变更审计、历史追溯与数据治理。

#### Scenario: 核心实体管理
- **WHEN** 系统管理数据
- **THEN** 系统管理身份与租户、网络资产、RPKI、BGP、安全运营、外部关系、审计与治理等核心实体

#### Scenario: 数据来源治理
- **WHEN** 系统处理多源数据
- **THEN** 系统支持数据来源标识、可信度、采集延迟、覆盖范围和可用性统计

#### Scenario: 数据保留策略
- **WHEN** 系统管理数据生命周期
- **THEN** 系统支持按热/温/冷数据制定保留、归档与检索策略，确保关键事件可以历史回放

#### Scenario: 多源差异对比
- **WHEN** 同一前缀、ASN、ROA 在多来源数据中存在差异
- **THEN** 系统支持差异对比和冲突展示

#### Scenario: 数据隔离与审计
- **WHEN** 管理敏感数据
- **THEN** 系统对客户、租户、敏感资产与内部拓扑数据执行逻辑隔离和最小可见范围控制，支持关键数据快照、版本对比、回滚和不可篡改审计

### Requirement: 检测、评分与处置规则
系统 SHALL 提供可解释的风险评分模型与事件定级能力。

#### Scenario: 事件定级
- **WHEN** 系统评估事件等级
- **THEN** 系统按 P0 严重、P1 高危、P2 中危、P3 低危、P4 信息进行定级，并执行相应处置要求

#### Scenario: 可解释风险评分
- **WHEN** 系统计算风险评分
- **THEN** 评分可解释，每个事件展示总分、主要加分项、减分项、置信度与建议动作，评分维度包含资产重要性、RPKI 证据、BGP 传播证据、授权与变更证据、历史与行为基线、外部风险特征

#### Scenario: 自动化处置边界
- **WHEN** 系统执行自动化处置
- **THEN** 系统可自动收集证据、发送通知、创建工单、生成策略建议、调用外部流程或进入审批；不得在未授权条件下直接修改生产 BGP 策略或 ROA

#### Scenario: 受控自动化
- **WHEN** 用户启用受控自动化
- **THEN** 系统支持规则白名单、双人审批、回滚预案、变更窗口、影响模拟、执行审计和失败熔断，所有高风险动作可追溯到发起人、审批人、执行人、目标对象、执行结果与回滚状态

### Requirement: 非功能需求（性能与容量）
系统 SHALL 满足企业级性能与容量要求。

#### Scenario: 资产规模
- **WHEN** 系统管理资产
- **THEN** 系统支持管理不少于 100 万条 IP 前缀记录、10 万条以上 ROA/VRP 相关记录，并可横向扩展

#### Scenario: BGP 事件处理
- **WHEN** 系统处理 BGP 事件
- **THEN** 系统支持日处理千万级 BGP UPDATE；高峰期通过分区、消息队列和水平扩容承接更高吞吐

#### Scenario: 检测时延
- **WHEN** 系统执行检测
- **THEN** 内部 BMP 数据源核心检测目标不超过 30 秒；外部公开数据源目标不超过 3 分钟，受上游数据延迟影响时需明确展示

#### Scenario: 查询性能
- **WHEN** 用户执行查询
- **THEN** 核心前缀匹配与状态查询 P95 不超过 500ms；普通 API 查询 P95 不超过 800ms

#### Scenario: 历史分析
- **WHEN** 用户执行大范围历史查询
- **THEN** 系统采用异步任务与可追踪进度

### Requirement: 非功能需求（可用性与弹性）
系统 SHALL 满足高可用与弹性要求。

#### Scenario: 服务可用性
- **WHEN** 系统运行
- **THEN** 核心平台服务目标可用性不低于 99.95%；RTR 服务目标可用性不低于 99.99%

#### Scenario: 故障恢复
- **WHEN** 组件故障
- **THEN** 核心组件支持多实例、故障自动切换、消息持久化、数据库备份恢复和服务健康检查

#### Scenario: 滚动升级
- **WHEN** 系统升级
- **THEN** 系统支持滚动升级、灰度发布、版本回退、配置灰度和关键数据快照回滚

#### Scenario: 灾备
- **WHEN** 部署灾备
- **THEN** 系统支持同城双活和异地灾备方案；RTO/RPO 可按客户等级配置

### Requirement: 部署形态
系统 SHALL 支持多种部署形态。

#### Scenario: 多种部署模式
- **WHEN** 部署平台
- **THEN** 系统支持单企业私有化部署、集团多租户部署、MSSP 托管部署、Kubernetes 云原生部署、内网半离线部署与混合云部署

#### Scenario: 高可用与扩展
- **WHEN** 配置高可用
- **THEN** 系统支持主备、同城双活、异地灾备和组件级水平扩展；核心服务和 RTR 服务独立伸缩；RPKI 验证、BGP 流处理、分析查询按工作负载分别扩容

#### Scenario: 多环境管理
- **WHEN** 管理环境
- **THEN** 系统支持配置隔离、租户隔离、数据留存策略和多环境（开发/测试/预生产/生产）发布管理

## MODIFIED Requirements
无（新建项目）

## REMOVED Requirements
无

## 分期建设说明
- **P0（首期必须上线）**：资产管理、RPKI 同步与验证、ROA/VRP 查询、BGP 数据接入、基础前缀/子前缀劫持检测、ROA 缺失和冲突检测、maxLength 风险、告警事件、基础可视化、审计、权限和部署
- **P1（首期增强/二期优先）**：ROA 创建建议、变更/撤销影响分析、审批流、良性冲突分类、ROV 策略模拟、RTR 服务、设备模板、BMP 深度接入、SIEM/SOC/ITSM 集成、多租户、风险评分和历史分析
- **P2（高级演进）**：ASPA 试验性支持、深度 route leak 检测、BGPsec 预留、图分析、机器学习辅助异常检测、自动化处置剧本、托管服务运营能力和全球态势分析

本 spec 以 P0 为首要交付目标，P1/P2 作为后续演进阶段。
