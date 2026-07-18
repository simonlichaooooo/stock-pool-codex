# 钞·作业项目 Handoff（当前基线）

最后更新：2026-07-18  
代码基线：`main@0870a73`  
线上地址：https://simonlichaooooo.github.io/stock-pool-codex/

## 1. 项目现状

项目是静态单页股票研究与组合管理工具。前端为原生 HTML / CSS / JavaScript，后端使用 Supabase Auth、Postgres、RLS、Edge Functions 和 pg_cron，前端由 GitHub Pages 发布。

已上线模块：

- 股池：多版本估值、行情、发布、共享和订阅。
- 组合管理：多组合、持仓、现金、份额、交易、标签、动态买卖点和净值。
- 日志：日志编辑、股票提及和筛选。
- 广场：公开发布者和共享股池。
- 管理后台：用户、股票和内容治理。
- 主题：冰川蓝、星云紫、翡翠绿、琥珀暖色。

## 2. 仓库地图

| 路径 | 作用 |
| --- | --- |
| `index.html` | 全部前端结构、样式、状态、业务逻辑和 REST 调用 |
| `logo/` | Logo 和透明素材 |
| `supabase/schema.sql` | 基础数据库结构 |
| `supabase/portfolio-management.sql` | 组合表和权限 |
| `supabase/portfolio-nav.sql` | 现金流、净值和基准数据 |
| `supabase/portfolio-nav-schedule.sql` | pg_cron / pg_net 调度模板 |
| `supabase/functions/daily-portfolio-nav/index.ts` | 日终净值 Edge Function |
| `supabase/journal-entries.sql` | 日志表 |
| `supabase/social-sharing.sql` | 发布、关注和共享数据 |
| `docs/PORTFOLIO_MANAGEMENT_PRD_CURRENT.md` | 当前组合需求基线 |
| `docs/PROJECT_HANDOFF_CURRENT.md` | 当前工程交接基线 |

## 3. 前端架构

- 无前端框架和构建步骤。
- 全局 `state` 管理登录、股池、组合、日志、广场和弹窗。
- `render()` 重新生成界面，`bindEvents()` 每次渲染后重新绑定。
- `supabaseRequest()` 直接访问 Supabase REST API。
- `init()` 负责主题、会话、档案、数据和自动刷新初始化。

主要组合入口：

- `renderPortfolioView()` / `renderPositionModal()`
- `updateActivePortfolio()`
- `portfolioMetrics()` / `positionBaseValue()`
- `refreshPortfolioQuotes()` / `refreshMarketCaps()`
- `positionPlanValuation()` / `positionPlanPriceFromMetric()`

`index.html` 已超过一万行，是当前最大技术风险。两个对话或分支同时修改该文件时很容易出现语义冲突，即使 Git 没有文本冲突。

## 4. 数据模型

### 4.1 股池

`stock_records.payload` 保存股票、版本、估值假设、备注和来源数据。`latestMarketCapCny` 是运行时数据；旧记录缺失 `quoteId` 时会根据市场和代码推导行情标识。

### 4.2 组合

```text
portfolio
├─ id / name / accountType
├─ startCny / startHkd / startUsd / startBase / totalUnits
├─ cash { CNY, HKD, USD }
├─ positions[]
│  ├─ id / code / market / currency
│  ├─ shares / averageCost / latestPrice
│  ├─ targetWeight / tags[] / valuationStockId
│  └─ tradePlan { buy[], sell[] }
├─ tagTargets
├─ tradeHistory[]
└─ cashFlows[]
```

`tradePlan.buy[]` 和 `sell[]` 是动态长度，新代码不得假设永远只有 3 行。

### 4.3 其他表

- `profiles`：用户档案和可见性。
- `stock_publications`：发布版本。
- `follows`：关注关系。
- `journal_entries`：日志。
- `portfolio_cash_flows`：申购赎回。
- `portfolio_daily_nav`：日终净值。
- `benchmark_daily_close`：基准收盘价。

## 5. 认证和安全

- Supabase Auth 支持 GitHub OAuth 和邮箱 Magic Link。
- 业务表使用 RLS 隔离用户数据。
- 前端可包含 anon key，不得包含 `service_role` 或 `CRON_SECRET`。
- 顶部邮箱脱敏展示；组合隐私模式属于展示层隐藏。

## 6. 外部数据

- 股票搜索：东方财富、腾讯，本地目录兜底。
- 行情：东方财富和腾讯互为备用。
- 汇率：Open ER API。
- 行情失败时持仓价格按“最近价 → 摊薄成本”回退。

## 7. 组合开发注意事项

- position `id` 是持仓真实标识，`code + market` 只用于兼容。
- 估值版本来自同股票、同市场的 `state.stocks`。
- 动态计划的渲染、保存、提醒和完成状态必须遍历实际数组长度。
- 编辑弹窗新增计划行使用 DOM 局部追加，避免整页重绘丢失未保存输入。
- 行情和汇率为异步数据，金额计算必须有兜底。

## 8. 部署

### 前端

- 生产分支：`main`。
- 推送后由 GitHub Pages 发布。
- 发布通常需数分钟刷新缓存。

### 后台

净值 Edge Function 和定时任务见 `docs/PORTFOLIO_NAV_DEPLOYMENT.md`。已有生产密钥和调度不应在无备份时重建。

## 9. 本地开发

```bash
python3 -m http.server 8765
```

- 普通页：`http://127.0.0.1:8765/index.html`
- 组合演示：`http://127.0.0.1:8765/index.html?portfolio-demo`

演示模式使用 Local Storage，不写入生产数库。

## 10. 发布前回归

1. JavaScript 语法和 `git diff --check`。
2. 登录、主导航和主题。
3. 股池列表、编辑抽屉和估值。
4. 组合切换、开仓、加仓、减持和调仓。
5. 持仓估值联动、动态买卖点和保存。
6. 申购赎回、净值和基准数据。
7. 日志、广场和管理后台基本导航。
8. 桌面和窄屏布局。

## 11. 已知限制

- 单文件过大，缺少模块边界。
- 无自动化测试和 CI 回归。
- 外部行情和汇率可能超时或缺数。
- 交易未建模佣金、税费、分红、利息和换汇。
- 现金校准无独立审计流水。
- 净值无自动历史回填。
- 动态买卖点尚无单行删除和排序。
- 组合不支持对外公开分享。

## 12. 建议后续工作

### P0

- 为净值、份额、摊薄成本、外汇和计划反算增加单元测试。
- 为交易和动态计划保存增加浏览器回归。
- 为 GitHub Pages 发布增加最低烟雾测试。

### P1

- 将 `index.html` 拆分为 ES Modules。
- 为 payload 增加 schema version 和迁移函数。
- 将交易、校准和换汇逐步迁移为独立流水表。
- 补充日终任务监控和失败告警。

### P2

- 买卖点删除、排序和批量完成。
- 费用、分红、利息和换汇流水。
- 券商导入或只读同步。
- 组合分享和业绩归因。

## 13. 发布检查

- [ ] 没有意外暂存或未跟踪文件。
- [ ] 语法检查和差异检查通过。
- [ ] `portfolio-demo` 关键流程通过。
- [ ] 不包含后台密钥或用户私密数据。
- [ ] 推送 `main` 后验证 GitHub Pages 更新。
