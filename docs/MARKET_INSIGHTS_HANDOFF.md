# 市场洞察 Handoff

- 文档版本：1.0
- 最后更新：2026-08-09
用途：市场洞察开发、数据回填、发布和故障处理的单一交接入口

## 1. 当前状态

### 1.1 已上线

- 四指数切换：恒生科技、大型股、中型股、小型股。
- 成分股搜索、全量排序、每页 50 只分页。
- 5 周超额收益、5/30/40/50 周乖离率和近 2 年分位值。
- SFC 空头持仓比例、HKEX 官方聚合港股通持仓比例。
- 3/4/5 星筛选和单项提示星。
- 详情页 2 年/1 年/今年以来三张走势图。
- 周线指标、空头、港股通和官方历史股本持久化。
- 定时更新、历史分批回填、定向修复和小批量比例刷新任务。

### 1.2 正在进行

- 官方历史股本按 2026、2025、2024、2023 年分批回填。2026 年已完成，其他年份以 Actions 和覆盖率查询的实际结果为准。
- 回填结束后需要修复警告公告，再统一刷新空头及港股通比例。

### 1.3 已确认的数据边界

- 港股通生产历史从 2025-08-11 开始，来源为港交所官方聚合数据。
- 2023—2024 年旧的单通道 `partial_sz` 数据属于不完整历史，已归档，不用于页面、比例或评星。
- SFC 数据是“达到申报门槛的合计淡仓”，股票缺席不等于空头为零。
- 官方股本只接受通过校验的港交所月报表和翌日披露报表；低质量数据不得覆盖高优先级官方数据。

## 2. 系统结构

```text
恒指公司公开资料 ───────────────┐
腾讯/东方财富周线 ──────────────┼─> GitHub Actions / Python ─> Supabase ─> index.html
SFC 周度空头 ──────────────────┤
HKEX 南向官方聚合持仓 ──────────┤
HKEX 月报表/翌日披露 PDF ───────┘

data/market-insights.json ─> 成分、权重/顺序、公开快照降级数据
Supabase                ─> 周线指标、持仓历史、官方股本和比例
```

浏览器优先读取数据库持久化指标，静态 JSON 用于成分和上一版公开快照降级。Service Role Key 只存在 GitHub Actions。

## 3. 关键文件

| 文件 | 职责 |
| --- | --- |
| [`../index.html`](../index.html) | 市场洞察列表、搜索、星级、图表和 Supabase 读取 |
| [`../data/market-insights.json`](../data/market-insights.json) | 四指数成分、公开权重/顺序和静态快照 |
| [`../scripts/update-market-insights.mjs`](../scripts/update-market-insights.mjs) | 更新静态市场洞察快照 |
| [`../scripts/market-data-ingest.py`](../scripts/market-data-ingest.py) | 成分、SFC、港股通、周线指标采集与持久化 |
| [`../scripts/hkex-share-capital.py`](../scripts/hkex-share-capital.py) | 港交所股本公告检索、PDF 解析、校验和比例刷新 |
| [`../supabase/market-data-history.sql`](../supabase/market-data-history.sql) | 历史数据基础表、视图、RLS |
| [`../supabase/market-insight-metrics.sql`](../supabase/market-insight-metrics.sql) | 周线指标表和当前指标视图 |
| [`../supabase/hkex-official-share-capital.sql`](../supabase/hkex-official-share-capital.sql) | 官方历史股本表、优先级、覆盖率及比例刷新函数 |
| [`../supabase/stock-connect-official-aggregate.sql`](../supabase/stock-connect-official-aggregate.sql) | 港股通官方聚合约束和旧数据归档 |
| [`../.github/workflows/update-market-data-history.yml`](../.github/workflows/update-market-data-history.yml) | 日常历史数据计划任务和手动回填入口 |
| [`../.github/workflows/update-market-insights.yml`](../.github/workflows/update-market-insights.yml) | 静态快照周度更新并提交 |
| [`../.github/workflows/backfill-hkex-share-capital.yml`](../.github/workflows/backfill-hkex-share-capital.yml) | 官方股本按年份、50 股票一批回填 |
| [`../.github/workflows/repair-hkex-share-capital.yml`](../.github/workflows/repair-hkex-share-capital.yml) | 指定股票和日期修复公告 |
| [`../.github/workflows/backfill-stock-connect-official.yml`](../.github/workflows/backfill-stock-connect-official.yml) | 港股通免费窗口历史回填 |
| [`../.github/workflows/refresh-holding-ratios.yml`](../.github/workflows/refresh-holding-ratios.yml) | 小批量刷新空头和港股通比例 |

