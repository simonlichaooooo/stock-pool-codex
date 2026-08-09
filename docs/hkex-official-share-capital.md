# 港交所官方历史股本回填

该任务只保存港交所披露易公告中明确披露的股本，不以行情反推值覆盖官方值。

## 首次启用

1. 在 Supabase 项目的 **SQL Editor** 新建查询。
2. 完整复制并执行 `supabase/hkex-official-share-capital.sql`。
3. GitHub 仓库进入 **Actions → Backfill official HKEX share capital**。
4. 点击 **Run workflow**，依次选择 `2023`、`2024`、`2025`、`2026` 各运行一次。
5. 每个年份会自动拆成 11 个股票批次，失败批次可单独重新运行；已成功解析的公告会自动跳过。

## 日常更新

`Update market data history` 每周五香港时间 18:00 自动回看最近 70 天公告，覆盖迟发或修订公告。官方记录会立即重新计算空头持仓比例和港股通持仓比例。

## 检查覆盖率

在 Supabase SQL Editor 执行：

```sql
select * from public.hk_official_share_capital_coverage;

select parse_status, count(*)
from public.hkex_share_capital_filings
group by parse_status
order by parse_status;
```

`parsed` 表示完成校验并写入；`failed` 会保留错误信息供修复；`no_listed_class` 表示公告中没有匹配到该港股上市股份类别。旧推算表暂时只作为未覆盖日期的兜底，官方覆盖达到 100% 后再移除。
