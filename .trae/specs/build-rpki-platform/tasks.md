# Tasks

## 阶段 0：项目基础设施与架构搭建

- [x] Task 1: 搭建项目工程骨架与开发环境
  - [x] SubTask 1.1: 创建 monorepo 结构（后端服务、前端应用、基础设施配置、文档目录）
  - [x] SubTask 1.2: 初始化后端工程（语言/框架选型、目录结构、依赖管理、lint/format 配置）
  - [x] SubTask 1.3: 初始化前端工程（框架选型、目录结构、UI 组件库、构建配置）
  - [x] SubTask 1.4: 配置 Docker 容器化与 docker-compose 本地开发环境
  - [x] SubTask 1.5: 配置 CI/CD 流水线（构建、测试、镜像打包、部署）

- [x] Task 2: 搭建基础设施组件（数据库、缓存、消息队列）
  - [x] SubTask 2.1: 部署 PostgreSQL 并设计初始迁移机制
  - [x] SubTask 2.2: 部署 Redis 缓存
  - [x] SubTask 2.3: 部署 Kafka 消息队列
  - [x] SubTask 2.4: 部署时序数据库与列式分析库（用于 BGP 事件与历史数据）

- [x] Task 3: 实现身份认证与权限基础
  - [x] SubTask 3.1: 实现用户、角色、权限、租户数据模型
  - [x] SubTask 3.2: 实现 RBAC 权限控制中间件
  - [x] SubTask 3.3: 实现登录认证（本地账号 + 密码哈希）
  - [x] SubTask 3.4: 预留 SSO/OIDC/SAML/LDAP 集成接口
  - [x] SubTask 3.5: 实现审计日志记录机制（关键操作审计）

## 阶段 1：资源资产管理（P0）

- [x] Task 4: 实现资源资产管理后端服务
  - [x] SubTask 4.1: 设计并实现 IP 前缀数据模型（CIDR 层级、父子关系、标签、业务归属、地域、机房、生命周期状态）
  - [x] SubTask 4.2: 实现 IP 前缀 CRUD API 与批量导入接口
  - [x] SubTask 4.3: 设计并实现 ASN 数据模型（类型、联系人、NOC、应急联系方式、关系标签、风险画像）
  - [x] SubTask 4.4: 实现 ASN CRUD API
  - [x] SubTask 4.5: 设计并实现 BGP 邻居数据模型（Peer IP、Remote AS、地址族、会话类型、路由策略、最大前缀数、会话状态、关联路由器）
  - [x] SubTask 4.6: 实现 BGP 邻居 CRUD API
  - [x] SubTask 4.7: 实现资产一致性检查逻辑（对比 IPAM/CMDB 与 BGP/ROA/IRR）
  - [x] SubTask 4.8: 实现关系视图查询接口（前缀—ASN—ROA—BGP—业务—事件关联）

- [x] Task 5: 实现资源资产管理前端页面
  - [x] SubTask 5.1: 实现 IP 前缀管理页面（列表、详情、创建/编辑、批量导入、CIDR 层级展示）
  - [x] SubTask 5.2: 实现 ASN 管理页面（列表、详情、创建/编辑、关系标签）
  - [x] SubTask 5.3: 实现 BGP 邻居管理页面（列表、详情、创建/编辑）
  - [x] SubTask 5.4: 实现资产一致性检查结果展示页面
  - [x] SubTask 5.5: 实现关系视图拓扑展示页面

## 阶段 2：RPKI 数据同步、验证与 VRP 服务（P0）

- [x] Task 6: 实现 RPKI 仓库同步与对象验证
  - [x] SubTask 6.1: 实现 TAL（Trust Anchor Locator）管理
  - [x] SubTask 6.2: 实现 RRDP 同步客户端
  - [x] SubTask 6.3: 实现 rsync 同步客户端
  - [x] SubTask 6.4: 实现同步健康检查与状态监控
  - [x] SubTask 6.5: 实现 RPKI 对象解析（证书、ROA、Manifest、CRL、Ghostbusters）
  - [x] SubTask 6.6: 实现签名链、有效期、资源范围与撤销状态校验
  - [x] SubTask 6.7: 实现多验证器并行运行与结果比对告警

- [x] Task 7: 实现 VRP 生成与验证状态服务
  - [x] SubTask 7.1: 实现依据已验证 ROA 生成 VRP
  - [x] SubTask 7.2: 实现 VRP 高性能查询（按 prefix、origin AS、maxLength、RIR/TAL、时间点）
  - [x] SubTask 7.3: 实现 BGP 公告验证状态输出（Valid/Invalid/NotFound 及 Invalid 原因细分）
  - [x] SubTask 7.4: 实现 RPKI 数据快照、历史版本差异与回滚

