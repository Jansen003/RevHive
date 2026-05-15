"""Tests for configuration loading and RevHiveConfig."""

import tempfile
from pathlib import Path

import yaml

from revhive.config import (
    AgentConfig,
    RevHiveConfig,
    MODEL_PRESETS,
    load_config,
)
from revhive.agents.base import Severity


class TestAgentConfig:
    def test_defaults(self):
        cfg = AgentConfig()
        assert cfg.enabled is True
        assert cfg.severity_threshold is None

    def test_disabled(self):
        cfg = AgentConfig(enabled=False)
        assert cfg.enabled is False

    def test_severity_threshold(self):
        cfg = AgentConfig(severity_threshold="medium")
        assert cfg.severity_threshold == "medium"


class TestRevHiveConfigDefaults:
    def test_empty_config(self):
        cfg = RevHiveConfig()
        assert cfg.model is None
        assert cfg.agents == {}
        assert cfg.ignore == []

    def test_is_agent_enabled_default(self):
        cfg = RevHiveConfig()
        assert cfg.is_agent_enabled("style") is True  # Not in config → enabled by default

    def test_get_severity_threshold_none(self):
        cfg = RevHiveConfig()
        assert cfg.get_severity_threshold("style") is None


class TestRevHiveConfigModelPresets:
    def test_resolve_known_preset(self):
        cfg = RevHiveConfig()
        result = cfg.resolve_preset("openai")
        assert result["base_url"] == "https://api.openai.com/v1"
        assert result["model"] == "gpt-4o"

    def test_resolve_unknown_preset(self):
        cfg = RevHiveConfig()
        result = cfg.resolve_preset("unknown-model-xyz")
        assert result == {}

    def test_resolve_none(self):
        cfg = RevHiveConfig()
        assert cfg.resolve_preset(None) == {}

    def test_all_presets_have_required_keys(self):
        for name, preset in MODEL_PRESETS.items():
            assert "base_url" in preset, f"Missing base_url in {name}"
            assert "model" in preset, f"Missing model in {name}"


class TestRevHiveConfigAgentManagement:
    def test_is_agent_enabled_false(self):
        cfg = RevHiveConfig(agents={"style": AgentConfig(enabled=False)})
        assert cfg.is_agent_enabled("style") is False

    def test_is_agent_enabled_true(self):
        cfg = RevHiveConfig(agents={"style": AgentConfig(enabled=True)})
        assert cfg.is_agent_enabled("style") is True

    def test_get_severity_threshold(self):
        cfg = RevHiveConfig(agents={"security": AgentConfig(severity_threshold="medium")})
        threshold = cfg.get_severity_threshold("security")
        assert threshold == Severity.MEDIUM

    def test_get_severity_threshold_high(self):
        cfg = RevHiveConfig(agents={"security": AgentConfig(severity_threshold="high")})
        threshold = cfg.get_severity_threshold("security")
        assert threshold == Severity.HIGH

    def test_get_severity_threshold_invalid(self):
        cfg = RevHiveConfig(agents={"security": AgentConfig(severity_threshold="superbad")})
        threshold = cfg.get_severity_threshold("security")
        assert threshold is None


