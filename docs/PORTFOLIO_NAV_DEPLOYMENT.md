# 组合净值后台部署说明

当前前端已上线，但日终净值依赖 Supabase 后台部署。按以下顺序操作。

## 1. 执行数据库 SQL

在 Supabase Dashboard → SQL Editor → New query 中，完整执行：

1. `supabase/portfolio-nav.sql`

成功标志：出现 `Success. No rows returned`，Table Editor 中新增：

- `portfolio_cash_flows`
- `portfolio_daily_nav`
- `benchmark_daily_close`

## 2. 部署 Edge Function

在本机安装并登录 Supabase CLI 后，在项目根目录执行：

```bash
supabase link --project-ref YOUR_PROJECT_REF
supabase functions deploy daily-portfolio-nav --no-verify-jwt
supabase secrets set CRON_SECRET=REPLACE_WITH_LONG_RANDOM_SECRET
```

`YOUR_PROJECT_REF` 位于项目 URL：`https://YOUR_PROJECT_REF.supabase.co`。

随机密钥请自行生成并保存，后续 SQL 必须使用完全相同的值。

## 3. 创建定时任务

打开 `supabase/portfolio-nav-schedule.sql`，替换两个占位符后，在 SQL Editor 完整执行。

## 4. 手工验证

在 Supabase Dashboard → Edge Functions → `daily-portfolio-nav` 点击 Invoke。

随后检查：

- `portfolio_daily_nav` 出现组合当日净值。
- `benchmark_daily_close` 出现基准指数收盘数据。
- `Cron Jobs` 中存在 `daily-portfolio-nav`。

## 5. 页面验证

进入线上“组合管理 → 净值曲线”。至少积累两个交易日数据后，曲线、区间收益、最大回撤和夏普比率开始显示。
