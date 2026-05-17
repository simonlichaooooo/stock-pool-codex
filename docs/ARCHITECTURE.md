# 股池管理系统架构文档

最后更新：2026-05-17  
项目形态：静态单页应用 + Supabase 后端  
线上地址：`https://simonlichaooooo.github.io/stock-pool-codex/`

## 1. 系统整体架构

当前系统采用轻量静态应用架构：

```text
用户浏览器
  |
  | 访问 GitHub Pages 静态页面
  v
GitHub Pages
  └─ index.html
       ├─ UI 渲染
       ├─ 前端状态管理
       ├─ 表单和列表交互
       ├─ 估值计算
       ├─ Supabase Auth 调用
       ├─ Supabase REST 调用
       ├─ 股票搜索/行情接口调用
       └─ 汇率接口调用

Supabase
  ├─ Auth
  │   ├─ Email Magic Link
  │   └─ GitHub OAuth
  ├─ PostgREST Data API
  ├─ PostgreSQL
  └─ Row Level Security

第三方行情/汇率服务
  ├─ 东方财富搜索/行情
  ├─ 腾讯行情
  └─ open.er-api.com 汇率
```

系统目前没有自定义后端服务，也没有构建流程。`index.html` 同时承担视图层、状态层、业务逻辑层和数据访问层。

## 2. 前后端数据流

### 2.1 登录数据流

```text
用户输入邮箱或点击 GitHub 登录
  |
  v
Supabase Auth
  |
  | 发送 Magic Link / OAuth 回调
  v
GitHub Pages 应用 URL
  |
  | URL hash 中带 access_token / refresh_token
  v
前端解析 sessionFromHash()
  |
  | 写入 localStorage
  v
后续请求携带 Authorization: Bearer <access_token>
```

### 2.2 股池读取数据流

```text
页面初始化 init()
  |
  v
currentSession()
  |
  v
loadProfile()
  |
  v
afterProfileReady()
  ├─ loadAdminMarker()
  ├─ loadFollowedPublishers()
  ├─ loadShareInvite()
  └─ loadStocks()
       |
       v
     /rest/v1/stock_records
       |
       v
     normalizeStockRow()
       |
       v
     mergeLatestSourceStocks()
       |
       v
     render()
```

### 2.3 新增/编辑股票数据流

```text
用户打开新增/编辑抽屉
  |
  v
state.form = emptyForm() 或已有股票 payload
  |
  v
用户搜索股票
  |
  v
searchStocks()
  ├─ 东方财富搜索 JSONP
  └─ stockCatalog 兜底
  |
  v
fetchQuote()
  ├─ 腾讯行情
  └─ 东方财富行情兜底
  |
  v
applyCatalog()
  |
  v
用户编辑估值假设
  |
  v
calc() 实时计算测算结果
  |
  v
saveStock()
  |
  v
/rest/v1/stock_records insert/update
```

### 2.4 发布数据流

```text
用户点击发布
  |
  v
publishStock()
  |
  v
saveStock({ keepOpen: true })
  |
  v
查询 stock_publications 最新版本号
  |
  v
更新 stock_records.is_shared = true
  |
  v
插入 stock_publications 快照
  |
  v
关闭抽屉并刷新列表
```

### 2.5 分享/订阅数据流

```text
发布者复制分享链接
  |
  v
https://simonlichaooooo.github.io/stock-pool-codex/?share=<publisher_id>
  |
  v
访问者打开链接
  |
  v
rememberPendingShareFromUrl()
  |
  | 未登录时暂存 publisher_id 到 localStorage
  v
登录后 loadShareInvite()
  |
  v
展示关注入口
  |
  v
followPublisher()
  |
  v
写入 follows
```

订阅股票时：

```text
查看发布者股池
  |
  v
点击订阅
  |
  v
copySharedStock(stockId, "subscribed")
  |
  ├─ 创建自己的 stock_records 副本
  └─ 创建 stock_subscriptions 关系
  |
  v
后续 loadStocks() 时 mergeLatestSourceStocks()
```

## 3. 数据库设计

数据库使用 Supabase PostgreSQL。核心表由以下 SQL 文件维护：

- `supabase/schema.sql`
- `supabase/social-sharing.sql`

### 3.1 表关系概览

```text
auth.users
  ├─ profiles.id
  ├─ stock_records.user_id
  ├─ stock_publications.publisher_id
  ├─ follows.follower_id
  ├─ follows.publisher_id
  ├─ stock_subscriptions.subscriber_id
  └─ stock_subscriptions.publisher_id

stock_records
  ├─ stock_publications.stock_id
  ├─ stock_subscriptions.source_stock_id
  ├─ stock_subscriptions.target_stock_id
  └─ moderation_actions.target_stock_id

admin_users
  └─ 用于识别管理员 GitHub username
```

