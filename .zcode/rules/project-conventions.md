# huntai-test 工程约定

本仓库以根目录 `AGENTS.md` 为跨工具 Agent 指令源（Claude Code 读根 `CLAUDE.md`，指向 `AGENTS.md`）。工程规范见 `docs/00_setup/project_rules.md`。本目录只允许短指针，正文以 `AGENTS.md` 为准；`.cursor/rules/` 必须与本文件同步。

## ZCode 配置

- 项目 MCP：`.zcode/config.json`（LangChain 文档 / 参考）。
- 同步清单：`.zcode/config.json`、`.mcp.json`、`.cursor/mcp.json` 的服务器条目保持一致。
- 保留 `.zcode/`，不要删除或合并进 `.cursor/`。

## 目录与阶段

- 业务目录只有 `frontend/`、`backend/`、`docs/`；设计文档只进 `docs/`，可执行代码只进 `frontend/` / `backend/`。
- 阶段产出只落入对应 `docs/NN_*`。

## 凭据与提交

- 后端配置只经 `.env` 注入；`.env.example` 只含键名。依赖一律用 uv，禁止 pip / `requirements.txt` / poetry。
- 禁止把密钥、`.env` 值、生产数据、用户隐私写入仓库、日志或提供给 AI。
- pre-commit（gitleaks 秘密扫描）必须通过；禁止 `git commit --no-verify`。
