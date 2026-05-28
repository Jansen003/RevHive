"""CLI entry point for RevHive."""

import asyncio
import logging
import sys
from pathlib import Path

import click

from revhive import __version__
from revhive.config import load_config
from revhive.graph.workflow import CodeReviewWorkflow, ReviewReport

logger = logging.getLogger(__name__)


@click.group()
@click.version_option(version=__version__)
def cli():
    """RevHive - AI-powered multi-agent code review system."""
    pass


def _run_with_timeout(coro, timeout: int = 600):
    """Run an async coroutine with a timeout (default 10 minutes)."""
    try:
        return asyncio.run(asyncio.wait_for(coro, timeout=timeout))
    except asyncio.TimeoutError:
        click.echo("Error: Review timed out after 10 minutes.", err=True)
        sys.exit(1)


@cli.command()
@click.option("--file", "-f", type=click.Path(exists=True), help="Path to file for review")
@click.option("--diff", "-d", "diff_ref", help="Git diff reference (e.g., HEAD~1)")
@click.option("--model", "-m", default=None, help="LLM model to use")
@click.option("--output", "-o", type=click.Path(), help="Output file path")
@click.option("--format", "fmt", type=click.Choice(["markdown", "json"]), default="markdown")
@click.option("--timeout", "-t", default=600, type=int, help="Review timeout in seconds")
def review(file: str, diff_ref: str, model: str, output: str, fmt: str, timeout: int):
    """Run code review on a file or git diff."""
    cfg = load_config()

    try:
        if file:
            if cfg.should_ignore(file):
                click.echo(f"Skipping {file} — matches ignore pattern in .revhive.yml")
                return
            try:
                code = Path(file).read_text(encoding="utf-8")
            except UnicodeDecodeError:
                click.echo(f"Error: {file} is not a valid text file (encoding issue).", err=True)
                sys.exit(1)
            except (PermissionError, OSError) as exc:
                click.echo(f"Error: cannot read {file}: {exc}", err=True)
                sys.exit(1)
            workflow = CodeReviewWorkflow(model=model, config=cfg)
            result = _run_with_timeout(workflow.run(code=code, file_path=file), timeout=timeout)
        elif diff_ref:
            workflow = CodeReviewWorkflow(model=model, config=cfg)
            result = _run_with_timeout(workflow.run_from_diff(diff_ref), timeout=timeout)
        else:
            click.echo("Please specify --file or --diff to review.")
            return
    except ValueError as e:
        msg = str(e)
        if "API key" in msg or "api_key" in msg:
            click.echo(
                "\n  No API key found. Try the demo first — no key needed:\n\n"
                "    revhive demo\n\n"
                "  Or set your LLM API key:\n\n"
                "    export LLM_API_KEY=your-api-key\n\n"
                "  Supported: MiMo, OpenAI, DeepSeek, Anthropic, Qwen, GLM, Kimi\n"
                "  Docs: https://github.com/Jansen003/RevHive#quick-start\n",
                err=True,
            )
            sys.exit(1)
        raise

    report_obj = ReviewReport(result)
    if fmt == "json":
        report = report_obj.to_json()
    else:
        report = report_obj.to_markdown()

    if output:
        Path(output).write_text(report, encoding="utf-8")
        click.echo(f"Report saved to {output}")
    else:
        click.echo(report)


