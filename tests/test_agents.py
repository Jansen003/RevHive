"""Unit tests for RevHive agents."""

import pytest
from revhive.agents.base import (
    BaseReviewAgent,
    ReviewFinding,
    Severity,
    AgentResult,
)
from revhive.agents.style_agent import StyleAgent
from revhive.agents.security_agent import SecurityAgent
from revhive.agents.performance_agent import PerformanceAgent
from revhive.agents.logic_agent import LogicAgent
from revhive.agents.repo_agent import RepoAgent
from revhive.agents.refactor_agent import RefactorAgent
from revhive.agents.fix_agent import FixAgent
from revhive.agents.test_agent import TestAgent
from revhive.agents.doc_agent import DocAgent
from revhive.agents.coordinator import CoordinatorAgent


# ---------------------------------------------------------------------------
# Dataclass / data model tests
# ---------------------------------------------------------------------------


def test_review_finding_creation():
    finding = ReviewFinding(
        agent="SecurityAgent",
        severity=Severity.HIGH,
        title="SQL Injection",
        description="User input directly interpolated into SQL query",
        line_number=10,
        suggestion="Use parameterized queries",
    )
    assert finding.agent == "SecurityAgent"
    assert finding.severity == Severity.HIGH
    assert finding.line_number == 10


def test_agent_result_defaults():
    result = AgentResult(agent_name="Test")
    assert result.findings == []
    assert result.summary == ""
    assert result.token_usage == 0


def test_severity_enum():
    assert Severity.LOW.value == "low"
    assert Severity.MEDIUM.value == "medium"
    assert Severity.HIGH.value == "high"
    assert Severity.CRITICAL.value == "critical"


# ---------------------------------------------------------------------------
# Agent instantiation tests
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "agent_cls, expected_name",
    [
        (StyleAgent, "StyleAgent"),
        (SecurityAgent, "SecurityAgent"),
        (PerformanceAgent, "PerformanceAgent"),
        (LogicAgent, "LogicAgent"),
        (RepoAgent, "RepoAgent"),
        (RefactorAgent, "RefactorAgent"),
        (FixAgent, "FixAgent"),
        (TestAgent, "TestAgent"),
        (DocAgent, "DocAgent"),
        (CoordinatorAgent, "CoordinatorAgent"),
    ],
)
def test_agent_instantiation(agent_cls, expected_name):
    agent = agent_cls(model="mimo-v2.5-pro", api_key="test-key")
    assert agent.name == expected_name
    assert isinstance(agent, BaseReviewAgent)


# ---------------------------------------------------------------------------
# System prompt tests (no API call needed)
# ---------------------------------------------------------------------------


def test_style_agent_prompt():
    agent = StyleAgent(model="mimo-v2.5-pro", api_key="test-key")
    prompt = agent.get_system_prompt()
    assert "code style" in prompt.lower()
    assert "naming" in prompt.lower()


def test_security_agent_prompt():
    agent = SecurityAgent(model="mimo-v2.5-pro", api_key="test-key")
    prompt = agent.get_system_prompt()
    assert "injection" in prompt.lower()
    assert "authentication" in prompt.lower()


def test_performance_agent_prompt():
    agent = PerformanceAgent(model="mimo-v2.5-pro", api_key="test-key")
    prompt = agent.get_system_prompt()
    assert "performance" in prompt.lower() or "n+1" in prompt.lower()


def test_logic_agent_prompt():
    agent = LogicAgent(model="mimo-v2.5-pro", api_key="test-key")
    prompt = agent.get_system_prompt()
    assert "edge case" in prompt.lower() or "error handling" in prompt.lower()


def test_all_agents_have_unique_focus():
    """Ensure every agent declares a distinct review focus."""
    agents = [
        StyleAgent(model="mimo-v2.5-pro", api_key="test-key"),
        SecurityAgent(model="mimo-v2.5-pro", api_key="test-key"),
        PerformanceAgent(model="mimo-v2.5-pro", api_key="test-key"),
        LogicAgent(model="mimo-v2.5-pro", api_key="test-key"),
        RepoAgent(model="mimo-v2.5-pro", api_key="test-key"),
        RefactorAgent(model="mimo-v2.5-pro", api_key="test-key"),
        FixAgent(model="mimo-v2.5-pro", api_key="test-key"),
        TestAgent(model="mimo-v2.5-pro", api_key="test-key"),
        DocAgent(model="mimo-v2.5-pro", api_key="test-key"),
    ]
    foci = [a.get_review_focus() for a in agents]
    assert len(foci) == len(set(foci))  # no duplicates


# ---------------------------------------------------------------------------
# Parse findings tests
# ---------------------------------------------------------------------------


