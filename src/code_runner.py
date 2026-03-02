"""
Safe code execution sandbox — v2 (hardened).

Security model:
  1. PRIMARY: Use LLM-provided expected_output (no execution needed).
  2. FALLBACK: Execute in restricted subprocess ONLY for Python/JS/bash,
     with AST-level validation (Python) and aggressive pattern blocking.
  3. LIMITS: 5s timeout, 500-char output cap, minimal env, temp cwd.

The sandbox is NOT a security boundary against a determined attacker.
It is designed to block common dangerous patterns that an LLM might
accidentally generate (file I/O, network, process spawning).
"""
import ast
import subprocess
import logging
import shutil
import tempfile


logger = logging.getLogger(__name__)

# ── Execution Limits ──────────────────────────────────────────
EXEC_TIMEOUT = 5          # seconds (reduced from 10)
MAX_OUTPUT_LEN = 500      # characters

# Languages we can actually execute
EXECUTABLE_LANGUAGES = {"python", "javascript", "bash"}

# ══════════════════════════════════════════════════════════════
#  PYTHON AST-LEVEL SAFETY VALIDATION
# ══════════════════════════════════════════════════════════════

# Modules that are NEVER safe to import
_BANNED_MODULES = frozenset({
    "os", "sys", "subprocess", "shutil", "pathlib", "importlib",
    "socket", "http", "urllib", "requests", "ftplib", "smtplib",
    "ctypes", "multiprocessing", "threading", "signal", "resource",
    "code", "codeop", "compileall", "py_compile",
    "pickle", "shelve", "marshal", "dbm",
    "webbrowser", "antigravity", "turtle",
    "builtins", "__builtin__",
})

# Built-in functions that are dangerous
_BANNED_BUILTINS = frozenset({
    "eval", "exec", "compile", "execfile",
    "open", "input", "__import__",
    "globals", "locals", "vars", "dir",
    "getattr", "setattr", "delattr",
    "breakpoint", "exit", "quit",
})

# Attributes that indicate system access
_BANNED_ATTRS = frozenset({
    "__import__", "__subclasses__", "__bases__", "__mro__",
    "__class__", "__globals__", "__builtins__",
    "system", "popen", "remove", "unlink", "rmtree",
    "environ", "getcwd", "listdir", "walk",
})


def _is_python_safe_ast(code: str) -> tuple[bool, str]:
    """
    Parse Python code into AST and check for dangerous constructs.
    Returns (is_safe, reason).
    """
    try:
        tree = ast.parse(code)
    except SyntaxError as e:
        return False, f"SyntaxError: {e}"

    for node in ast.walk(tree):
        # Block: import os, import subprocess, etc.
        if isinstance(node, ast.Import):
            for alias in node.names:
                root_module = alias.name.split(".")[0]
                if root_module in _BANNED_MODULES:
                    return False, f"Banned import: {alias.name}"

        # Block: from os import system, from subprocess import run, etc.
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                root_module = node.module.split(".")[0]
                if root_module in _BANNED_MODULES:
                    return False, f"Banned import: from {node.module}"

        # Block: eval(), exec(), open(), __import__(), etc.
        elif isinstance(node, ast.Call):
            func = node.func
            func_name = None

            if isinstance(func, ast.Name):
                func_name = func.id
            elif isinstance(func, ast.Attribute):
                func_name = func.attr

            if func_name and func_name in _BANNED_BUILTINS:
                return False, f"Banned builtin: {func_name}()"

        # Block: obj.__import__, obj.__subclasses__, etc.
        elif isinstance(node, ast.Attribute):
            if node.attr in _BANNED_ATTRS:
                return False, f"Banned attribute: .{node.attr}"

    return True, "OK"


# ══════════════════════════════════════════════════════════════
#  JAVASCRIPT PATTERN SAFETY
# ══════════════════════════════════════════════════════════════

_BLOCKED_PATTERNS_JS = [
    "require(", "import(", "import ",
    "process.env", "process.exit", "process.kill",
    "child_process", "fs.", "fs,", "'fs'", '"fs"',
    "net.", "'net'", '"net"',
    "http.", "'http'", '"http"',
    "eval(", "Function(",
    "globalThis", "global.",
    "Deno.", "Bun.",
]


def _is_js_safe(code: str) -> tuple[bool, str]:
    """Pattern-based check for JavaScript."""
    code_lower = code.lower()
    for pattern in _BLOCKED_PATTERNS_JS:
        if pattern.lower() in code_lower:
            return False, f"Blocked JS pattern: {pattern}"
    return True, "OK"


# ══════════════════════════════════════════════════════════════
#  BASH SAFETY (very restrictive allow-list)
# ══════════════════════════════════════════════════════════════

_SAFE_BASH_COMMANDS = frozenset({
    "echo", "printf", "date", "seq", "expr", "bc", "wc",
    "head", "tail", "sort", "uniq", "tr", "cut", "rev",
})


def _is_bash_safe(code: str) -> tuple[bool, str]:
    """Allow-list approach for bash: only specific commands."""
    for line in code.strip().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue

        # Get the first real command (skip variable assignments like X=1)
        if "=" in line.split()[0] and not line.split()[0].startswith("-"):
            continue

        # Handle pipes: check each command in the pipeline
        for cmd_part in line.split("|"):
            cmd_word = cmd_part.strip().split()[0] if cmd_part.strip() else ""
            if cmd_word and cmd_word not in _SAFE_BASH_COMMANDS:
                return False, f"Bash command not in allow-list: {cmd_word}"

    return True, "OK"


