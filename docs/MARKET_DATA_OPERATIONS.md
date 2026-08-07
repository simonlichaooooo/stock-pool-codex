# 市场历史数据部署与运维

最后更新：2026-08-07

## 一次性启用

### 1. 执行数据库迁移

在生产 Supabase 的 SQL Editor 中完整执行：

```text
supabase/market-data-history.sql
```

该脚本只新增市场数据表、索引、RLS 和只读视图，不修改股池、组合或用户表。

### 2. 配置 GitHub Actions 密钥

在仓库 `Settings → Secrets and variables → Actions` 新增：

- `SUPABASE_URL`：项目 URL，例如 `https://<project-ref>.supabase.co`。
- `SUPABASE_SERVICE_ROLE_KEY`：仅放在 GitHub Secret，禁止写入前端和仓库。

没有配置密钥时，计划任务会显示 warning 后安全跳过，不会失败或误写。

### 3. 首次回填

打开 GitHub Actions 的 `Update market data history`，选择 `Run workflow`：

- Dataset：`both`
- Start date：`2023-01-01`
- End date：留空

回填是幂等的；中断后可用相同日期再次运行。港股通回填量较大，任务超时上限为 120 分钟。

## 日常计划

| 数据 | 香港时间 | 行为 |
| --- | --- | --- |
| 证监会空头 | 每周五 18:00 | 写入最新报告；前端静态快照同时刷新 |
| 港股通 | 周一至周五 20:00 | 重查最近 10 天，补齐延迟发布或节假日后的数据 |
| HSCI 成分 | 每个任务开始时 | 写入当日成分快照 |

GitHub Actions 使用 UTC cron；周五 18:00 对应 `0 10 * * 5`，工作日 20:00 对应 `0 12 * * 1-5`。

## 数据检查

迁移和回填后，在 SQL Editor 执行：

```sql
select dataset, status, range_start, range_end, rows_written, finished_at
from public.market_data_ingestion_runs
order by finished_at desc
limit 20;

select completeness, min(holding_date), max(holding_date), count(*)
from public.hk_stock_connect_holdings_daily
group by completeness
order by completeness;

select min(report_date), max(report_date), count(*)
from public.hk_short_positions_weekly;

select count(*) as current_hsci_count
from public.current_market_index_constituents
where index_code = 'HSCI';
```

预期：

- 2023-01-01 至 2024-08-18 的港股通记录主要为 `partial_sz`。
- 2024-08-19 以后，交易日通常为 `complete`；最近日期可能因源站迟发暂缺，下一次任务会补。
- 空头最早日期不早于 2023-01-01，频率约为每周一次。
- HSCI 当前成分数量应大于 400；2026-08-07 验收值为 534。

## 比例回填

当前自动化只使用明确允许批量读取的官方持股数，不自动抓取 HKEXnews。因官方文件不含历史总股本，`holding_ratio_pct`、`short_ratio_pct` 暂时为空，`ratio_quality` 为 `missing_denominator`。

取得授权数据后，优先按以下顺序处理：

1. 保存供应商原始记录与许可范围。
2. 按报告日写入 `issued_shares`。
3. 计算百分比并把 `ratio_quality` 标记为 `licensed_vendor`；若数据直接来自官方则用 `official`。
4. 抽查拆股、合股、配股和回购附近日期，禁止用当前股本覆盖历史。

## 手工只读验证

本地不写数据库的源站验证：

```bash
python3 scripts/market-data-ingest.py --dry-run sync-hsci
python3 scripts/market-data-ingest.py --dry-run short --latest-only
python3 scripts/market-data-ingest.py --dry-run stock-connect --start 2024-08-19 --end 2024-08-19
python3 scripts/market-data-ingest.py --dry-run stock-connect --start 2023-01-03 --end 2023-01-03
```