class TestRevHiveConfigIgnorePatterns:
    def test_exact_match(self):
        cfg = RevHiveConfig(ignore=["node_modules/something.js"])
        assert cfg.should_ignore("node_modules/something.js") is True

    def test_no_match(self):
        cfg = RevHiveConfig(ignore=["node_modules/**"])
        assert cfg.should_ignore("src/main.py") is False

    def test_glob_match(self):
        cfg = RevHiveConfig(ignore=["*.min.js"])
        assert cfg.should_ignore("bundle.min.js") is True
        assert cfg.should_ignore("bundle.js") is False

    def test_double_star_prefix(self):
        cfg = RevHiveConfig(ignore=["vendor/**"])
        assert cfg.should_ignore("vendor/lib/utils.py") is True
        assert cfg.should_ignore("vendor/something.py") is True

    def test_double_star_middle(self):
        cfg = RevHiveConfig(ignore=["src/**/__pycache__/**"])
        assert cfg.should_ignore("src/revhive/__pycache__/base.pyc") is True
        assert cfg.should_ignore("src/revhive/__pycache__/something.pyc") is True

    def test_node_modules_pattern(self):
        cfg = RevHiveConfig(ignore=["node_modules/**"])
        assert cfg.should_ignore("node_modules/lodash/index.js") is True
        assert cfg.should_ignore("src/node_modules/something.js") is False

    def test_multiple_patterns(self):
        cfg = RevHiveConfig(ignore=["*.min.js", "vendor/**", "*.pyc"])
        assert cfg.should_ignore("app.min.js") is True
        assert cfg.should_ignore("vendor/lib.js") is True
        assert cfg.should_ignore("cache.pyc") is True
        assert cfg.should_ignore("src/main.py") is False

    def test_empty_ignore_list(self):
        cfg = RevHiveConfig(ignore=[])
        assert cfg.should_ignore("anything.js") is False

    def test_suffix_only_double_star(self):
        """Pattern like '**/migrations/**' — prefix is empty."""
        cfg = RevHiveConfig(ignore=["**/migrations/**"])
        assert cfg.should_ignore("migrations/001_init.py") is True

    def test_dot_git_pattern(self):
        cfg = RevHiveConfig(ignore=[".git/**"])
        assert cfg.should_ignore(".git/objects/abc") is True
        assert cfg.should_ignore("src/.git/something") is False


class TestLoadConfig:
    def test_load_from_yaml_file(self):
        yaml_content = {
            "model": "gpt-4o",
            "agents": {
                "style": {"enabled": False},
                "security": {"severity_threshold": "high"},
            },
            "ignore": ["*.pyc", "vendor/**"],
        }
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yml", delete=False) as f:
            yaml.dump(yaml_content, f)
            temp_path = f.name

        try:
            cfg = load_config(temp_path)
            assert cfg.model == "gpt-4o"
            assert cfg.is_agent_enabled("style") is False
            assert cfg.get_severity_threshold("security") == Severity.HIGH
            assert "*.pyc" in cfg.ignore
            assert "vendor/**" in cfg.ignore
        finally:
            Path(temp_path).unlink()

    def test_load_missing_file_returns_default(self):
        cfg = load_config("/nonexistent/path/.revhive.yml")
        assert isinstance(cfg, RevHiveConfig)
        assert cfg.model is None
        assert cfg.agents == {}

    def test_load_bool_agent_config(self):
        """Agent config can be a plain boolean (true/false)."""
        yaml_content = {"agents": {"doc": False, "style": True}}
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yml", delete=False) as f:
            yaml.dump(yaml_content, f)
            temp_path = f.name

        try:
            cfg = load_config(temp_path)
            assert cfg.is_agent_enabled("doc") is False
            assert cfg.is_agent_enabled("style") is True
        finally:
            Path(temp_path).unlink()

    def test_load_invalid_yaml_returns_default(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yml", delete=False) as f:
            f.write(": invalid yaml: : ::")
            temp_path = f.name

        try:
            cfg = load_config(temp_path)
            assert isinstance(cfg, RevHiveConfig)
            assert cfg.model is None
        finally:
            Path(temp_path).unlink()

    def test_load_empty_file_returns_default(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yml", delete=False) as f:
            f.write("")
            temp_path = f.name

        try:
            cfg = load_config(temp_path)
            assert isinstance(cfg, RevHiveConfig)
        finally:
            Path(temp_path).unlink()

    def test_cache_returns_same_instance(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yml", delete=False) as f:
            yaml.dump({"model": "gpt-4o"}, f)
            temp_path = f.name

        try:
            cfg1 = load_config(temp_path)
            cfg2 = load_config(temp_path)
            assert cfg1 is cfg2  # Same cached instance
        finally:
            Path(temp_path).unlink()
