# 港股通官方合计持仓

当前采集使用港交所“沪港通及深港通持股纪录按日查询”，其数值为中国结算上海及深圳两个 CCASS 参与者的合计持股量。

## 首次启用

1. 在 Supabase SQL Editor 完整执行 `supabase/stock-connect-official-aggregate.sql`。
2. 在 GitHub Actions 运行 `Backfill official Stock Connect holdings`。
3. 起始日期应处于执行当天向前 12 个月内；超出港交所免费窗口的日期会被拒绝。

## 数据范围

- 免费、官方、按交易日更新。
- 在线页面只保留最近 12 个月。
- 2023-01-01 至免费窗口起点的旧记录目前只有深交所单边数据，继续标记为 `partial_sz`，不会冒充沪深合计或参与比例计算。
- 更早的完整历史需要向港交所申请收费的历史 CCASS 持股报告，或使用有授权的商业数据源。