### 3.2 `stock_records`

用途：保存用户股池记录。

特点：

- 核心业务字段存于 `payload jsonb`。
- 分享和来源相关字段以普通列冗余保存，方便查询和 RLS。
- 支持私有记录、公开分享、复制来源、订阅来源。

主要字段：

- `id`
- `user_id`
- `payload`
- `source_user_id`
- `source_stock_id`
- `source_nickname`
- `source_type`
- `last_source_updated_at`
- `source_seen_published_at`
- `is_shared`
- `last_published_at`
- `admin_hidden`
- `created_at`
- `updated_at`

### 3.3 `profiles`

用途：用户基础资料和分享设置。

主要字段：

- `id`
- `email`
- `nickname`
- `bio`
- `share_visibility`
- `square_hidden`
- `share_banned`
- `admin_note`
- `created_at`
- `updated_at`

### 3.4 `stock_publications`

用途：记录每次发布快照和版本。

主要字段：

- `stock_id`
- `publisher_id`
- `version_number`
- `change_note`
- `payload`
- `created_at`

设计原因：

- 发布版本不可只依赖当前 `stock_records`，否则无法追踪观点变化。
- `payload` 快照可保留当时的完整估值假设。

### 3.5 `follows`

用途：记录用户关注发布者。

主键：

- `(follower_id, publisher_id)`

设计原因：

- 后续可扩展为付费订阅、关注列表、动态提醒。

### 3.6 `stock_subscriptions`

用途：记录用户订阅了发布者的哪只股票，以及本地副本。

主要字段：

- `subscriber_id`
- `publisher_id`
- `source_stock_id`
- `target_stock_id`
- `status`
- `last_seen_published_at`

设计原因：

- “订阅”需要区别于“一键复制”。
- 一键复制后用户可自由修改；订阅则需要跟随发布者更新。

### 3.7 `admin_users`

用途：管理员白名单。

当前记录：

- `simonlichaooooo`

设计原因：

- MVP 阶段避免复杂 RBAC。
- 利用 Supabase Auth GitHub metadata 中的 username 与表记录匹配。

### 3.8 `moderation_actions`

用途：记录管理员操作日志。

主要字段：

- `admin_github_username`
- `action_type`
- `target_user_id`
- `target_stock_id`
- `reason`
- `created_at`

## 4. API 设计

当前没有自定义后端 API。API 分为三类：

1. Supabase Auth API
2. Supabase PostgREST Data API
3. 第三方行情/汇率 API

### 4.1 Supabase Auth API

#### 发送 Magic Link

```http
POST https://woywnriyagjlfphezlnx.supabase.co/auth/v1/otp
```

用途：

- 发送邮箱登录链接。

关键字段：

- `email`
- `create_user: true`
- `email_redirect_to: AUTH_REDIRECT_URL`
- `options.email_redirect_to`

#### GitHub OAuth

```http
GET https://woywnriyagjlfphezlnx.supabase.co/auth/v1/authorize?provider=github&redirect_to=...
```

用途：

- 使用 GitHub 账号登录。

#### 刷新 Token

```http
POST https://woywnriyagjlfphezlnx.supabase.co/auth/v1/token?grant_type=refresh_token
```

用途：

- JWT 即将过期时刷新 session。

### 4.2 Supabase REST API

所有请求封装在：

- `supabaseRequest(path, options)`
- `supabaseFetch(path, options)`

统一请求头：

```http
apikey: SUPABASE_ANON_KEY
Authorization: Bearer <access_token>
Content-Type: application/json
Prefer: ...
```

常用资源：

```text
/rest/v1/profiles
/rest/v1/stock_records
/rest/v1/stock_publications
/rest/v1/follows
/rest/v1/stock_subscriptions
/rest/v1/admin_users
/rest/v1/moderation_actions
```

### 4.3 第三方 API

#### 东方财富搜索

```text
https://searchapi.eastmoney.com/api/suggest/get
```

使用方式：

- JSONP。
- 搜索 A 股、港股、美股。

#### 腾讯行情

```text
https://qt.gtimg.cn/q=<symbol>
```

用途：

- 获取股票总市值。

#### 东方财富行情兜底

```text
https://push2.eastmoney.com/api/qt/stock/get
```

用途：

- 腾讯行情失败时尝试获取总市值。

#### 汇率

```text
https://open.er-api.com/v6/latest/CNY
```

用途：

- 获取 `CNY` 到 `HKD`、`USD` 汇率。
- 失败时使用前端固定备用汇率。

