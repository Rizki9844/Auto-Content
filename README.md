# 🎬 Auto-Content — Automated Coding Shorts Pipeline

Fully automated pipeline that generates, renders, and uploads coding tutorial short videos to YouTube — powered by AI, zero manual effort.

## What It Does

Every run (2× daily via GitHub Actions):

1. **AI Content Generation** — Gemini 2.5 Flash generates unique coding tips, output demos, quizzes, and before/after comparisons across 15+ programming languages
2. **Text-to-Speech** — Microsoft Neural TTS creates natural voiceover with word-level timestamps
3. **Video Rendering** — Pillow + moviepy produce 1080×1920 vertical video with typing animation, syntax highlighting, intro/outro cards, and synced subtitles
4. **Code Execution** — Safe sandbox runs code snippets (Python/JS/bash) to show real output in videos
5. **YouTube Upload** — Automatically uploads as YouTube Shorts with title, description, and hashtags
6. **Notifications** — Telegram bot alerts on success/failure (optional)
7. **Deduplication** — MongoDB Atlas tracks history to ensure unique content every time

## Content Types

| Type | Description |
|------|-------------|
| `tip` | Quick coding tips and tricks |
| `output_demo` | Code with actual execution output shown |
| `quiz` | "What does this code print?" with reveal |
| `before_after` | Code improvement comparisons |

## Tech Stack

| Component | Technology |
|-----------|-----------|
| AI / LLM | Google Gemini 2.5 Flash |
| TTS | Microsoft Edge TTS (Neural) |
| Video | moviepy 2.x + Pillow + Pygments |
| Database | MongoDB Atlas (M0 free tier) |
| Upload | YouTube Data API v3 (OAuth2) |
| Notifications | Telegram Bot API |
| CI/CD | GitHub Actions (scheduled + manual) |
| Code Execution | Subprocess sandbox (Python, Node.js, bash) |

## Project Structure

```
├── .github/workflows/
│   └── generate.yml        # GitHub Actions workflow (2× daily)
├── assets/fonts/            # JetBrains Mono fonts
├── scripts/
│   └── auth_youtube.py      # One-time OAuth setup script
├── src/
│   ├── main.py              # Pipeline orchestrator
│   ├── config.py            # Centralized configuration
│   ├── llm.py               # Gemini content generation + JSON repair
│   ├── tts.py               # Edge TTS with word timestamps
│   ├── renderer.py          # Video frame rendering (Pillow)
│   ├── video.py             # Video assembly (moviepy)
│   ├── code_runner.py       # Safe code execution sandbox
│   ├── uploader_youtube.py  # YouTube Shorts upload
│   ├── notifier.py          # Telegram notifications
│   └── db.py                # MongoDB Atlas operations
└── requirements.txt
```

## Required Secrets (GitHub Actions)

| Secret | Description |
|--------|-------------|
| `GEMINI_API_KEY` | Google AI Studio API key |
| `MONGODB_URI` | MongoDB Atlas connection string |
| `YOUTUBE_CLIENT_ID` | Google OAuth client ID |
| `YOUTUBE_CLIENT_SECRET` | Google OAuth client secret |
| `YOUTUBE_REFRESH_TOKEN` | YouTube OAuth refresh token |

### Optional Secrets

| Secret | Description |
|--------|-------------|
| `TELEGRAM_BOT_TOKEN` | Telegram bot token (from @BotFather) |
| `TELEGRAM_CHAT_ID` | Your Telegram chat ID |

## Schedule

Runs automatically via GitHub Actions:
- **08:00 UTC** (15:00 WIB)
- **20:00 UTC** (03:00 WIB)

Can also be triggered manually from the Actions tab.

## License

Private project — all rights reserved.
