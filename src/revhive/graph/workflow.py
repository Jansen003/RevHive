"""LangGraph workflow for multi-agent code review.

Default backend: MiMo (https://api.xiaomimimo.com/v1).
"""

import importlib.util
import json
import logging
import os
import glob
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from langgraph.graph import StateGraph, END, START

from revhive.agents import (
    StyleAgent,
    SecurityAgent,
    PerformanceAgent,
    LogicAgent,
    RepoAgent,
    RefactorAgent,
    FixAgent,
    TestAgent,
    DocAgent,
    CoordinatorAgent,
)
from revhive.agents.base import BaseReviewAgent, AgentResult, SEVERITY_ORDER
from revhive.config import RevHiveConfig, load_config

logger = logging.getLogger(__name__)

# Agent class registry — maps YAML agent names to their class.
# To add a new agent: (1) add entry here, (2) add a state field below.
_AGENT_CLASSES: dict[str, type] = {
    "style":       StyleAgent,
    "security":    SecurityAgent,
    "performance": PerformanceAgent,
    "logic":       LogicAgent,
    "repo":        RepoAgent,
    "refactor":    RefactorAgent,
    "fix":         FixAgent,
    "test":        TestAgent,
    "doc":         DocAgent,
}


def load_plugins(plugin_dir: str = "plugins") -> dict[str, type]:
    """Load custom agent plugins from a directory.

    Each .py file in *plugin_dir* can define an agent class that extends
    :class:`BaseReviewAgent`. The class must be named ``Agent`` or have
    a ``PLUGIN_NAME`` attribute specifying the registry name.

    Returns a dict mapping plugin names to agent classes.
    """
    plugins: dict[str, type] = {}
    plugin_path = Path(plugin_dir)
    if not plugin_path.is_dir():
        return plugins

    for py_file in plugin_path.glob("*.py"):
        if py_file.name.startswith("_"):
            continue
        try:
            spec = importlib.util.spec_from_file_location(f"plugin_{py_file.stem}", py_file)
            if spec is None or spec.loader is None:
                continue
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)

            # Look for an Agent class or any BaseReviewAgent subclass
            agent_cls = getattr(module, "Agent", None)
            if agent_cls is None:
                for attr_name in dir(module):
                    attr = getattr(module, attr_name)
                    if (isinstance(attr, type) and issubclass(attr, BaseReviewAgent)
                            and attr is not BaseReviewAgent):
                        agent_cls = attr
                        break

            if agent_cls is not None:
                name = getattr(agent_cls, "PLUGIN_NAME", py_file.stem)
                plugins[name] = agent_cls
                logger.info("Loaded plugin agent: %s from %s", name, py_file)
        except Exception as exc:
            logger.warning("Failed to load plugin %s: %s", py_file, exc)

    return plugins


@dataclass
class ReviewState:
    """State shared across the review workflow.

    Each agent writes to its own field so that LangGraph's shallow-merge
    semantics work correctly with concurrent runners.
    """
    code: str = ""
    file_path: str = ""
    style_result: Optional[AgentResult] = None
    security_result: Optional[AgentResult] = None
    performance_result: Optional[AgentResult] = None
    logic_result: Optional[AgentResult] = None
    repo_result: Optional[AgentResult] = None
    refactor_result: Optional[AgentResult] = None
    fix_result: Optional[AgentResult] = None
    test_result: Optional[AgentResult] = None
    doc_result: Optional[AgentResult] = None
    final_result: Optional[AgentResult] = None
    plugin_results: dict[str, AgentResult] = field(default_factory=dict)


# Reverse-lookup: agent name → ReviewState field name.
_STATE_ATTR_MAP: dict[str, str] = {name: f"{name}_result" for name in _AGENT_CLASSES}