## 5. 状态管理方式

当前使用单一全局对象 `state` 管理应用状态。

核心字段包括：

```js
state = {
  loading,
  session,
  profile,
  profileRequired,
  shareInviteProfile,
  followedPublishers,
  stocks,
  publisherStocks,
  publisherProfile,
  mainView,
  isAdmin,
  squareProfiles,
  adminUsers,
  adminStocks,
  viewPublisherId,
  shareFilter,
  filter,
  query,
  sort,
  stockConnectDividendTax,
  drawerOpen,
  editingId,
  form,
  drawerError,
  loginNotice,
  lastError
}
```

### 5.1 渲染方式

当前采用手写字符串模板渲染：

```text
state 变化
  |
  v
render()
  |
  v
document.getElementById("app").innerHTML = ...
  |
  v
bindEvents()
```

每次 render 后重新绑定事件。

### 5.2 状态持久化

持久化使用 `localStorage`：

- `stockpool.supabaseSession`
  - 保存 Supabase session。
- `stockpool.pendingSharePublisher`
  - 保存未登录状态下访问分享链接的发布者 ID。

### 5.3 风险

- 手写状态管理没有 diff，复杂页面会频繁重渲染。
- 所有事件每次 render 后重新绑定，规模扩大后维护成本升高。
- 字符串模板拼接容易引入 XSS 或结构错误，目前通过 `escapeHtml()` 处理大部分展示值。

## 6. Auth 流程

### 6.1 Email Magic Link

```text
用户输入邮箱
  |
  v
sendMagicLink(email)
  |
  v
Supabase 发送邮件
  |
  v
用户点击邮件链接
  |
  v
Supabase 验证 token
  |
  v
跳转 AUTH_REDIRECT_URL
  |
  v
URL hash 携带 access_token / refresh_token
  |
  v
sessionFromHash()
  |
  v
写入 localStorage
```

`AUTH_REDIRECT_URL` 由 `appBaseUrl()` 生成。  
在 GitHub Pages 环境下强制为：

```text
https://simonlichaooooo.github.io/stock-pool-codex/
```

### 6.2 GitHub OAuth

```text
用户点击 GitHub 登录
  |
  v
loginWithGithub()
  |
  v
Supabase OAuth authorize
  |
  v
GitHub 授权
  |
  v
Supabase auth callback
  |
  v
跳回 AUTH_REDIRECT_URL
```

### 6.3 首次注册昵称

登录后：

```text
loadProfile()
  |
  | 找不到 profile
  v
state.profileRequired = true
  |
  v
renderProfileSetup()
  |
  v
用户输入 nickname
  |
  v
createProfile()
```

`nickname` 在数据库中唯一。

### 6.4 Session 刷新

每次 Supabase REST 请求前：

```text
supabaseRequest()
  |
  v
ensureFreshSession()
  |
  | access_token 快过期
  v
refreshSession()
```

如果请求返回 401 且错误包含 `jwt expired`，会再次尝试刷新并重试请求。

## 7. 部署结构

### 7.1 前端部署

部署平台：

- GitHub Pages

仓库：

- `simonlichaooooo/stock-pool-codex`

分支：

- `main`

入口文件：

- `index.html`

线上路径：

```text
https://simonlichaooooo.github.io/stock-pool-codex/
```

注意：

- 由于是 GitHub Pages 项目页，路径必须包含 `/stock-pool-codex/`。
- Supabase Auth 的回跳地址也必须包含这个路径。

### 7.2 后端部署

后端由 Supabase 托管：

- Auth
- PostgreSQL
- REST API
- RLS

数据库迁移目前手动执行：

1. 打开 Supabase Dashboard。
2. 进入 SQL Editor。
3. 复制执行 `supabase/schema.sql`。
4. 复制执行 `supabase/social-sharing.sql`。

### 7.3 Auth 配置

Supabase URL Configuration：

```text
Site URL:
https://simonlichaooooo.github.io/stock-pool-codex/

Redirect URLs:
https://simonlichaooooo.github.io/stock-pool-codex/
https://simonlichaooooo.github.io/stock-pool-codex/**
```

GitHub OAuth App Callback URL：

```text
https://woywnriyagjlfphezlnx.supabase.co/auth/v1/callback
```

## 8. 第三方服务依赖

### Supabase

用途：

- Auth
- 数据库存储
- REST API
- RLS

风险：

- 免费邮件发送有限频率。
- 默认邮件服务不适合大量普通用户。
- 数据库结构和 RLS 需要谨慎维护。

### GitHub Pages

用途：

- 静态页面托管。

