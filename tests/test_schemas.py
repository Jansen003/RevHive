"""Tests for Pydantic schemas (Finding and ReviewResult)."""

import pytest
from revhive.models.schemas import Finding, ReviewResult


class TestFinding:
    def test_minimal_finding(self):
        f = Finding(
            title="Test issue",
            severity="MEDIUM",
            description="Something is wrong",
        )
        assert f.title == "Test issue"
        assert f.severity == "MEDIUM"
        assert f.description == "Something is wrong"
        assert f.suggestion == ""

    def test_full_finding(self):
        f = Finding(
            title="SQL Injection",
            severity="CRITICAL",
            description="Unsanitized input in query",
            file_path="src/app.py",
            line_number=42,
            code_snippet="query = 'SELECT * FROM users WHERE id=' + user_input",
            suggestion="Use parameterized queries",
        )
        assert f.file_path == "src/app.py"
        assert f.line_number == 42
        assert "SELECT" in f.code_snippet
        assert "parameterized" in f.suggestion

    def test_default_values(self):
        f = Finding(title="X", severity="LOW", description="Y")
        assert f.file_path is None
        assert f.line_number is None
        assert f.code_snippet is None
        assert f.suggestion == ""

    def test_title_case_keys_normalized(self):
        """Keys from LLM with Title case should be normalized to lowercase."""
        data = {
            "Title": "Capitalized issue",
            "Severity": "HIGH",
            "Description": "Something wrong",
            "Suggestion": "Fix it",
            "Line_number": 10,
        }
        f = Finding.model_validate(data)
        assert f.title == "Capitalized issue"
        assert f.severity == "HIGH"
        assert f.description == "Something wrong"
        assert f.suggestion == "Fix it"
        assert f.line_number == 10

    def test_extra_fields_ignored(self):
        """Unknown fields from LLM should be silently ignored."""
        data = {
            "title": "Issue",
            "severity": "MEDIUM",
            "description": "Something",
            "unknown_field": "should be ignored",
            "another_extra": 123,
        }
        f = Finding.model_validate(data)
        assert f.title == "Issue"
        assert not hasattr(f, "unknown_field")

    def test_invalid_severity_rejected(self):
        with pytest.raises(ValueError):
            Finding(title="X", severity="INVALID", description="Y")

    def test_severity_case_sensitive(self):
        """Severity must be uppercase."""
        with pytest.raises(ValueError):
            Finding(title="X", severity="high", description="Y")

    def test_missing_required_fields(self):
        with pytest.raises(ValueError):
            Finding.model_validate({"severity": "LOW"})


class TestReviewResult:
    def test_empty_review_result(self):
        r = ReviewResult()
        assert r.findings == []
        assert r.summary == ""
        assert r.risk_level == "LOW"

    def test_with_findings(self):
        r = ReviewResult(
            findings=[
                Finding(title="Issue 1", severity="HIGH", description="Bad thing"),
                Finding(title="Issue 2", severity="LOW", description="Minor thing"),
            ],
            summary="Two issues found",
            risk_level="MEDIUM",
        )
        assert len(r.findings) == 2
        assert r.summary == "Two issues found"
        assert r.risk_level == "MEDIUM"

    def test_title_case_keys_normalized(self):
        """Keys from LLM should be normalized."""
        data = {
            "Findings": [
                {"Title": "Issue", "Severity": "CRITICAL", "Description": "Bad"},
            ],
            "Summary": "One critical issue",
            "Risk_Level": "HIGH",
        }
        r = ReviewResult.model_validate(data)
        assert len(r.findings) == 1
        assert r.findings[0].title == "Issue"
        assert r.summary == "One critical issue"
        assert r.risk_level == "HIGH"

    def test_extra_fields_ignored(self):
        data = {
            "findings": [],
            "summary": "ok",
            "risk_level": "LOW",
            "model": "gpt-4o",
            "tokens_used": 500,
        }
        r = ReviewResult.model_validate(data)
        assert not hasattr(r, "model")

    def test_nested_finding_normalization(self):
        """Finding fields within ReviewResult should also be normalized."""
        data = {
            "Findings": [
                {"Title": "SQL Injection", "Severity": "CRITICAL", "Description": "Bad SQL", "Suggestion": "Use params"}
            ],
            "Summary": "Critical issue",
            "Risk_Level": "CRITICAL",
        }
        r = ReviewResult.model_validate(data)
        assert r.findings[0].title == "SQL Injection"
        assert r.findings[0].severity == "CRITICAL"
