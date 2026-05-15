"""EXPERIMENTAL: Team-level batch processing engine.

Not integrated into the main workflow. May be removed or redesigned.

Runs continuous code review across multiple repositories for an entire team.
This is the primary driver for high-volume token consumption."""

import asyncio
import logging
import os
import warnings
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

from revhive.graph.workflow import CodeReviewWorkflow

logger = logging.getLogger(__name__)


@dataclass
class RepoConfig:
    """Configuration for a monitored repository."""
    path: str
    name: str
    file_patterns: list[str] = field(default_factory=lambda: [
        "**/*.py", "**/*.js", "**/*.jsx", "**/*.mjs",
        "**/*.ts", "**/*.tsx", "**/*.go", "**/*.rs",
        "**/*.java", "**/*.c", "**/*.cpp", "**/*.h",
        "**/*.hpp", "**/*.rb", "**/*.php", "**/*.swift", "**/*.kt",
    ])
    review_interval_minutes: int = 60
    max_files_per_scan: int = 100
    enabled_modes: list[str] = field(default_factory=lambda: [
        "review",
        "fix",
        "test",
        "doc",
    ])


@dataclass
class TeamConfig:
    """Team-level configuration."""
    team_name: str
    repos: list[RepoConfig]
    deep_review_enabled: bool = True
    deep_review_schedule: str = "daily"
    ci_integration: bool = True
    daily_token_budget: int = 10_000_000


