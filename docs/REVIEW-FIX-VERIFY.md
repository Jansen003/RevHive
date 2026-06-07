# RevHive Review → Fix → Verify 闭环设计方案

> 版本: v1.0 | 日期: 2026-05-11
> 目标: 实现 `review → fix → verify` 闭环，让 RevHive 从"只诊断"变成"能治病"

---

## 一、用户交互设计

### 目标命令流

```bash
# 1. Review — 发现问题，结果自动持久化
revhive review -f app.py
# → 发现 5 个问题（结果已保存到 .revhive/last-review.json）

# 2. Fix — 选择性修复，diff 预览，确认写入
revhive fix --finding 2,4
# → 读取上次 review 结果
# → 针对第 2、4 个 finding 调 LLM 生成修复代码
# → 展示 diff 预览（红色删除/绿色新增）
# → 确认后写入文件

# 3. Verify — 重跑 review，确认修复有效
revhive verify -f app.py
# → 重新审查
# → 对比上次结果：哪些 finding 消失了、哪些还在、新增了什么
# → 输出修复验证报告
```

### 辅助命令

```bash
revhive fix --finding 1-3,5      # 范围选择
revhive fix --auto               # 自动修复 Critical + High
revhive fix --dry-run --finding 2  # 只看 diff 不写入
revhive fix --finding 2 --yes    # 跳过确认直接写入

revhive verify --compare .revhive/review-20260511-200000.json  # 和指定报告对比
```

---

## 二、当前架构缺口 & 修补方案

### 缺口 1: ReviewFinding 数据模型太薄

**现状:**
```python
@dataclass
class ReviewFinding:
    agent: str
    severity: Severity
    title: str
    description: str
    line_number: Optional[int] = None
    code_snippet: Optional[str] = None    # 声明了但从未填充
    suggestion: Optional[str] = None       # 一句话文本，不可执行
```

**改为:**
```python
@dataclass
class ReviewFinding:
    # 原有字段
    agent: str
    severity: Severity
    title: str
    description: str
    line_number: Optional[int] = None

    # 新增字段
    file_path: Optional[str] = None        # 来源文件（从 ReviewState 传入）
    end_line: Optional[int] = None         # 结束行号（多行问题）
    code_snippet: Optional[str] = None     # 问题代码片段（新填充）
    suggestion: Optional[str] = None       # 保留：简短修复建议

    # Fix 专用字段（仅 fix agent 填充）
    fix_diff: Optional[str] = None         # unified diff 格式的修复代码
    fix_description: Optional[str] = None  # 修复说明（为什么要这样改）
```

**关键改动点:**

1. `ReviewState.file_path` → 传入每个 `ReviewFinding.file_path`
   - 在 `_make_runner()` 中，review 完成后给所有 finding 打上 `file_path`
2. `_parse_findings()` 扩展：提取 `EndLine` 字段 + `FixDiff` 代码块
3. `ReviewReport.to_json()` 增加 `file_path`、`end_line`、`fix_diff` 字段

### 缺口 2: FixAgent 输出被丢弃

**现状:** `_parse_findings()` 只提取 5 个 bullet 字段，FixAgent 输出的完整修复代码被丢弃。

**改法:** 给 FixAgent（及未来 TestAgent/DocAgent）单独的解析路径。

```python
# base.py 中新增
def _parse_findings(self, response: str) -> list[ReviewFinding]:
    findings = self._parse_bullet_findings(response)   # 原有逻辑
    # 如果是代码生成型 agent，额外提取代码块
    if self._is_code_gen_agent():
        code_blocks = self._extract_code_blocks(response)
        for i, block in enumerate(code_blocks):
            if i < len(findings):
                findings[i].fix_diff = block
            else:
                # 多余的代码块附加到最后一个 finding
                if findings:
                    findings[-1].fix_diff = (findings[-1].fix_diff or "") + "\n" + block
    return findings

def _is_code_gen_agent(self) -> bool:
    return self.name in ("FixAgent",)

def _extract_code_blocks(self, response: str) -> list[str]:
    """提取 ```lang ... ``` 代码块"""
    import re
    pattern = r'```(?:\w+)?\n(.*?)```'
    return re.findall(pattern, response, re.DOTALL)
```

