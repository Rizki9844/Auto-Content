<div align="center">

# 🎬 Auto-Content

**Fully Automated AI-Powered Coding Shorts Pipeline**

*Generate → Render → Upload — Zero Human Intervention*

[![Python](https://img.shields.io/badge/Python_3.12-3776AB?style=for-the-badge&logo=python&logoColor=white)](#)
[![Gemini](https://img.shields.io/badge/Gemini_2.5_Flash-8E75B2?style=for-the-badge&logo=googlegemini&logoColor=white)](#)
[![YouTube](https://img.shields.io/badge/YouTube_Shorts-FF0000?style=for-the-badge&logo=youtube&logoColor=white)](#)
[![GitHub Actions](https://img.shields.io/badge/GitHub_Actions-2088FF?style=for-the-badge&logo=githubactions&logoColor=white)](#)
[![MongoDB](https://img.shields.io/badge/MongoDB_Atlas-47A248?style=for-the-badge&logo=mongodb&logoColor=white)](#)

</div>

---

## 📌 Overview

**Auto-Content** is a serverless, end-to-end pipeline that autonomously produces professional coding tutorial short videos and publishes them directly to YouTube Shorts — running entirely on GitHub Actions with zero infrastructure cost.

Every execution cycle generates a unique topic (never repeating thanks to MongoDB-powered deduplication), renders a polished vertical video with syntax-highlighted typing animation, natural AI voiceover, karaoke-style synced subtitles, and uploads it with optimized metadata — all in under 5 minutes.

## ✨ Core Features

| Feature | Description |
| :--- | :--- |
| **AI Content Engine** | Gemini 2.5 Flash generates structured content with 4 distinct content types, rotating across 15+ languages and categories |
| **Neural Text-to-Speech** | Microsoft Edge TTS produces natural voiceover with word-level timing for precise subtitle synchronization |
| **Cinema-Grade Renderer** | Pillow + Pygments render 1080×1920 frames with GitHub Dark theme syntax highlighting, smooth easing animations, and cinematic intro/outro cards |
| **Live Code Execution** | Sandboxed subprocess runner executes Python, JavaScript, and Bash snippets to display real output in videos |
| **Smart Deduplication** | MongoDB Atlas history prevents topic repetition across thousands of generations |
| **Telegram Monitoring** | Real-time bot notifications on pipeline success or failure — straight to your phone |
| **Credential Security** | Built-in log redaction filter masks MongoDB URIs, API keys, and OAuth tokens from CI output |

## 🎨 Content Types

The AI rotates between four distinct video formats to maximize viewer engagement:

```
┌──────────────────┬──────────────────────────────────────────────────────┐
│  💡 tip          │  Quick coding tricks and one-liners                 │
│  ▶️ output_demo  │  Code with real execution output shown live         │
│  🧠 quiz         │  "What does this print?" challenge with reveal      │
│  ✨ before_after │  Bad code → Better code transformation              │
└──────────────────┴──────────────────────────────────────────────────────┘
```

## 🏗️ Architecture

```
                    ┌─────────────────────────────────┐
                    │       GitHub Actions (cron)      │
                    │    ┌─────────────────────────┐   │
                    │    │   ubuntu-latest runner   │   │
                    │    └────────────┬────────────┘   │
                    └─────────────────┼────────────────┘
                                      │
          ┌───────────────────────────┼───────────────────────────┐
          ▼                           ▼                           ▼
  ┌───────────────┐          ┌───────────────┐          ┌───────────────┐
  │   Gemini AI   │          │  MongoDB Atlas │          │  YouTube API  │
  │  Content Gen  │          │   Dedup Store  │          │ Shorts Upload │
  └───────┬───────┘          └───────────────┘          └───────▲───────┘
          │                                                     │
          ▼                                                     │
  ┌───────────────┐     ┌───────────────┐     ┌───────────────┐ │
  │   Edge TTS    │────▶│   Renderer    │────▶│    moviepy    │─┘
  │  + Timestamps │     │  Pillow/Pyg   │     │  Video Build  │
  └───────────────┘     └───────────────┘     └───────────────┘
                              │
                        ┌─────┴─────┐
                        ▼           ▼
                  ┌───────────┐ ┌──────────┐
                  │  Code     │ │ Telegram  │
                  │  Runner   │ │ Notifier  │
                  └───────────┘ └──────────┘
```

### Pipeline Flow

1. **Content Generation** — Gemini 2.5 Flash generates structured JSON with code, narration, hashtags, and content-type-specific fields
2. **Code Execution** — For `output_demo` and `quiz` types, a sandboxed subprocess runs the code to capture real output
3. **Voiceover Synthesis** — Edge TTS generates audio with word-level timestamps for subtitle synchronization
4. **Video Rendering** — Pillow renders each frame (intro card → typing animation → output panel → outro CTA) at 30fps
5. **Video Assembly** — moviepy composites frames + audio into a 1080×1920 MP4
6. **YouTube Upload** — OAuth2-authenticated upload as YouTube Shorts with auto-generated metadata
7. **Record & Notify** — MongoDB stores the full record; Telegram sends a status alert

## 🛠️ Stack & Dependencies

| Category | Technology | Version | Purpose |
| :--- | :--- | :--- | :--- |
| **LLM** | Google Gemini (genai SDK) | ≥1.0.0 | AI content generation with structured JSON output |
| **TTS** | edge-tts | ≥6.1.0 | Neural voiceover with word-level timestamps |
| **Video** | moviepy | 2.x | Video composition and audio sync |
| **Graphics** | Pillow | ≥10.0.0 | Frame-by-frame rendering with anti-aliased text |
| **Syntax** | Pygments | ≥2.17.0 | Token-level syntax highlighting (GitHub Dark) |
| **Database** | pymongo[srv] | ≥4.6.0 | MongoDB Atlas operations + deduplication |
| **Upload** | google-api-python-client | ≥2.100.0 | YouTube Data API v3 |
| **Auth** | google-auth-oauthlib | ≥1.2.0 | OAuth2 refresh token flow |
| **Runtime** | Python | 3.12 | Primary runtime |
| **CI/CD** | GitHub Actions | ubuntu-latest | Scheduled + manual execution |

<details>
<summary><b>📂 Project Structure</b></summary>

```text
.
├── .github/
│   └── workflows/
│       └── generate.yml          # Cron schedule (2×/day) + manual dispatch
├── assets/
│   └── fonts/
│       ├── JetBrainsMono-Bold.ttf
│       └── JetBrainsMono-Regular.ttf
├── scripts/
│   └── auth_youtube.py           # One-time OAuth2 setup helper
├── src/
│   ├── __init__.py
│   ├── main.py                   # Pipeline orchestrator (5-step flow)
│   ├── config.py                 # Centralized config (env vars, colors, layout)
│   ├── llm.py                    # Gemini content gen + 5-step JSON repair
│   ├── tts.py                    # Edge TTS with word timestamps
│   ├── renderer.py               # Frame renderer (800+ lines of Pillow magic)
│   ├── video.py                  # moviepy video assembly
│   ├── code_runner.py            # Sandboxed code execution (Python/JS/bash)
│   ├── uploader_youtube.py       # YouTube Shorts OAuth2 upload
│   ├── notifier.py               # Telegram Bot API notifications
│   └── db.py                     # MongoDB Atlas CRUD + stats
└── requirements.txt
```

</details>

## 🔒 Security Design

| Layer | Mechanism |
| :--- | :--- |
| **Credential Storage** | All secrets stored as GitHub Actions encrypted secrets — never in code |
| **Log Redaction** | `CredentialFilter` regex masks MongoDB URIs, API keys, and OAuth tokens in CI logs |
| **Code Sandbox** | Pattern-based blocklist prevents `os`, `subprocess`, `eval`, filesystem, and network access in executed snippets |
| **Execution Limits** | 10-second timeout + 500-char output cap per code execution |
| **OAuth2** | Refresh token flow — no long-lived access tokens stored |
| **GitHub Actions** | Pinned action SHAs prevent supply-chain attacks; minimal `contents: write` permission |

## ⚙️ Environment Configuration

### Required Secrets (GitHub Actions → Settings → Secrets)

| Secret | Description |
| :--- | :--- |
| `GEMINI_API_KEY` | Google AI Studio API key |
| `MONGODB_URI` | MongoDB Atlas connection string |
| `YOUTUBE_CLIENT_ID` | Google OAuth2 client ID |
| `YOUTUBE_CLIENT_SECRET` | Google OAuth2 client secret |
| `YOUTUBE_REFRESH_TOKEN` | YouTube OAuth2 refresh token |

### Optional Secrets

| Secret | Description |
| :--- | :--- |
| `TELEGRAM_BOT_TOKEN` | Telegram bot token from @BotFather |
| `TELEGRAM_CHAT_ID` | Target Telegram chat ID |

### Optional Variables (GitHub Actions → Settings → Variables)

| Variable | Default | Description |
| :--- | :--- | :--- |
| `CHANNEL_NAME` | `@DevInSeconds` | Watermark branding on video |
| `GEMINI_MODEL` | `gemini-2.5-flash` | Gemini model identifier |
| `TTS_VOICE` | `en-US-GuyNeural` | Microsoft Neural TTS voice |

## 📅 Schedule

Automated via GitHub Actions cron:

| Time (UTC) | Time (WIB) | Frequency |
| :--- | :--- | :--- |
| `08:00` | 15:00 | Daily |
| `20:00` | 03:00 | Daily |

Manual trigger available via **Actions** → **Run workflow**.

<details>
<summary><b>🚀 Local Development</b></summary>

Prerequisites: Python 3.12+, FFmpeg, Node.js 20+

```bash
# 1. Clone
git clone https://github.com/Rizki9844/Auto-Content.git
cd Auto-Content

# 2. Install dependencies
python -m venv .venv
.venv\Scripts\activate        # Windows
pip install -r requirements.txt

# 3. Set environment variables
cp .env.example .env          # Edit with your credentials

# 4. Run pipeline
python -m src.main
```

</details>

---

<div align="center">

**Built with** 🐍 Python **·** 🤖 Gemini AI **·** 🎬 moviepy **·** ☁️ GitHub Actions

<sub>Hak Cipta © 2026 Rizki Malik Fajar. All rights reserved.</sub>

</div>