SAMPLE_RESPONSE = """- Severity: HIGH
- Title: SQL Injection Risk
- Line: 12
- Description: User input directly interpolated into SQL query.
- Suggestion: Use parameterized queries with placeholder syntax.

- Severity: LOW
- Title: Missing docstring
- Line: 25
- Description: The function has no docstring.
- Suggestion: Add a docstring describing parameters and return value.
"""


def test_parse_findings():
    agent = StyleAgent(model="mimo-v2.5-pro", api_key="test-key")
    findings = agent._parse_findings(SAMPLE_RESPONSE)
    assert len(findings) == 2
    assert findings[0].severity == Severity.HIGH
    assert findings[0].title == "SQL Injection Risk"
    assert findings[0].line_number == 12
    assert findings[1].severity == Severity.LOW


def test_parse_findings_empty():
    agent = SecurityAgent(model="mimo-v2.5-pro", api_key="test-key")
    findings = agent._parse_findings("No issues found.")
    # Fallback: non-empty text is wrapped as a single finding so output is never lost
    assert len(findings) == 1
    assert findings[0].severity == Severity.LOW
    assert "No issues found" in findings[0].title


def test_parse_findings_truly_empty():
    agent = SecurityAgent(model="mimo-v2.5-pro", api_key="test-key")
    findings = agent._parse_findings("")
    assert findings == []


# ---------------------------------------------------------------------------
# Coordinator tests (no LLM needed)
# ---------------------------------------------------------------------------


def test_coordinator_synthesize():
    coordinator = CoordinatorAgent(model="mimo-v2.5-pro", api_key="test-key")
    results = [
        AgentResult(
            agent_name="SecurityAgent",
            findings=[
                ReviewFinding(
                    agent="SecurityAgent",
                    severity=Severity.HIGH,
                    title="SQL Injection",
                    description="...",
                ),
            ],
            summary="Done",
            token_usage=1000,
        ),
        AgentResult(
            agent_name="StyleAgent",
            findings=[
                ReviewFinding(
                    agent="StyleAgent",
                    severity=Severity.LOW,
                    title="Missing docstring",
                    description="...",
                ),
            ],
            summary="Done",
            token_usage=500,
        ),
        AgentResult(
            agent_name="SecurityAgent",
            findings=[
                ReviewFinding(
                    agent="SecurityAgent",
                    severity=Severity.HIGH,
                    title="SQL Injection",  # duplicate
                    description="...",
                ),
            ],
            summary="Done",
            token_usage=300,
        ),
    ]

    import asyncio
    result = asyncio.run(coordinator.synthesize(results))

    assert result.agent_name == "CoordinatorAgent"
    assert len(result.findings) == 2  # duplicates removed
    assert result.token_usage == 1800  # 1000 + 500 + 300
    assert "SQL Injection" in result.findings[0].title  # HIGH comes first


def test_coordinator_empty_input():
    coordinator = CoordinatorAgent(model="mimo-v2.5-pro", api_key="test-key")
    import asyncio
    result = asyncio.run(coordinator.synthesize([]))
    assert result.agent_name == "CoordinatorAgent"
    assert result.findings == []
    assert result.token_usage == 0


