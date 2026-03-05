"""
Preview Renderer — generates a visual preview image for the top panel.

Two rendering paths:
  1. **Playwright (headless browser)** — for HTML/CSS/JS content, renders real
     browser output as a screenshot.
  2. **Terminal panel (Pillow)** — for Python/Bash/etc., draws a styled terminal
     showing execution output.

The result is a ``PIL.Image`` that ``FrameRenderer`` composites into the
preview panel area (y=90 → y=680).

Phase 10.1 — Visual Demo Preview
"""
from __future__ import annotations

import html
import logging
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from src import config

logger = logging.getLogger(__name__)

# ── Heuristics to detect browser-renderable content ───────────
_BROWSER_LANGUAGES = {"html", "css", "javascript", "js", "typescript", "ts", "svg"}

_BROWSER_MARKERS = [
    "document.", "getElementById", "querySelector", "canvas",
    "innerHTML", "createElement", "addEventListener",
    "<html", "<div", "<canvas", "<svg", "<style",
    "requestAnimationFrame", "window.", "DOM",
]


def _is_browser_content(code: str, language: str) -> bool:
    """Return True if the code is best rendered in a headless browser."""
    if language.lower() in _BROWSER_LANGUAGES:
        return True
    code_lower = code.lower()
    return any(marker.lower() in code_lower for marker in _BROWSER_MARKERS)


# ══════════════════════════════════════════════════════════════
#  PLAYWRIGHT PATH — real browser screenshot
# ══════════════════════════════════════════════════════════════

def _build_html_page(code: str, language: str) -> str:
    """Wrap code in a minimal HTML page for browser rendering.

    If the code is already HTML (contains <html or <body), use it as-is.
    Otherwise, wrap it in a basic scaffold.
    """
    code_stripped = code.strip()
    lower = code_stripped.lower()

    # Already a full HTML document
    if "<html" in lower or "<!doctype" in lower:
        return code_stripped

    # Has a <body> or block-level elements — wrap with html/head
    if any(tag in lower for tag in ["<div", "<canvas", "<svg", "<style", "<body"]):
        return f"""<!DOCTYPE html>
<html lang="en">
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
<style>body {{ margin:0; background:#0d1117; color:#e6edf3; font-family:monospace; }}</style>
</head>
<body>
{code_stripped}
</body>
</html>"""

    # CSS-only — render in a preview div
    if language.lower() == "css":
        return f"""<!DOCTYPE html>
<html lang="en">
<head><meta charset="UTF-8">
<style>body {{ margin:0; background:#0d1117; display:flex; align-items:center;
justify-content:center; min-height:100vh; }}
{code_stripped}
</style>
</head>
<body><div class="demo">CSS Preview</div></body>
</html>"""

    # JavaScript — wrap in script tag with a canvas
    if language.lower() in ("javascript", "js"):
        return f"""<!DOCTYPE html>
<html lang="en">
<head><meta charset="UTF-8">
<style>body {{ margin:0; background:#0d1117; color:#e6edf3; font-family:monospace;
display:flex; align-items:center; justify-content:center; min-height:100vh; }}</style>
</head>
<body>
<canvas id="canvas" width="600" height="400"></canvas>
<div id="output"></div>
<script>
try {{
{code_stripped}
}} catch(e) {{ document.getElementById('output').textContent = e.message; }}
</script>
</body>
</html>"""

    # Fallback: pre-formatted
    escaped = html.escape(code_stripped)
    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="UTF-8">