class TeamBatchProcessor:
    """Processes code reviews across multiple repos for an entire team.

    Token consumption breakdown (conservative estimates):
    ┌──────────────────────────────────────────────────────────┐
    │ Scenario                   │ Tokens/event  │ Events/day  │
    ├──────────────────────────────────────────────────────────┤
    │ Single file 9-agent review│   35,000      │ ×80 files   │
    │ Auto-fix generation       │   50,000      │ ×40 files   │
    │ Test suite generation     │   40,000      │ ×30 files   │
    │ Doc generation            │   20,000      │ ×30 files   │
    │ Multi-turn deep review    │  120,000      │ ×10 files   │
    │ Repo-level scan (full)    │ 1,500,000     │ ×2 repos    │
    │ CI/CD per PR              │   80,000      │ ×15 PRs     │
    ├──────────────────────────────────────────────────────────┤
    │ DAILY TOTAL               │              │ ~10,000,000  │
    └──────────────────────────────────────────────────────────┘
    """

    def __init__(self, config: TeamConfig, model: Optional[str] = None):
        warnings.warn("TeamBatchProcessor is EXPERIMENTAL and may be removed or redesigned.", FutureWarning, stacklevel=2)
        self.config = config
        self.workflow = CodeReviewWorkflow(model=model)
        self._model = model or self.workflow.config.model or os.getenv("LLM_MODEL", "mimo-v2.5-pro")
        self._semaphore = asyncio.Semaphore(3)

        # Pre-create agent instances for modes that bypass the workflow.
        common_kwargs = {
            "model": self._model,
            "api_key": os.getenv("LLM_API_KEY"),
            "base_url": os.getenv("LLM_BASE_URL"),
        }
        from revhive.agents.fix_agent import FixAgent
        from revhive.agents.test_agent import TestAgent
        from revhive.agents.doc_agent import DocAgent
        self._fix_agent = FixAgent(**common_kwargs)
        self._test_agent = TestAgent(**common_kwargs)
        self._doc_agent = DocAgent(**common_kwargs)

    async def run_daily_cycle(self) -> dict:
        """Execute a full daily review cycle across all repos."""
        results = {
            "date": datetime.now().isoformat(),
            "team": self.config.team_name,
            "repos": {},
            "total_tokens_used": 0,
        }

        for repo in self.config.repos:
            repo_result = await self._process_repo(repo)
            results["repos"][repo.name] = repo_result
            results["total_tokens_used"] += repo_result["tokens_used"]

        results["budget_remaining"] = max(0, self.config.daily_token_budget - results["total_tokens_used"])
        return results

    async def _process_repo(self, repo: RepoConfig) -> dict:
        """Process a single repository through all enabled modes."""
        result = {
            "tokens_used": 0,
            "files_reviewed": 0,
            "modes": {},
        }

        files = self._collect_files(repo)
        result["total_files"] = len(files)

        for mode in repo.enabled_modes:
            mode_result = await self._run_mode(mode, files[:repo.max_files_per_scan], repo)
            result["modes"][mode] = mode_result
            result["tokens_used"] += mode_result["tokens_used"]
            result["files_reviewed"] += mode_result.get("files_processed", 0)

        if self.config.deep_review_enabled:
            all_findings = []
            for mode_data in result["modes"].values():
                all_findings.extend(mode_data.get("critical_findings", []))

            if all_findings:
                try:
                    from revhive.agents.conversation_reviewer import ConversationReviewer
                    reviewer = ConversationReviewer(
                        model=self._model,
                        api_key=os.getenv("LLM_API_KEY"),
                        base_url=os.getenv("LLM_BASE_URL"),
                    )
                    deep_result = await reviewer.deep_review(
                        code="",
                        initial_findings=all_findings[:10],
                        file_path=repo.name,
                    )
                    result["modes"]["deep_review"] = {
                        "findings_analyzed": len(deep_result.findings),
                        "tokens_used": deep_result.token_usage,
                    }
                    result["tokens_used"] += deep_result.token_usage
                except Exception as exc:
                    logger.error("BatchProcessor: deep review failed for %s: %s", repo.name, exc)

        return result

    async def _run_mode(self, mode: str, files: list[str], repo: RepoConfig) -> dict:
        """Run a specific review mode on a set of files."""
        result = {"tokens_used": 0, "files_processed": 0, "critical_findings": []}

        for i in range(0, len(files), 10):
            batch = files[i:i+10]
            tasks = [self._throttled_process(f, mode) for f in batch]
            batch_results = await asyncio.gather(*tasks, return_exceptions=True)

            for r in batch_results:
                if isinstance(r, dict):
                    result["tokens_used"] += r["tokens_used"]
                    result["files_processed"] += 1
                    result["critical_findings"].extend(r.get("critical_findings", []))

        return result

    async def _throttled_process(self, file_path: str, mode: str) -> dict:
        """Acquire the concurrency semaphore before processing a file."""
        async with self._semaphore:
            return await self._process_single_file(file_path, mode)

    async def _process_single_file(self, file_path: str, mode: str) -> dict:
        """Process a single file in a specific mode."""
        try:
            code = Path(file_path).read_text(encoding="utf-8", errors="ignore")
        except Exception:
            return {"tokens_used": 0, "critical_findings": []}

        try:
            if mode == "review":
                result = await self.workflow.run(code=code, file_path=file_path)
                critical = [f for f in result.findings if f.severity.value in ("high", "critical")]
                return {"tokens_used": result.token_usage, "critical_findings": critical}

            elif mode == "fix":
                result = await self._fix_agent.review(code, file_path)
                return {"tokens_used": result.token_usage}

            elif mode == "test":
                result = await self._test_agent.review(code, file_path)
                return {"tokens_used": result.token_usage}

            elif mode == "doc":
                result = await self._doc_agent.review(code, file_path)
                return {"tokens_used": result.token_usage}

        except Exception as exc:
            logger.error("BatchProcessor: LLM call failed for %s (%s mode): %s", file_path, mode, exc)
            return {"tokens_used": 0, "critical_findings": []}

        return {"tokens_used": 0}

    def _collect_files(self, repo: RepoConfig) -> list[str]:
        """Collect all files matching patterns in a repo."""
        import glob
        files = []
        for pattern in repo.file_patterns:
            files.extend(glob.glob(str(Path(repo.path) / pattern), recursive=True))
        return [f for f in files if not any(ign in f for ign in [
            "node_modules", ".git", "__pycache__", "vendor", ".venv", "dist", "build"
        ])]