## 阶段 3：BGP 数据采集、解析与存储（P0）

- [x] Task 8: 实现 BGP 数据采集层
  - [x] SubTask 8.1: 实现外部 BGP 数据源接入（RIPE RIS、RouteViews，支持实时 update 流与 MRT/RIB 文件）
  - [x] SubTask 8.2: 实现 BMP 采集 RIB/UPDATE
  - [x] SubTask 8.3: 实现多厂商设备适配接口（Cisco、Juniper、Huawei、H3C、Arista、Nokia、FRRouting、BIRD、OpenBGPD）
  - [x] SubTask 8.4: 实现 SNMP/NETCONF/RESTCONF/gNMI/CLI 接入路由器状态

- [x] Task 9: 实现 BGP 数据解析与存储
  - [x] SubTask 9.1: 实现 BGP 属性解析（announce、withdraw、AS_PATH、NEXT_HOP、COMMUNITY、Large Community、MED、LocalPref、时间戳、地址族）
  - [x] SubTask 9.2: 实现数据治理（去重、聚合、归并、数据源可信度、延迟、覆盖范围统计）
  - [x] SubTask 9.3: 实现热数据与历史数据存储策略
  - [x] SubTask 9.4: 实现 BGP 数据查询 API

## 阶段 4：BGP 路由安全检测（P0）

- [x] Task 10: 实现核心路由安全检测引擎
  - [x] SubTask 10.1: 实现源 AS 劫持检测（关联 ROA、资产台账、历史基线、传播范围）
  - [x] SubTask 10.2: 实现子前缀劫持检测（评估流量吸引风险与 ROA/maxLength 漏洞）
  - [x] SubTask 10.3: 实现 MOAS 异常检测（区分授权多 origin、Anycast、客户托管、清洗业务、未知双 origin）
  - [x] SubTask 10.4: 实现路由泄露检测（结合上游/下游/对等关系、AS_PATH 模式）
  - [x] SubTask 10.5: 实现路径异常检测（AS_PATH 突变、异常中转、异常区域传播、路径拉长、黑洞风险）
  - [x] SubTask 10.6: 实现撤路与震荡检测（大范围撤路、频繁 announce/withdraw、前缀数突变、收敛异常）
  - [x] SubTask 10.7: 实现 RPKI Invalid 传播统计

- [x] Task 11: 实现检测规则引擎与配置
  - [x] SubTask 11.1: 设计可配置规则模型（规则定义、阈值、白名单、生效范围）
  - [x] SubTask 11.2: 实现规则引擎执行框架
  - [x] SubTask 11.3: 提供默认规则集

## 阶段 5：ROA 生命周期管理（P0 基础 + P1 增强）

- [x] Task 12: 实现 ROA 查询与管理基础（P0）
  - [x] SubTask 12.1: 实现 ROA 数据模型与查询接口（prefix、origin AS、maxLength、状态、签发机构、有效期、历史版本）
  - [x] SubTask 12.2: 实现 ROA 与 BGP 公告、VRP 关联查询
  - [x] SubTask 12.3: 实现 ROA 缺失检测与冲突检测
  - [x] SubTask 12.4: 实现 maxLength 风险检查（过宽授权、未使用子前缀授权、劫持面分析）

- [x] Task 13: 实现 ROA 高级管理能力（P1）
  - [x] SubTask 13.1: 实现 ROA 创建建议（minimal ROA 原则）
  - [x] SubTask 13.2: 实现 ROA 变更影响评估（计算影响 BGP 公告、业务、客户、观察点、验证状态）
  - [x] SubTask 13.3: 实现 ROA 审批控制（分级审批、审计链）
  - [x] SubTask 13.4: 实现 ROA 变更后自动验证

## 阶段 6：ROA 良性冲突识别（P1）

- [x] Task 14: 实现良性冲突识别引擎
  - [x] SubTask 14.1: 实现 DDoS 清洗临时宣告识别（清洗商 ASN、工单、授权时间窗、路径模式）
  - [x] SubTask 14.2: 实现 Anycast 扩容识别（节点 ASN、地域、业务标签、历史多 origin 模式）
  - [x] SubTask 14.3: 实现计划内割接识别（变更窗口、审批记录、内部 BMP/RIB、业务变更记录）
  - [x] SubTask 14.4: 实现资源迁移/转让识别（IPAM/CMDB 状态、组织归属、历史 ROA、IRR 变化）
  - [x] SubTask 14.5: 实现 RPKI 数据源延迟识别（多验证器差异、同步状态、仓库对象时间戳）
  - [x] SubTask 14.6: 实现客户误配置识别（客户 ASN 授权边界、客户合同、BGP 记录）

## 阶段 7：ROV 策略模拟与变更影响评估（P1）