## 4. 数据库模型

| 对象 | 主键/粒度 | 说明 |
| --- | --- | --- |
| `market_securities` | 股票代码 | 港股证券主数据和简体名称 |
| `market_index_constituents` | 指数、股票、生效日 | 历史成分关系 |
| `hk_market_insight_metrics_weekly` | 指数、股票、周 | 乖离率、分位值、5 周收益和超额收益 |
| `hk_short_positions_weekly` | 股票、报告日 | SFC 空头股数、历史股本、比例和质量 |
| `hk_stock_connect_holdings_daily` | 股票、持仓日 | 官方南向持股数、历史股本、比例和完整性 |
| `hkex_share_capital_filings` | 公告编号 | 公告检索、解析状态、错误和源链接 |
| `hk_issued_shares_official` | 股票、生效日、股份类别 | 官方已发行股本、库存股、有效分母和优先级 |
| `market_data_ingestion_runs` | 任务运行 | 数据集、时间、状态、行数和错误摘要 |
| `hk_stock_connect_holdings_legacy_archive` | 旧记录 | 已退出生产的单通道/旧版港股通记录 |

常用视图：

- `current_hk_market_insight_metrics`：每个指数成分的最新周线指标。
- `current_market_index_constituents`：当前成分。
- `hk_official_share_capital_coverage`：官方股本覆盖情况。

## 5. 数据质量规则

### 5.1 官方股本

- `hkex_next_day_disclosure` 优先级 100，高于 `hkex_monthly_return` 的 80。
- 高优先级记录不得被低优先级 upsert 覆盖。
- `effective_issued_shares = issued_shares - treasury_shares`。
- 月报表股数加库存股与总数不一致、翌日披露找不到期末结余、找不到发行股本区块时，记录失败/警告，不写入错误官方分母。
- H 股只使用对应香港上市股份类别；REIT 使用上市单位；双柜台不重复计算。

### 5.2 比例质量

- `official`：分母来自官方历史股本。
- `licensed_vendor`：兼容旧供应商/兜底数据，不得覆盖官方。
- `missing_denominator`：分子存在但历史分母缺失，比例必须为空。

### 5.3 港股通完整性

- 当前生产记录必须为 `official_aggregate`。
- `partial_sh`、`partial_sz` 不参与生产；`complete` 只保留兼容语义。
- 官方聚合记录只有 `total_holding_shares`，沪/深子字段为空是正常的。

## 6. 自动任务

GitHub Actions cron 使用 UTC，以下均已换算为香港时间：

| 任务 | 时间 | 内容 |
| --- | --- | --- |
| Update market insights | 周五 18:00 | 更新静态成分/公开快照并提交 JSON |
| Update market data history | 周五 18:00 | 同步成分、更新 SFC、回看 70 天官方股本 |
| Update market data history | 工作日 20:00 | 港股通回看最近 10 天，覆盖节假日和迟到数据 |
| Update market data history | 周五 19:00 | 计算并持久化周线指标 |

注意：同一个 `Update market data history` 使用 concurrency group 串行执行，不取消在途任务。

## 7. 首次部署与 SQL 顺序

新 Supabase 项目按以下顺序执行完整文件：

1. `supabase/market-data-history.sql`
2. `supabase/market-insight-metrics.sql`
3. `supabase/hkex-official-share-capital.sql`
4. `supabase/stock-connect-official-aggregate.sql`

配置 GitHub Actions Secrets：

- `SUPABASE_URL`：Supabase Project URL，例如 `https://<project-ref>.supabase.co`。
- `SUPABASE_SERVICE_ROLE_KEY`：Project Settings → API Keys 中的 Secret/Service Role Key。

不得把 Service Role Key 写入仓库或浏览器代码。

## 8. 当前历史回填收尾流程

这一节替代聊天记录，按顺序执行。

### 阶段 A：完成官方股本年度回填

在 Actions 运行 `Backfill official HKEX share capital`，一次选择一个年份：

1. 2026（已完成）
2. 2025
3. 2024
4. 2023

单个年份内部由 11 个矩阵批次处理，每批最多 50 只股票，最多并行 2 个。不同年份不要并行，避免港交所请求压力和 Supabase 写入/比例刷新争用。

