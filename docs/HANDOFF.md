# 钞·作业项目交接手册

最后更新：2026-08-07
交接基线：`main`
线上地址：https://simonlichaooooo.github.io/stock-pool-codex/

## 1. 当前状态

项目是已上线的静态单页私人股票研究与组合管理工具。股池、组合管理、市场洞察、日志和四套主题均已投入使用。

产品规则见 [`PRD.md`](./PRD.md)，组合细则见 [`PORTFOLIO_MANAGEMENT.md`](./PORTFOLIO_MANAGEMENT.md)，技术边界见 [`ARCHITECTURE.md`](./ARCHITECTURE.md)。

## 2. 仓库地图

| 路径 | 作用 |
| --- | --- |
| `index.html` | 全部前端结构、样式、状态、业务逻辑和 REST 调用 |
| `data/market-insights.json` | 恒生科技指数成分、空头和港股通公开快照 |
| `scripts/update-market-insights.mjs` | 更新香港证监会空头快照 |
| `.github/workflows/update-market-insights.yml` | 周五 18:00 检查证监会最新 CSV 并提交前端快照 |
| `scripts/market-data-ingest.py` | HSCI、空头与港股通历史数据回填和日常更新 |
| `.github/workflows/update-market-data-history.yml` | 空头周度、港股通日度数据库计划 |
| `logo/` | Logo 和透明素材 |
| `supabase/schema.sql` | 基础数据库结构 |
| `supabase/portfolio-management.sql` | 组合表和权限 |
| `supabase/portfolio-nav.sql` | 现金流、净值和基准数据 |
| `supabase/portfolio-nav-schedule.sql` | pg_cron / pg_net 调度模板 |
| `supabase/market-data-history.sql` | 市场历史数据表、RLS、索引和 HSCI 视图 |
| `supabase/functions/daily-portfolio-nav/index.ts` | 日终净值 Edge Function |
| `supabase/journal-entries.sql` | 日志表 |
| `supabase/profiles.sql` | 私人用户资料表和权限 |
| `supabase/remove-social-sharing.sql` | 一次性移除旧分享、订阅、广场和后台数据库对象 |
| `docs/` | 当前需求、架构与交接文档 |

## 3. 本地开发

```bash
python3 -m http.server 8765
```

- 普通页面：`http://127.0.0.1:8765/index.html`
- 组合演示：`http://127.0.0.1:8765/index.html?portfolio-demo`
- 市场洞察演示：`http://127.0.0.1:8765/index.html?market-insight-demo`
- 演示模式使用 Local Storage，不写生产数据库。

修改前先检查工作区和最新提交，避免覆盖其他对话正在进行的变更。

## 4. 开发约束

- position `id` 是持仓真实标识，`code + market` 只用于旧数据兼容。
- `tradePlan.buy[]` 和 `sell[]` 为动态长度，不得固定遍历 3 行。
- 编辑弹窗新增计划行采用局部追加，避免整页重绘丢失未保存输入。
- 估值版本来自同股票、同市场的 `state.stocks`。
- 行情和汇率是异步数据，金额计算必须有空值与回退处理。
- 登录回跳、RLS、估值计算和组合份额逻辑属于高风险区域。
- 同时开发时尽量按模块串行合入 `index.html`，每次合入后做跨模块回归。

## 5. 发布流程

### 前端

1. 检查 JavaScript 语法和差异格式。
2. 本地验证主路径和组合演示模式。
3. 提交并推送 `main`。
4. 等待 GitHub Pages 发布。
5. 打开线上页面做登录前烟雾检查；涉及账户数据的改动再做登录后验证。

### Supabase

1. 先审阅 SQL、RLS 和数据兼容影响。
2. 在生产控制台执行所需迁移。
3. Edge Function 变更独立部署并检查 secrets。
4. 手工验证请求和写表结果。
5. 数据库与定时任务变更必须记录执行时间和结果。

市场历史数据首次部署与回填见 [`MARKET_DATA_OPERATIONS.md`](./MARKET_DATA_OPERATIONS.md)。

已有生产密钥和调度不应在无备份时重建。

### 旧社交模块退场（一次性）

1. 先确认包含本次精简的前端已经发布，避免旧页面继续请求即将删除的表和字段。
2. 在 Supabase Dashboard 打开 **SQL Editor**，新建查询。
3. 完整复制并运行 [`../supabase/remove-social-sharing.sql`](../supabase/remove-social-sharing.sql)。
4. 成功结果应包含 `social sharing removal ok`。脚本会把既有复制/订阅股票保留为普通私人股票，再删除发布、关注、订阅、治理表及相关字段和 RLS。
5. 刷新线上页面，验证登录、股池读取、编辑、保存和删除；随后可在 Table Editor 确认旧社交表已不存在。

该脚本会永久删除历史发布快照、关注关系和治理日志。需要留档时，应先在 Supabase 导出对应表。

## 6. 发布前回归

- [ ] 登录、会话恢复、退出和顶部导航。
- [ ] 股池列表、搜索、估值编辑和保存。
- [ ] 组合切换、开仓、加仓、减持和调仓。
- [ ] 市场洞察成分数量、周线指标、数据日期、缺失值和来源链接。
- [ ] 申购、赎回、现金校准、份额和净值。
- [ ] 持仓估值联动、动态买卖点、提醒和保存。
- [ ] 日志、股票提及和筛选。
- [ ] 隐私模式、四套主题、桌面和窄屏布局。
- [ ] 线上静态资源、控制台和关键接口无新增错误。

## 7. 故障定位

- 页面完全异常：先检查浏览器控制台的 JavaScript 语法错误。
- 数据为空或保存失败：检查会话、REST 响应和 RLS。
- 行情或市值为空：检查 `quoteId` 推导、外部接口和降级路径。
- 市场洞察空头为空：检查两个 market data workflow、Actions secrets 和 `market_data_ingestion_runs`；港股通最近日期为空时先等回看任务补齐，不要填零。
- 组合数字异常：依次核对币种、汇率、现金、持仓市值和 `totalUnits`。
- 净值未更新：检查 cron、Edge Function 日志、secrets 和三张净值表。
- 发布后未变化：确认 `main` 已推送、Pages workflow 完成并排除缓存。

## 8. 已知技术债务

- 单文件过大，缺少清晰模块边界。
- 无自动化测试和 CI 回归。
- 外部行情和汇率可能超时或缺数。
- JSONB payload 缺少版本化迁移。
- 交易费用、分红、利息、换汇和现金校准缺少完整审计流水。
- 净值任务缺少自动历史回填与失败告警。

## 9. 接手优先级

### P0 稳定性

- 为净值、份额、摊薄成本、外汇和计划反算补单元测试。
- 为交易、动态计划保存和登录补浏览器回归。
- 为 Pages 发布增加最小烟雾测试。

### P1 可维护性

- 拆分 `index.html`。
- 引入 payload schema version 和迁移函数。
- 建立交易和资金审计流水。
- 增加日终任务监控与失败告警。

### P2 产品能力

- 动态买卖点删除、排序和批量完成。
- 费用、分红、利息和换汇流水。
- 券商导入和组合业绩归因。

## 10. 交付检查

- [ ] 工作区没有意外暂存或未跟踪文件。
- [ ] 文档与当前代码、SQL 和线上行为一致。
- [ ] 不包含后台密钥、Token 或用户私密数据。
- [ ] 提交信息说明业务影响和验证范围。
- [ ] 推送后确认 GitHub Pages 状态。