- [x] Task 15: 实现 ROV 策略模拟
  - [x] SubTask 15.1: 实现 drop-invalid/de-preference-invalid 策略模拟（对当前/历史路由表）
  - [x] SubTask 15.2: 实现受影响前缀、路径、设备、业务、客户清单输出
  - [x] SubTask 15.3: 实现按路由器、地域、机房、VRF、地址族、业务域、前缀重要性查看影响范围
  - [x] SubTask 15.4: 实现分阶段部署建议（先监控、再降权、后拒收）
  - [x] SubTask 15.5: 实现高风险阻断机制（核心前缀或大规模合法路由变 Invalid 时强制升级审批）

- [x] Task 16: 实现 ROA 变更影响模拟
  - [x] SubTask 16.1: 实现创建/修改/撤销 ROA 或调整 maxLength 前的 Valid/Invalid/NotFound 状态变化模拟
  - [x] SubTask 16.2: 实现新增攻击面分析

## 阶段 8：RPKI-RTR 服务与设备集成（P1）

- [x] Task 17: 实现 RPKI-RTR 服务
  - [x] SubTask 17.1: 实现 RTR 协议服务端（Session ID、Serial Number、增量更新）
  - [x] SubTask 17.2: 实现会话监控、一致性检查、白名单、mTLS/访问控制
  - [x] SubTask 17.3: 实现快照回滚
  - [x] SubTask 17.4: 实现多实例、高可用、负载均衡、多站点部署
  - [x] SubTask 17.5: 实现 RTR 客户端连接状态监控

- [x] Task 18: 实现设备配置模板与集成
  - [x] SubTask 18.1: 实现 Cisco IOS XE/IOS XR 配置生成模板
  - [x] SubTask 18.2: 实现 Juniper JunOS 配置生成模板
  - [x] SubTask 18.3: 实现 Huawei VRP 配置生成模板
  - [x] SubTask 18.4: 实现 H3C、Arista EOS、Nokia SR OS 配置生成模板
  - [x] SubTask 18.5: 实现 FRRouting、BIRD、OpenBGPD 配置生成模板
  - [x] SubTask 18.6: 实现设备侧策略模板（Valid/Invalid/NotFound 匹配、drop-invalid、de-preference-invalid、回滚、风险提示）

## 阶段 9：告警、事件与处置闭环（P0 基础 + P1 增强）

- [x] Task 19: 实现告警与事件管理（P0）
  - [x] SubTask 19.1: 实现实时告警生成、规则匹配、事件去重、聚合与同源事件归并
  - [x] SubTask 19.2: 实现事件数据模型与 CRUD API
  - [x] SubTask 19.3: 实现事件定级（P0-P4 等级与处置要求）
  - [x] SubTask 19.4: 实现事件确认、分派、升级、静默、维护窗口功能

- [x] Task 20: 实现自动取证与处置闭环（P1）
  - [x] SubTask 20.1: 实现自动取证（收集 ROA/VRP、BGP 样本、AS_PATH、传播范围、观察点、资产关系、变更记录、历史基线）
  - [x] SubTask 20.2: 实现风险评分模型（可解释评分、加分项、减分项、置信度、建议动作）
  - [x] SubTask 20.3: 实现处置建议生成（联系异常 ASN/上游、修正 ROA、调整策略、发布更具体合法前缀、清洗联动、客户通知）
  - [x] SubTask 20.4: 实现事件关闭与复盘（确认恢复、记录根因、保留证据与操作链、沉淀规则和案例库）
  - [x] SubTask 20.5: 实现通知集成（Webhook、邮件、短信、企业协作工具、ITSM/SOC 集成）

## 阶段 10：可视化与驾驶舱（P0 基础 + P1 增强）

- [x] Task 21: 实现总览驾驶舱（P0）
  - [x] SubTask 21.1: 实现总览数据聚合接口（IP/ASN 数量、ROA 覆盖率、Valid/Invalid/NotFound 分布、P0/P1 事件、cache 状态、RTR 会话、BGP 数据源状态、风险趋势）
  - [x] SubTask 21.2: 实现总览驾驶舱前端页面（图表、指标卡、趋势图）

- [x] Task 22: 实现详情视图（P0）
  - [x] SubTask 22.1: 实现前缀详情页面（资产属性、合法 origin、当前公告、AS_PATH、ROA/VRP 命中、IRR 信息、历史状态、告警、业务影响、操作建议）
  - [x] SubTask 22.2: 实现 ASN 详情页面（关联前缀、上游/下游/对等关系、历史路径、异常记录、风险画像）
  - [x] SubTask 22.3: 实现事件详情时间线页面（首次出现、传播变化、告警、人工确认、处置、恢复、关闭）

## 阶段 11：开放接口与集成能力（P0 + P1）

