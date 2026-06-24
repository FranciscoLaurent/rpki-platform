# 前端占位页面实现 Spec

## Why
当前前端 5 个核心业务模块（RPKI 管理、BGP 监测、ROA 管理、告警事件、系统设置）仍为占位页面（"该模块正在建设中，敬请期待。"），但后端 API 已全部就绪。需要将这些页面开发出来，使平台具备完整的可视化操作能力，供专家验收。

## What Changes
- 实现 **RPKI 管理页面**（`/rpki`）：TAL 列表、VRP 查询、RPKI 健康摘要、手动触发同步
- 实现 **BGP 监测页面**（`/bgp`）：BGP 数据源列表、观察点、最近公告（含 RPKI 验证状态分布）、撤路记录
- 实现 **ROA 管理页面**（`/roa`）：ROA 列表、覆盖率统计、缺失/冲突检测、maxLength 风险检查
- 实现 **告警事件页面**（`/alerts`）：检测规则列表、告警列表（含状态过滤/分派/处置）、事件列表（含关闭/详情跳转）
- 实现 **系统设置页面**（`/settings`）：用户管理、租户管理、API Key 管理、审计日志查询（Tab 切换）
- 移除 `App.tsx` 中的 `PlaceholderPage` 组件及其路由
- 新增对应 API 客户端模块：`src/api/rpki.ts`、`src/api/bgp.ts`、`src/api/roas.ts`、`src/api/detection.ts`、`src/api/settings.ts`

## Impact
- Affected specs: `build-rpki-platform`（前端模块补全）
- Affected code:
  - 前端：`frontend/src/App.tsx`、`frontend/src/pages/{Rpki,Bgp,Roas,Alerts,Settings}/index.tsx`、`frontend/src/api/*.ts`
  - 后端：无改动（仅消费已有 API）

## ADDED Requirements

### Requirement: RPKI 管理页面
系统 SHALL 提供 RPKI 管理页面，展示 TAL 列表（名称、URI、状态、同步状态）、VRP 总数、RPKI 健康摘要，并支持手动触发同步。

#### Scenario: 查看 RPKI 管理页面
- **WHEN** 用户访问 `/rpki`
- **THEN** 显示 TAL 列表、VRP 统计、健康摘要卡片

#### Scenario: 手动触发同步
- **WHEN** 用户点击"触发同步"按钮
- **THEN** 调用 `POST /rpki/sync` 并刷新状态

### Requirement: BGP 监测页面
系统 SHALL 提供 BGP 监测页面，展示数据源、观察点、最近 BGP 公告（含 RPKI 验证状态）、撤路记录。

#### Scenario: 查看 BGP 监测页面
- **WHEN** 用户访问 `/bgp`
- **THEN** 显示数据源列表、最近公告表格（含验证状态标签）、撤路记录

### Requirement: ROA 管理页面
系统 SHALL 提供 ROA 管理页面，展示 ROA 列表、覆盖率统计、缺失/冲突检测结果。

#### Scenario: 查看 ROA 管理页面
- **WHEN** 用户访问 `/roa`
- **THEN** 显示覆盖率卡片、ROA 列表表格、缺失检测与冲突检测结果

### Requirement: 告警事件页面
系统 SHALL 提供告警事件页面，展示检测规则、告警列表（支持状态过滤与分派）、事件列表（支持关闭与详情跳转）。

#### Scenario: 查看告警事件页面
- **WHEN** 用户访问 `/alerts`
- **THEN** 显示 Tab 切换：检测规则 / 告警 / 事件

#### Scenario: 跳转事件详情
- **WHEN** 用户点击事件行
- **THEN** 跳转到 `/incidents/:id` 详情页

### Requirement: 系统设置页面
系统 SHALL 提供系统设置页面，以 Tab 形式展示用户管理、租户管理、API Key 管理、审计日志。

#### Scenario: 查看系统设置页面
- **WHEN** 用户访问 `/settings`
- **THEN** 显示 4 个 Tab：用户 / 租户 / API Key / 审计日志

## MODIFIED Requirements

### Requirement: 前端路由
`App.tsx` 中 5 个占位路由 SHALL 替换为真实页面组件，并移除 `PlaceholderPage` 组件定义。
