# 港股持仓比例历史数据预研

最后更新：2026-08-07

## 结论

整体可行，但两类数据的实施难度不同：

- 历史空头持仓：可以直接回填。香港证监会按周发布指明股份的合计须申报淡仓 CSV，公开数据可追溯至 2012 年 9 月。
- 历史港股通持仓：业务上可行，但生产化前需要合规的授权数据源或港交所正式数据申请。不建议通过脚本批量抓取 HKEXnews，其查询服务条款明确限制程序化和系统性获取。

## 数据源

### 1. 空头持仓比例

主数据源：香港证监会“Aggregated reportable short positions of specified shares”。

- 频率：周度，报告日为每周最后一个交易日。
- 原始字段：报告日、股票代码、股票名称、合计须申报空仓股数、空仓市值。
- 历史深度：聚合数据发布于 2012-09-07 启动，官网保留历史 CSV/PDF。
- 口径限制：只包含达到申报门槛的净空头，不是全市场总做空量。现行普通指明股份门槛为发行人市值 0.02% 或 3,000 万港元的较低者。

比例计算建议：

```text
空头持仓比例 = 合计须申报空仓股数 / 报告日已发行股数
```

证监会 CSV 不直接给出比例，因此历史回填需要同时获取“报告日已发行股数”。不能用当前总股本回算多年历史，否则拆股、回购、配股和双柜台变更会导致偏差。

### 2. 港股通持仓比例

权威口径：中国结算对应的两个 CCASS 参与者日终持仓合计，除以已发行股数。

- 频率：交易日日终。
- 公开起点：HKEXnews 的 Stock Connect 持仓查询从 2017-03-17 起提供。
- 字段：日期、股票代码、持股数、占已发行股份比例。
- 官方提示：用于计算比例的已发行股数可能尚未反映公司行动，比例仅供参考。
- 合规边界：HKEXnews 条款不允许使用程序化或机械方式获取并建立数据库。

可选生产数据源，按优先级排序：

1. 采购 Choice、Wind、Bloomberg、LSEG/Refinitiv 等包含港股通历史持仓的授权数据。
2. 向港交所正式申请历史 CCASS 数据，确认批量使用、再发布和费用条款。
3. 仅用于内部原型时，可以对第三方公开页面做小样本人工核验，但不作为正式历史数据管道。

## 建议存储设计

建议放入 Supabase PostgreSQL，原始文件放入 Supabase Storage。比例与原始股数同时保存，避免后续口径变更时无法复算。

### `market_securities`

- `security_id` UUID
- `hk_stock_code` text，固定五位存储
- `name_zh` / `name_en`
- `listed_at` / `delisted_at`

### `hk_short_positions_weekly`

- 联合主键：`security_id + report_date`
- `short_shares`
- `short_value_hkd`
- `issued_shares`
- `short_ratio`
- `source_url` / `raw_object_path` / `ingested_at`
- `quality_status`：`official` / `denominator_estimated` / `missing_denominator`

### `hk_stock_connect_holdings_daily`

- 联合主键：`security_id + holding_date`
- `holding_shares`
- `holding_ratio_reported`
- `issued_shares_reported`
- 可选 `sh_connect_shares` / `sz_connect_shares`
- `source_vendor` / `source_record_id` / `ingested_at`
- `license_scope`：标记是否允许对终端用户展示

### `market_data_ingestion_runs`

记录每次任务的数据日期、来源、文件哈希、行数、缺失股票数、状态和错误，用于发现源站格式变更和迟到数据。

## 回填与日常更新

1. 先建立股票代码和公司行动映射，统一 `00700`、`700`、`0700.HK` 等代码。
2. 将证监会历史 CSV 原样归档，按周写入空头表，再用当日总股本计算比例。
3. 授权数据源到位后，按交易日回填港股通；保留数据源给出的原始比例。
4. 日常任务使用 upsert，以数据日期而不是抓取日期作为唯一键，允许官方更正。
5. 前端时序图默认展示原始比例，并标注周度/日度频率、缺失日和数据滞后。

## 实施建议

下一阶段先选 3 只股做数据验收（腾讯、阿里、美团）：

- 空头从 2012 年或上市日起全量回填。
- 港股通从 2017-03-17 或首次可用日起回填。
- 抽查 20 个日期与官方页面/原始文件一致性，再扩展到全部港股。

对“单只股历史曲线”的数据量很小，Supabase 完全能承载；真正的前置条件是港股通历史数据的授权和供应稳定性，不是技术容量。
