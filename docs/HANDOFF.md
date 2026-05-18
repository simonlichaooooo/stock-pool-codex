# 股池管理项目交接文档

最后更新：2026-05-17  
当前形态：静态单页应用 + Supabase 后端服务  
线上地址：`https://simonlichaooooo.github.io/stock-pool-codex/`

## 1. 项目目标

本项目目标是构建一个个人股池管理与观点分享工具，服务于投资研究、估值假设记录、预期回报测算和投资观点发布。

核心目标包括：

- 支持中国 A 股、香港 H 股、美国美股的股池录入与管理。
- 用户可以通过邮箱 Magic Link 或 GitHub OAuth 登录。
- 用户可以维护自己的私有股池，包括当前市值、前瞻利润、前瞻 PE、净现金、股东回报等估值假设。
- 系统自动计算前瞻市值、Upside、Forward PE、前瞻股东回报率。
- 用户可以将部分股票发布为公开或私密分享股池，并记录每次发布版本。
- 粉丝/其他用户可以通过分享链接关注发布者，也可以复制或订阅发布者的股票。
- 提供公开广场，用于展示公开分享的用户股池。
- 提供管理员能力，用于查看用户、隐藏广场展示、禁用分享能力、隐藏股票。

## 2. 当前完成的功能

### 登录与账户

- 邮箱 Magic Link 登录。
- GitHub OAuth 登录。
- 登录 session 保存在 `localStorage`。
- JWT 即将过期时自动刷新。
- 首次登录后需要设置唯一昵称。
- 分享链接未登录访问时，会把发布者 ID 写入 `localStorage`，登录后继续展示关注入口。

### 个人股池

- 新增、编辑、删除股票。
- 股票名称/代码搜索匹配。
- 匹配股票后自动填充名称、代码、市场、交易所、当前市值。
- 支持 A 股、港股、美股。
- 支持货币展示：`CNY`、`HKD`、`USD`。
- 金额底层以人民币 `CNY` 基准保存，编辑时按当前选择货币展示。
- 支持前瞻年份选择，当前从 `2025E` 到 `2035E`。
- 支持前瞻利润、前瞻 PE、利润备注、前瞻股东回报、股东回报政策、净现金、净现金口径、净现金折扣系数、个人备注。
- 列表支持置顶、置底、排序。
- 列表支持按市场筛选、按已分享筛选、文本搜索。

### 测算逻辑

- 前瞻市值 = `前瞻利润 * 前瞻 PE + 净现金 * 净现金折扣系数`
- Upside = `前瞻市值 / 最新市值 - 1`
- Forward PE = `(最新市值 - 净现金 * 净现金折扣系数) / 前瞻利润`
- 前瞻股东回报率 = `前瞻股东回报 / 最新市值`
- 港股列表支持 `20%股息税后` 口径，勾选后港股前瞻股东回报率按 `80%` 计算。

### 发布与分享

- 保存：只保存私有记录，不记录版本。
- 发布：先保存当前股票，再写入分享股池，并生成一个发布版本。
- 每次发布写入 `stock_publications`，包含 `version_number`、`change_note` 和完整 payload 快照。
- 用户可以设置分享方式：
  - `private`：私密分享，仅通过 URL 访问。
  - `public`：公开分享，可在广场展示。
- 用户可以复制自己的分享链接。
- 被分享用户登录后可以关注发布者。
- 关注只表示把发布者加入可查看列表，不会复制股票，也不会订阅任何股票。
- 已关注发布者的分享链接会自动打开发布者股池视图；粉丝视角的操作只有“一键复制”“订阅”“历史”，不能编辑、置顶、置底或删除发布者股票。
- 查看关注人的股池时，可以：
  - 一键复制：复制一份到自己的股池，之后可以自行修改。
  - 订阅：复制一份到自己的股池，后续发布者更新后同步更新核心估值内容。
- 发布历史浮层展示结构化快照，包括当时市值、前瞻市值、Upside、前瞻利润、估值、Forward PE、净现金、现金折扣、净现金口径、股东回报和股东回报政策。
- 发布者删除源股票时：
  - 一键复制副本不受影响。
  - 订阅副本保留在粉丝股池中，核心估值内容清空，来源列显示“发布者昵称 + 已删除”和删除日期。