def test_coordinator_risk_score():
    """Verify risk score calculation for various severity combinations."""
    import asyncio

    coordinator = CoordinatorAgent(model="mimo-v2.5-pro", api_key="test-key")

    def _make_findings(severities):
        descs = [
            "User input passed to subprocess without sanitization allows shell injection",
            "Database query concatenates strings instead of using parameterized placeholders",
            "Module imports os.path but never uses it anywhere in the codebase",
            "Two goroutines write to same map without mutex causing data corruption",
            "AWS secret key AKIA1234567890 hardcoded in config.py line 42",
            "File descriptor opened in loop but never closed causing resource exhaustion",
            "Array index off by one when iterating range(len(items))",
            "MD5 hash used for password storage instead of bcrypt or argon2",
            "HTTP request has no timeout causing thread to block indefinitely",
            "Function calculateTotal uses camelCase but module uses snake_case",
            "ORM loads related objects inside loop instead of using select_related",
            "Deprecated logging.warn() called instead of logging.warning()",
            "Redis cache key collision causes stale data served to different users",
            "JWT token expiry not validated allowing replay attacks after logout",
            "CORS header wildcard allows any origin to make authenticated requests",
            "Log injection via unsanitized user-controlled string in log message",
            "XML parser vulnerable to billion laughs denial of service attack",
            "Redirect URL not validated enabling open redirect phishing attacks",
        ]
        # Use distinct titles so dedup doesn't merge them
        titles = [
            "Shell injection via subprocess",
            "SQL concatenation vulnerability",
            "Unused import statement",
            "Race condition in goroutine map",
            "Hardcoded AWS secret key",
            "Resource leak unclosed descriptor",
            "Off-by-one array index error",
            "Weak MD5 password hash",
            "Missing HTTP request timeout",
            "Inconsistent camelCase naming",
            "N+1 query missing select_related",
            "Deprecated logging.warn usage",
            "Redis cache key collision",
            "JWT expiry not validated",
            "CORS wildcard origin",
            "Log injection unsanitized input",
            "Billion laughs XML DoS",
            "Open redirect URL validation",
        ]
        return [
            ReviewFinding(agent="Test", severity=s, title=titles[i], description=descs[i % len(descs)])
            for i, s in enumerate(severities)
        ]

    # Empty: 0 points
    result_empty = asyncio.run(coordinator.synthesize([]))
    assert result_empty.risk_score == 0

    # All LOW (6 * 1 = 6): LOW
    low_findings = _make_findings([Severity.LOW] * 6)
    result_low = asyncio.run(coordinator.synthesize([
        AgentResult(agent_name="Test", findings=low_findings)
    ]))
    assert result_low.risk_score == 6
    assert result_low.risk_score <= 20  # LOW range

    # 4 MEDIUM + 2 LOW (4*5 + 2*1 = 22): MEDIUM
    mixed_findings = _make_findings([Severity.MEDIUM] * 4 + [Severity.LOW] * 2)
    result_medium = asyncio.run(coordinator.synthesize([
        AgentResult(agent_name="Test", findings=mixed_findings)
    ]))
    assert result_medium.risk_score == 22
    assert 21 <= result_medium.risk_score <= 50  # MEDIUM range

    # 2 HIGH + 3 MEDIUM + 2 LOW (2*15 + 3*5 + 2*1 = 47): MEDIUM
    high_findings = _make_findings(
        [Severity.HIGH] * 2 + [Severity.MEDIUM] * 3 + [Severity.LOW] * 2
    )
    result_high = asyncio.run(coordinator.synthesize([
        AgentResult(agent_name="Test", findings=high_findings)
    ]))
    assert result_high.risk_score == 47
    assert 21 <= result_high.risk_score <= 50  # MEDIUM range

    # 1 CRITICAL + 2 HIGH + 4 MEDIUM + 6 LOW (25 + 30 + 20 + 6 = 81): CRITICAL
    critical_findings = _make_findings(
        [Severity.CRITICAL] + [Severity.HIGH] * 2 + [Severity.MEDIUM] * 4 + [Severity.LOW] * 6
    )
    result_critical = asyncio.run(coordinator.synthesize([
        AgentResult(agent_name="Test", findings=critical_findings)
    ]))
    assert result_critical.risk_score == 81
    assert result_critical.risk_score >= 81  # CRITICAL range

    # Cap at 100
    many_critical = _make_findings([Severity.CRITICAL] * 10)
    result_capped = asyncio.run(coordinator.synthesize([
        AgentResult(agent_name="Test", findings=many_critical)
    ]))
    assert result_capped.risk_score == 100

    # Verify risk score appears in summary
    assert "Risk Score" in result_critical.summary
    assert "CRITICAL" in result_critical.summary


# ---------------------------------------------------------------------------
# Build human prompt tests
# ---------------------------------------------------------------------------


def test_build_human_prompt():
    agent = StyleAgent(model="mimo-v2.5-pro", api_key="test-key")
    prompt = agent._build_human_prompt("def foo(): pass", "test.py")
    assert "test.py" in prompt
    assert "def foo(): pass" in prompt
    assert agent.get_review_focus() in prompt


# ---------------------------------------------------------------------------
# MiMo endpoint compatibility tests
# ---------------------------------------------------------------------------


def test_mimo_base_url_accepted():
    """Verify agents accept a MiMo-compatible base_url."""
    agent = SecurityAgent(
        model="mimo-v2.5-pro",
        base_url="https://api.xiaomimimo.com/v1",
        api_key="test-key",
    )
    assert str(agent.llm.openai_api_base) == "https://api.xiaomimimo.com/v1"
    assert agent.llm.model_name == "mimo-v2.5-pro"


def test_deepseek_base_url_accepted():
    """Verify agents accept a DeepSeek-compatible base_url."""
    agent = SecurityAgent(
        model="deepseek-chat",
        base_url="https://api.deepseek.com/v1",
        api_key="test-key",
    )
    assert str(agent.llm.openai_api_base) == "https://api.deepseek.com/v1"


def test_agent_placeholder_api_key(monkeypatch):
    """When no api_key provided and no env var set, a ValueError is raised."""
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    with pytest.raises(ValueError, match="API key is required"):
        StyleAgent(model="mimo-v2.5-pro")
