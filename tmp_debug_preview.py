import asyncio
from src.preview_renderer import _capture_with_playwright

html_test = """
<!DOCTYPE html>
<html>
<head>
<style>
  body {
    margin: 0;
    padding: 0;
    display: flex;
    justify-content: center;
    align-items: center;
    height: 100vh;
    background: linear-gradient(135deg, #1e3a8a, #9333ea);
    color: white;
    font-family: sans-serif;
  }
  h1 { font-size: 50px; }
</style>
</head>
<body>
  <h1>Hello Playwright</h1>
</body>
</html>
"""

async def main():
    print("Capturing...")
    img = await _capture_with_playwright(html_test, viewport=(1000, 700))
    if img:
        img.save("debug_preview.png")
        print("Saved debug_preview.png")
    else:
        print("Capture failed.")

if __name__ == "__main__":
    asyncio.run(main())