- 自己股池中显示来源信息，复制/订阅来源会展示发布者昵称、来源类型、更新时间。

### 广场

- 展示公开分享且未被管理员隐藏的发布者。
- 支持按发布者昵称搜索。
- 支持按最近发布、发布数量排序。
- 广场卡片展示发布者昵称、已发布股票数量、最近发布时间和部分代表股票。
- 可以从广场进入发布者股池。

### 管理后台

- 仅管理员可见，目前管理员标识通过 `admin_users` 表配置。
- 当前管理员 GitHub 用户名：`simonlichaooooo`。
- 管理员可查看用户列表。
- 管理员可查看用户股池，并区分公开发布/私有记录。
- 管理员可将用户从广场隐藏/恢复。
- 管理员可禁用/恢复用户分享能力。
- 管理员可保存管理员备注。
- 管理员可隐藏/恢复单只股票。
- 管理动作写入 `moderation_actions`。

### UI/UX

- 已完成多轮 UI 调整：
  - 股池列表基础样式。
  - 新增/编辑股票抽屉页布局优化。
  - 按金融工具风格降低圆角、降低阴影、提高信息密度。
  - 输入框、按钮、表格、卡片做了统一视觉收敛。
- 移动端有基础响应式支持：
  - 表格在窄屏下卡片化。
  - 新增/编辑抽屉在窄屏下改为单列。

## 3. 当前未完成功能

以下功能尚未完成或只是初步形态：

- 完整专业级 UI 重构尚未完成，当前仍是单文件内 CSS 和字符串模板拼接。
- 表格摘要卡片未实现，例如股票数量、平均 Upside、已分享数量、覆盖市场数量。
- 表格 loading skeleton 未实现。
- 表单字段级校验未实现，目前主要使用 `drawerError` 或 `alert`。
- 保存/发布按钮 loading 状态未实现，存在重复点击风险。
- 未保存内容关闭提醒未实现。
- 发布、删除等高风险动作只有部分确认，发布动作没有二次确认。
- 股票搜索的 loading/无结果/已选择状态还比较粗糙。
- 管理后台权限判断较简化，目前只要当前 GitHub 用户名能读到 `admin_users` 表记录即视为管理员。
- 关注/订阅暂无付费能力。
- 订阅同步逻辑在前端加载时合并，不是后端实时推送。
- 没有自动化测试。
- 没有构建流程、lint、TypeScript、模块化组件。
- 没有服务端代理，行情 API 直接从浏览器调用，稳定性依赖第三方接口和跨域/JSONP 能力。

## 4. 当前项目架构

当前项目是一个静态单页应用：

```text
GitHub Pages
  └─ index.html
       ├─ HTML 容器
       ├─ 内联 CSS
       └─ 内联 JavaScript
            ├─ 状态管理 state
            ├─ 路由/视图渲染
            ├─ Supabase Auth
            ├─ Supabase REST 数据访问
            ├─ 股票搜索和行情 API
            ├─ 汇率 API
            └─ UI 交互事件绑定

Supabase
  ├─ Auth
  ├─ PostgREST Data API
  ├─ Row Level Security
  └─ PostgreSQL tables
```

前端没有使用框架，所有逻辑都在 `index.html` 内。  
数据库结构通过 SQL 文件维护，但没有迁移工具，需手动在 Supabase SQL Editor 执行。

## 5. 技术栈

- 前端：原生 HTML / CSS / JavaScript
- 部署：GitHub Pages
- 后端：Supabase
- 数据库：Supabase PostgreSQL
- 鉴权：
  - Supabase Email Magic Link
  - Supabase GitHub OAuth
- 数据访问：Supabase PostgREST REST API
- 股票搜索：
  - 东方财富搜索接口 JSONP
  - 内置 `stockCatalog` 兜底样例
- 股票市值：
  - 腾讯行情接口 `qt.gtimg.cn`
  - 东方财富行情接口作为兜底
- 汇率：
  - `https://open.er-api.com/v6/latest/CNY`
  - 内置固定备用汇率
- 包管理/构建：无
- 测试：无

## 6. 数据库结构

数据库 SQL 文件：

