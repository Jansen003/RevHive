# RevHive

[![PyPI](https://img.shields.io/pypi/v/revhive-ai)](https://pypi.org/project/revhive-ai/)
[![Downloads](https://img.shields.io/pypi/dm/revhive-ai)](https://pypi.org/project/revhive-ai/)
[![Python](https://img.shields.io/badge/python-3.10%2B-blue)](https://www.python.org/)
[![License](https://img.shields.io/badge/license-BSL--1.1-blue)](LICENSE)
[![CI](https://github.com/Jansen003/RevHive/actions/workflows/ci.yml/badge.svg)](https://github.com/Jansen003/RevHive/actions)

> **10 个 AI Agent 并行审查你的代码，30 秒出报告。安全漏洞、性能瓶颈、逻辑 Bug，一个都不放过。**

```bash
pip install revhive-ai && revhive demo   # 30 秒体验，无需 API Key
```

**RevHive** 是一个 AI 驱动的多 Agent 代码审查系统。9 个专业 Agent 并行审查，1 个 Coordinator 汇总去重、解决冲突、计算风险评分。

- **10 个专业 Agent** — 安全、性能、逻辑、风格、测试、文档……各司其职
- **风险评分 0-100** — 一眼看出这个 PR 能不能合并
- **Demo 模式** — 不需要 API Key，30 秒跑完完整流程
- **CLI 优先** — 本地运行，数据不出你的电脑

- **Structured Output** — Agents return structured JSON via Pydantic schemas, with regex fallback for unsupported LLMs
- **Semantic Deduplication** — Title matching + keyword Jaccard similarity prevents duplicate findings across agents
- **LLM Conflict Resolution** — Coordinator uses AI to resolve contradictory assessments between agents

### Risk Score

Every review outputs a risk score (0-100) so you know at a glance whether it's safe to merge:

| Score | Level | Meaning |
|-------|-------|---------|
| 0-20 | ✅ LOW | Safe to merge |
| 21-50 | ⚠️ MEDIUM | Review recommended before merge |
| 51-80 | 🔴 HIGH | Fix before merge |
| 81-100 | 🚨 CRITICAL | Do not merge |

Example output:

```
🚨 Risk Score: CRITICAL (91/100)

1 Critical · 1 High · 8 Medium · 11 Low
```

## Why RevHive?

| 你的痛点 | RevHive 的解法 |
|---|---|
| 人工 Code Review 每天花 1-2 小时 | 9 个 Agent 并行审查，30 秒出报告 |
| 人工审查容易遗漏细节 | 每个 Agent 是领域专家（安全、性能、逻辑……） |
| "LGTM" 文化让 Bug 溜进去 | 每个 PR 都有完整的客观审计 |
| 不知道团队代码质量趋势 | 跟踪代码健康度变化 |

## 为什么值得 Star？

- 这是目前**唯一支持中文 LLM（MiMo、DeepSeek、Qwen、GLM、Kimi）的代码审查工具**
- CLI 完全免费，BYOK（自带 API Key），数据不出本地
- Demo 模式让你 30 秒看到完整效果，零成本评估
- 我们在持续迭代，Star 了就能收到更新通知

## Pricing

| Tier | Price | Reviews | Agents | Concurrent | Inline Comments | Commit Status | History | Slack | Support |
|------|-------|---------|--------|------------|:---:|:---:|:---:|:---:|:---:|
| **Free** | $0 | 50/mo | 4 core | 1 | — | — | — | — | Community |
| **Pro** | $12/mo | Unlimited | All 9 | 10 | ✅ | ✅ | 30 days | — | Email (48h) |
| **Business** | $25/mo | Unlimited | All 9 | 100 | ✅ | ✅ | Permanent | ✅ | Priority (4h SLA) |

**CLI mode is free forever** — `pip install revhive-ai`, bring your own LLM key, run locally or in CI.

**GitHub App** uses the tiers above. Start free, upgrade when you need inline annotations, commit status gates, and all 9 agents.

All plans are **BYOK** — you pay your LLM provider directly. RevHive charges for orchestration, not tokens.

**Typical LLM cost per PR review:** ~$0.05 with DeepSeek · ~$0.05–0.15 with MiMo · ~$0.10–0.30 with GPT-4o · Free with MiMo credits. You control spend through your own LLM account.

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

> 🔜 = Coming soon

## Architecture

```
┌─────────────┐
│  Coordinator │ ← Synthesizes findings, resolves conflicts
└──────┬──────┘
       │ collects results from 9 parallel agents
       ▼
  Style  Security  Perf  Logic  Repo  Refactor  Fix  Test  Doc
```

### All 9 Review Agents + Coordinator

| Agent | Role |
|---|---|
| **StyleAgent** | Naming conventions, formatting, documentation |
| **SecurityAgent** | SQL injection, XSS, secrets, weak crypto, auth flaws |
| **PerformanceAgent** | N+1 queries, memory leaks, algorithmic complexity |
| **LogicAgent** | Edge cases, error handling, race conditions, type safety |
| **RepoAgent** | Design patterns, SOLID principles, module structure, testability |
| **RefactorAgent** | Design patterns, code transformation, incremental migration |
| **FixAgent** | Generates complete corrected code with root cause analysis |
| **TestAgent** | Unit tests, edge case tests, security regression tests |
| **DocAgent** | API docs, architecture docs, usage examples |
| **Coordinator** | Deduplicates (semantic), resolves conflicts via LLM, calculates risk score, generates report |

## Quick Start

**Option A: CLI (30 seconds)**

```bash
pip install revhive-ai              # 1. 安装
revhive demo                        # 2. 跑 Demo（无需 API Key）
revhive review --file src/main.py   # 3. 真实审查（需要 API Key）
```

**Option B: Docker**

```bash
docker build -t revhive .
docker run --rm -e LLM_API_KEY=your-api-key -v $(pwd):/code revhive review --file /code/src/main.py
```

**Option C: GitHub App (automatic PR reviews)**

[Install the GitHub App](https://github.com/apps/revhive-bot), paste your LLM API key in the dashboard (auto-created on install), and every PR gets reviewed automatically. Starts free (50 reviews/mo, 4 core agents). Upgrade to **Pro ($12/mo)** for all 9 agents, inline comments, and commit status gates, or **Business ($25/mo)** for Slack notifications, permanent history, and priority support. **DeepSeek is the default provider** in the dashboard — ~$0.05/review.

## Demo Mode

RevHive ships with a fully functional **demo mode** that runs the complete multi-agent pipeline with mock responses. No API key, no network, no cost — perfect for evaluation.

```bash
python examples/sample_review.py
```

This produces a realistic review report identical in structure to a live MiMo-backed run, including:
- 20+ simulated findings across all 9 review agents
- Severity-ordered report (CRITICAL / HIGH / MEDIUM / LOW)
- Markdown and JSON output formats

## Supported LLM Backends

| Provider | Model | Cost / Review | Setup |
|---|---|---|---|
| **DeepSeek** | `deepseek-chat` | ~$0.05 | `LLM_BASE_URL=https://api.deepseek.com/v1` |
| **MiMo (Xiaomi)** | `mimo-v2.5-pro` | ~$0.05–0.15 (free credits) | `LLM_BASE_URL=https://api.xiaomimimo.com/v1` |
| OpenAI | `gpt-4o` | ~$0.10–0.30 | `LLM_BASE_URL=https://api.openai.com/v1` |
| Qwen (Alibaba) | `qwen-plus` | ~$0.05–0.10 | `LLM_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1` |
| Anthropic | `claude-sonnet-4-20250514` | ~$0.15–0.40 | `pip install -e ".[anthropic]"`, set `ANTHROPIC_API_KEY` |

**Quick preset:** Set `LLM_MODEL` to a preset name (e.g., `deepseek`, `openai`, `qwen`) and RevHive auto-configures the base URL. Explicit `LLM_BASE_URL` takes priority.

**CLI default:** MiMo (`mimo-v2.5-pro`). **GitHub App dashboard default:** DeepSeek (`deepseek-chat`) — the cheapest option at ~$0.05/review.

## Supported Languages

RevHive's LLM-powered agents can review code in any language. Currently optimized for:

| Language | Extensions | Security Patterns | Performance Patterns |
|----------|-----------|-------------------|---------------------|
| Python | .py | ✅ Full | ✅ Full |
| JavaScript/TypeScript | .js .jsx .mjs .ts .tsx | ✅ Full | ✅ Full |
| Go | .go | ✅ Full | ✅ Full |
| Rust | .rs | ✅ Full | ✅ Full |
| Java | .java | ✅ Full | ✅ Full |
| C/C++ | .c .cpp .h .hpp | ✅ Core | ⚠️ Basic |
| Ruby | .rb | ✅ Core | ⚠️ Basic |
| PHP | .php | ✅ Full | ⚠️ Basic |
| Swift | .swift | ✅ Core | ⚠️ Basic |
| Kotlin | .kt | ✅ Core | ⚠️ Basic |

Other languages are supported via LLM understanding but may have fewer specialized patterns.

## Environment Variables

| Variable | Required | Default | Description |
|---|---|---|---|
| `LLM_API_KEY` | **Yes** | — | API key for the LLM provider |
| `LLM_BASE_URL` | No | `https://api.xiaomimimo.com/v1` | LLM API endpoint |
| `LLM_MODEL` | No | `mimo-v2.5-pro` | Model name |

## Configuration

Create `.revhive.yml` in your project root:

```yaml
model: mimo-v2.5-pro

agents:
  style:
    enabled: true
  security:
    enabled: true
    severity_threshold: medium   # only report medium and above
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
    enabled: false               # disable documentation agent

ignore:                          # glob patterns — ** matches any depth
  - "*.min.js"
  - "*.min.css"
  - "vendor/**"
  - "node_modules/**"
  - "migrations/**"
  - "__pycache__/**"
  - ".git/**"
  - ".venv/**"
```

## GitHub App Integration

[Install the GitHub App](https://github.com/apps/revhive-bot) for automatic PR reviews. Every PR gets a detailed review report — no CLI needed.

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
          LLM_API_KEY: ${{ secrets.LLM_API_KEY }}       # DeepSeek is ~$0.05/review
          LLM_BASE_URL: https://api.deepseek.com/v1
          LLM_MODEL: deepseek-chat
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

## Project Structure

```
src/revhive/
  agents/          # 10 specialized agents (9 review + coordinator)
  graph/           # LangGraph workflow orchestration
  utils/           # Utility modules
  team/            # Batch processing engine
  analysis/        # Historical trend analysis
  demo.py           # Demo mode (no API key required)
  main.py           # CLI entry point
tests/              # 54+ tests covering agents, workflow, demo, dedup, integration
examples/           # Ready-to-run examples
```

## Security

RevHive takes its own security seriously:

- **Dependency scanning** — `pip-audit` runs in CI on every push and PR to catch known CVEs in dependencies.
- **Static analysis** — `bandit` scans the source code for common security issues (hardcoded secrets, unsafe deserialization, injection risks).
- **Docker hardening** — the container runs as a non-root user (`appuser`). Sensitive files (`.env`, `*.pem`, `.git/`) are excluded via `.dockerignore`.

To run security checks locally:

```bash
pip install pip-audit bandit
pip-audit
bandit -r src/ -ll --skip B101
```

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). All contributions welcome!

## License

BSL 1.1 — see [LICENSE](LICENSE). Converts to Apache 2.0 on 2030-05-12.