class CodeReviewWorkflow:
    """Orchestrates the multi-agent code review using LangGraph."""

    def __init__(self, model: Optional[str] = None, config: Optional[RevHiveConfig] = None, plugin_dir: str = "plugins",
                 api_key: Optional[str] = None, base_url: Optional[str] = None):
        self.config = config or load_config()
        _api_key = api_key or os.getenv("LLM_API_KEY")
        _base_url = base_url or os.getenv("LLM_BASE_URL", "https://api.xiaomimimo.com/v1")

        # Load built-in + plugin agents
        all_agents = dict(_AGENT_CLASSES)
        plugins = load_plugins(plugin_dir)
        all_agents.update(plugins)
        _model = model or self.config.model or os.getenv("LLM_MODEL", "mimo-v2.5-pro")

        common_kwargs = {"model": _model, "api_key": _api_key, "base_url": _base_url, "request_timeout": 120}

        # Only instantiate agents that are enabled in the config.
        self.agents: dict[str, object] = {}
        for name, cls in all_agents.items():
            if self.config.is_agent_enabled(name):
                self.agents[name] = cls(**common_kwargs)

        self.coordinator = CoordinatorAgent(**common_kwargs)
        self.graph = self._build_graph()

    def _build_graph(self) -> StateGraph:
        """Build the LangGraph workflow with only enabled agents."""
        workflow = StateGraph(ReviewState)

        for name in self.agents:
            workflow.add_node(f"{name}_review", self._make_runner(name))

        review_nodes = [f"{name}_review" for name in self.agents]
        workflow.add_node("coordinate", self._run_coordinate)

        for node in review_nodes:
            workflow.add_edge(START, node)
            workflow.add_edge(node, "coordinate")

        workflow.add_edge("coordinate", END)
        return workflow.compile()

    def _make_runner(self, agent_name: str):
        """Return an async runner that reviews with the named agent."""
        agent = self.agents[agent_name]
        is_plugin = agent_name not in _STATE_ATTR_MAP

        async def _run(state: ReviewState) -> dict:
            result = await self._safe_review(agent, state)
            # Apply severity threshold filtering if configured.
            threshold = self.config.get_severity_threshold(agent_name)
            if threshold is not None and result.findings:
                min_level = SEVERITY_ORDER.get(threshold.value, 99)
                result.findings = [f for f in result.findings if SEVERITY_ORDER.get(f.severity.value, 99) <= min_level]
            if is_plugin:
                plugins = dict(state.plugin_results)
                plugins[agent_name] = result
                return {"plugin_results": plugins}
            return {_STATE_ATTR_MAP[agent_name]: result}

        return _run

    async def _safe_review(self, agent, state: ReviewState) -> AgentResult:
        """Run a single agent review, returning a failure result on exception
        rather than crashing the entire workflow."""
        try:
            return await agent.review(state.code, state.file_path)
        except Exception as exc:
            logger.exception("%s failed: %s", agent.name, exc)
            return AgentResult(
                agent_name=agent.name,
                summary=f"Agent error: {exc}",
            )

    async def _run_coordinate(self, state: ReviewState) -> dict:
        """Collect results from all enabled agents and synthesize."""
        results = []
        for name in self.agents:
            # Built-in agents have dedicated state fields
            if name in _STATE_ATTR_MAP:
                r = getattr(state, _STATE_ATTR_MAP[name], None)
            else:
                # Plugin agents use the plugin_results dict
                r = state.plugin_results.get(name)
            if r is not None:
                results.append(r)
        final = await self.coordinator.synthesize(results)
        return {"final_result": final}

    async def run(self, code: str, file_path: str = "") -> AgentResult:
        """Run the full review workflow."""
        initial_state = ReviewState(code=code, file_path=file_path)
        final_state = await self.graph.ainvoke(initial_state)
        return final_state.get("final_result", AgentResult(agent_name="System", summary="No results"))

    @staticmethod
    def _validate_diff_ref(diff_ref: str) -> None:
        """Validate that diff_ref contains only safe characters for git."""
        import re
        if '..' in diff_ref or not re.match(r'^[a-zA-Z0-9._/~^:-]+$', diff_ref):
            raise ValueError(f"Invalid diff reference: {diff_ref}")

    async def run_from_diff(self, diff_ref: str) -> AgentResult:
        """Run review on a git diff."""
        import asyncio as _asyncio
        self._validate_diff_ref(diff_ref)
        proc = await _asyncio.create_subprocess_exec(
            "git", "diff", diff_ref,
            stdout=_asyncio.subprocess.PIPE,
            stderr=_asyncio.subprocess.PIPE,
            cwd=os.getcwd(),
        )
        stdout, stderr = await proc.communicate()
        if proc.returncode != 0:
            raise RuntimeError(f"git diff failed: {stderr.decode()}")
        return await self.run(code=stdout.decode(), file_path=f"diff:{diff_ref}")

    async def run_on_repo(self, repo_path: str, file_patterns: list[str] = None) -> list[AgentResult]:
        """Run review on an entire repository. High token consumption scenario.

        Scans all matching files, runs 9 agents per file, and produces
        a consolidated repository-level report.
        """
        if file_patterns is None:
            file_patterns = [
                "**/*.py", "**/*.js", "**/*.jsx", "**/*.mjs",
                "**/*.ts", "**/*.tsx", "**/*.go", "**/*.rs",
                "**/*.java", "**/*.c", "**/*.cpp", "**/*.h",
                "**/*.hpp", "**/*.rb", "**/*.php", "**/*.swift", "**/*.kt",
            ]

        files = []
        for pattern in file_patterns:
            files.extend(glob.glob(str(Path(repo_path) / pattern), recursive=True))

        # Apply ignore patterns from config.
        files = [f for f in files if not self.config.should_ignore(f)]

        _MAX_FILE_SIZE = 1 * 1024 * 1024  # 1 MB
        results = []
        for f in files[:50]:
            try:
                if Path(f).stat().st_size > _MAX_FILE_SIZE:
                    logger.info("Skipping %s (exceeds 1 MB limit)", f)
                    continue
                code = Path(f).read_text(encoding="utf-8", errors="ignore")
            except (OSError, UnicodeDecodeError) as exc:
                logger.warning("Skipping %s: %s", f, exc)
                continue
            result = await self.run(code=code, file_path=f)
            results.append(result)

        return results

    async def run_ci_mode(self, diff_ref: str = "HEAD~1") -> AgentResult:
        """CI/CD integration mode — runs full review on every PR.

        Designed for automated pipeline: git hook / GitHub Action / GitLab CI.
        Runs all 9 agents + coordinator + repo-level scan.
        """
        diff_result = await self.run_from_diff(diff_ref)

        import asyncio as _asyncio
        self._validate_diff_ref(diff_ref)
        proc = await _asyncio.create_subprocess_exec(
            "git", "diff", "--name-only", diff_ref,
            stdout=_asyncio.subprocess.PIPE,
            stderr=_asyncio.subprocess.PIPE,
            cwd=os.getcwd(),
        )
        stdout, _ = await proc.communicate()

        _MAX_FILE_SIZE = 1 * 1024 * 1024  # 1 MB
        full_results = [diff_result]
        for file in stdout.decode().strip().split("\n"):
            if file and os.path.exists(file):
                try:
                    if Path(file).stat().st_size > _MAX_FILE_SIZE:
                        logger.info("Skipping %s (exceeds 1 MB limit)", file)
                        continue
                    code = Path(file).read_text(encoding="utf-8")
                except (OSError, UnicodeDecodeError) as exc:
                    logger.warning("Skipping %s: %s", file, exc)
                    continue
                result = await self.run(code=code, file_path=file)
                full_results.append(result)

        final = await self.coordinator.synthesize(full_results)
        return final