def _render_demo_rich(result) -> None:
    """Render demo review as a rich terminal panel."""
    from rich.console import Console
    from rich.panel import Panel
    from rich.text import Text
    from rich import box

    from revhive.agents.base import Severity

    console = Console()
    score = result.risk_score or 0
    findings = result.findings

    # Risk score line
    if score <= 20:
        emoji, level, bar_color = "✅", "LOW", "green"
    elif score <= 50:
        emoji, level, bar_color = "⚠️", "MEDIUM", "yellow"
    elif score <= 80:
        emoji, level, bar_color = "🔴", "HIGH", "orange3"
    else:
        emoji, level, bar_color = "🚨", "CRITICAL", "red"

    filled = int(score / 100 * 40)
    bar = "█" * filled + "░" * (40 - filled)

    risk_text = Text()
    risk_text.append(f"{emoji} Risk Score: {score}/100 {level}\n", style=f"bold {bar_color}")
    risk_text.append(f"{bar} {score}%\n", style=bar_color)

    # Severity counts
    counts: dict[str, int] = {}
    for f in findings:
        counts[f.severity.value] = counts.get(f.severity.value, 0) + 1

    sev_icons = {"critical": "🔴", "high": "🟠", "medium": "🟡", "low": "🟢"}
    sev_line = Text()
    for sev in ("critical", "high", "medium", "low"):
        if sev in counts:
            sev_line.append(f"{sev_icons[sev]} {sev.upper()} ×{counts[sev]}   ")
    sev_line.append("\n")

    # Build body
    body = Text()
    body.append_text(risk_text)
    body.append("\n")
    body.append_text(sev_line)
    body.append("\n")

    # Critical / High findings table
    critical_high = [f for f in findings if f.severity in (Severity.CRITICAL, Severity.HIGH)]
    if critical_high:
        body.append("── Critical/High Findings ──────────────────────\n", style="dim")
        for f in critical_high:
            icon = "🔴" if f.severity == Severity.CRITICAL else "🟠"
            body.append(f"{icon} {f.title}\n", style="bold")
            loc = f.agent
            if f.line_number:
                loc += f" · Line {f.line_number}"
            body.append(f"  {loc}\n", style="dim")
            desc = f.description[:100] + ("..." if len(f.description) > 100 else "")
            body.append(f"  {desc}\n")
        body.append("\n")

    # Medium — titles only
    medium = [f for f in findings if f.severity == Severity.MEDIUM]
    if medium:
        body.append("── Medium Findings ────────────────────────────\n", style="dim")
        for f in medium:
            body.append(f"🟡 {f.title}\n")
        body.append("\n")

    # Low — count only
    low_count = counts.get("low", 0)
    if low_count:
        body.append(f"🟢 Low: {low_count} finding{'s' if low_count != 1 else ''} (not shown)\n\n")

    # Footer
    agent_count = len({f.agent for f in findings})
    tokens = result.token_usage or 0
    body.append(f"{agent_count} agents · {len(findings)} findings", style="dim")
    if tokens:
        body.append(f" · ~{tokens:,} tokens", style="dim")
    body.append("\n")
    body.append("⚡ Demo mode — no API key required", style="dim cyan")
    body.append("\n")
    body.append("🖥️ Automate on every PR → ", style="cyan")
    body.append("https://github.com/apps/revhive-bot", style="cyan link https://github.com/apps/revhive-bot")

    panel = Panel(body, title="[bold]🛡️ RevHive Review Report[/bold]", box=box.ROUNDED)
    console.print(panel)

    # Star prompt
    star_text = Text()
    star_text.append("\n⭐ Like RevHive? ", style="bold")
    star_text.append("Star us on GitHub", style="bold yellow link https://github.com/Jansen003/RevHive")
    star_text.append(" — helps more developers find this tool!", style="dim")
    console.print(star_text)


@cli.command()
@click.option("--format", "fmt", type=click.Choice(["markdown", "json"]), default="markdown")
@click.option("--output", "-o", type=click.Path(), help="Output file path")
def demo(fmt: str, output: str):
    """Run a demo review with mock findings (no API key needed)."""
    from revhive.demo import DemoReviewWorkflow
    from revhive.graph.workflow import ReviewReport

    demo_wf = DemoReviewWorkflow()
    result = demo_wf.run()

    if fmt == "json" or output:
        report_obj = ReviewReport(result)
        report = report_obj.to_json() if fmt == "json" else report_obj.to_markdown()
        if output:
            Path(output).write_text(report, encoding="utf-8")
            click.echo(f"Report saved to {output}")
        else:
            click.echo(report)
        return

    # Rich terminal output
    try:
        _render_demo_rich(result)
    except ImportError:
        click.echo(ReviewReport(result).to_markdown())


if __name__ == "__main__":
    cli()