# ══════════════════════════════════════════════════════════════
#  CODE EXECUTION
# ══════════════════════════════════════════════════════════════

def is_safe_code(code: str, language: str) -> tuple[bool, str]:
    """
    Validate code safety. Returns (is_safe, reason).
    Python uses AST analysis; JS/bash use pattern matching.
    """
    if language == "python":
        return _is_python_safe_ast(code)
    elif language == "javascript":
        return _is_js_safe(code)
    elif language == "bash":
        return _is_bash_safe(code)
    return False, f"Unsupported language: {language}"


def run_code(code: str, language: str) -> str | None:
    """
    Execute code and capture stdout.
    Returns stdout (truncated) or None if blocked/failed.
    """
    if language not in EXECUTABLE_LANGUAGES:
        logger.info(f"Language '{language}' is not executable, skipping")
        return None

    safe, reason = is_safe_code(code, language)
    if not safe:
        logger.warning(f"Code blocked by safety check: {reason}")
        return None

    try:
        if language == "python":
            return _run_python(code)
        elif language == "javascript":
            return _run_javascript(code)
        elif language == "bash":
            return _run_bash(code)
    except Exception as e:
        logger.warning(f"Code execution failed: {e}")
        return None

    return None


def _run_python(code: str) -> str | None:
    """Execute Python code in a restricted subprocess."""
    # Minimal environment — no access to secrets or system paths beyond basics
    safe_env = {
        "PATH": "/usr/bin:/bin",
        "HOME": tempfile.gettempdir(),
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONIOENCODING": "utf-8",
    }

    try:
        result = subprocess.run(
            ["python3", "-c", code],
            capture_output=True,
            text=True,
            timeout=EXEC_TIMEOUT,
            cwd=tempfile.gettempdir(),
            env=safe_env,
        )
        output = result.stdout or result.stderr
        return _truncate(output)
    except subprocess.TimeoutExpired:
        logger.warning("Python execution timed out")
        return "⏱ Timeout (>5s)"
    except FileNotFoundError:
        # python3 not found, try python — SAME restricted env
        try:
            result = subprocess.run(
                ["python", "-c", code],
                capture_output=True,
                text=True,
                timeout=EXEC_TIMEOUT,
                cwd=tempfile.gettempdir(),
                env=safe_env,
            )
            output = result.stdout or result.stderr
            return _truncate(output)
        except Exception:
            return None


def _run_javascript(code: str) -> str | None:
    """Execute JavaScript code via Node.js."""
    node_path = shutil.which("node")
    if not node_path:
        logger.info("Node.js not found, skipping JS execution")
        return None

    try:
        result = subprocess.run(
            [node_path, "-e", code],
            capture_output=True,
            text=True,
            timeout=EXEC_TIMEOUT,
            cwd=tempfile.gettempdir(),
            env={
                "PATH": "/usr/bin:/bin:/usr/local/bin",
                "HOME": tempfile.gettempdir(),
                "NODE_OPTIONS": "--max-old-space-size=64",
            },
        )
        output = result.stdout or result.stderr
        return _truncate(output)
    except subprocess.TimeoutExpired:
        logger.warning("JS execution timed out")
        return "⏱ Timeout (>5s)"


def _run_bash(code: str) -> str | None:
    """Execute simple bash commands."""
    bash_path = shutil.which("bash") or shutil.which("sh")
    if not bash_path:
        return None

    try:
        result = subprocess.run(
            [bash_path, "-c", code],
            capture_output=True,
            text=True,
            timeout=EXEC_TIMEOUT,
            cwd=tempfile.gettempdir(),
            env={"PATH": "/usr/bin:/bin", "HOME": tempfile.gettempdir()},
        )
        output = result.stdout or result.stderr
        return _truncate(output)
    except subprocess.TimeoutExpired:
        return "⏱ Timeout (>5s)"


# ══════════════════════════════════════════════════════════════
#  PUBLIC API
# ══════════════════════════════════════════════════════════════

def get_output_for_content(content: dict) -> str | None:
    """
    Get execution output for a content dict.

    Strategy (output_demo):
      1. Try LLM-provided expected_output FIRST (safest, fastest)
      2. Only run real execution if expected_output is empty
    Strategy (quiz):
      - Return quiz_answer directly (no execution)
    """
    ct = content.get("content_type", "tip")

    if ct == "output_demo":
        # Prefer LLM-provided expected_output (no execution risk)
        expected = content.get("expected_output", "").strip()
        if expected:
            logger.info("Using LLM-provided expected_output (safest path)")
            return expected

        # Fallback: try real execution only if expected_output is empty
        real_output = run_code(content["code"], content["language"])
        if real_output and real_output.strip():
            logger.info(f"Code executed successfully, output: {len(real_output)} chars")
            return real_output.strip()

        return None

    elif ct == "quiz":
        return content.get("quiz_answer", "").strip() or None

    return None


def _truncate(text: str) -> str:
    """Truncate output to MAX_OUTPUT_LEN characters."""
    text = text.strip()
    if len(text) > MAX_OUTPUT_LEN:
        return text[:MAX_OUTPUT_LEN - 3] + "..."
    return text
