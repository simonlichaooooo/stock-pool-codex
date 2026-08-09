# 项目文档索引

最后更新：2026-08-09

本目录只保留当前有效文档：

| 文档 | 用途 |
| --- | --- |
| [`PRD.md`](./PRD.md) | 整体产品定位、模块范围和产品验收 |
| [`PORTFOLIO_MANAGEMENT.md`](./PORTFOLIO_MANAGEMENT.md) | 组合管理需求、计算规则、后台部署和专项回归 |
| [`MARKET_INSIGHTS_PRD.md`](./MARKET_INSIGHTS_PRD.md) | 市场洞察产品范围、指标口径、交互和验收标准 |
| [`MARKET_INSIGHTS_HANDOFF.md`](./MARKET_INSIGHTS_HANDOFF.md) | 市场洞察数据架构、任务顺序、核验 SQL 和故障处理 |
| [`MARKET_INSIGHTS_RESEARCH.md`](./MARKET_INSIGHTS_RESEARCH.md) | 市场洞察早期数据源预研；现状以专项 PRD 和 Handoff 为准 |
| [`MARKET_DATA_OPERATIONS.md`](./MARKET_DATA_OPERATIONS.md) | HSCI、空头与港股通历史数据部署、回填和日常运维 |
| [`ARCHITECTURE.md`](./ARCHITECTURE.md) | 技术架构、数据域、权限、外部依赖和演进方向 |
| [`HANDOFF.md`](./HANDOFF.md) | 本地开发、发布、排障、回归和接手优先级 |

维护规则：

- 只描述当前代码和线上事实；历史变更由 Git 记录，不在目录内保留旧版副本。
- 功能规则更新 PRD 或专项文档，技术边界更新架构，操作流程更新交接手册。
- 不创建 `*_CURRENT.md`、`*_OLD.md` 或重复 Handoff；直接更新固定入口。
- 文档引用代码基线时，功能提交后同步更新基线和日期。