@dataclass
class ReviewReport:
    """Formatted review report."""
    result: AgentResult

    def to_markdown(self) -> str:
        """Render the review result as a concise Markdown report.

        Critical/High findings are shown in full. Medium are listed by title.
        Low are summarized as a count. Full details are in a collapsed section.
        """
        lines = [
            "# RevHive Review Report\n",
            "## 📊 Overview\n",
            self.result.summary,
            f"\n**Total Findings:** {len(self.result.findings)}\n",
        ]

        critical_high = [f for f in self.result.findings if f.severity.value in ("critical", "high")]
        medium = [f for f in self.result.findings if f.severity.value == "medium"]
        low = [f for f in self.result.findings if f.severity.value == "low"]

        # Critical & High — full detail
        if critical_high:
            lines.append("\n## ⚠️ Critical & High Findings\n")
            for f in critical_high:
                emoji = "🔴" if f.severity.value == "critical" else "🟠"
                lines.append(f"### {emoji} [{f.severity.value.upper()}] {f.title}")
                if f.line_number is not None:
                    lines.append(f"**Line:** {f.line_number}")
                lines.append(f"\n{f.description}")
                if f.suggestion:
                    lines.append(f"\n**Suggestion:** {f.suggestion}")
                lines.append("")

        # Medium — title only
        if medium:
            lines.append(f"\n## 🟡 Medium ({len(medium)})\n")
            for f in medium:
                loc = f" (`{f.file_path}:{f.line_number}`)" if f.file_path and f.line_number else ""
                lines.append(f"- {f.title}{loc}")

        # Low — count only
        if low:
            lines.append(f"\n## 🟢 Low ({len(low)})\n")
            lines.append(f"{len(low)} low-severity issues found. Expand below for details.\n")

        # Full details in collapsed section
        all_findings = self.result.findings
        if all_findings:
            lines.append("\n<details><summary>📋 Full Findings Detail</summary>\n")
            categories: dict[str, list] = {}
            for f in all_findings:
                categories.setdefault(f.agent, []).append(f)
            for agent, findings in categories.items():
                lines.append(f"\n### {agent} ({len(findings)} issues)\n")
                for f in findings:
                    emoji = {"critical": "🔴", "high": "🟠", "medium": "🟡", "low": "🟢"}.get(f.severity.value, "⚪")
                    lines.append(f"#### {emoji} [{f.severity.value.upper()}] {f.title}")
                    if f.line_number is not None:
                        lines.append(f"**Line:** {f.line_number}")
                    lines.append(f"\n{f.description}")
                    if f.suggestion:
                        lines.append(f"\n**Suggestion:** {f.suggestion}")
                    lines.append("")
            lines.append("</details>")

        return "\n".join(lines)

    def to_json(self) -> str:
        """Render the review result as a JSON string."""
        data = {
            "summary": self.result.summary,
            "total_findings": len(self.result.findings),
            "findings": [
                {
                    "agent": f.agent,
                    "severity": f.severity.value,
                    "title": f.title,
                    "line": f.line_number,
                    "description": f.description,
                    "suggestion": f.suggestion,
                }
                for f in self.result.findings
            ],
        }
        return json.dumps(data, indent=2, ensure_ascii=False)