- `supabase/schema.sql`
- `supabase/social-sharing.sql`

### `stock_records`

用户股池记录表。

主要字段：

- `id uuid primary key`
- `user_id uuid references auth.users(id)`
- `payload jsonb`
- `created_at timestamptz`
- `updated_at timestamptz`
- `source_user_id uuid`
- `source_stock_id uuid`
- `source_nickname text`
- `source_type text`
- `last_source_updated_at timestamptz`
- `source_seen_published_at timestamptz`
- `is_shared boolean`
- `last_published_at timestamptz`
- `admin_hidden boolean`

重要说明：

- 大部分股票业务字段保存在 `payload` JSONB 中。
- 表字段中额外冗余保存分享、来源、发布、隐藏等信息，方便查询和 RLS。
- 用户只能读写自己的记录。
- 登录用户可以读取已分享且未被管理员隐藏的记录。
- 管理员可以读取和更新所有记录。

### `profiles`

用户资料表。

主要字段：

- `id uuid primary key references auth.users(id)`
- `email text`
- `nickname text not null unique`
- `bio text`
- `share_visibility text default 'private'`
- `square_hidden boolean`
- `share_banned boolean`
- `admin_note text`
- `created_at timestamptz`
- `updated_at timestamptz`

重要说明：

- `nickname` 唯一。
- `share_visibility` 控制公开广场展示还是私密分享。
- `square_hidden`、`share_banned` 由管理员控制。

### `stock_publications`

股票发布版本表。

主要字段：

- `id uuid primary key`
- `stock_id uuid references stock_records(id)`
- `publisher_id uuid references auth.users(id)`
- `version_number integer`
- `change_note text`
- `payload jsonb`
- `created_at timestamptz`

重要说明：

- 每次点击发布都会生成新版本。
- `payload` 保存发布时结构化股票快照，包含股票基础信息、核心估值假设、计算结果和发布说明。
- `(stock_id, version_number)` 唯一。

### `follows`

关注关系表。

主要字段：

- `follower_id uuid`
- `publisher_id uuid`
- `created_at timestamptz`

重要说明：

- 主键为 `(follower_id, publisher_id)`。
- 不允许自己关注自己。
- 关注只用于让发布者出现在“股池筛选”下拉框，以及通过分享链接直接进入发布者股池。
- 关注不等于股票订阅，不产生 `stock_records` 副本。

### `stock_subscriptions`

股票订阅关系表。

主要字段：

- `id uuid primary key`
- `subscriber_id uuid`
- `publisher_id uuid`
- `source_stock_id uuid`
- `target_stock_id uuid`
- `status text`
- `last_seen_published_at timestamptz`
- `created_at timestamptz`
- `updated_at timestamptz`

重要说明：

- 用于记录“一键订阅”后的来源股票与用户本地副本之间的关系。
- 当前同步主要在前端 `mergeLatestSourceStocks()` 中完成。
- 如果发布者删除来源股票，前端会先调用 `mark_subscriptions_source_deleted()`：
  - 清空订阅副本中的核心估值字段。
  - 保留订阅副本本身。
  - 写入 `payload.sourceDeletedAt`，用于来源列展示删除日期。

### `admin_users`

管理员标识表。

主要字段：

- `github_username text primary key`
- `created_at timestamptz`

当前默认管理员：

- `simonlichaooooo`

### `moderation_actions`

管理员操作日志表。

主要字段：

- `id uuid primary key`
- `admin_github_username text`
- `action_type text`
- `target_user_id uuid`
- `target_stock_id uuid`
- `reason text`
- `created_at timestamptz`

## 7. API routes

当前项目没有自定义后端 API routes。所有接口均为第三方或 Supabase 自动生成接口。

### Supabase Auth

- `POST /auth/v1/otp`
  - 用于发送邮箱 Magic Link。
- `GET /auth/v1/authorize?provider=github`
  - 用于 GitHub OAuth 登录。
- `POST /auth/v1/token?grant_type=refresh_token`
  - 用于刷新 session。

### Supabase REST

通过 `${SUPABASE_URL}/rest/v1/...` 调用：