**注意:** 这个提取逻辑是启发式的，不需要 100% 准确。fix 命令本身会再次调 LLM 生成精确 diff，这里只是提供参考。

### 缺口 3: 跨命令状态持久化

**方案:** `.revhive/` 目录存储 review 结果

```
.revhive/
├── last-review.json          # 最近一次 review 结果（fix/verify 读取）
├── reviews/                  # 历史记录（可选，用于趋势分析）
│   ├── 2026-05-11T20-00-00.json
│   └── 2026-05-11T21-30-00.json
└── config.yml                # 项目级配置（已有，.revhive.yml）
```

**`last-review.json` 结构:**

```json
{
  "version": 1,
  "timestamp": "2026-05-11T20:00:00+08:00",
  "file_path": "app.py",
  "file_hash": "sha256:abc123...",
  "summary": "...",
  "risk_score": 65,
  "total_findings": 5,
  "findings": [
    {
      "id": 1,
      "agent": "SecurityAgent",
      "severity": "critical",
      "title": "SQL Injection",
      "description": "...",
      "file_path": "app.py",
      "line": 12,
      "end_line": 15,
      "suggestion": "Use parameterized queries.",
      "fix_diff": "--- a/app.py\n+++ b/app.py\n@@ -12,3 +12,3 @@...",
      "fix_description": "Replace string interpolation with parameterized query"
    }
  ]
}
```

**实现:**

```python
# 新文件: src.revhive/storage.py
import json
import hashlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from revhive.agents.base import AgentResult, ReviewFinding

_STORAGE_DIR = ".revhive"
_LAST_REVIEW_FILE = "last-review.json"

def _storage_path() -> Path:
    return Path.cwd() / _STORAGE_DIR

def ensure_storage() -> Path:
    """确保 .revhive/ 目录存在，返回路径。"""
    p = _storage_path()
    p.mkdir(exist_ok=True)
    return p

def file_hash(path: str) -> str:
    """计算文件 SHA256，用于 verify 时判断文件是否被修改。"""
    return "sha256:" + hashlib.sha256(
        Path(path).read_bytes()
    ).hexdigest()

def save_review(result: AgentResult, file_path: str) -> Path:
    """保存 review 结果到 .revhive/last-review.json"""
    ensure_storage()
    data = {
        "version": 1,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "file_path": file_path,
        "file_hash": file_hash(file_path) if Path(file_path).exists() else "",
        "summary": result.summary,
        "risk_score": result.risk_score,
        "total_findings": len(result.findings),
        "findings": [
            {
                "id": i + 1,
                "agent": f.agent,
                "severity": f.severity.value,
                "title": f.title,
                "description": f.description,
                "file_path": f.file_path,
                "line": f.line_number,
                "end_line": f.end_line,
                "suggestion": f.suggestion,
                "fix_diff": f.fix_diff,
                "fix_description": f.fix_description,
            }
            for i, f in enumerate(result.findings)
        ],
    }
    out = _storage_path() / _LAST_REVIEW_FILE
    out.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    return out

def load_last_review() -> Optional[dict]:
    """读取最近一次 review 结果。"""
    f = _storage_path() / _LAST_REVIEW_FILE
    if not f.is_file():
        return None
    return json.loads(f.read_text(encoding="utf-8"))
```

---

## 三、新 CLI 命令设计

### 3.1 `review` 命令增强

**改动:** 默认自动保存结果到 `.revhive/last-review.json`，不再需要 `--save` 参数。

```python
# main.py — review 命令末尾增加保存逻辑
from revhive.storage import save_review

# ... 原有逻辑 ...
result = _run_with_timeout(workflow.run(code=code, file_path=file))

# 自动保存（新增）
saved_path = save_review(result, file or diff_ref or "unknown")
click.echo(f"📄 Review saved to {saved_path}", err=True)

# 输出报告（原有）
report_obj = ReviewReport(result)
# ...
```

