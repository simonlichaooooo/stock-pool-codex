# 市场洞察 AI 解读部署

前端发布到 GitHub Pages 后，还需要完成以下一次性配置，AI 解读才能在生产环境工作。

## 1. 执行数据库迁移

1. 打开 Supabase 项目控制台。
2. 进入 **SQL Editor**，新建查询。
3. 复制并执行 [`supabase/market-insight-ai.sql`](../supabase/market-insight-ai.sql) 的全部内容。
4. 在 **Table Editor** 中确认已出现 `market_insight_ai_analyses` 表。

该表只保存模型生成结果、客观证据摘要和数据指纹。登录用户只能读取，只有服务端角色可以写入。

## 2. 配置服务端 Secret

在 Supabase Dashboard 的 **Edge Functions → Secrets** 中新增：

- `OPENAI_API_KEY`：OpenAI 项目 API Key。
- `OPENAI_MARKET_INSIGHT_MODEL`：可选，默认 `gpt-5.6-terra`。

不要把 API Key 写入 `index.html`、SQL、GitHub Secrets 以外的代码文件或浏览器 Local Storage。

也可以在已登录并关联项目的 Supabase CLI 中执行：

```bash
supabase secrets set OPENAI_API_KEY="你的 OpenAI API Key"
supabase secrets set OPENAI_MARKET_INSIGHT_MODEL="gpt-5.6-terra"
```

## 3. 部署 Edge Function

在仓库根目录执行：

```bash
supabase functions deploy market-insight-ai
```

函数默认校验登录用户 JWT，不需要关闭 JWT 验证。

## 4. 验证

1. 登录线上应用，进入 **市场洞察**。
2. 打开一只历史数据较完整的股票详情。
3. 等待“股价与持仓行为解读”卡片生成内容。
4. 再次打开同一股票、同一时间范围，应显示“读取缓存”。
5. 若提示历史比例数据不足，先确认 `hk_market_insight_metrics_weekly`、`hk_short_positions_weekly` 和 `hk_stock_connect_holdings_daily` 已有该股票的数据。

函数日志位于 **Supabase Dashboard → Edge Functions → market-insight-ai → Logs**。
