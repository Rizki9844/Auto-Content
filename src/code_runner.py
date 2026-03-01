"""
Safe code execution sandbox.
Runs Python and Node.js code in isolated subprocesses with strict timeouts
and resource limits. Used for "output_demo" content type to show real output.
"""
import subprocess
import logging
import shutil
import tempfile
from pathlib import Path

from src import config

logger = logging.getLogger(__name__)

# Maximum execution time per code snippet (seconds)
EXEC_TIMEOUT = 10

# Maximum output length (characters) — truncated beyond this
MAX_OUTPUT_LEN = 500

# Languages we can actually execute
EXECUTABLE_LANGUAGES = {"python", "javascript", "bash"}

# Dangerous patterns to block (basic safety net)
_BLOCKED_PATTERNS_PYTHON = [
    "import os",
    "import sys",
    "import subprocess",
    "import shutil",
    "__import__",
    "eval(",
    "exec(",
    "open(",
    "os.system",
    "os.popen",
    "os.remove",
    "os.unlink",
    "shutil.rmtree",
    "pathlib",
    "socket",
    "requests",
    "urllib",
    "http.client",
]

_BLOCKED_PATTERNS_JS = [
    "require('fs')",
    "require('child_process')",
    "require('net')",
    "require('http')",
    "require(\"fs\")",
    "require(\"child_process\")",
    "process.exit",
    "process.env",
    "eval(",
    "Function(",
]


def is_safe_code(code: str, language: str) -> bool:
    """
    Basic safety check — block obviously dangerous patterns.
    This is NOT a full sandbox; we rely on subprocess isolation + timeout.
    """
    code_lower = code.lower()

    if language == "python":
        for pattern in _BLOCKED_PATTERNS_PYTHON:
            if pattern.lower() in code_lower:
                logger.warning(f"Blocked unsafe Python pattern: {pattern}")
                return False

    elif language == "javascript":
        for pattern in _BLOCKED_PATTERNS_JS:
            if pattern.lower() in code_lower:
                logger.warning(f"Blocked unsafe JS pattern: {pattern}")
                return False

    return True


def run_code(code: str, language: str) -> str | None:
    """
    Execute code and capture stdout.

    Args:
        code: The source code to execute.
        language: Programming language name.

    Returns:
        stdout as string (truncated if too long), or None if execution
        is not possible or blocked for safety.
    """
    if language not in EXECUTABLE_LANGUAGES:
        logger.info(f"Language '{language}' is not executable, skipping run")
        return None

    if not is_safe_code(code, language):
        logger.warning("Code blocked by safety check")
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
    """Execute Python code in a subprocess."""
    try:
        result = subprocess.run(
            ["python3", "-c", code],
            capture_output=True,
            text=True,
            timeout=EXEC_TIMEOUT,
            cwd=tempfile.gettempdir(),
            env={"PATH": "/usr/bin:/bin", "HOME": tempfile.gettempdir()},
        )
        output = result.stdout or result.stderr
        return _truncate(output)
    except subprocess.TimeoutExpired:
        logger.warning("Python execution timed out")
        return "⏱ Timeout (>10s)"
    except FileNotFoundError:
        # python3 not found, try python
        try:
            result = subprocess.run(
                ["python", "-c", code],
                capture_output=True,
                text=True,
                timeout=EXEC_TIMEOUT,
                cwd=tempfile.gettempdir(),
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
        )
        output = result.stdout or result.stderr
        return _truncate(output)
    except subprocess.TimeoutExpired:
        logger.warning("JS execution timed out")
        return "⏱ Timeout (>10s)"


def _run_bash(code: str) -> str | None:
    """Execute simple bash commands (echo, printf, etc.)."""
    # Extra restrictive for bash — only allow echo/printf/date/seq
    safe_commands = {"echo", "printf", "date", "seq", "expr", "bc", "wc"}
    first_word = code.strip().split()[0] if code.strip() else ""
    if first_word not in safe_commands:
        logger.info(f"Bash command '{first_word}' not in safe list, skipping")
        return None

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
        )
        output = result.stdout or result.stderr
        return _truncate(output)
    except subprocess.TimeoutExpired:
        return "⏱ Timeout (>10s)"


def get_output_for_content(content: dict) -> str | None:
    """
    Get execution output for a content dict.
    For output_demo: runs the code and returns real output (falls back to expected_output).
    For quiz: returns the quiz_answer.
    For other types: returns None.
    """
    ct = content.get("content_type", "tip")

    if ct == "output_demo":
        # Try real execution first
        real_output = run_code(content["code"], content["language"])
        if real_output and real_output.strip():
            logger.info(f"Code executed successfully, output: {len(real_output)} chars")
            return real_output.strip()
        # Fall back to LLM-provided expected output
        expected = content.get("expected_output", "")
        if expected:
            logger.info("Using LLM-provided expected_output (execution skipped)")
            return expected.strip()
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
