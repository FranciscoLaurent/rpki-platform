# Tasks

## 阶段 1：API 客户端层

- [x] Task 1: 创建 5 个业务模块的 API 客户端
  - [x] SubTask 1.1: 创建 `src/api/rpki.ts`（TAL 列表、VRP 查询、健康摘要、触发同步）
  - [x] SubTask 1.2: 创建 `src/api/bgp.ts`（数据源、观察点、公告、撤路）
  - [x] SubTask 1.3: 创建 `src/api/roas.ts`（ROA 列表、覆盖率、缺失/冲突检测）
  - [x] SubTask 1.4: 创建 `src/api/detection.ts`（规则、告警、事件）
  - [x] SubTask 1.5: 创建 `src/api/settings.ts`（用户、租户、API Key、审计日志）

## 阶段 2：业务页面实现

- [x] Task 2: 实现 RPKI 管理页面（`pages/Rpki/index.tsx`）
  - [x] SubTask 2.1: TAL 列表卡片（名称、URI、状态、同步状态）
  - [x] SubTask 2.2: VRP 统计与健康摘要卡片
  - [x] SubTask 2.3: 触发同步按钮与刷新

- [x] Task 3: 实现 BGP 监测页面（`pages/Bgp/index.tsx`）
  - [x] SubTask 3.1: 数据源列表表格
  - [x] SubTask 3.2: 最近 BGP 公告表格（含 RPKI 验证状态标签）
  - [x] SubTask 3.3: 撤路记录表格

- [x] Task 4: 实现 ROA 管理页面（`pages/Roas/index.tsx`）
  - [x] SubTask 4.1: 覆盖率统计卡片
  - [x] SubTask 4.2: ROA 列表表格（前缀、起源 AS、maxLength、状态、TAL）
  - [x] SubTask 4.3: 缺失检测与冲突检测结果展示

- [x] Task 5: 实现告警事件页面（`pages/Alerts/index.tsx`）
  - [x] SubTask 5.1: Tab 切换：检测规则 / 告警 / 事件
  - [x] SubTask 5.2: 检测规则列表表格（名称、类型、严重等级、启用状态）
  - [x] SubTask 5.3: 告警列表表格（支持状态过滤、分派操作）
  - [x] SubTask 5.4: 事件列表表格（点击跳转 `/incidents/:id`）

- [x] Task 6: 实现系统设置页面（`pages/Settings/index.tsx`）
  - [x] SubTask 6.1: Tab 切换：用户 / 租户 / API Key / 审计日志
  - [x] SubTask 6.2: 用户管理表格
  - [x] SubTask 6.3: 租户管理表格
  - [x] SubTask 6.4: API Key 管理表格
  - [x] SubTask 6.5: 审计日志查询表格

## 阶段 3：路由集成与清理

- [x] Task 7: 更新 `App.tsx` 路由与清理占位组件
  - [x] SubTask 7.1: 替换 5 个占位路由为真实页面组件
  - [x] SubTask 7.2: 移除 `PlaceholderPage` 组件定义
  - [x] SubTask 7.3: 更新 `Layout` 侧边栏菜单（确保图标与页面匹配）

## 阶段 4：验证

- [x] Task 8: 端到端验证
  - [x] SubTask 8.1: 5 个页面均可访问且无白屏
  - [x] SubTask 8.2: 各页面 API 调用成功（无 500 错误）
  - [x] SubTask 8.3: 浏览器控制台无致命错误（antd 弃用警告可接受）

# Task Dependencies
- Task 2-6 依赖 Task 1（API 客户端）
- Task 7 依赖 Task 2-6（页面实现完成）
- Task 8 依赖 Task 7
- Task 2、3、4、5、6 之间无依赖，可并行
