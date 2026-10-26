# AGENTS.md — huntai-test 仓库级指令（精简版）

> Cursor / ZCode / Claude Code 均须遵守本文件。Claude Code 入口为根 `CLAUDE.md`（指向本文）。Cursor 另读 `.cursor/rules/`；ZCode 另读 `.zcode/rules/`。二者只允许短指针，不另写业务规则。
> 工程细则见 `docs/00_setup/project_rules.md`。MCP 三份清单保持一致：`.zcode/config.json`、`.cursor/mcp.json`、`.mcp.json`。
> 业务与技术细节不在本文展开：以 `docs/` 对应设计文档为唯一事实源，本文只留导航与凭据防泄漏基线。

**新会话起步**：先读本文 → 按任务打开下表对应文档。

| 要做什么 | 先打开 |
|---|---|
| 目标 / 非目标 / US·FR·AC | `docs/08_prd/prd.md` |
| 23 对象 / 状态机 / IA | `docs/03_problem_modeling/problem_model.md` |
| 页面流 C1–C4 | `docs/04_interaction_design/interaction_flows.md` 与 `chains/` |
| 架构 / Worker / 数据面 | `docs/06_architecture_design/architecture.md` |
| 前后端谁做什么 | `docs/06_architecture_design/frontend_backend_boundary_spec-v1.0.md` |
| 页面 P01–P25 / 路由 / UI | `docs/06_architecture_design/frontend_design_spec-v1.0.md` |
| 锁定技术栈与版本 | `docs/06_architecture_design/tech_stack_decision-v1.0.md` |
| API 路径 / 鉴权 / 错误码 | `docs/07_backend_design/api_spec.md` |
| 表 / 分级 / 秘密 | `docs/07_backend_design/data_model.md` |
| 命名 / Git / 提交检查 | `docs/00_setup/project_rules.md` |
| 切片进度 | `docs/10_ai_context/ai_context.md` §4 状态列与 `context/mN.md` |
| 变更记录 | `docs/13_changes/change_log.md` |

## 1. 项目目标与目录结构

HuntAI Test：企业内部自用 AI 测试平台（≤1000 用户、部门级多租户）。核心是接口 / Web / 性能自动化，用 AI 生成与分诊，用确定性工作流、副作用分级、审批与证据链约束副作用，并与 Jira / GitHub / CI / Release 打通。平台编排质量证据，不替代外部系统。北极星、分期 M0–M4、非目标见 `docs/README.md` 与 `docs/08_prd/prd.md` §1。

```text
frontend/    前端源码与前端工程配置。
backend/     后端源码与后端工程配置。
docs/        全部设计资产的唯一存放地（Markdown 内代码示例除外）。
```

- 仓库顶层除上述三个业务目录外，只放仓库级配置：`README.md`、`AGENTS.md`、`CLAUDE.md`、`.gitignore`、`.env.example`、`.pre-commit-config.yaml`、`.zcode/`、`.cursor/`、`.mcp.json`、`docker-compose.yml`、`.github/`。其中 `docker-compose.yml` 做本地/单机编排，`.github/` 放 CI 工作流（当前仅 gitleaks 秘密扫描）。
- `docs/` 阶段目录 `00_setup`–`13_changes`：序号与名称保持稳定；产出只进对应 `docs/NN_*`，各阶段约定输出见其 `README.md`。
- `backend/` / `frontend/` 子目录按 Stage 6/7 设计落地（见技术栈决策与前端规范）。
- 技术栈与锁定版本以 `docs/06_architecture_design/tech_stack_decision-v1.0.md`（ADR 0009）为准；根 `README.md` 技术栈段落已过时，不作为选版本依据。

## 2. 凭据防泄漏与提交 hooks

- 禁止把密钥、`.env` 值、生产数据、真实 PII 写入仓库、日志、示例、Prompt 或提供给 AI。
- 凭据 / 令牌只存 `credential_ref` 或单向哈希；明文不进数据库、日志、Trace、错误信息或前端（签发当次响应除外）。
- `.env` 禁止入库；`.env.example` 只含键名；新增配置项同步 `.env.example`；代码不硬编码配置值，配置只从仓库根 `.env` 注入。
- pre-commit（gitleaks 秘密扫描）必须通过；禁止 `git commit --no-verify`。
- 需要 AI 协助处理数据时，只提供脱敏或合成样例，不使用真实用户标识。

## 3. 本地开发与提交

- 本地运行：后端 `uv sync` 后按 `backend/README.md`；前端 `cd frontend && npm install && npm run dev`（见 `frontend/README.md`）。
- 开发参考命令（非合入门禁）：
  - 后端（在 `backend/`）：`uv run ruff check . && uv run ruff format --check . && uv run mypy app && uv run pytest`
  - 前端（在 `frontend/`）：`npm run lint && npx tsc --noEmit && npm run build && npm run test`
- Git 分支策略与 Commit 规范（type / scope / subject 正则）见 `docs/00_setup/project_rules.md` §3。
- 变更记录：对设计资产或工程规范的修改，在 `docs/13_changes/change_log.md` 登记一行。