**同时:** 给 finding 打上 file_path

```python
# workflow.py — _make_runner 中补充 file_path 传播
async def _run(state: ReviewState) -> dict:
    result = await self._safe_review(agent, state)
    # 给所有 finding 打上 file_path（新增）
    for f in result.findings:
        if not f.file_path:
            f.file_path = state.file_path
    # ... 原 severity filter 逻辑 ...
```

### 3.2 `fix` 命令（新增）

```python
@cli.command()
@click.option("--finding", "-n", "finding_ids", help="Finding IDs to fix (e.g., 2,4 or 1-3,5)")
@click.option("--auto", is_flag=True, help="Auto-fix Critical + High findings")
@click.option("--dry-run", is_flag=True, help="Show diff without writing")
@click.option("--yes", "-y", is_flag=True, help="Skip confirmation")
def fix(finding_ids: str, auto: bool, dry_run: bool, yes: bool):
    """Auto-fix selected findings from the last review."""
    from revhive.storage import load_last_review
    from revhive.fix import FixEngine

    # 1. 读取上次 review 结果
    review = load_last_review()
    if not review:
        click.echo("No review results found. Run `revhive review` first.")
        sys.exit(1)

    # 2. 选择要修复的 findings
    if auto:
        targets = [f for f in review["findings"]
                   if f["severity"] in ("critical", "high")]
    elif finding_ids:
        ids = _parse_finding_ids(finding_ids)
        targets = [f for f in review["findings"] if f["id"] in ids]
    else:
        # 交互式选择
        targets = _interactive_select(review["findings"])

    if not targets:
        click.echo("No findings selected for fix.")
        return

    # 3. 执行修复
    engine = FixEngine()
    fixes = _run_with_timeout(engine.fix(review, targets))

    # 4. 展示 diff + 确认
    for fix in fixes:
        click.echo(f"\n📝 {fix.finding_title}")
        click.echo(fix.colored_diff)  # 红绿 diff

        if dry_run:
            continue

        if not yes:
            if not click.confirm("Apply this fix?"):
                continue

        # 写入文件
        fix.apply()
        click.echo(f"✅ Applied fix to {fix.file_path}")

    # 5. 如果有修复被应用，提示 verify
    applied = [f for f in fixes if f.applied]
    if applied and not dry_run:
        click.echo(f"\n🔍 {len(applied)} fix(es) applied. "
                   f"Run `revhive verify` to confirm they work.")
```

### 3.3 `verify` 命令（新增）

```python
@cli.command()
@click.option("--file", "-f", type=click.Path(exists=True), help="File to verify")
@click.option("--compare", type=click.Path(), help="Previous review JSON to compare against")
def verify(file: str, compare: str):
    """Re-review and verify fixes from the last review."""
    from revhive.storage import load_last_review, save_review, file_hash

    # 1. 加载上次 review 结果
    previous = load_last_review()
    if compare:
        previous = json.loads(Path(compare).read_text(encoding="utf-8"))
    if not previous:
        click.echo("No previous review found. Run `revhive review` first.")
        sys.exit(1)

    target_file = file or previous.get("file_path", "")
    if not target_file or not Path(target_file).exists():
        click.echo(f"Cannot find file: {target_file}")
        sys.exit(1)

    # 2. 检查文件是否被修改（如果 hash 变了，说明有其他改动）
    old_hash = previous.get("file_hash", "")
    new_hash = file_hash(target_file)
    if old_hash and old_hash != new_hash:
        click.echo("⚠️  File has been modified since last review "
                   "(beyond RevHive fixes).", err=True)

    # 3. 重新 review
    click.echo("🔍 Re-running review...")
    code = Path(target_file).read_text(encoding="utf-8")
    cfg = load_config()
    workflow = CodeReviewWorkflow(config=cfg)
    result = _run_with_timeout(workflow.run(code=code, file_path=target_file))

    # 4. 对比
    current_titles = {f.title.lower().strip() for f in result.findings}
    previous_titles = {f["title"].lower().strip() for f in previous["findings"]}

    resolved = previous_titles - current_titles
    remaining = previous_titles & current_titles
    new_issues = current_titles - previous_titles

    # 5. 输出验证报告
    click.echo(f"\n{'='*50}")
    click.echo(f"📋 Verification Report for {target_file}")
    click.echo(f"{'='*50}\n")

    if resolved:
        click.echo(f"✅ Resolved ({len(resolved)}):")
        for title in sorted(resolved):
            click.echo(f"   ✓ {title}")

    if remaining:
        click.echo(f"\n⚠️  Still present ({len(remaining)}):")
        for title in sorted(remaining):
            click.echo(f"   ✗ {title}")

    if new_issues:
        click.echo(f"\n🆕 New findings ({len(new_issues)}):")
        for title in sorted(new_issues):
            click.echo(f"   + {title}")

    # Risk score 变化
    old_score = previous.get("risk_score", 0)
    new_score = result.risk_score or 0
    delta = new_score - old_score
    arrow = "↓" if delta < 0 else "↑" if delta > 0 else "→"
    click.echo(f"\n🎯 Risk Score: {old_score} → {new_score} ({arrow} {abs(delta)})")

    # 6. 保存新 review 结果
    save_review(result, target_file)
```

