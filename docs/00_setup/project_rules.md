# 项目工程规范（project_rules）

- **适用范围**：huntai-test 全仓库（`frontend/`、`backend/`、`docs/`）
- **生效方式**：仓库根 `AGENTS.md` 为跨工具 Agent 指令；`CLAUDE.md` 指向 `AGENTS.md`。本文件管工程约定（命名 / 目录 / Git / 提交检查 / 本地验证命令 / 凭据防泄漏基线）。
- **约束用语**：**必须** ／ **禁止** ／ **默认**（不声明变更即按此执行）。

## 1. 代码命名规范

### 1.1 后端（Python）

| 对象 | 规范 | 示例 |
|---|---|---|
| 模块 / 文件 | snake_case | `chat_service.py` |
| 类 | PascalCase | `ChatSession` |
| 函数 / 方法 / 变量 | snake_case | `build_prompt` |
| 常量 | UPPER_SNAKE_CASE | `MAX_RETRY = 3` |
| 环境变量 | UPPER_SNAKE_CASE | `LLM_API_KEY` |
| 包名 | 单个小写单词 | `app.api` |

- 公开函数与类方法必须带完整类型注解（参数 + 返回值）。

### 1.2 前端（TypeScript / React）

| 对象 | 规范 | 示例 |
|---|---|---|
| 组件文件 | PascalCase.tsx | `ChatPanel.tsx` |
| Hook 文件 | use 前缀 + camelCase.ts | `useChatStream.ts` |
| 工具 / 纯函数文件 | camelCase.ts | `formatTime.ts` |
| 组件名 / 类型 / 接口 | PascalCase | `ChatMessage` |
| 变量 / 函数 | camelCase | `sendMessage` |
| 常量 | UPPER_SNAKE_CASE | `MAX_MESSAGES` |
| 自定义 CSS 类 | kebab-case（优先使用 Tailwind 原子类） | `chat-panel` |

- tsconfig 必须开启 `strict: true`；禁止 `any`，确需宽类型用 `unknown` + 类型收窄。

### 1.3 文档、数据与 API

- `docs/` 内文件名：全小写 snake_case，扩展名 `.md`（如 `market_research.md`）。
- `docs/` 阶段目录名固定为 `NN_名称`（00–13）：序号与名称保持稳定。
- 数据库：表名 snake_case 复数（`chat_sessions`），字段名 snake_case。
- API 路径：全小写、连字符分隔、名词复数（如 `/api/v1/chat-sessions`）。

## 2. 目录组织规范

1. 仓库顶层三类业务目录：`frontend/`、`backend/`、`docs/`；其余为仓库级配置文件（`README.md`、`AGENTS.md`、`CLAUDE.md`、`.gitignore`、`.env.example`、`.pre-commit-config.yaml`、`.zcode/`、`.cursor/`、`.mcp.json`、`docker-compose.yml`、`.github/`）。顶层 `docker-compose.yml` 与 `.github/` 仅用于本地编排与 CI（当前仅 gitleaks 秘密扫描），不写业务规则。
2. 设计资产与过程文档只存放于 `docs/`；`frontend/`、`backend/` 内不出现设计文档（代码目录内的 `README.md` 不算设计文档，但内容只限「如何构建 / 运行」）。
3. 可执行代码只存放于 `frontend/`、`backend/`；`docs/` 内不出现代码文件（`.md` 内嵌的代码示例片段不算）。
4. 阶段产物只进对应 `docs/NN_*` 目录；跨阶段引用使用相对路径链接。
5. `backend/`、`frontend/` 的内部结构按 Stage 6/7 设计落地（见 `docs/06_architecture_design/tech_stack_decision-v1.0.md` 与 `docs/06_architecture_design/frontend_design_spec-v1.0.md`）。

## 3. Git 分支策略与 Commit 规范

### 3.1 分支策略

- `main`：唯一长期分支，保持「可构建、可部署」状态。
- 代码变更：从 `main` 切出 `feat/<slug>` 或 `fix/<slug>`（slug 全小写连字符，可带阶段号，如 `feat/stage11-chat-api`），完成后 squash merge 回 `main` 并删除分支。
- 文档与规范变更：可直接提交 `main`。

### 3.2 Commit 规范（Conventional Commits）

格式：`<type>(<scope>): <subject>`

- **type 限定**：`feat` `fix` `docs` `style` `refactor` `test` `chore` `perf` `ci` `build` `revert`
- **scope 限定**（可省略）：`frontend` `backend` `docs` `setup` `deploy`
- **subject**：中文祈使句，不超过 72 字符，结尾不加句号，匹配正则 `^(feat|fix|docs|style|refactor|test|chore|perf|ci|build|revert)(\((frontend|backend|docs|setup|deploy)\))?: .{1,72}$`。
- 一个 commit 只做一件事；涉及行为变更或非平凡修改写 body 说明动机与影响。

### 3.3 提交检查

- pre-commit（含 gitleaks 秘密扫描）必须通过；禁止 `git commit --no-verify`。

## 5. 测试与验证（本地开发参考）

> 以下命令为本地开发自验参考，非合入门禁（合入门禁已于 2026-10-26 移除，见 `docs/13_changes/change_log.md`）。

### 5.1 后端

- 框架：pytest + pytest-asyncio + httpx；测试位于 `backend/tests/`。
- `uv run ruff check . && uv run ruff format --check . && uv run mypy app && uv run pytest`

### 5.2 前端

- `npm run lint && npx tsc --noEmit && npm run build && npm run test`

### 5.3 通用

- 无法本地验证的变更（如部署配置），在对应阶段输出文档中记录验证方式与验证人。

## 6. AI 使用基线（凭据防泄漏）

- 密钥只存在于本地 `.env`；任何 AI 会话、提示词、粘贴内容、日志、示例中不得出现 `.env` 的值。
- 需要 AI 协助处理数据问题时，必须使用脱敏或合成样例（不含真实用户标识）。
- **执行检查**：提交内容经 pre-commit 的 gitleaks 扫描（`.pre-commit-config.yaml`）。