- `/rest/v1/profiles`
  - 创建、读取、更新用户资料。
  - 管理员更新用户分享状态、广场隐藏、禁用分享、备注。
- `/rest/v1/stock_records`
  - 创建、读取、更新、删除股票。
  - 查询公开分享股票。
  - 管理员读取/隐藏股票。
- `/rest/v1/stock_publications`
  - 查询发布版本号。
  - 插入发布快照。
- `/rest/v1/follows`
  - 查询关注关系。
  - 关注发布者。
- `/rest/v1/stock_subscriptions`
  - 创建订阅关系。
  - 取消订阅。
- `/rest/v1/admin_users`
  - 判断当前 GitHub 用户是否为管理员。
- `/rest/v1/moderation_actions`
  - 写入/读取管理员操作日志。

### 外部行情与汇率

- 东方财富搜索：
  - `https://searchapi.eastmoney.com/api/suggest/get`
- 腾讯行情：
  - `https://qt.gtimg.cn/q=...`
- 东方财富行情：
  - `https://push2.eastmoney.com/api/qt/stock/get`
- 汇率：
  - `https://open.er-api.com/v6/latest/CNY`

## 8. 关键目录结构说明

```text
.
├── index.html
├── supabase
│   ├── schema.sql
│   └── social-sharing.sql
├── docs
│   └── HANDOFF.md
└── REQUIREMENTS.md
```

### `index.html`

项目核心文件，包含：

- 页面样式。
- 应用状态 `state`。
- 登录与 session 处理。
- Supabase REST 封装。
- 股票搜索、行情、汇率。
- 估值计算。
- 列表页渲染。
- 广场渲染。
- 管理后台渲染。
- 新增/编辑股票抽屉渲染。
- 事件绑定。

### `supabase/schema.sql`

初始股池表结构和基础 RLS。

### `supabase/social-sharing.sql`

分享、关注、订阅、广场、管理员相关表结构与 RLS。

### `docs/HANDOFF.md`

当前交接文档。

### `REQUIREMENTS.md`

当前工作区存在但未纳入 Git 跟踪。内容来源待确认，交接前建议决定是否纳入版本控制。

## 9. 环境变量说明

当前项目没有环境变量系统，Supabase URL 和 anon key 直接写在 `index.html`。

当前硬编码配置：

```js
const SUPABASE_URL = "https://woywnriyagjlfphezlnx.supabase.co";
const SUPABASE_ANON_KEY = "...";
const APP_GITHUB_PAGES_PATH = "/stock-pool-codex/";
```

Supabase Auth 配置需要在控制台设置：

- Site URL：
  - `https://simonlichaooooo.github.io/stock-pool-codex/`
- Redirect URLs：
  - `https://simonlichaooooo.github.io/stock-pool-codex/`
  - `https://simonlichaooooo.github.io/stock-pool-codex/**`

GitHub OAuth 配置：

- GitHub OAuth App callback：
  - `https://woywnriyagjlfphezlnx.supabase.co/auth/v1/callback`
- Supabase Auth Provider GitHub 需要填入 GitHub OAuth App 的 Client ID 和 Client Secret。

建议后续重构时将这些值迁移到构建期环境变量，例如：

- `VITE_SUPABASE_URL`
- `VITE_SUPABASE_ANON_KEY`
- `VITE_APP_BASE_PATH`

## 10. 已知问题和技术债务

### 技术债务

- 所有代码集中在单个 `index.html`，维护成本高。
- 没有模块化组件。
- 没有构建流程。
- 没有 lint、format、类型检查。
- 没有单元测试或端到端测试。
- 没有统一 API 层，Supabase 请求散落在多个函数中。
- 样式全局 CSS 与页面结构强耦合。
- 表单校验较弱，错误多为 alert 或抽屉底部错误。
- 保存/发布等异步动作没有 loading 状态和防重复提交。
- 发布与删除等关键操作缺少统一确认弹窗。
- 行情与汇率 API 直接由浏览器调用，稳定性受跨域、网络、第三方接口变动影响。
- `stock_records.payload` 保存大量业务字段，结构灵活但缺少数据库层类型约束。
- 管理员判断依赖 GitHub username 与 `admin_users` 表匹配，逻辑较粗。

### 已知问题

