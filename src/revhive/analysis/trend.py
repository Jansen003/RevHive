"""EXPERIMENTAL: Historical code quality trend analysis.

Not integrated into the main workflow. May be removed or redesigned.

Scans every commit in a date range, running full review on each version.
Extremely token-intensive: N commits × full review per commit."""

import subprocess
import warnings
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional

from revhive.graph.workflow import CodeReviewWorkflow


@dataclass
class TrendPoint:
    """A single data point in the quality trend."""
    commit: str
    date: str
    total_findings: int
    critical_count: int
    high_count: int
    medium_count: int
    low_count: int
    token_usage: int


class TrendAnalyzer:
    """Analyzes code quality trends over time by reviewing historical commits.

    Token consumption:
    - Per commit: full repo scan ~1,500,000 tokens
    - 30-day analysis with ~5 commits/day = 150 commits
    - 150 × 1,500,000 = 225,000,000 tokens (one-time historical scan)
    - Ongoing daily: ~5 new commits × 1,500,000 = 7,500,000 tokens/day
    """

    def __init__(self, repo_path: str, model: Optional[str] = None):
        warnings.warn("TrendAnalyzer is EXPERIMENTAL and may be removed or redesigned.", FutureWarning, stacklevel=2)
        self.repo_path = repo_path
        self.workflow = CodeReviewWorkflow(model=model)

    async def analyze_range(self, days: int = 30, files_per_commit: int = 10) -> list[TrendPoint]:
        """Analyze code quality over the past N days.

        Uses ``git show <commit>:<path>`` to read historical files read-only,
        so the working tree is never modified.
        """
        commits = self._get_commits(days)
        trend = []

        for commit_hash, commit_date in commits:
            files = self._get_changed_files(commit_hash)[:files_per_commit]
            total_findings = 0
            severity_counts = {"critical": 0, "high": 0, "medium": 0, "low": 0}
            total_tokens = 0

            for f in files:
                code = self._read_file_at_commit(commit_hash, f)
                if code is None:
                    continue
                result = await self.workflow.run(code=code, file_path=f)
                total_findings += len(result.findings)
                total_tokens += result.token_usage
                for finding in result.findings:
                    severity_counts[finding.severity.value] = severity_counts.get(finding.severity.value, 0) + 1

            trend.append(TrendPoint(
                commit=commit_hash[:8],
                date=commit_date,
                total_findings=total_findings,
                critical_count=severity_counts["critical"],
                high_count=severity_counts["high"],
                medium_count=severity_counts["medium"],
                low_count=severity_counts["low"],
                token_usage=total_tokens,
            ))

        return trend

    def _read_file_at_commit(self, commit_hash: str, file_path: str) -> str | None:
        """Read a file at a specific commit without modifying the working tree."""
        result = subprocess.run(
            ["git", "show", f"{commit_hash}:{file_path}"],
            capture_output=True, text=True, cwd=self.repo_path,
        )
        if result.returncode != 0:
            return None
        return result.stdout

    def _get_commits(self, days: int) -> list[tuple[str, str]]:
        """Get commit hashes and dates for the past N days."""
        since = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
        result = subprocess.run(
            ["git", "log", f"--since={since}", "--format=%H %ad", "--date=short"],
            capture_output=True, text=True, cwd=self.repo_path
        )
        commits = []
        for line in result.stdout.strip().split("\n"):
            if line:
                parts = line.split(" ", 1)
                commits.append((parts[0], parts[1]))
        return commits

    def _get_changed_files(self, commit_hash: str) -> list[str]:
        """Get files changed in a commit."""
        result = subprocess.run(
            ["git", "diff-tree", "--no-commit-id", "--name-only", "-r", commit_hash],
            capture_output=True, text=True, cwd=self.repo_path
        )
        return [f for f in result.stdout.strip().split("\n") if f]
