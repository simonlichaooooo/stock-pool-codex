# 钞·作业系统架构

最后更新：2026-07-18
代码基线：`main@d57d6cc`

## 1. 架构概览

```text
浏览器单页应用（index.html）
├─ Supabase Auth：GitHub OAuth / Email Magic Link
├─ Supabase REST：业务数据与 RLS
├─ Supabase Edge Function：日终组合净值
├─ GitHub Pages：静态前端发布
└─ 外部数据：东方财富、腾讯、Open ER API
```

前端使用原生 HTML、CSS 和 JavaScript，无框架、打包器和构建步骤。全部页面结构、状态、业务逻辑和接口调用集中在 `index.html`。

## 2. 前端运行模型

- 全局 `state` 保存会话、股池、组合、日志、广场和弹窗状态。
- `init()` 初始化主题、会话、档案、业务数据和自动刷新。
- `render()` 根据 state 重建界面。
- `bindEvents()` 在渲染后重新绑定事件。
- `supabaseRequest()` 访问 Supabase REST API。
- Local Storage 保存主题、部分偏好和演示数据。

组合关键入口：

- `renderPortfolioView()` / `renderPositionModal()`
- `updateActivePortfolio()`
- `portfolioMetrics()` / `positionBaseValue()`
- `refreshPortfolioQuotes()` / `refreshMarketCaps()`
- `positionPlanValuation()` / `positionPlanPriceFromMetric()`

## 3. 数据域

| 数据域 | 主要存储 | 说明 |
| --- | --- | --- |
| 用户 | `profiles` | 昵称、账户信息和可见性 |
| 股池 | `stock_records` | 私有股票与估值 payload |
| 发布 | `stock_publications` | 公开版本快照 |
| 社交 | `follows`、订阅相关表 | 关注、复制和订阅关系 |
| 日志 | `journal_entries` | 私有研究日志 |
| 组合 | `portfolios` | 组合主体和嵌套 payload |
| 净值 | `portfolio_cash_flows`、`portfolio_daily_nav` | 外部现金流和日终净值 |
| 基准 | `benchmark_daily_close` | 指数收盘价 |

股池与组合主体使用 JSONB payload，便于单文件前端快速迭代，但缺少强 schema 约束。新增字段必须兼容旧 payload，并优先提供默认值或迁移函数。

组合结构摘要：

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

## 4. 认证、权限与公开内容

- Supabase Auth 支持 GitHub OAuth 和 Email Magic Link。
- 登录后使用用户 JWT 请求 REST API。
- 业务表通过 RLS 隔离用户数据。
- 公开发布使用独立记录，不直接开放私有草稿。
- 前端可以包含 anon key，不得包含 `service_role` 或 `CRON_SECRET`。
- 管理员能力必须由后台权限与 RLS 共同约束。

## 5. 外部数据与降级

- 股票搜索：东方财富、腾讯，本地目录兜底。
- 行情：东方财富与腾讯互为备用。
- 汇率：Open ER API。
- 行情失败时持仓价格按最近价、摊薄成本顺序回退。
- 旧记录缺少 `quoteId` 时，根据市场和代码推导行情标识。
- 外部数据均可能超时、限流或缺数，UI 必须允许空值并显示刷新状态。

## 6. 日终净值链路

```text
pg_cron / pg_net
  → daily-portfolio-nav Edge Function
  → 行情与汇率
  → portfolio_daily_nav
  → benchmark_daily_close
  → 前端净值曲线
```

现金流通过份额机制隔离投资收益。部署和验证步骤见 [`PORTFOLIO_MANAGEMENT.md`](./PORTFOLIO_MANAGEMENT.md)。

## 7. 部署

- 前端生产分支为 `main`，推送后由 GitHub Pages 发布。
- 数据库结构和 RLS 位于 `supabase/*.sql`。
- Edge Function 位于 `supabase/functions/`。
- 前端发布与数据库变更是两条独立链路；SQL 和密钥配置不会因推送前端自动生效。

## 8. 关键风险

1. `index.html` 超过一万行，是最大的维护风险。
2. 多对话或多分支同时修改单文件，可能没有 Git 文本冲突但产生语义冲突。
3. 缺少自动化测试和 CI，金融计算主要依赖人工回归。
4. JSONB payload 没有正式 schema version，历史数据兼容依赖代码兜底。
5. 外部行情、汇率和市值服务不可控。

## 9. 演进方向

- 将样式、数据访问、股池、组合、日志和广场拆为 ES Modules。
- 为 payload 增加 schema version、校验和迁移。
- 把交易、现金校准、换汇等迁移到可审计流水表。
- 为份额、净值、摊薄成本、外汇和估值反算增加单元测试。
- 增加浏览器回归、GitHub Pages 烟雾测试和日终任务告警。