- Supabase 默认邮件存在发送频率限制，可能出现 `over_email_send_rate_limit`。
- 邮件登录链接依赖 Supabase URL Configuration，配置错误会跳转到 GitHub Pages 根域名导致 404。
- 旧邮件链接无法修复，需要重新发送。
- GitHub Pages 可能有缓存，发布后需要等待或强制刷新。
- 免费邮件服务不适合大规模用户登录，后续需要专业邮件服务和自有域名。
- 股票市值接口字段可能变动，尤其港股/美股行情来源需要长期验证。
- 广场、订阅、管理员功能都已实现基础版，但缺少完整产品级交互细节。

## 11. 哪些模块不要轻易修改

### 登录与回跳逻辑

相关函数：

- `appBaseUrl()`
- `rememberPendingShareFromUrl()`
- `sessionFromHash()`
- `currentSession()`
- `sendMagicLink()`
- `loginWithGithub()`

原因：

- GitHub Pages 子路径 `/stock-pool-codex/` 容易导致回跳 404。
- 分享链接依赖 pending share 写入本地存储。

### 金额保存和货币转换逻辑

相关函数：

- `defaultCurrencyFor()`
- `toDisplay()`
- `toCny()`
- `updateAmountField()`
- `fetchExchangeRates()`

原因：

- 底层金额统一以 CNY 保存，展示时才转换。
- 修改时容易造成列表、编辑页和保存数据不一致。

### 估值计算逻辑

相关函数：

- `calc()`
- `shareholderReturnRateForList()`

原因：

- 列表排序、展示、右侧测算结果都依赖这些函数。
- 港股通 20% 股息税后口径在这里处理。

### 发布与订阅逻辑

相关函数：

- `saveStock()`
- `publishStock()`
- `copySharedStock()`
- `mergeLatestSourceStocks()`
- `markSubscribedCopiesSourceDeleted()`
- `unsubscribeStock()`
- `convertToOwnStock()`

原因：

- 这里同时更新 `stock_records`、`stock_publications`、`stock_subscriptions`。
- 一键复制和订阅的行为差异依赖 `sourceType`。
- 发布者删除源股票前，会通过 RPC `mark_subscriptions_source_deleted()` 标记订阅副本；复制副本不处理。

### Supabase RLS 策略

相关文件：

- `supabase/schema.sql`
- `supabase/social-sharing.sql`

原因：

- 这些策略决定用户可见数据边界。
- 修改前必须验证私有记录、公开分享、管理员视图是否仍然正确。

## 12. 当前开发进度

当前处于 MVP+ 阶段：

- 个人股池管理闭环已完成。
- 登录和昵称注册已完成。
- 发布/版本记录已完成。
- 分享链接和关注已完成。
- 一键复制和订阅已完成。
- 广场基础版已完成。
- 管理后台基础版已完成。
- UI 已经历多轮优化，但仍未达到完整专业产品级组件体系。
- 数据库可用，但迁移方式仍是手动 SQL。

最近重要提交：

- `df3265a Fix share auth redirect path`
- `39d0b98 Restructure stock drawer UI`

## 13. 下一步开发优先级

建议优先级如下：

1. **稳定登录链路**
   - 继续验证 Magic Link 和 GitHub OAuth。
   - 确保分享链接登录后能正确恢复关注邀请。

2. **组件化和工程化**
   - 从单个 `index.html` 迁移到 Vite + React 或类似框架。
   - 抽象组件：`PageHeader`、`FilterBar`、`DataTable`、`MetricCard`、`SectionCard`、`FormField`、`Badge`、`IconButton`。

3. **UI 专业化**
   - 股池列表和新增/编辑页做系统级重构。
   - 增加摘要卡片、loading skeleton、empty state。
   - 统一按钮和表单状态。

4. **表单和操作安全**
   - 字段级校验。
   - 保存/发布 loading 状态。
   - 未保存退出提醒。
   - 删除/发布二次确认。

5. **行情稳定性**
   - 将行情和汇率接口迁移到服务端代理或 Edge Function。
   - 增加错误重试和数据来源标识。

6. **分享产品化**
   - 发布历史可视化。
   - 发布者主页。
   - 订阅更新提醒。
   - 关注列表管理。