---

## 四、核心引擎: FixEngine

```python
# 新文件: src.revhive/fix/__init__.py
# 新文件: src.revhive/fix/engine.py

"""Fix engine: 生成、预览、应用代码修复。"""

import difflib
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from revhive.agents.base import AgentResult, ReviewFinding, Severity
from revhive.agents.fix_agent import FixAgent
from revhive.config import load_config


@dataclass
class FixResult:
    """单个 finding 的修复结果。"""
    finding_id: int
    finding_title: str
    file_path: str
    original_code: str
    fixed_code: str
    diff: str                  # unified diff
    colored_diff: str          # 终端带颜色的 diff
    applied: bool = False
    error: Optional[str] = None

    def apply(self) -> bool:
        """将修复写入文件。"""
        try:
            Path(self.file_path).write_text(self.fixed_code, encoding="utf-8")
            self.applied = True
            return True
        except Exception as e:
            self.error = str(e)
            return False


class FixEngine:
    """根据 review 结果生成代码修复。"""

    def __init__(self, model: Optional[str] = None):
        self.config = load_config()
        self.model = model or self.config.model or os.getenv("LLM_MODEL", "mimo-v2.5-pro")

    async def fix(self, review_data: dict, targets: list[dict]) -> list[FixResult]:
        """对选中的 findings 生成修复。

        策略:
        1. 如果 finding 已有 fix_diff（review 阶段 FixAgent 生成），直接用
        2. 否则，带原始代码调 LLM 生成修复
        """
        results = []
        file_path = review_data.get("file_path", "")

        # 按文件分组（为未来多文件支持做准备）
        for target in targets:
            result = await self._fix_single(target, file_path)
            results.append(result)

        return results

    async def _fix_single(self, finding: dict, file_path: str) -> FixResult:
        """修复单个 finding。"""
        fp = finding.get("file_path") or file_path
        if not Path(fp).exists():
            return FixResult(
                finding_id=finding["id"],
                finding_title=finding["title"],
                file_path=fp,
                original_code="",
                fixed_code="",
                diff="",
                colored_diff="",
                error=f"File not found: {fp}",
            )

        original = Path(fp).read_text(encoding="utf-8")

        # 策略 1: 已有 fix_diff，尝试应用
        if finding.get("fix_diff"):
            fixed = self._apply_unified_diff(original, finding["fix_diff"])
            if fixed is not None:
                diff, colored = self._compute_diff(original, fixed, fp)
                return FixResult(
                    finding_id=finding["id"],
                    finding_title=finding["title"],
                    file_path=fp,
                    original_code=original,
                    fixed_code=fixed,
                    diff=diff,
                    colored_diff=colored,
                )

        # 策略 2: 调 LLM 生成修复
        fixed_code = await self._llm_fix(finding, original, fp)
        diff, colored = self._compute_diff(original, fixed_code, fp)
        return FixResult(
            finding_id=finding["id"],
            finding_title=finding["title"],
            file_path=fp,
            original_code=original,
            fixed_code=fixed_code,
            diff=diff,
            colored_diff=colored,
        )

    async def _llm_fix(self, finding: dict, code: str, file_path: str) -> str:
        """调用 LLM 生成修复代码。"""
        api_key = os.getenv("LLM_API_KEY")
        base_url = os.getenv("LLM_BASE_URL", "https://api.xiaomimimo.com/v1")
        agent = FixAgent(model=self.model, api_key=api_key, base_url=base_url)

        # 构造精准的修复 prompt
        fix_prompt = f"""Fix this specific issue in the file `{file_path}`:

Issue: {finding['title']}
Severity: {finding['severity']}
Line: {finding.get('line', 'unknown')}
Description: {finding.get('description', '')}
Suggestion: {finding.get('suggestion', '')}

Original code:
```
{code}
```

Output the COMPLETE fixed file. Do not output anything else besides the fixed code."""

        from langchain_core.messages import SystemMessage, HumanMessage
        messages = [
            SystemMessage(content=agent.get_system_prompt()),
            HumanMessage(content=fix_prompt),
        ]
        response = await agent.llm.ainvoke(messages)
        return self._extract_code(response.content, code)

    def _extract_code(self, llm_response: str, original: str) -> str:
        """从 LLM 响应中提取修复后的完整代码。

        优先提取 ``` 代码块；如果没有，则返回原始代码（安全回退）。
        """
        import re
        blocks = re.findall(r'```(?:\w+)?\n(.*?)```', llm_response, re.DOTALL)
        if blocks:
            # 取最长的代码块（通常是完整文件）
            return max(blocks, key=len)
        return original  # 无法提取则不动文件

    @staticmethod
    def _apply_unified_diff(original: str, diff_text: str) -> Optional[str]:
        """尝试应用 unified diff。失败返回 None。"""
        import patch as patchlib  # pip install patch
        try:
            p = patchlib.from_string(diff_text)
            return p.apply(original)
        except Exception:
            return None

    @staticmethod
    def _compute_diff(original: str, fixed: str, file_path: str) -> tuple[str, str]:
        """计算 unified diff 和终端彩色 diff。"""
        orig_lines = original.splitlines(keepends=True)
        fixed_lines = fixed.splitlines(keepends=True)
        diff_lines = list(difflib.unified_diff(
            orig_lines, fixed_lines,
            fromfile=f"a/{file_path}",
            tofile=f"b/{file_path}",
        ))
        plain = "".join(diff_lines)

        # 终端彩色版本
        colored = []
        for line in diff_lines:
            if line.startswith("+") and not line.startswith("+++"):
                colored.append(f"\033[32m{line}\033[0m")  # green
            elif line.startswith("-") and not line.startswith("---"):
                colored.append(f"\033[31m{line}\033[0m")  # red
            elif line.startswith("@@"):
                colored.append(f"\033[36m{line}\033[0m")  # cyan
            else:
                colored.append(line)
        return plain, "".join(colored)
```

---

## 五、文件清单 & 改动范围

### 新增文件

| 文件 | 说明 |
|------|------|
| `src.revhive/storage.py` | Review 结果持久化（save/load/file_hash） |
| `src.revhive/fix/__init__.py` | fix 模块入口 |
| `src.revhive/fix/engine.py` | FixEngine 核心逻辑 |
| `tests/test_storage.py` | 存储层测试 |
| `tests/test_fix_engine.py` | 修复引擎测试 |

### 修改文件

| 文件 | 改动 |
|------|------|
| `src.revhive/agents/base.py` | ReviewFinding 增加 file_path/end_line/fix_diff/fix_description；`_parse_findings` 扩展 |
| `src.revhive/graph/workflow.py` | `_make_runner` 中传播 file_path；ReviewReport.to_json() 增加新字段；review 命令自动 save |
| `src.revhive/main.py` | 新增 fix/verify 命令；review 命令增加自动保存 |
| `src.revhive/demo.py` | mock findings 增加 file_path/end_line 字段 |
| `pyproject.toml` | 增加 `patch` 依赖（可选）；版本号 → 0.4.0 |

### 不改动的文件

- 所有 agent 的 system prompt（不改行为）
- config.py（不增加新配置项，一期够用）
- LangGraph workflow 拓扑（不改并行结构）

---

## 六、实施阶段

### Phase 1: 地基（必须先做）

**目标:** 数据模型 + 持久化，让 fix/verify 有数据可读

1. `ReviewFinding` 增加 4 个新字段
2. `_make_runner` 传播 `file_path` 到 finding
3. `storage.py` 实现 save/load
4. `review` 命令自动保存
5. `ReviewReport.to_json()` 序列化新字段
6. 测试

**验证:** `revhive review -f app.py` 后 `.revhive/last-review.json` 包含 file_path 和 finding id

### Phase 2: fix 命令

**目标:** 选择 finding → 调 LLM → diff 预览 → 确认写入

1. `FixEngine` 实现（策略 2 优先：LLM 生成修复）
2. `fix` CLI 命令（--finding/--auto/--dry-run/--yes）
3. finding ID 解析（`1-3,5` → `[1,2,3,5]`）
4. Rich diff 渲染（复用 rich 库）
5. 测试

**验证:** `revhive review -f app.py` → `revhive fix --finding 2` → 文件被修改，diff 正确

### Phase 3: verify 命令

**目标:** 重跑 review → 对比前后 → 验证报告

1. `verify` CLI 命令
2. 前后 finding 对比逻辑（按 title 匹配）
3. Risk Score 变化展示
4. 文件 hash 校验
5. 测试

**验证:** fix 后运行 `revhive verify`，看到 resolved/remaining/new 分组

### Phase 4: 优化（锦上添花）

1. FixAgent 输出捕获（策略 1：复用 review 阶段已生成的修复代码）
2. 交互式 finding 选择（TUI 界面）
3. `patch` 库应用 unified diff（策略 1 精确应用）
4. Git integration：fix 后自动 commit，verify 失败自动 revert
5. 多文件 fix（按文件分组批量处理）
6. `revhive fix --auto` CI 模式

---

## 七、依赖 & 风险

### 新增依赖

| 包 | 用途 | 必须？ |
|---|------|--------|
| `patch` | 应用 unified diff（策略 1） | 可选，策略 2 不需要 |

### 风险

| 风险 | 概率 | 影响 | 缓解 |
|------|------|------|------|
| LLM 生成的修复代码不正确 | 高 | 破坏用户代码 | diff 预览 + 确认机制；dry-run 模式 |
| LLM 修复不完整（漏掉行） | 中 | 部分修复 | verify 命令兜底；完整文件替换而非局部 patch |
| finding ID 跨 session 不稳定 | 低 | fix 选错目标 | 每次重新编号；用 title 匹配做冗余校验 |
| `.revhive/` 目录冲突 | 低 | 污染用户仓库 | `.gitignore` 建议；文档说明 |

### 安全边界

- fix 默认需要确认（`--yes` 才跳过）
- 写入前保留 `.revhive/backup/` 原始文件副本
- verify 检测到文件被外部修改时发出警告
- 不做 git commit（让用户自己决定是否提交）

---

## 八、版本规划

| 版本 | 内容 | 估计改动量 |
|------|------|-----------|
| v0.4.0 | Phase 1 + Phase 2 + Phase 3（完整闭环） | ~800 行新代码 |
| v0.4.1 | Phase 4 部分（FixAgent 输出捕获、交互式选择） | ~200 行 |
| v0.5.0 | Phase 4 完整（git integration、多文件、CI 模式） | ~500 行 |
