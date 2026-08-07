# 港股持仓比例历史数据预研

最后更新：2026-08-07

## 结论

从 2023-01-01 起存储“持股数”可行；要得到严谨的历史“持仓比例”，还需要报告日总股本。

- 空头：香港证监会官方历史 CSV 可直接回填，数据为周度。CSV 给出申报空仓股数和市值，不给总股本，因此比例暂时为空。
- 港股通：深交所官方逐股持仓能回查至 2023 年；上交所当前公开接口从 2024-08-19 才有逐股持仓。2023-01-01 至 2024-08-18 只能标记为 `partial_sz`，不能冒充沪深合计。
- 完整的 2023 年港股通总持仓及历史比例，需要向港交所购买历史 CCASS 数据，或采购 Wind、Choice、Bloomberg、LSEG 等授权数据。HKEXnews 查询页不用于自动化建库。
- 当前恒生综合指数成分由恒生指数公司官方实时成分接口同步；截至验收日返回 534 只。

## 官方数据源与更新规律

### 空头持仓

数据源：香港证监会 [Aggregated reportable short positions of specified shares](https://www.sfc.hk/en/Regulatory-functions/Market/Short-position-reporting/Aggregated-reportable-short-positions-of-specified-shares)。

- 报告日：通常为每周最后一个交易日，节假日周可能提前。
- 发布：证监会说明为报告日后三个营业日，通常周五发布。
- 计划：香港时间每周五 18:00 读取最新 CSV；任务按 `stock_code + report_date` upsert，官方迟发时下周运行仍会补上。
- 数据含义：仅包含达到申报门槛的合计须申报淡仓，不等于所有做空交易或所有借券。

### 港股通持仓

官方公告明确为交易日收市后，沪深交易所分别披露每只港股通证券的投资者合计持有数量；未承诺固定时点。

- 沪股通渠道：[上交所港股通证券持有数量](https://star.sse.com.cn/services/hkexsc/ggtscsj/ggtzqcysl/)。当前逐股公开历史起点为 2024-08-19。
- 深股通渠道：[深交所港股通持股数量](https://www.szse.cn/szhk/szhkshareholding/hkholdamount/index.html)。抽样确认 2023-01-03 可用。
- 实测规律：2026-08-07 上午，两站最新均为 2026-08-05，2026-08-06 尚未出现，存在至少一个工作日的发布滞后。
- 计划：香港时间工作日 20:00 运行，每次回看最近 10 个自然日。即使 T+1/T+2 才发布，后续任务也会自动补齐。

完整性规则：

| 状态 | 含义 | 是否生成合计持股数 |
| --- | --- | --- |
| `complete` | 当日沪、深两个官方数据集都已发布 | 是 |
| `partial_sh` | 只有上交所渠道 | 否 |
| `partial_sz` | 只有深交所渠道 | 否 |

### 恒生综合指数成分

数据源：恒生指数公司 [Hang Seng Composite Index](https://origin-www.hsi.com.hk/eng/indexes/all-indexes/hsci) 及其官网成分接口。

- 每次港股通或空头任务运行前同步一份成分快照。
- 历史数据表保留原始证券数据，展示视图按最新 HSCI 成分筛选，因此指数调样后无需改历史表。

## 比例口径

```text
空头持仓比例 = 合计须申报空仓股数 / 报告日已发行股数 × 100%
港股通持仓比例 = 沪股通持股数与深股通持股数之和 / 报告日已发行股数 × 100%
```

不能用当前总股本倒算 2023 年比例。拆股、合股、配股、回购、增发和双柜台安排都会造成历史失真。数据库已预留 `issued_shares`、比例和质量字段；在取得报告日总股本或授权供应商直接提供的比例后再回填。

## 已实现

- Supabase 表、RLS、HSCI 当前成分历史视图：`supabase/market-data-history.sql`。
- 官方源回填与日常更新程序：`scripts/market-data-ingest.py`。
- 周五 18:00 空头计划、工作日 20:00 港股通计划：`.github/workflows/update-market-data-history.yml`。
- 回填与验收操作：`docs/MARKET_DATA_OPERATIONS.md`。

## 验收样本

2026-08-07 只读验证：

- HSCI：534 只成分股。
- 证监会最新 CSV：1,232 条空头记录。
- 2024-08-19 港股通：794 只证券，两渠道完整。
- 2023-01-03 港股通：712 只证券，仅深交所渠道，正确标记为 `partial_sz`。
