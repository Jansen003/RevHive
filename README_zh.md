# RevHive

[![Python](https://img.shields.io/badge/python-3.10%2B-blue)](https://www.python.org/)
[![License](https://img.shields.io/badge/license-BSL--1.1-blue)](LICENSE)
[![LangGraph](https://img.shields.io/badge/framework-LangGraph-orange)](https://langchain-ai.github.io/langgraph/)
[![MiMo](https://img.shields.io/badge/powered_by-MiMo-red)](https://platform.xiaomimimo.com)
[![Agents](https://img.shields.io/badge/agents-10-blue)]()
[![CI](https://github.com/Jansen003/RevHive/actions/workflows/ci.yml/badge.svg)](https://github.com/Jansen003/RevHive/actions)

**基于 Multi-Agent 协作的 AI 代码审查与安全扫描系统**

RevHive 部署 10 个专业 AI Agent — 9 个并行审查，1 个综合汇总 — 在代码进入生产环境之前捕获安全漏洞、性能瓶颈、逻辑 Bug 和风格问题。

- **结构化输出** — Agent 通过 Pydantic schema 返回结构化 JSON，不支持的 LLM 自动降级为正则解析
- **语义去重** — 标题匹配 + 关键词 Jaccard 相似度，防止不同 Agent 重复报告同一问题
- **LLM 冲突解决** — Coordinator 用 AI 解决多个 Agent 之间的矛盾判定

### 风险评分

每次审查都会输出一个风险评分（0-100），让你一眼判断是否可以合并：

| 分数 | 等级 | 含义 |
|------|------|------|
| 0-20 | ✅ LOW | 可以放心合并 |
| 21-50 | ⚠️ MEDIUM | 建议审查后再合并 |
| 51-80 | 🔴 HIGH | 修复后再合并 |
| 81-100 | 🚨 CRITICAL | 不建议合并 |

示例输出：

```
🚨 Risk Score: CRITICAL (91/100)

1 Critical · 1 High · 8 Medium · 11 Low
```

## 为什么选择 RevHive？

| 痛点 | RevHive 解决方案 |
|---|---|
| 人工 CR 每天耗时 1-2 小时 | 9 个 Agent 并行审查，30 秒内完成 |
| 人工审查容易遗漏 Bug | 每个 Agent 都是领域专家（安全/性能/逻辑...） |
| "LGTM" 文化让审查形同虚设 | 每个 PR 都有详尽、客观的审计报告 |
| 缺少团队级质量可见性 | 趋势分析持续追踪代码健康度 |

## RevHive vs Others

| Feature | RevHive | CodeRabbit | Sourcery | SonarQube | Copilot Review |
|---------|:---:|:---:|:---:|:---:|:---:|
| AI-driven review | ✅ | ✅ | ✅ | ❌ | ✅ |
| Multi-agent parallel | ✅ 10 | ❌ | ❌ | ❌ | ❌ |
| Chinese LLM support | ✅ 5 providers | ❌ | ❌ | ❌ | ❌ |
| Risk score (0-100) | ✅ | ✅ | ❌ | ✅ | ❌ |
| CLI local-first | ✅ | ❌ | ❌ | ❌ | ❌ |
| Demo mode (no API key) | ✅ | ❌ | ❌ | N/A | ❌ |
| PR inline comments | ✅ | ✅ | ✅ | ✅ | ✅ |
| Quality gate (status check) | ✅ | ❌ | ❌ | ✅ | ❌ |
| IDE integration | 🔜 | ❌ | ✅ | ✅ | ✅ |
| Open source | ✅ BSL | Partial | ❌ | ✅ | ❌ |
| Self-hosted | ✅ | ❌ | ❌ | ✅ | ❌ |

> 🔜 = 即将推出

## 架构设计

```
┌─────────────┐
│  Coordinator │ ← 汇总结果，解决冲突评级
└──────┬──────┘
       │ 收集 9 个并行 Agent 的结果
       ▼
  Style  Security  Perf  Logic  Repo  Refactor  Fix  Test  Doc
```

**ConversationReviewer** 按需对单个发现进行多轮深度审查——挑战假设、探索替代方案、通过 5 轮对话测试边缘情况。用于批处理模式中的严重/高危发现。

### 全部 10 个 Agent

| Agent | 职责 |
|---|---|
| **StyleAgent** | 命名规范、代码格式、注释文档 |
| **SecurityAgent** | SQL 注入、XSS、密钥泄露、弱加密、认证缺陷 |
| **PerformanceAgent** | N+1 查询、内存泄漏、算法复杂度 |
| **LogicAgent** | 边界条件、异常处理、竞态条件、类型安全 |
| **RepoAgent** | 设计模式、SOLID 原则、模块结构、可测试性 |
| **RefactorAgent** | 设计模式、代码转换、渐进式重构 |
| **FixAgent** | 完整修复代码生成、根因分析、回归风险评估 |
| **TestAgent** | 单元测试、边界用例、安全回归测试 |
| **DocAgent** | API 文档、架构说明、使用示例 |
| **Coordinator** | 语义去重、LLM 冲突解决、风险评分、报告生成 |

## 快速开始

**方式一：CLI（30 秒上手）**

```bash
pip install revhive-ai
revhive demo                        # 无需 API Key
export LLM_API_KEY=your-api-key
revhive review --file src/main.py   # 真实审查
```

**方式二：Docker**

```bash
docker build -t revhive .
docker run --rm -e LLM_API_KEY=your-api-key -v $(pwd):/code revhive review --file /code/src/main.py
```

**方式三：GitHub App（自动 PR 审查）**

[安装 GitHub App](https://github.com/apps/revhive-bot) → 每个 PR 自动审查，无需 CLI。

## Demo 模式

RevHive 内置完整的 **Demo 模式**，无需 API Key、无需网络、零成本即可运行完整的多 Agent 审查流程。

```bash
python examples/sample_review.py
```

生成与真实 MiMo 调用结构完全一致的审查报告：
- 20+ 条模拟发现，覆盖全部 9 个审查 Agent
- 按严重程度排序（CRITICAL / HIGH / MEDIUM / LOW）
- 支持 Markdown 和 JSON 两种输出格式

## 支持的 LLM 后端

| 服务商 | 模型 | 配置 |
|---|---|---|
| **MiMo (小米)** | `mimo-v2.5-pro` | `LLM_BASE_URL=https://api.xiaomimimo.com/v1` |
| OpenAI | `gpt-4o` | `LLM_BASE_URL=https://api.openai.com/v1` |
| DeepSeek | `deepseek-chat` | `LLM_BASE_URL=https://api.deepseek.com/v1` |
| Qwen (通义) | `qwen-plus` | `LLM_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1` |
| GLM (智谱) | `glm-4` | `LLM_BASE_URL=https://open.bigmodel.cn/api/paas/v4` |
| Kimi | `kimi` | `LLM_BASE_URL=https://api.moonshot.cn/v1` |
| **Anthropic** | `claude-sonnet-4-20250514` | `pip install -e ".[anthropic]"`，设置 `ANTHROPIC_API_KEY` |

**快速预设：** 将 `LLM_MODEL` 设为预设名（如 `openai`、`deepseek`、`qwen`），RevHive 自动配置 base URL。显式设置 `LLM_BASE_URL` 优先级更高。

MiMo 是**默认且推荐的后端**。RevHive 针对 MiMo 的 Token 经济性和模型能力进行了优化。

## 支持的语言

RevHive 的 LLM 驱动 Agent 可以审查任何语言的代码。目前已针对以下语言优化：

| 语言 | 扩展名 | 安全模式 | 性能模式 |
|------|--------|---------|---------|
| Python | .py | ✅ 完整 | ✅ 完整 |
| JavaScript/TypeScript | .js .jsx .mjs .ts .tsx | ✅ 完整 | ✅ 完整 |
| Go | .go | ✅ 完整 | ✅ 完整 |
| Rust | .rs | ✅ 完整 | ✅ 完整 |
| Java | .java | ✅ 完整 | ✅ 完整 |
| C/C++ | .c .cpp .h .hpp | ✅ 核心 | ⚠️ 基础 |
| Ruby | .rb | ✅ 核心 | ⚠️ 基础 |
| PHP | .php | ✅ 完整 | ⚠️ 基础 |
| Swift | .swift | ✅ 核心 | ⚠️ 基础 |
| Kotlin | .kt | ✅ 核心 | ⚠️ 基础 |

其他语言通过 LLM 理解支持，但可能缺少专门的检测模式。

## 环境变量

| 变量 | 必填 | 默认值 | 说明 |
|---|---|---|---|
| `LLM_API_KEY` | **是** | — | LLM 服务商的 API Key |
| `LLM_BASE_URL` | 否 | `https://api.xiaomimimo.com/v1` | LLM API 端点 |
| `LLM_MODEL` | 否 | `mimo-v2.5-pro` | 模型名称 |

## 配置

在项目根目录创建 `.revhive.yml`：

```yaml
model: mimo-v2.5-pro

agents:
  style:
    enabled: true
  security:
    enabled: true
    severity_threshold: medium   # 只报告 medium 及以上
  performance:
    enabled: true
  logic:
    enabled: true
  repo:
    enabled: true
  refactor:
    enabled: true
  fix:
    enabled: true
  test:
    enabled: true
  doc:
    enabled: false               # 禁用文档 Agent

ignore:                          # glob 模式 — ** 匹配任意层级子目录
  - "*.min.js"
  - "*.min.css"
  - "vendor/**"
  - "node_modules/**"
  - "migrations/**"
  - "__pycache__/**"
  - ".git/**"
  - ".venv/**"
```

## GitHub App 集成

[安装 GitHub App](https://github.com/apps/revhive-bot) 即可实现自动 PR 审查，每个 PR 自动审查并生成详细审查报告，无需 CLI。

```yaml
# .github/workflows/code-review.yml
name: AI Code Review
on:
  pull_request:
    types: [opened, synchronize]
jobs:
  review:
    runs-on: ubuntu-latest
    permissions:
      contents: read
      pull-requests: write
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - run: pip install revhive-ai
      - name: Run RevHive Review
        env:
          LLM_API_KEY: ${{ secrets.MIMO_API_KEY }}
          LLM_BASE_URL: https://api.xiaomimimo.com/v1
          LLM_MODEL: mimo-v2.5-pro
        run: |
          revhive review --diff HEAD~1 --format markdown --output review_report.md
      - name: Post Review Comment
        uses: actions/github-script@v7
        with:
          script: |
            const fs = require('fs');
            const report = fs.readFileSync('review_report.md', 'utf8');
            github.rest.issues.createComment({
              issue_number: context.issue.number,
              owner: context.repo.owner,
              repo: context.repo.repo,
              body: report
            });
```

## 项目结构

```
src/revhive/
  agents/          # 10 个专业审查 Agent
  graph/           # LangGraph 工作流编排
  utils/           # 工具模块
  team/            # 批量处理引擎
  analysis/        # 历史趋势分析
  demo.py           # Demo 模式（无需 API Key）
  main.py           # CLI 入口
tests/              # 37 测试覆盖 agents、workflow、demo
examples/           # 开箱即用的示例
```

## 安全

RevHive 重视自身代码安全：

- **依赖扫描** — CI 中每次推送和 PR 都运行 `pip-audit`，检测依赖中的已知 CVE。
- **静态分析** — `bandit` 扫描源码中的常见安全问题（硬编码密钥、不安全反序列化、注入风险）。
- **Docker 加固** — 容器以非 root 用户（`appuser`）运行。敏感文件（`.env`、`*.pem`、`.git/`）通过 `.dockerignore` 排除。

本地运行安全检查：

```bash
pip install pip-audit bandit
pip-audit
bandit -r src/ -ll --skip B101
```

## 贡献

欢迎贡献！详见 [CONTRIBUTING.md](CONTRIBUTING.md)。

## License

BSL 1.1 — 详见 [LICENSE](LICENSE)。2030-05-12 自动转为 Apache 2.0。

