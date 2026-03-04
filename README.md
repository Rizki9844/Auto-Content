<div align="center">

# 🎬 Auto-Content

**Fully Automated AI-Powered Coding Shorts Pipeline**

*Generate → Render → Upload — Zero Human Intervention*

[![Python](https://img.shields.io/badge/Python_3.12+-3776AB?style=for-the-badge&logo=python&logoColor=white)](#)
[![Gemini](https://img.shields.io/badge/Gemini_2.5_Flash-8E75B2?style=for-the-badge&logo=googlegemini&logoColor=white)](#)
[![YouTube](https://img.shields.io/badge/YouTube_Shorts-FF0000?style=for-the-badge&logo=youtube&logoColor=white)](#)
[![GitHub Actions](https://img.shields.io/badge/GitHub_Actions-2088FF?style=for-the-badge&logo=githubactions&logoColor=white)](#)
[![MongoDB](https://img.shields.io/badge/MongoDB_Atlas-47A248?style=for-the-badge&logo=mongodb&logoColor=white)](#)
[![Tests](https://img.shields.io/badge/Tests-744_passing-brightgreen?style=for-the-badge)](#)

</div>

---

## 📌 Overview

**Auto-Content** is a serverless, end-to-end pipeline that autonomously produces professional coding tutorial short videos and publishes them directly to YouTube Shorts — running entirely on GitHub Actions with zero infrastructure cost.

Every execution cycle generates a unique topic (never repeating thanks to MongoDB-powered deduplication), renders a polished vertical video with syntax-highlighted typing animation, natural AI voiceover, karaoke-style synced subtitles, and uploads it with optimized metadata — all in under 5 minutes.

## ✨ Features

### 🧠 Content Intelligence
| Feature | Description |
| :--- | :--- |
| **AI Content Engine** | Gemini 2.5 Flash generates structured content with 4 distinct types, rotating across 15+ languages |
| **Trending Topics** | Google Trends + YouTube Trending integration for topic freshness |
| **YouTube Analytics Loop** | Fetches views, likes, AVD — feeds back into prompt optimization |
| **Multi-Language** | Full Bahasa Indonesia (`id`) support with localized narration & TTS |
| **Series Generator** | Multi-episode series planning with episode chaining |
| **Prompt A/B Testing** | Variant A vs B prompt rotation with performance tracking |
| **Content Templates** | Reusable template library (Python tips, JS patterns, Git tricks) |
| **Voice & Tone Variety** | Energetic, calm, curious, dramatic — auto-rotates daily |

### 🎨 Visual Excellence
| Feature | Description |
| :--- | :--- |
| **Cinema-Grade Renderer** | 1080×1920 Pillow frames with syntax highlighting, smooth easing, and cinematic cards |
| **Animated Code Highlighting** | Line-level glow synced to narration word timestamps |
| **Theme System** | GitHub Dark, Monokai, Dracula — auto-rotate or pick one |
| **Background Particles** | Subtle animated particles for visual depth |
| **Line Slide-In** | Each code line slides in from left for smooth appearance |
| **AI Thumbnails v2** | Stability AI backgrounds + Pillow text overlay (with auto-cache) |

### 📈 Growth Engine
| Feature | Description |
| :--- | :--- |
| **SEO Descriptions** | AI-generated YouTube descriptions with keywords, timestamps, hashtags |
| **Auto Pinned Comments** | CTA comment posted automatically after upload |
| **Smart Playlists** | Auto-managed playlists per language and series |
| **Upload Queue** | Retry-safe queue with exponential backoff |
| **Rate Limiter** | Token bucket rate limiting for all external APIs |
| **Multi-Channel** | Upload to multiple YouTube channels simultaneously |

### 🛡️ Production Reliability
| Feature | Description |
| :--- | :--- |
| **Self-Healing** | Health monitor with auto-recovery, Gemini model fallback |
| **DB Maintenance** | Auto-archive old records, storage alerts at 80% capacity |
| **Pipeline Logger** | Step-by-step structured logging with timing |
| **Graceful Timeouts** | Per-step timeout with automatic cleanup |
| **Staging Workflow** | Separate staging environment for safe testing |

### 🎵 Advanced Features
| Feature | Description |
| :--- | :--- |
| **Background Music** | Royalty-free lo-fi track mixing with anti-repeat logic |
| **Dashboard** | Flask web UI for monitoring pipeline, videos, analytics, health |

### 🔧 Core Pipeline
| Feature | Description |
| :--- | :--- |
| **Neural TTS** | Microsoft Edge TTS with word-level timing for subtitle sync |
| **Live Code Execution** | Sandboxed subprocess runs Python, JavaScript, Bash snippets |
| **Smart Deduplication** | MongoDB history prevents topic repetition |
| **Telegram Monitoring** | Real-time notifications on success or failure |
| **Credential Security** | Log redaction masks all secrets from CI output |

## 🎨 Content Types

The AI rotates between four distinct video formats to maximize engagement:

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
    ┌─────────────┬───────────────────┼───────────────────┬─────────────┐
    ▼             ▼                   ▼                   ▼             ▼
┌─────────┐ ┌──────────┐     ┌───────────────┐    ┌──────────┐ ┌──────────┐
│ Gemini  │ │ Trending │     │  MongoDB Atlas │    │ YouTube  │ │ Stability│
│ Content │ │ (Google  │     │  Dedup + Stats │    │ Data API │ │ AI (Thumb│
│  Gen    │ │ Trends)  │     └───────────────┘    │ Upload   │ │  nails)  │
└────┬────┘ └──────────┘                           └─────▲────┘ └──────────┘
     │                                                   │
     ▼                                                   │
┌──────────┐    ┌──────────┐    ┌──────────┐    ┌───────┴──────┐
│ Edge TTS │───▶│ BG Music │───▶│ Renderer │───▶│ moviepy      │
│ + Timing │    │  Mixer   │    │ Pillow   │    │ Video Build  │
└──────────┘    └──────────┘    └──────────┘    └──────────────┘
                                      │
                              ┌───────┴───────┐
                              ▼               ▼
                        ┌──────────┐    ┌──────────┐
                        │  Code    │    │ Telegram  │
                        │  Runner  │    │ Notifier  │
                        └──────────┘    └──────────┘
```

### Pipeline Flow

1. **Content Generation** — Gemini 2.5 Flash generates structured JSON with code, narration, hashtags
2. **Code Execution** — Sandboxed subprocess runs the code to capture real output
3. **Voiceover Synthesis** — Edge TTS generates audio with word-level timestamps
4. **Background Music** — Optional lo-fi track mixed at 7% volume with fade in/out
5. **Video Rendering** — Pillow renders frames at 30fps with animated highlights
6. **Video Assembly** — moviepy composites frames + audio into a 1080×1920 MP4
7. **Thumbnail** — Pillow or AI-generated (Stability AI) cover image
8. **YouTube Upload** — OAuth2-authenticated upload with SEO metadata, auto-comment, playlist
9. **Record & Notify** — MongoDB stores record; Telegram sends status alert

## 🛠️ Stack & Dependencies

| Category | Technology | Purpose |
| :--- | :--- | :--- |
| **LLM** | Google Gemini (genai SDK) | AI content generation with structured JSON |
| **TTS** | edge-tts / gTTS (fallback) | Neural voiceover with word-level timestamps |
| **Video** | moviepy 2.x | Video composition, audio sync, BG music mixing |
| **Graphics** | Pillow + Pygments | Frame rendering with syntax highlighting |
| **Database** | pymongo[srv] | MongoDB Atlas operations + deduplication |
| **Upload** | google-api-python-client | YouTube Data API v3 |
| **Auth** | google-auth-oauthlib | OAuth2 refresh token flow |
| **Dashboard** | Flask | Pipeline monitoring web UI |
| **AI Thumbnails** | requests + Stability AI | AI-generated video thumbnails |
| **Trending** | pytrends | Google Trends integration |
| **Runtime** | Python 3.12+ | Primary runtime |
| **CI/CD** | GitHub Actions | Scheduled (3×/day) + manual execution |

<details>
<summary><b>📂 Project Structure</b></summary>

```text
.
├── .github/workflows/
│   ├── generate.yml              # Main pipeline (cron 3×/day + manual)
│   ├── upload-queue.yml          # Upload retry queue
│   ├── ci.yml                    # Test suite on push/PR
│   └── staging.yml               # Staging environment pipeline
├── assets/
│   ├── fonts/
│   │   ├── JetBrainsMono-Bold.ttf
│   │   └── JetBrainsMono-Regular.ttf
│   └── music/                    # Royalty-free background tracks
├── dashboard/
│   ├── app.py                    # Flask monitoring dashboard
│   └── templates/                # Dark-themed HTML templates
├── scripts/
│   └── auth_youtube.py           # OAuth2 setup (supports multi-channel)
├── src/
│   ├── main.py                   # Pipeline orchestrator
│   ├── config.py                 # Centralized config (env vars, colors, layout)
│   ├── llm.py                    # Gemini content gen + JSON repair + templates
│   ├── tts.py                    # Edge TTS / gTTS with word timestamps
│   ├── renderer.py               # Frame renderer (1200+ lines)
│   ├── video.py                  # moviepy video assembly
│   ├── bgmusic.py                # Background music selection & mixing
│   ├── code_runner.py            # Sandboxed code execution (Python/JS/Bash)
│   ├── uploader_youtube.py       # YouTube Shorts OAuth2 upload
│   ├── uploader_base.py          # Base uploader with retry queue
│   ├── multi_channel.py          # Multi-channel YouTube support
│   ├── thumbnail.py              # Pillow + AI (Stability) thumbnail generator
│   ├── seo.py                    # SEO description generator
│   ├── youtube_actions.py        # Auto-comment, playlists, end-screen
│   ├── playlist_manager.py       # Playlist CRUD
│   ├── trending.py               # Google Trends + YouTube Trending
│   ├── yt_analytics.py           # YouTube Analytics feedback loop
│   ├── series_planner.py         # Multi-episode series planning
│   ├── analytics.py              # Content performance analytics
│   ├── scheduler.py              # Smart upload scheduling
│   ├── rate_limiter.py           # Token bucket rate limiter
│   ├── health_monitor.py         # Self-healing health checks
│   ├── db_maintenance.py         # Archive, cleanup, storage alerts
│   ├── pipeline_logger.py        # Structured step logging
│   ├── quality.py                # Content quality scoring
│   ├── notifier.py               # Telegram notifications
│   ├── db.py                     # MongoDB Atlas CRUD + stats
│   ├── theme_loader.py           # Theme system (JSON themes)
│   ├── errors.py                 # Custom exception hierarchy
│   └── plugins/                  # Plugin system (event logger, etc.)
├── templates/                    # Content template library (JSON)
├── themes/                       # Color themes (github_dark, monokai, dracula)
├── tests/                        # 744 tests across 14 test files
└── requirements.txt
```

</details>

## 🔒 Security Design

| Layer | Mechanism |
| :--- | :--- |
| **Credential Storage** | All secrets stored as GitHub Actions encrypted secrets — never in code |
| **Log Redaction** | `CredentialFilter` regex masks MongoDB URIs, API keys, and OAuth tokens in CI logs |
| **Code Sandbox** | Pattern-based blocklist prevents `os`, `subprocess`, `eval`, filesystem, and network access |
| **Execution Limits** | 10-second timeout + 500-char output cap per code execution |
| **OAuth2** | Refresh token flow — no long-lived access tokens stored |
| **GitHub Actions** | Pinned action SHAs prevent supply-chain attacks; minimal permissions |
| **Self-Healing** | Auto-recovery from API failures with model fallback |

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
| `STABILITY_API_KEY` | Stability AI key (for AI thumbnails) |
| `YOUTUBE_CHANNEL_ID` | YouTube channel ID (for analytics) |
| `YOUTUBE_API_KEY` | YouTube API key (for trending/analytics) |

### Optional Variables

| Variable | Default | Description |
| :--- | :--- | :--- |
| `CHANNEL_NAME` | `@DevInSeconds` | Watermark branding on video |
| `GEMINI_MODEL` | `gemini-2.5-flash` | Gemini model identifier |
| `TTS_VOICE` | `en-US-ChristopherNeural` | Microsoft Neural TTS voice |
| `CONTENT_LANGUAGE` | `en` | Content language (`en` / `id`) |
| `ACTIVE_THEME` | `github_dark` | Color theme (github_dark / monokai / dracula) |
| `AUTO_ROTATE_THEMES` | `0` | Set `1` to rotate themes daily |
| `PROMPT_VARIANT` | `auto` | A/B test variant (`A` / `B` / `auto`) |
| `NARRATOR_TONE` | `auto` | Voice tone (energetic / calm / curious / dramatic / auto) |
| `ENABLE_BGMUSIC` | `0` | Set `1` to enable background music |
| `ENABLE_THUMBNAILS` | `0` | Set `1` to generate custom thumbnails |
| `THUMBNAIL_STYLE` | `pillow` | Thumbnail engine (`pillow` / `ai`) |
| `ENABLE_YT_ANALYTICS` | `0` | Set `1` to enable analytics feedback |
| `ENABLE_TRENDING` | `0` | Set `1` to use trending topics |
| `ENABLE_SEO_DESCRIPTION` | `1` | SEO-optimized video descriptions |
| `ENABLE_SMART_SCHEDULE` | `0` | Analytics-based upload timing |
| `ENVIRONMENT` | `production` | `production` / `staging` |

## 📊 Dashboard

Run the built-in monitoring dashboard locally:

```bash
python -m dashboard.app
# Open http://localhost:5050
```

**Routes:** Overview (`/`) · Videos (`/videos`) · Analytics (`/analytics`) · Health (`/health`) · API (`/api/stats`)

## 📅 Schedule

Automated via GitHub Actions cron — optimized for US audience peak engagement:

| Time (UTC) | Time (EST) | Time (PST) | Target |
| :--- | :--- | :--- | :--- |
| `13:00` | 8:00 AM | 5:00 AM | Morning commute |
| `18:00` | 1:00 PM | 10:00 AM | Lunch break |
| `00:00` | 7:00 PM | 4:00 PM | Prime time (evening) |

Plus monthly maintenance run at `03:00 UTC` on the 1st of each month.

Manual trigger available via **Actions** → **Run workflow**.

## 🧪 Testing

```bash
# Run full test suite (744 tests)
python -m pytest

# Run specific phase tests
python -m pytest tests/test_phase9.py -v
```

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

# 5. Run tests
python -m pytest
```

</details>

---

<div align="center">

**Built with** 🐍 Python **·** 🤖 Gemini AI **·** 🎬 moviepy **·** ☁️ GitHub Actions

**744 tests** · **9 development phases** · **10,000+ lines of production code**

<sub>Copyright © 2026 Rizki Malik Fajar. All rights reserved.</sub>

</div>