- [x] Task 23: 实现 REST/gRPC API 与认证
  - [x] SubTask 23.1: 设计 API 版本化、分页、筛选、限流、幂等机制
  - [x] SubTask 23.2: 实现核心 API（前缀验证、ROA/VRP 查询、BGP 状态查询、告警事件查询、资产同步、风险评估、报告导出、策略模拟）
  - [x] SubTask 23.3: 实现服务账号、API Key、OAuth2、mTLS 认证
  - [x] SubTask 23.4: 实现细粒度权限控制与 API 审计

- [x] Task 24: 实现事件推送与外部集成
  - [x] SubTask 24.1: 实现 Webhook、Syslog、Kafka 事件推送通道
  - [x] SubTask 24.2: 实现 IPAM/CMDB/NetBox 集成适配器
  - [x] SubTask 24.3: 实现 SIEM/SOC/ITSM 集成适配器
  - [x] SubTask 24.4: 实现 NMS/Prometheus/Grafana 指标集成
  - [x] SubTask 24.5: 实现 RIR/NIR/IRR/PeeringDB 外部信息关联
  - [x] SubTask 24.6: 实现企业协作与通知系统集成（邮件、短信、电话、企业微信、钉钉、Slack、Teams、PagerDuty）

## 阶段 12：多租户、安全与合规（P1）

- [x] Task 25: 实现多租户隔离
  - [x] SubTask 25.1: 实现数据层租户隔离
  - [x] SubTask 25.2: 实现权限、任务、缓存、对象存储隔离
  - [x] SubTask 25.3: 实现租户管理与配置

- [x] Task 26: 实现安全与合规能力
  - [x] SubTask 26.1: 实现 TLS、mTLS、密钥轮换、IP 白名单、访问限流、防暴力破解、异常登录检测
  - [x] SubTask 26.2: 实现敏感数据加密存储与密钥托管
  - [x] SubTask 26.3: 实现容器镜像扫描、依赖漏洞扫描、SBOM、代码静态检查
  - [x] SubTask 26.4: 实现关键操作审计与导出审计

## 阶段 13：高可用、部署与验收（P0）

- [x] Task 27: 实现高可用与弹性部署
  - [x] SubTask 27.1: 实现核心组件多实例与故障自动切换
  - [x] SubTask 27.2: 实现消息持久化与数据库备份恢复
  - [x] SubTask 27.3: 实现滚动升级、灰度发布、版本回退、配置灰度
  - [x] SubTask 27.4: 实现同城双活与异地灾备方案
  - [x] SubTask 27.5: 实现 Kubernetes 云原生部署编排

- [x] Task 28: 实现自动化测试与验收准备
  - [x] SubTask 28.1: 为关键检测逻辑、RPKI 验证、前缀树匹配、策略模拟、审批控制、RTR 服务编写自动化测试
  - [x] SubTask 28.2: 实现性能压测脚本（资产规模、BGP 吞吐、检测时延、查询性能）
  - [x] SubTask 28.3: 准备示例数据与默认规则集，使验收环境可完成核心场景验证
  - [x] SubTask 28.4: 编写部署文档与运行配置模板

# Task Dependencies
- Task 2 depends on Task 1
- Task 3 depends on Task 2
- Task 4 depends on Task 3
- Task 5 depends on Task 4
- Task 6 depends on Task 2
- Task 7 depends on Task 6
- Task 8 depends on Task 2
- Task 9 depends on Task 8
- Task 10 depends on Task 7, Task 9, Task 4
- Task 11 depends on Task 10
- Task 12 depends on Task 7, Task 4
- Task 13 depends on Task 12
- Task 14 depends on Task 10, Task 12
- Task 15 depends on Task 7, Task 9
- Task 16 depends on Task 12, Task 15
- Task 17 depends on Task 7
- Task 18 depends on Task 17
- Task 19 depends on Task 10
- Task 20 depends on Task 19
- Task 21 depends on Task 4, Task 7, Task 9, Task 19
- Task 22 depends on Task 21
- Task 23 depends on Task 4, Task 7, Task 9, Task 12, Task 19
- Task 24 depends on Task 23
- Task 25 depends on Task 3
- Task 26 depends on Task 25
- Task 27 depends on Task 1
- Task 28 depends on all previous tasks

# 可并行任务说明
- Task 4（资产管理）、Task 6（RPKI 同步）、Task 8（BGP 采集）在 Task 2/3 完成后可并行开发
- Task 5（资产管理前端）可与 Task 6/8 并行（依赖 Task 4 接口稳定）
- Task 17（RTR 服务）与 Task 18（设备模板）可与 Task 14/15/16 并行
- Task 25（多租户）与 Task 26（安全合规）可与业务功能任务并行