矩阵批次末尾若旧版本仍因 `refresh_hk_holding_ratios` statement timeout 显示失败，只要公告采集已完成，数据通常已入库；不要因此重跑整个年份。统一在阶段 C 使用专用小批量刷新任务。

### 阶段 B：修复公告警告

汇总年度日志中的：

- `issued-shares section not found`
- `next-day closing balance not found`
- `invalid share totals`

在解析器已支持相应版式后，运行 `Repair official HKEX share capital`，输入股票代码和日期范围。已知需要重点复核的代码包括 `00151`、`01478`、`02400`、`09890`、`09896`，但应以最新日志和覆盖率为准。

修复原则：先验证公告真实股数和股份类别，再改解析器；禁止仅为消除警告而跳过算术校验。

### 阶段 C：统一刷新比例

所有年份采集和定向修复结束后，运行：

`Refresh market holding ratios`

该任务按 10 只股票一组调用数据库函数，避免整表刷新触发 Supabase statement timeout。日志中 `short_updated` 应有正数；`connect_updated` 是否为正取决于该组股票是否同时存在 2025-08-11 之后港股通分子和官方历史股本。

### 阶段 D：最终核验

执行第 10 节 SQL。覆盖率未达到目标时，只修复缺失股票/公告，不重跑已经成功的全年任务。

## 9. 港股通回填流程

基础 SQL `stock-connect-official-aggregate.sql` 必须先执行一次；随后运行 `Backfill official Stock Connect holdings`：

- `start_date` 使用 `2025-08-11`。
- `end_date` 留空代表今天。
- 日志 `(115/260)` 表示已处理第 115 个交易日，共识别 260 个有效交易日。
- `874 rows` 表示该交易日港交所返回 874 只证券记录，不是 874 个交易日。
- 任务结束后会尝试刷新比例；若旧任务因整表刷新超时，改运行 `Refresh market holding ratios`。

港交所免费在线查询通常只覆盖近 12 个月。不要反复请求窗口外日期；补齐更早完整历史需要付费官方数据或持牌供应商。

## 10. 核验 SQL

### 10.1 四指数周线指标覆盖

```sql
select
  index_code,
  count(*) as row_count,
  count(distinct stock_code) as stock_count,
  min(week_date) as first_week,
  max(week_date) as latest_week
from public.hk_market_insight_metrics_weekly
where index_code in ('HSTECH', 'HSLI', 'HSMI', 'HSSI')
group by index_code
order by index_code;
```

检查 `latest_week` 不得晚于真实当前交易周。若出现未来日期，先检查行情源和任务运行日期，禁止直接展示。

### 10.2 官方股本覆盖

```sql
select *
from public.hk_official_share_capital_coverage
order by stock_code;
```

按年份汇总：

```sql
select
  extract(year from effective_date)::int as year,
  count(*) as official_rows,
  count(distinct stock_code) as stock_count,
  count(*) filter (where source_type = 'hkex_next_day_disclosure') as next_day_rows,
  count(*) filter (where source_type = 'hkex_monthly_return') as monthly_rows
from public.hk_issued_shares_official
group by 1
order by 1;
```

### 10.3 公告解析异常

```sql
select stock_code, announcement_id, publication_date, filing_type,
       parse_status, parse_error, source_url
from public.hkex_share_capital_filings
where parse_status <> 'success'
order by publication_date desc, stock_code;
```

### 10.4 空头比例覆盖

```sql
select
  count(*) as all_rows,
  count(short_ratio_pct) as ratio_rows,
  count(*) filter (where ratio_quality = 'official') as official_rows,
  count(*) filter (where ratio_quality = 'missing_denominator') as missing_denominator_rows,
  min(report_date) as first_date,
  max(report_date) as latest_date
from public.hk_short_positions_weekly;
```

### 10.5 港股通完整性和比例覆盖

```sql
select
  completeness,
  count(*) as row_count,
  count(distinct stock_code) as stock_count,
  count(holding_ratio_pct) as ratio_rows,
  count(*) filter (where ratio_quality = 'official') as official_ratio_rows,
  min(holding_date) as first_date,
  max(holding_date) as latest_date
from public.hk_stock_connect_holdings_daily
group by completeness
order by completeness;
```

预期生产结果只出现 `official_aggregate`，最早日期不早于 `2025-08-11`。

### 10.6 指定缺失股票排查