7. **管理员能力增强**
   - 操作日志列表。
   - 用户搜索。
   - 审核状态和原因。

8. **测试与质量**
   - 增加关键业务的端到端测试。
   - 增加数据库 RLS 验证脚本。

## 14. 当前重要业务逻辑

### 保存 vs 发布

- 保存：
  - 调用 `saveStock()`。
  - 只更新 `stock_records`。
  - 不生成版本。
  - 不改变分享状态，除非 payload 原本已有 `isShared`。

- 发布：
  - 调用 `publishStock()`。
  - 先调用 `saveStock({ keepOpen: true })`。
  - 更新 `stock_records.is_shared = true`。
  - 写入 `stock_publications` 新版本。
  - 清空当前编辑态的 `publishNote`。

### 复制 vs 订阅

- 一键复制：
  - `sourceType = "copied"`。
  - 创建一条自己的 `stock_records`。
  - 之后可以自由修改，不跟随发布者更新。

- 订阅：
  - `sourceType = "subscribed"`。
  - 创建一条自己的 `stock_records`。
  - 创建 `stock_subscriptions`。
  - 加载股池时通过 `mergeLatestSourceStocks()` 合并发布者最新内容。
  - 订阅股票不能直接发布，需要先转为自己的股票。

### 分享链接

- 分享链接格式：

```text
https://simonlichaooooo.github.io/stock-pool-codex/?share=<publisher_id>
```

- 未登录打开分享链接：
  - `rememberPendingShareFromUrl()` 将 `share` 写入 `localStorage`。
  - 登录完成后 `loadShareInvite()` 读取并展示关注入口。

### 广场展示

一个发布者出现在广场需要满足：

- `profiles.share_visibility = 'public'`
- `profiles.square_hidden = false`
- `profiles.share_banned = false`
- 至少有一条 `stock_records.is_shared = true`
- 股票没有被管理员隐藏：`stock_records.admin_hidden = false`

### 管理员

- 当前用户 GitHub username 与 `admin_users.github_username` 匹配时，被视为管理员。
- 管理员可以读取全部用户和股票。
- 管理员对用户/股票的操作会写入 `moderation_actions`。

### 金额单位

- 底层金额保存为 CNY 亿。
- 编辑时如果选择 `HKD` 或 `USD`，通过汇率转换展示。
- 保存时再转换回 CNY。
- 列表统一展示 CNY 亿。

### 港股通股息税后

- 列表表头有 `20%股息税后` checkbox。
- 仅对港股生效。
- 勾选后前瞻股东回报率按 `原回报率 * 0.8` 展示。

## 15. 当前 UI/UX 设计约定

### 视觉风格

- 方向：专业、克制、金融工具感。
- 主色：深金融绿/蓝绿。
- 背景：浅灰白分层背景。
- 卡片和表格：轻边框、轻阴影、低圆角。
- 不使用过亮的 demo 色。

### 数据颜色

- 中国用户习惯：
  - 红色表示正向/上涨/收益。
  - 绿色或蓝绿色表示负向/下跌。

### 字体和数字

- 标题、表头、数字字段要有清晰层级。
- 金额、PE、Upside 等关键数字建议继续强化 `tabular-nums` 或等宽数字风格。

### 列表页

- 股票名称和代码上下两行。
- 代码弱化显示。
- 表头背景浅灰。
- 文本列左对齐，数值列后续建议右对齐。
- 已分享/未分享建议使用 Badge。
- 操作按钮建议保持 icon button 风格，并补 tooltip。

### 新增/编辑页

- 当前为抽屉式编辑。
- 左侧是主表单，右侧是估值测算和发布区。
- 金额输入使用 suffix 显示 `亿 CNY`。
- 当前市值是只读信息，不应表现为可编辑输入框。
- 右侧测算结果使用 2x2 KPI 卡片。
- 发布区文案使用“发布观点/发布快照”方向。

### 文案倾向

- “我的备注”后续建议统一改为“个人研究备注”或“私人备注”。
- “测算结果”后续建议统一改为“估值测算”。
- “发布”后续建议统一改为“发布快照”。
- “保存”后续可根据逻辑改为“保存股票”或“保存草稿”。