风险：

- 有缓存延迟。
- 项目页路径必须包含仓库名。
- 没有服务端能力。

### GitHub OAuth

用途：

- 登录。
- 管理员身份识别依赖 GitHub username。

风险：

- 如果用户 GitHub metadata 字段变化，管理员识别可能失败。

### 东方财富

用途：

- 股票搜索。
- 行情兜底。

风险：

- 非正式商业 API。
- 接口字段可能变动。
- JSONP 依赖浏览器行为。

### 腾讯行情

用途：

- 获取股票市值。

风险：

- 非正式商业 API。
- 不同市场字段可能不稳定。

### open.er-api.com

用途：

- 获取最新汇率。

风险：

- 免费接口可用性不保证。
- 请求失败会使用固定备用汇率。

## 9. 关键技术决策原因

### 9.1 使用单文件静态应用

原因：

- 初期开发快。
- 无需搭建复杂工程。
- GitHub Pages 免费托管。

代价：

- 可维护性差。
- 组件复用困难。
- 没有类型检查和自动化测试。

### 9.2 使用 Supabase

原因：

- 免费起步。
- Auth、数据库、REST API 一体化。
- RLS 可快速实现多用户数据隔离。

代价：

- 前端直连数据库 REST API，业务逻辑较分散。
- 邮件默认服务有频率限制。
- 复杂权限需要谨慎写 RLS。

### 9.3 金额统一保存为 CNY

原因：

- 列表统一展示人民币口径。
- 跨 A 股、港股、美股比较更直观。
- 避免同一字段在不同货币下混存。

代价：

- 编辑时需要根据展示货币来回转换。
- 汇率更新会影响展示值。

### 9.4 大量股票字段存入 JSONB payload

原因：

- MVP 阶段字段变化快。
- 避免频繁改数据库列。
- 发布快照天然适合 JSONB。

代价：

- 数据库层难以做类型约束。
- 后续统计分析、筛选、索引会更困难。

### 9.5 发布版本单独存表

原因：

- 发布观点需要可追踪。
- 用户私有保存不应污染观点历史。
- 后续可以做观点变化追踪。

### 9.6 复制和订阅区分

原因：

- 一键复制是静态复制，用户可自由改。
- 订阅是动态跟随发布者观点。
- 两者对应不同用户心智和后续商业模式。

### 9.7 管理员用 GitHub username 判断

原因：

- 快速实现“仅有我能登录管理后台”。
- 不需要额外角色系统。

代价：

- 不够严谨。
- 后续多管理员、权限分级需要重构。

## 10. 后续扩展建议

### 10.1 工程化重构

建议迁移为：

- Vite + React
- TypeScript
- ESLint + Prettier
- Vitest 或 Playwright

建议抽象组件：

- `PageHeader`
- `FilterBar`
- `DataTable`
- `MetricCard`
- `SectionCard`
- `FormField`
- `Badge`
- `IconButton`
- `ConfirmDialog`

### 10.2 后端能力增强

建议增加：

- Supabase Edge Functions 或独立后端。
- 行情 API 代理。
- 汇率 API 代理。
- 数据清洗和缓存。
- 服务端校验。

### 10.3 数据库结构优化

建议逐步把高频字段从 `payload` 拆成真实列：

- `name`
- `code`
- `market`
- `latest_market_cap_cny`
- `expected_profit_cny`
- `expected_pe`
- `expected_shareholder_return_cny`
- `net_cash_cny`
- `net_cash_discount_rate`

优点：

- 更好查询。
- 更好排序。
- 更好做统计和索引。

### 10.4 UI/UX 产品化

建议优先补齐：

- 列表摘要卡片。
- 表格 loading skeleton。
- 专业 empty state。
- 表单字段级错误。
- 保存/发布 loading 状态。
- 未保存退出提醒。
- 删除/发布确认弹窗。
- 操作成功 toast。
- 表格数值右对齐和 tabular nums。

### 10.5 分享体系扩展

建议后续支持：

- 发布者主页。
- 发布历史时间线。
- 单只股票观点变化图。
- 关注列表管理。
- 订阅更新通知。
- 私密链接权限管理。
- 付费订阅。

### 10.6 权限与合规

建议后续支持：

- 更完整的 RBAC。
- 管理员审计页面。
- 用户举报。
- 内容隐藏原因。
- 投资建议免责声明统一展示。

### 10.7 部署和配置

建议后续：

- 使用自有域名。
- 使用专业邮件服务，例如 Resend、Postmark、SendGrid 或 AWS SES。
- 把 Supabase URL 和 anon key 移到环境变量。
- 增加部署流水线检查。

