"""Tests for code parsing utilities."""

import pytest
from revhive.utils.parser import (
    CodeStructure,
    _detect_language,
    _parse_with_regex,
    _parse_with_tree_sitter,
    parse_code,
    EXT_LANG,
    SUPPORTED_EXTENSIONS,
)


class TestDetectLanguage:
    def test_python(self):
        assert _detect_language("file.py") == "python"

    def test_javascript_variants(self):
        assert _detect_language("app.js") == "javascript"
        assert _detect_language("component.jsx") == "javascript"
        assert _detect_language("module.mjs") == "javascript"

    def test_typescript_variants(self):
        assert _detect_language("app.ts") == "typescript"
        assert _detect_language("component.tsx") == "typescript"

    def test_go(self):
        assert _detect_language("main.go") == "go"

    def test_rust(self):
        assert _detect_language("lib.rs") == "rust"

    def test_java(self):
        assert _detect_language("Main.java") == "java"

    def test_c_and_cpp(self):
        assert _detect_language("main.c") == "c"
        assert _detect_language("app.cpp") == "cpp"
        assert _detect_language("header.h") == "c_header"
        assert _detect_language("header.hpp") == "cpp_header"

    def test_ruby(self):
        assert _detect_language("app.rb") == "ruby"

    def test_php(self):
        assert _detect_language("index.php") == "php"

    def test_swift(self):
        assert _detect_language("app.swift") == "swift"

    def test_kotlin(self):
        assert _detect_language("main.kt") == "kotlin"

    def test_unknown_extension_defaults_to_python(self):
        assert _detect_language("file.xyz") == "python"

    def test_no_extension_defaults_to_python(self):
        assert _detect_language("Makefile") == "python"

    def test_case_insensitive(self):
        assert _detect_language("file.PY") == "python"
        assert _detect_language("file.TS") == "typescript"


class TestExtLangMapping:
    def test_all_extensions_have_languages(self):
        for ext, lang in EXT_LANG.items():
            assert isinstance(ext, str)
            assert ext.startswith(".")
            assert isinstance(lang, str)
            assert len(lang) > 0

    def test_supported_extensions_list(self):
        assert len(SUPPORTED_EXTENSIONS) == len(EXT_LANG)
        assert ".py" in SUPPORTED_EXTENSIONS
        assert ".go" in SUPPORTED_EXTENSIONS


class TestParseWithRegex:
    def test_python_functions(self):
        code = "def hello():\n    pass\n\ndef world(x, y):\n    return x + y\n"
        result = _parse_with_regex(code, "python")
        assert "hello" in result.functions
        assert "world" in result.functions

    def test_python_classes(self):
        code = "class MyClass:\n    pass\n\nclass Another:\n    pass\n"
        result = _parse_with_regex(code, "python")
        assert "MyClass" in result.classes
        assert "Another" in result.classes

    def test_python_imports(self):
        code = "import os\nfrom pathlib import Path\nimport sys\n"
        result = _parse_with_regex(code, "python")
        assert len(result.imports) == 3

    def test_javascript_functions(self):
        code = "function hello() {}\nconst greet = () => {};\nconst world = function() {};"
        result = _parse_with_regex(code, "javascript")
        # JS regex captures function names from declarations
        assert len(result.functions) > 0

    def test_javascript_classes(self):
        code = "class Component {}\nclass Service {}"
        result = _parse_with_regex(code, "javascript")
        assert "Component" in result.classes
        assert "Service" in result.classes

    def test_typescript_interfaces(self):
        code = "interface Props {}\ntype State = {};\nclass App {}"
        result = _parse_with_regex(code, "typescript")
        # TypeScript class_re matches class|interface|type
        assert len(result.classes) >= 3

    def test_go_functions(self):
        code = 'func hello() {}\nfunc (s *Server) Start() error { return nil }\nimport "fmt"'
        result = _parse_with_regex(code, "go")
        assert len(result.functions) >= 1

    def test_rust_functions_and_structs(self):
        code = "fn main() {}\npub fn helper() {}\nstruct Point { x: i32, y: i32 }\nenum Color { Red, Green }"
        result = _parse_with_regex(code, "rust")
        assert len(result.functions) >= 2
        assert len(result.classes) >= 2

    def test_java_methods_and_classes(self):
        code = (
            "public class Main {\n"
            '    public static void main(String[] args) {}\n'
            "    private int getValue() { return 0; }\n"
            "}\n"
            "interface Callback { void onEvent(); }"
        )
        result = _parse_with_regex(code, "java")
        assert "Main" in result.classes or len(result.classes) >= 1

    def test_empty_code(self):
        result = _parse_with_regex("", "python")
        assert result.functions == []
        assert result.classes == []
        assert result.imports == []
        assert result.language == "python"

    def test_code_structure_dataclass(self):
        cs = CodeStructure(
            functions=["foo", "bar"],
            classes=["Baz"],
            imports=["import os"],
            language="python",
        )
        assert cs.functions == ["foo", "bar"]
        assert cs.classes == ["Baz"]
        assert cs.imports == ["import os"]
        assert cs.language == "python"

    def test_fallback_to_python_patterns(self):
        """Unknown language falls back to python patterns."""
        result = _parse_with_regex("def hello():\n    pass", "unknown_lang")
        assert "hello" in result.functions

    def test_php_functions(self):
        code = "<?php\nfunction hello() {}\nfunction world() {}\nuse App\\Service;"
        result = _parse_with_regex(code, "php")
        assert len(result.functions) >= 2

    def test_ruby_functions(self):
        code = "def hello\nend\ndef world!\nend\nrequire 'json'"
        result = _parse_with_regex(code, "ruby")
        assert len(result.functions) >= 2

    def test_swift_functions(self):
        code = "func greet() {}\nfunc add(_ x: Int, _ y: Int) -> Int {}\nimport Foundation"
        result = _parse_with_regex(code, "swift")
        assert len(result.functions) >= 2

    def test_kotlin_functions(self):
        # NB: The regex only matches "fun name(" — generic params before the name
        # (fun <T> identity(...)) are not captured.
        code = "fun main() {}\nfun greet(name: String) {}\nimport kotlin.math.*"
        result = _parse_with_regex(code, "kotlin")
        assert "main" in result.functions
        assert "greet" in result.functions


class TestParseCode:
    def test_auto_detect_language(self):
        code = "def foo():\n    pass"
        result = parse_code(code, file_path="test.py")
        assert result.language == "python"

    def test_explicit_language_overrides_file(self):
        code = "function hello() {}"
        result = parse_code(code, language="javascript", file_path="test.py")
        assert result.language == "javascript"

    def test_non_python_falls_back_to_regex(self):
        """Non-python languages fall back to regex (no tree-sitter grammar)."""
        code = "function hello() {}"
        result = parse_code(code, language="javascript", file_path="test.js")
        assert result.language == "javascript"


class TestTreeSitterPython:
    @pytest.mark.skip(reason="tree-sitter is an optional dependency, not always installed")
    def test_tree_sitter_python(self):
        code = "def foo():\n    pass\n\nclass Bar:\n    pass\nimport os\n"
        result = _parse_with_tree_sitter(code, "python")
        assert "foo" in result.functions
        assert "Bar" in result.classes
        assert len(result.imports) > 0