<style>body {{ margin:20px; background:#0d1117; color:#7ee787; font-family:monospace;
font-size:16px; white-space:pre-wrap; }}</style>
</head><body><pre>{escaped}</pre></body></html>"""


def _build_visual_ui_html(html_code: str) -> str:
    """Prepare Visual UI HTML code for rendering.
    
    The LLM outputs complete self-contained HTML.
    We just return it, ensuring it represents a full page.
    """
    return html_code.strip()


async def _capture_with_playwright(
    html_content: str,
    viewport: tuple[int, int] = (1000, 600),
    timeout_ms: int = 5000,
) -> Image.Image | None:
    """Launch headless Chromium/Chrome, render HTML, return screenshot as PIL Image.

    Tries Playwright's own Chromium first; if not yet downloaded, falls back
    to any locally-installed Chrome or Edge found on the system.
    """
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        logger.warning("playwright not installed — skipping browser preview")
        return None

    # Candidate local Chrome/Edge paths (Windows)
    _LOCAL_CHROME_PATHS = [
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    ]

    tmp_path = None
    try:
        # Write HTML to temp file
        with tempfile.NamedTemporaryFile(
            suffix=".html", delete=False, mode="w", encoding="utf-8",
        ) as f:
            f.write(html_content)
            tmp_path = f.name

        async with async_playwright() as p:
            # Try default Playwright Chromium first
            launch_kwargs: dict = {"headless": True}
            try:
                browser = await p.chromium.launch(**launch_kwargs)
            except Exception as e:
                # Playwright's own Chromium not downloaded yet — try local Chrome
                if "Executable doesn't exist" in str(e) or "executable" in str(e).lower():
                    local_exe = next(
                        (path for path in _LOCAL_CHROME_PATHS if Path(path).exists()),
                        None,
                    )
                    if local_exe:
                        logger.info(f"Using local Chrome: {local_exe}")
                        launch_kwargs["executable_path"] = local_exe
                        browser = await p.chromium.launch(**launch_kwargs)
                    else:
                        logger.warning("No local Chrome/Edge found — skipping browser preview")
                        return None
                else:
                    raise

            page = await browser.new_page(
                viewport={"width": viewport[0], "height": viewport[1]},
            )
            await page.goto(f"file://{tmp_path}", wait_until="networkidle", timeout=timeout_ms)
            # Wait a bit for CSS animations / JS to start
            await page.wait_for_timeout(800)
            screenshot_bytes = await page.screenshot(type="png")
            await browser.close()

        import io
        return Image.open(io.BytesIO(screenshot_bytes)).convert("RGB")

    except Exception as e:
        logger.warning(f"Playwright capture failed: {e}")
        return None
    finally:
        if tmp_path:
            try:
                Path(tmp_path).unlink(missing_ok=True)
            except Exception:
                pass


async def _capture_animated_with_playwright(
    html_content: str,
    viewport: tuple[int, int] = (1000, 600),
    timeout_ms: int = 5000,
    frame_count: int = 30,  # 30 frames for a smooth snippet
    capture_duration_ms: int = 2000,
) -> list[Image.Image] | None:
    """Capture multiple frames over a duration for animated preview."""
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        logger.warning("playwright not installed — skipping animated browser preview")
        return None

    _LOCAL_CHROME_PATHS = [
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    ]

    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".html", delete=False, mode="w", encoding="utf-8") as f:
            f.write(html_content)
            tmp_path = f.name

        async with async_playwright() as p:
            launch_kwargs: dict = {"headless": True}
            try:
                browser = await p.chromium.launch(**launch_kwargs)
            except Exception as e:
                if "Executable doesn't exist" in str(e) or "executable" in str(e).lower():
                    local_exe = next((path for path in _LOCAL_CHROME_PATHS if Path(path).exists()), None)
                    if local_exe:
                        launch_kwargs["executable_path"] = local_exe
                        browser = await p.chromium.launch(**launch_kwargs)
                    else:
                        return None
                else:
                    raise

            page = await browser.new_page(viewport={"width": viewport[0], "height": viewport[1]})
            await page.goto(f"file://{tmp_path}", wait_until="networkidle", timeout=timeout_ms)
            
            # Inject a fake CSS/SVG cursor on top of interactive elements (if any) to simulate real interaction
            await page.evaluate("""
                () => {
                    const btn = document.querySelector('button, input, .btn, .button, [role="button"], a');
                    if (btn) {
                        const rect = btn.getBoundingClientRect();
                        const cursor = document.createElement('div');
                        cursor.innerHTML = '<svg width="24" height="24" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg"><path d="M5.5 3.21V20.8C5.5 21.45 6.27 21.8 6.76 21.36L11.44 17H18.5C19.05 17 19.5 16.55 19.5 16V4C19.5 3.45 19.05 3 18.5 3H6.46C5.9 3 5.5 3.06 5.5 3.21Z" fill="white" stroke="black" stroke-width="1.5"/></svg>';
                        cursor.style.position = 'fixed';
                        cursor.style.left = (rect.left + rect.width / 2) + 'px';
                        cursor.style.top = (rect.top + rect.height / 2) + 'px';
                        cursor.style.zIndex = '999999';
                        cursor.style.pointerEvents = 'none';
                        // Add a subtle click bounce animation CSS
                        const style = document.createElement('style');
                        style.textContent = '@keyframes __autoClick { 0%,100% {transform:scale(1);} 50% {transform:scale(0.85);}}';
                        document.head.appendChild(style);
                        // Bind it to the click class that AI script might trigger
                        setInterval(() => {
                           cursor.style.animation = '__autoClick 0.3s ease';
                           setTimeout(()=> cursor.style.animation = '', 300);
                        }, 1500); // sync with typical AI JS loop
                        document.body.appendChild(cursor);
                    }
                }
            """)
            
            # Allow initial load/animations to start
            await page.wait_for_timeout(500)

            frames = []
            import io
            import time

            interval_ms = capture_duration_ms / frame_count
            for _ in range(frame_count):
                start_time = time.time()
                
                # Use JPEG for faster capture / less memory overhead
                screenshot_bytes = await page.screenshot(type="jpeg", quality=85)
                img = Image.open(io.BytesIO(screenshot_bytes)).convert("RGB")
                frames.append(img)
                
                elapsed_ms = (time.time() - start_time) * 1000
                wait_ms = max(0.0, interval_ms - elapsed_ms)
                if wait_ms > 0:
                    await page.wait_for_timeout(wait_ms)

            await browser.close()
            return frames
            
    except Exception as e:
        logger.warning(f"Animated Playwright capture failed: {e}")
        return None
    finally:
        if tmp_path:
            try:
                Path(tmp_path).unlink(missing_ok=True)
            except Exception:
                pass


def _capture_browser_preview(
    code: str,
    language: str,
    viewport: tuple[int, int] = (1000, 600),
    timeout_ms: int = 5000,
) -> Image.Image | None:
    """Synchronous wrapper around Playwright async capture."""
    import asyncio

    html_page = _build_html_page(code, language)
    try:
        return asyncio.run(
            _capture_with_playwright(html_page, viewport, timeout_ms)
        )
    except Exception as e:
        logger.warning(f"Browser preview failed: {e}")
        return None


def generate_animated_preview(
    html_code: str,
) -> list[Image.Image] | None:
    """Generate a multi-frame animated preview for visual UI content."""
    if not config.ENABLE_VISUAL_PREVIEW:
        return None

    import asyncio
    viewport = config.PLAYWRIGHT_VIEWPORT
    timeout = config.PLAYWRIGHT_TIMEOUT_MS

    logger.info("Generating animated browser preview for visual_ui content")
    html_page = _build_visual_ui_html(html_code)
    try:
        return asyncio.run(
            _capture_animated_with_playwright(
                html_page, 
                viewport, 
                timeout,
                frame_count=30,
                capture_duration_ms=2000,
            )
        )
    except Exception as e:
        logger.warning(f"Animated browser preview failed: {e}")
        return None


# ══════════════════════════════════════════════════════════════
#  TERMINAL PATH — Pillow-drawn terminal panel
# ══════════════════════════════════════════════════════════════

def _render_terminal_preview(
    code_output: str,
    language: str,
    width: int = 1000,
    height: int = 560,
) -> Image.Image:
    """Draw a styled terminal panel showing code execution output."""
    img = Image.new("RGB", (width, height), color=(13, 17, 23))  # #0d1117
    draw = ImageDraw.Draw(img)

    # ── Terminal chrome bar ────────────────────────────────
    chrome_h = 36
    draw.rectangle([0, 0, width, chrome_h], fill="#1c2128")

    # Traffic lights
    dot_cy = chrome_h // 2
    for i, color in enumerate(("#ff5f57", "#febc2e", "#28c840")):
        cx = 24 + i * 22
        draw.ellipse([cx - 5, dot_cy - 5, cx + 5, dot_cy + 5], fill=color)

    # Terminal title
    try:
        chrome_font = ImageFont.truetype(config.FONT_REGULAR, 13)
    except Exception:
        chrome_font = ImageFont.load_default()
    draw.text((width // 2, dot_cy), "Terminal — Output", fill="#8b949e",
              font=chrome_font, anchor="mm")

    # Separator
    draw.line([(0, chrome_h), (width, chrome_h)], fill="#30363d", width=1)

    # ── Output text ───────────────────────────────────────
    try:
        output_font = ImageFont.truetype(config.FONT_REGULAR, 18)
    except Exception:
        output_font = ImageFont.load_default()

    y = chrome_h + 16
    x_pad = 20

    # Prompt line
    prompt = f"$ {language}"
    draw.text((x_pad, y), prompt, fill="#8b949e", font=output_font)
    y += 28

    # Output lines
    if code_output:
        lines = code_output.split("\n")
        max_lines = (height - y - 10) // 24
        for line in lines[:max_lines]:
            # Truncate long lines
            if len(line) > 80:
                line = line[:77] + "..."
            draw.text((x_pad, y), line, fill="#7ee787", font=output_font)
            y += 24
    else:
        draw.text((x_pad, y), "(no output)", fill="#484f58", font=output_font)

    return img


# ══════════════════════════════════════════════════════════════
#  PUBLIC API
# ══════════════════════════════════════════════════════════════

def generate_preview_image(
    code: str,
    language: str,
    code_output: str | None = None,
) -> Image.Image | None:
    """Generate a preview image for the top panel.

    For HTML/CSS/JS content → Playwright browser screenshot.
    For Python/Bash/etc. → Pillow terminal panel with output.
    Returns None if preview cannot be generated.
    """
    if not config.ENABLE_VISUAL_PREVIEW:
        return None

    viewport = config.PLAYWRIGHT_VIEWPORT
    timeout = config.PLAYWRIGHT_TIMEOUT_MS

    # Path 1: Browser-renderable content
    if _is_browser_content(code, language):
        logger.info(f"Generating browser preview for {language} content")
        img = _capture_browser_preview(code, language, viewport, timeout)
        if img is not None:
            return img
        # Fallback to terminal if browser capture failed
        logger.info("Browser preview failed, falling back to terminal preview")

    # Path 2: Terminal output (Python, Bash, etc.)
    if code_output:
        logger.info(f"Generating terminal preview for {language} output")
        return _render_terminal_preview(
            code_output, language,
            width=viewport[0], height=viewport[1],
        )

    # No preview available
    return None
