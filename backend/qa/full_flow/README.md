# Full-flow QA kit

一套**与个人开发环境隔离**的 HuntAI Test 全流程测试包：独立数据库、独立端口、独立 `.env.qa`，加上一台真实的 Docker Jenkins（含 JUnit 归档与 HMAC 回填），用于从登录到门禁、证据、Release、Jenkins CI 回填的手工 + 自动化验收。

> 这个包服务于“把仓库里已实现的 M0–M3 功能真实跑一遍”，**不修改**产品代码的 AI 行为，也不替代 `docs/00_setup/` 下的正式教程。
> 完整的图文手册（模块、架构图、技术栈、逐步操作、验收清单）见：
> [`docs/11_test/full_flow_test_guide/index.html`](../../../docs/11_test/full_flow_test_guide/index.html)

## 1. 隔离了什么

| 项 | 产品本地默认 | QA 测试包 |
|---|---|---|
| 配置 | 仓库根 `.env` | `backend/qa/full_flow/.env.qa`（gitignored） |
| 数据库 | `.env` 里 `DATABASE_URL` 指向的库 | 同实例上独立库 `huntai_qa`（运行）/ `huntai_test_qa`（pytest） |
| API | 8000 | 8013（绑定 `0.0.0.0`，供 Jenkins 容器访问） |
| 前端 | 5173 | 5180 |
| mock IdP | 8090 | 8190 |
| mock 集成 | 8091 | 8091（若已被占用则复用） |
| Jenkins | 无 | 8088（Docker，仅 loopback） |
| 会话 Cookie | 根 `.env` 的名称 | `huntai_qa_session` |

根 `.env` 只被读取 `DATABASE_URL` 用于推导 QA 库连接；**不会被修改**，也不会打印任何值。

## 2. 前置条件

- macOS / Linux
- Python 3.14 + uv
- Node 24 + npm
- PostgreSQL 18（本机实例即可；测试包会创建 `huntai_qa`）
- Docker Desktop / Docker Engine（Jenkins 用）
- 仓库根 `.env` 已存在（模板见根 `.env.example`）

## 3. 快速开始

在仓库根执行：

```bash
# 0) 预检：工具、端口、.env.qa、数据库
backend/qa/full_flow/qa.sh doctor

# 1) 一次性初始化：生成 .env.qa、创建 huntai_qa、迁移、写入本地身份/项目/mock 连接器
backend/qa/full_flow/qa.sh init

# 2) 启动本地四件套（mock IdP / mock 集成 / API / Vite）
backend/qa/full_flow/qa.sh up

# 3) 启动真实 Jenkins
backend/qa/full_flow/qa.sh jenkins-up
# 如果基础镜像无法拉取（离线 / 镜像源 403），已有本地镜像时可用：
# backend/qa/full_flow/qa.sh jenkins-up --no-build

# 4) 浏览器打开
open http://127.0.0.1:5180/
```

登录账号（合成账号，仅 loopback mock）：

| 用户名 | 项目角色 | 口令 | 用途 |
|---|---|---|---|
| `local-dev-user` | owner | `local-dev` | 造数据、发起执行 |
| `local-dev-user-2` | admin | `local-dev` | 四眼审批、用例复核 |

切换身份：访问 <http://127.0.0.1:8190/switch-account>，或开无痕窗口。

## 4. 自动化测试

```bash
# 现有 live smoke（OIDC + 自建资产 + 接口执行 + 门禁 + Jira/Release）
backend/qa/full_flow/qa.sh test-live

# 真实 Jenkins 全链路（环境注册 → 四眼 → 触发 → JUnit/日志回填 → 门禁）
backend/qa/full_flow/qa.sh test-jenkins

# 产品自带单测/集成测试与前端测试
backend/qa/full_flow/qa.sh test-backend
backend/qa/full_flow/qa.sh test-frontend

# 全部（耗时较长）
backend/qa/full_flow/qa.sh test-all
```

`test-jenkins` 的机器可读报告写到 `backend/qa/full_flow/.runtime/last_e2e_report.json`。

> `test-backend` 会 TRUNCATE 所有业务表，因此固定指向独立的 `huntai_test_qa`，不会动 `huntai_qa` 或你本机的 `huntai_test`。

## 5. Jenkins 是怎么接的

