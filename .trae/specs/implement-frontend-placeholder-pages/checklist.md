# Checklist

## API 客户端层
- [x] `src/api/rpki.ts` 已创建，导出 TAL/VRP/健康/同步相关函数
- [x] `src/api/bgp.ts` 已创建，导出数据源/观察点/公告/撤路相关函数
- [x] `src/api/roas.ts` 已创建，导出 ROA 列表/覆盖率/缺失/冲突检测函数
- [x] `src/api/detection.ts` 已创建，导出规则/告警/事件相关函数
- [x] `src/api/settings.ts` 已创建，导出用户/租户/API Key/审计日志函数

## RPKI 管理页面
- [x] `pages/Rpki/index.tsx` 已创建
- [x] 展示 TAL 列表（名称、URI、状态、同步状态）
- [x] 展示 VRP 统计与健康摘要
- [x] 支持触发同步按钮

## BGP 监测页面
- [x] `pages/Bgp/index.tsx` 已创建
- [x] 展示数据源列表
- [x] 展示最近 BGP 公告（含 RPKI 验证状态标签）
- [x] 展示撤路记录

## ROA 管理页面
- [x] `pages/Roas/index.tsx` 已创建
- [x] 展示覆盖率统计卡片
- [x] 展示 ROA 列表表格
- [x] 展示缺失/冲突检测结果

## 告警事件页面
- [x] `pages/Alerts/index.tsx` 已创建
- [x] Tab 切换：检测规则 / 告警 / 事件
- [x] 检测规则列表正常显示
- [x] 告警列表支持状态过滤
- [x] 事件列表点击可跳转 `/incidents/:id`

## 系统设置页面
- [x] `pages/Settings/index.tsx` 已创建
- [x] Tab 切换：用户 / 租户 / API Key / 审计日志
- [x] 4 个子表格均能正常加载数据

## 路由集成
- [x] `App.tsx` 中 5 个占位路由已替换为真实页面
- [x] `PlaceholderPage` 组件已移除
- [x] 侧边栏菜单图标与页面匹配

## 端到端验证
- [x] 5 个页面均可访问且无白屏
- [x] 各页面 API 调用成功（无 500 错误）
- [x] 浏览器控制台无致命错误
