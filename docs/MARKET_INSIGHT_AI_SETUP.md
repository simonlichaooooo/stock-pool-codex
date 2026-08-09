# 市场洞察 AI 解读部署

前端发布到 GitHub Pages 后，还需要完成以下一次性配置，DeepSeek AI 解读才能在生产环境工作。

## 1. 执行数据库迁移

1. 打开 Supabase 项目控制台。
2. 进入 **SQL Editor**，新建查询。
3. 复制并执行 [`supabase/market-insight-ai.sql`](../supabase/market-insight-ai.sql) 的全部内容。
4. 在 **Table Editor** 中确认已出现 `market_insight_ai_analyses` 表。

该表只保存模型生成结果、客观证据摘要和数据指纹。登录用户只能读取，只有服务端角色可以写入。

## 2. 配置服务端 Secret

先登录 [DeepSeek 开放平台](https://platform.deepseek.com/)，在 **API keys** 中创建一个新的 API Key。Key 只会完整显示一次，请立即复制到 Supabase，不要写进代码、聊天记录或截图。

然后在 Supabase Dashboard 的 **Edge Functions → Secrets** 中新增：

- `DEEPSEEK_API_KEY`：刚刚创建的 DeepSeek API Key。
- `DEEPSEEK_MARKET_INSIGHT_MODEL`：可选，默认 `deepseek-v4-pro`。

不要再配置 `OPENAI_API_KEY`。如果之前已经添加，可以从 Supabase Secrets 中删除；不要把任何 API Key 写入 `index.html`、SQL 或浏览器 Local Storage。

也可以在已登录并关联项目的 Supabase CLI 中执行：

```bash
supabase secrets set DEEPSEEK_API_KEY="你的 DeepSeek API Key"
supabase secrets set DEEPSEEK_MARKET_INSIGHT_MODEL="deepseek-v4-pro"
```

## 3. 部署 Edge Function

### 方法 A：Supabase Dashboard

1. 进入 **Edge Functions → Functions**。
2. 点击 **Deploy a new function**，选择在 Dashboard 编辑器中创建。
3. 函数名填写 `market-insight-ai`。
4. 将 [`supabase/functions/market-insight-ai/index.ts`](../supabase/functions/market-insight-ai/index.ts) 的全部内容粘贴到编辑器。
5. 保持 JWT 验证开启，点击 **Deploy function**。

### 方法 B：Supabase CLI

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