```
HuntAI API ──POST /job/full-flow-smoke/buildWithParameters──▶ Jenkins
     │                                                         │
     │                                          归档 junit.xml / report.json
     │                                                         │
     │                                          下游 notify-* 任务（build 完成后启动）
     │◀──HMAC POST /api/v1/inbound-webhooks/{ci connector}──────┘
     │
     └─ 平台恢复收集：日志分片 + JUnit 解析 + CaseResult + 门禁评估
```

- Job：`full-flow-smoke`（1 passed）、`full-flow-fail`（JUnit 内 1 failure）。
- 下游任务：`notify-full-flow-smoke` / `notify-full-flow-fail`，在**上游构建已结束**后发送 `phase=COMPLETED` 的 HMAC webhook。这样平台恢复时 Jenkins 已不再 `building=true`。
- CI 连接器复用种子的 `00000000-0000-4000-8000-000000000012`（`webhook_secret_ref=env:JENKINS_WEBHOOK_SECRET`）；执行环境由 E2E 通过 API-102 创建并四眼批准。
- Jenkins 安全被**显式关闭**，因为产品执行器用 `HTTP Basic(空用户名, JENKINS_API_TOKEN)` 触发；该 Jenkins 只监听 `127.0.0.1`，**禁止用于共享环境**。

## 6. AI / DeepSeek 的真实边界

当前 M0–M3 的 `llm_factory.invoke()` 是**确定性 stub**：

- A1 用本地解析器产出草稿（不需要 key）；
- A2 走规则聚类 fallback；
- A3 / Copilot 走服务端确定性结果；
- 页面显示“AI 降级”横幅，这是设计行为，不是故障。

因此 **DeepSeek key 不会被产品消费**。测试包只提供可选的连通性检查：

```bash
# 把 DEEPSEEK_API_KEY 写进 .env.qa 后
backend/qa/full_flow/qa.sh ai-check
```

它只验证 key/网络可用，不改变平台 AI 行为。若要让平台真实调用 DeepSeek，需要改 `llm_factory` 与各 AI 服务（产品变更，需单独立项 + change_log）。

## 7. 复位与停止

```bash
backend/qa/full_flow/qa.sh reset          # 清空业务数据，保留表结构与身份种子
backend/qa/full_flow/qa.sh reset --hard   # 删库重建 + 迁移 + 种子
backend/qa/full_flow/qa.sh down           # 停 API / Vite / mocks
backend/qa/full_flow/qa.sh jenkins-down   # 停 Jenkins（保留卷）
backend/qa/full_flow/qa.sh jenkins-reset  # 停 Jenkins 并删卷
```

## 8. 常见问题

| 现象 | 处理 |
|---|---|
| `doctor` 报端口占用 | 停掉占用进程，或改 `.env.qa` 的 `QA_*` 端口后重新 `init --force` |
| 登录后立刻掉线 | 确认 `.env.qa` 的 `SESSION_COOKIE_SECURE=false`，且用 5180 访问 |
| Jenkins job 404 | `qa.sh jenkins-reset && qa.sh jenkins-up` 重建卷与 job |
| E2E 卡在 `WAITING_EXTERNAL` | 看 `docker compose -f backend/qa/full_flow/docker-compose.jenkins.yml logs`，确认下游 notify 任务执行且 `host.docker.internal:8013` 可达 |
| `HT-IAM-002` | 你在用发起人账号批准；换 `local-dev-user-2` |
| 数据库连不上 | 本机 PostgreSQL 未启动，或 `.env` 的 `DATABASE_URL` 用户无建库权限 |

## 9. 文件地图

```
backend/qa/full_flow/
├── qa.sh                        # 唯一入口
├── env.qa.example               # 键名模板（init 会生成 .env.qa）
├── docker-compose.jenkins.yml   # 真实 Jenkins
├── jenkins/
│   ├── Dockerfile               # LTS + junit + curl/jq/openssl
│   ├── plugins.txt
│   ├── init.groovy.d/           # 关安全向导 / CSRF / quiet period
│   └── jobs/                    # 2 个上游 job + 2 个 notify 下游 job
└── scripts/
    ├── _qa_env.py               # .env.qa 解析/写入/DB URL 推导
    ├── init_env.py              # 生成隔离配置
    ├── ensure_db.py             # 建库
    ├── doctor.py                # 预检
    ├── run_jenkins_e2e.py       # 真实 Jenkins E2E
    └── ai_check.py              # 可选 DeepSeek 连通性检查
```