```sql
select stock_code, count(*) as row_count,
       count(total_holding_shares) as shares_count,
       count(holding_ratio_pct) as ratio_count,
       min(holding_date) as first_date,
       max(holding_date) as latest_date
from public.hk_stock_connect_holdings_daily
where stock_code in ('00257', '00270')
group by stock_code;
```

若 `shares_count > 0` 但 `ratio_count = 0`，问题是历史股本分母缺失或比例尚未刷新，而不是港股通分子缺失。

## 11. 常见故障

### 11.1 `PGRST125 Invalid path`

原因：`SUPABASE_URL` 配成了 Dashboard、Data API 子路径或其他非 Project URL。

处理：Secret 必须是 `https://<project-ref>.supabase.co`，不附加 `/rest/v1`。

### 11.2 `PGRST102 All object keys must match`

原因：同一批 upsert 的 JSON 对象字段不一致。

处理：升级到当前脚本；它会按相同字段形状分批。不要手工删除数据绕过。

### 11.3 `57014 canceling statement due to statement timeout`

原因：旧流程在每个矩阵任务末尾执行全表比例重算。公告数据通常已经写入。

处理：不要重跑全年；运行 `Refresh market holding ratios` 小批量刷新，并用核验 SQL 确认。

### 11.4 GitHub Actions 长时间 `Queued`

含义：等待可用 runner 或等待并发槽，不是脚本卡死。已运行批次可继续，关闭网页和电脑不影响云端任务。

### 11.5 公告解析警告

- `issued-shares section not found`：PDF 版式/股份类别未被识别。
- `next-day closing balance not found`：翌日披露事件表较长或字段位置变化。
- `invalid share totals`：解析值未通过公告内算术关系；必须人工核对，不能强制入库。

### 11.6 页面比例为空

按以下顺序检查：

1. 该日期是否有分子数据。
2. 对应日期之前是否有可用官方股本。
3. `ratio_quality` 是否为 `missing_denominator`。
4. 是否已运行小批量比例刷新。
5. 页面用户是否有 Supabase 读取权限。

### 11.7 页面一直显示“正在计算周线指标”

当前版本应直接读取 `current_hk_market_insight_metrics`。若仍发生：

1. 确认线上 Pages 已部署最新 `main`。
2. 检查浏览器控制台是否为未定义变量或 Supabase 请求失败。
3. 查询周线指标表是否有该指数最新数据。
4. 不要恢复逐股临时行情请求；应修复持久化读取链路。

## 12. 发布与回归

代码变更后：

1. 本地检查 HTML 内脚本语法。
2. 运行相关 Python 测试或脚本 `--dry-run`。
3. 检查 Git diff，确认没有 Secret、缓存、`.DS_Store` 或临时文件。
4. 提交并推送 `main`，等待 GitHub Pages 部署成功。
5. 回归四指数、搜索、默认排序、七列排序、星级筛选、分页和三个详情图。
6. 检查页面日期与数据库最新日期一致。

数据脚本或 SQL 变更还需：

1. 在 Supabase 执行对应 SQL。
2. 先对少量股票或短日期运行任务。
3. 通过第 10 节 SQL 后再做全量回填。
4. 失败重跑只针对缺失范围，避免重复抓取港交所。

## 13. 当前已知限制与待办

- 官方股本年度回填尚未以最终覆盖率报告确认 100%。
- 少数公告存在发行人填报口径与表内算术不一致，需要人工核验后定向处理。
- 港股通 2025-08-11 前没有完整免费官方历史，旧不完整数据不再使用。
- 详情页现有说明仍可能出现“使用当前股本估算”的旧文案；产品口径应以 PRD 为准，后续应改为明确展示质量状态。
- 指数权重公开资料不完整时，默认排序退化为官方成分顺序。
- 当前前端一次最多读取 2,000 行详情历史；现有时间范围足够，扩展更长历史时需服务端分页。

## 14. 接手完成定义

满足以下条件才可认定本轮市场洞察数据工程完成：

- 2023—2026 四个年度股本任务结束且失败公告有明确处置结果。
- 四指数当前成分均有覆盖率报告，未覆盖项可追溯到具体公告或上市日期。
- 空头和 2025-08-11 之后港股通比例完成统一刷新。
- 港股通生产表不存在单通道脏数据。
- 页面列表和详情抽查股票的分子、分母、比例与数据库一致。
- 定时任务连续两周成功，失败能通过本手册恢复。
