# 🗺️ Development Roadmap — Auto-Content Pipeline

> **Document ini mencatat seluruh rencana pengembangan berdasarkan hasil audit arsitektur profesional.**
> Dibuat setelah analisis mendalam terhadap 13 file / 2.680+ baris kode.
>
> **Last updated:** 2 Maret 2026

---

## 📊 Progress Overview

| Phase | Nama | Status | Tasks |
| :---: | :--- | :---: | :---: |
| 1 | Stabilization & Security | ✅ Complete | 7/7 |
| 2 | Observability & Testing | ⬜ Not Started | 0/7 |
| 3 | Feature Hardening | ⬜ Not Started | 0/7 |
| 4 | Scale & Extensibility | ⬜ Not Started | 0/7 |

**Total: 28 tasks** — 7 completed, 21 remaining

---

## ✅ Phase 1 — Stabilization & Security

> **Goal:** Perbaiki bug kritis, hardening keamanan, optimasi performa renderer, dan tambahkan mekanisme retry.
>
> **Status:** ✅ Complete — Commit `13cee22` (2 Maret 2026)
>
> **Files changed:** 8 files, +313 / -145 lines

### 1.1 Fix CredentialFilter Regex ✅

| Item | Detail |
| :--- | :--- |
| **File** | `src/main.py` |
| **Masalah** | `PATTERNS` adalah list regex tunggal dengan replacement `\2` yang mereferensikan capture group yang tidak ada (hanya 1 group). Menyebabkan `re.error` silent failure — credential bisa bocor ke log. |
| **Solusi** | Ubah `PATTERNS` menjadi list of `(regex, replacement)` tuples. Setiap pattern punya replacement string sendiri. `record.args = None` (bukan `()`) untuk mencegah `TypeError` pada `%s`-style formatting. Tambahkan `try/except` di `getMessage()`. |
| **Impact** | MongoDB URI, Gemini API key, OAuth token, dan refresh token sekarang **pasti** ter-redact di log output. |

### 1.2 Rewrite Code Sandbox ✅

| Item | Detail |
| :--- | :--- |
| **File** | `src/code_runner.py` (complete rewrite, ~345 lines) |
| **Masalah** | Sandbox lama menggunakan string-matching blocklist yang mudah di-bypass: `from os import system`, `importlib.import_module('os')`, `__builtins__.__import__` semuanya lolos. |
| **Solusi** | **Python:** AST-level validation — `ast.parse()` + `ast.walk()` mengecek setiap `Import`, `ImportFrom`, `Call`, dan `Attribute` node. `_BANNED_MODULES` (20+), `_BANNED_BUILTINS` (15+), `_BANNED_ATTRS` (15+) sebagai `frozenset`. **JavaScript:** Pattern list diperluas (`import(`, `import `, `global.`, `Deno.`, `Bun.`). **Bash:** Validasi SETIAP command dalam pipeline (split `\|`), bukan hanya kata pertama. Allow-list approach. |
| **Strategi eksekusi baru** | `expected_output` dari LLM dipakai PERTAMA (paling aman). Real execution hanya jika `expected_output` kosong. Timeout dikurangi 10s → 5s. Semua subprocess pakai restricted env tanpa access ke secrets. |

### 1.3 Pre-compute Renderer Gradient ✅

| Item | Detail |
| :--- | :--- |
| **File** | `src/renderer.py` |
| **Masalah** | `_create_gradient_bg()` dipanggil 3× (base, intro, outro) dan masing-masing menjalankan 1.920 iterasi `draw.line()` — total 5.760 PIL draw calls. Per-frame intro blend juga memanggil ulang fungsi ini. |
| **Solusi** | (1) Gradient dihitung SEKALI di `__init__` menggunakan `numpy` (`np.linspace` + `np.broadcast_to`) — ~100× lebih cepat. (2) Disimpan sebagai `self._gradient_bg`. (3) Ketiga method (`_create_base_image`, `_create_intro_image`, `_create_outro_image`) menggunakan `self._gradient_bg.copy()`. (4) `_render_intro()` blend menggunakan `self._gradient_bg` langsung (blend membuat image baru, jadi aman tanpa `.copy()`). (5) Dead import `from functools import lru_cache` dihapus. |
| **Impact** | Estimasi penghematan ~2-3 detik per video render. Memory stabil (1 gradient ~6MB + 3 copy saat init saja). |

### 1.4 Add Retry + Exponential Backoff ✅

| Item | Detail |
| :--- | :--- |
| **Files** | `src/llm.py`, `src/uploader_youtube.py`, `src/tts.py` |
| **Masalah (llm.py)** | Fixed `RETRY_DELAY = 10` — jika Gemini API overloaded, retry terus dalam interval sama tanpa memberi waktu recovery. |
| **Solusi (llm.py)** | `BASE_RETRY_DELAY = 5` dengan formula `5 × 2^(attempt-1)` → delay 5s, 10s, 20s. |
| **Masalah (uploader)** | Zero retry — jika upload chunk gagal (network hiccup), seluruh pipeline langsung fail. Token refresh juga tanpa retry. |
| **Solusi (uploader)** | (1) Token refresh: 3 attempts dengan delay `2 × attempt` (2s, 4s, 6s). (2) Upload chunk: 3 retries dengan exponential backoff `5 × 2^(n-1)` (5s, 10s, 20s). Error chaining via `raise ... from e`. |
| **Masalah (tts.py)** | `asyncio.get_event_loop()` deprecated di Python 3.12+. Anti-pattern ThreadPoolExecutor fallback yang tidak perlu. |
| **Solusi (tts.py)** | Ganti seluruh blok menjadi `asyncio.run()` — clean, standard sejak Python 3.7+. |

### 1.5 Pin setup-node SHA + Clean Dead Imports ✅

| Item | Detail |
| :--- | :--- |
| **Files** | `.github/workflows/generate.yml`, `src/db.py` |
| **Masalah (CI)** | `actions/setup-node@v4` menggunakan floating tag — vulnerable terhadap supply-chain attack jika tag di-hijack. |
| **Solusi (CI)** | Pin ke SHA `49933ea5288caeca8642d1e84afbd3f7d6820020` (v4.4.0). Sekarang ketiga actions (checkout, setup-python, setup-node) semua pinned SHA. |
| **Masalah (db.py)** | `from pymongo.encryption_options import AutoEncryptionOpts` — tidak pernah digunakan, dan import akan crash tanpa package `pymongocrypt`. |
| **Solusi (db.py)** | Hapus import. |

### 1.6 Content Safety Check ✅

| Item | Detail |
| :--- | :--- |
| **File** | `src/main.py` |
| **Masalah** | LLM bisa menghasilkan konten yang tidak pantas dan langsung di-upload ke YouTube tanpa filter apapun. |
| **Solusi** | `_BLOCKED_KEYWORDS` frozenset (4 kategori: violence, hate speech, explicit, illegal activity). Fungsi `_is_content_safe()` mengecek title + script + code + code_before + expected_output. Ditempatkan setelah content generation, **sebelum** TTS/render/upload. Jika terblokir → `RuntimeError` → ditangkap exception handler → disimpan ke MongoDB + notifikasi Telegram. |
| **Catatan** | Keyword `"kill"` dan `"exploit"` punya false positive risk rendah (konteks coding tip), perlu dimonitor. |

---

## ⬜ Phase 2 — Observability & Testing

> **Goal:** Tambahkan unit test, structured logging, dan monitoring agar pipeline bisa dipercaya dalam jangka panjang.
>
> **Status:** Not Started

### 2.1 Unit Tests — Core Modules

| Item | Detail |
| :--- | :--- |
| **Target** | `tests/test_llm.py`, `tests/test_code_runner.py`, `tests/test_renderer.py` |
| **Scope** | (1) `_repair_json()` — test 5+ kasus edge (truncated, unescaped newlines, missing braces). (2) `_is_python_safe_ast()` — test banned imports, builtins, attributes, dan kode yang seharusnya AMAN. (3) `_is_js_safe()`, `_is_bash_safe()` — same approach. (4) `_create_gradient_bg()` — output shape dan dtype correct. |
| **Framework** | `pytest` + `pytest-cov` (target coverage ≥ 70%) |
| **Priority** | 🔴 High — zero tests saat ini sangat berisiko untuk regressions |

### 2.2 Unit Tests — Safety Filter & CredentialFilter

| Item | Detail |
| :--- | :--- |
| **Target** | `tests/test_main.py` |
| **Scope** | (1) `_is_content_safe()` — test blocked keywords, safe content, edge cases. (2) `CredentialFilter` — test redaction of MongoDB URI, API keys, tokens. Test bahwa pesan normal TIDAK ter-redact. |

### 2.3 Integration Test — Pipeline Dry-Run

| Item | Detail |
| :--- | :--- |
| **Target** | `tests/test_integration.py` |
| **Scope** | Mock Gemini API, edge-tts, dan YouTube upload. Run `main()` end-to-end dan verify: (1) record tersimpan ke MongoDB, (2) video file terbuat, (3) tidak ada uncaught exceptions. |
| **Benefit** | Bisa dijalankan di CI tanpa secrets (semua API di-mock). |

### 2.4 Structured JSON Logging

| Item | Detail |
| :--- | :--- |
| **Target** | `src/main.py` logging config |
| **Scope** | Tambahkan opsi `LOG_FORMAT=json` via env variable. Output `{"timestamp": "...", "level": "INFO", "module": "pipeline", "message": "..."}`. Berguna jika nanti pakai log aggregator (Datadog, Loki, dll). |
| **Default** | Tetap human-readable format seperti sekarang jika `LOG_FORMAT` tidak di-set. |

### 2.5 Pipeline Metrics Tracking

| Item | Detail |
| :--- | :--- |
| **Target** | `src/db.py` (tambah field ke MongoDB record) |
| **Scope** | Track: `gemini_latency_ms`, `tts_latency_ms`, `render_latency_ms`, `upload_latency_ms`, `total_latency_ms`, `retry_count` per step. Simpan di MongoDB record. |
| **Benefit** | Bisa query MongoDB untuk melihat trend performa seiring waktu. |

### 2.6 GitHub Actions CI Workflow

| Item | Detail |
| :--- | :--- |
| **Target** | `.github/workflows/ci.yml` (workflow baru) |
| **Scope** | Trigger on PR/push. Run: `py_compile` semua file → `pytest` → `ruff` linter. Block merge jika gagal. |
| **Benefit** | Mencegah kode rusak masuk ke main branch. |

### 2.7 Health Check Endpoint

| Item | Detail |
| :--- | :--- |
| **Target** | `src/main.py` atau script terpisah |
| **Scope** | Command `python -m src.main --health` yang mengecek: (1) Gemini API reachable, (2) MongoDB connection OK, (3) YouTube credentials valid, (4) edge-tts available. Return exit code 0/1. |
| **Benefit** | Bisa di-schedule sebagai monitoring terpisah di GitHub Actions. |

---

## ⬜ Phase 3 — Feature Hardening

> **Goal:** Perkuat fitur yang sudah ada — kualitas konten, video rendering, dan error recovery.
>
> **Status:** Not Started

### 3.1 Content Quality Scoring

| Item | Detail |
| :--- | :--- |
| **Target** | `src/llm.py` |
| **Scope** | Setelah content generation, hitung quality score berdasarkan: (1) Script word count dalam range ideal (40-60). (2) Code line count dalam range (3-15). (3) Hashtag count (5-8). (4) Content type diversity (bonus jika berbeda dari 5 terakhir). Jika score < threshold → regenerate (max 2 extra attempts). |

### 3.2 Video Quality Verification

| Item | Detail |
| :--- | :--- |
| **Target** | `src/video.py` |
| **Scope** | Setelah video render: (1) Cek file size > 100KB dan < 50MB. (2) Cek duration antara 15-60 detik. (3) Verify video codec dengan `ffprobe`. Jika gagal → abort upload, save error to MongoDB. |

### 3.3 Smarter Content Deduplication

| Item | Detail |
| :--- | :--- |
| **Target** | `src/db.py`, `src/llm.py` |
| **Scope** | Selain title matching, tambahkan: (1) Code similarity check (normalize whitespace, compare). (2) Language + category frequency balancing — jika Python sudah 5× berturut-turut, paksa pilih bahasa lain. |

### 3.4 Graceful Degradation

| Item | Detail |
| :--- | :--- |
| **Target** | `src/main.py` |
| **Scope** | Jika YouTube upload gagal setelah semua retry: (1) Simpan video file sebagai artifact. (2) Set status = "rendered_not_uploaded". (3) Next run bisa mencoba re-upload video yang tertunda. |

### 3.5 Dynamic Font Scaling

| Item | Detail |
| :--- | :--- |
| **Target** | `src/renderer.py` |
| **Scope** | Jika kode > 12 baris atau ada baris > 45 karakter: otomatis kurangi font size agar tidak terpotong. Hitung optimal `CODE_FONT_SIZE` berdasarkan konten. |

### 3.6 Rate Limiting Awareness

| Item | Detail |
| :--- | :--- |
| **Target** | `src/llm.py`, `src/uploader_youtube.py` |
| **Scope** | Parse Gemini API rate limit headers. Jika mendekati limit → add extra delay. YouTube: check quota usage sebelum upload (YouTube Data API quota = 10.000 units/hari, upload = 1.600 units). |

### 3.7 Improved Error Classification

| Item | Detail |
| :--- | :--- |
| **Target** | `src/main.py`, `src/notifier.py` |
| **Scope** | Classify errors: (1) `TRANSIENT` — API timeout, network error → worth retrying. (2) `PERMANENT` — invalid credentials, quota exceeded → jangan retry, kirim alert berbeda. (3) `CONTENT` — safety filter, validation → regenerate content. Telegram notification menyertakan error class. |

---

## ⬜ Phase 4 — Scale & Extensibility

> **Goal:** Skalakan pipeline ke multi-platform, tambahkan scheduling, dan buat arsitektur extensible.
>
> **Status:** Not Started

### 4.1 Multi-Platform Upload

| Item | Detail |
| :--- | :--- |
| **Target** | `src/uploader_tiktok.py`, `src/uploader_instagram.py` (file baru) |
| **Scope** | Abstraksi uploader interface. Upload ke TikTok dan/atau Instagram Reels selain YouTube Shorts. Config via env variable `UPLOAD_TARGETS=youtube,tiktok,instagram`. |

### 4.2 Content Scheduling

| Item | Detail |
| :--- | :--- |
| **Target** | `src/scheduler.py` (file baru), update `generate.yml` |
| **Scope** | (1) Generate beberapa video sekaligus (batch mode). (2) Simpan di queue (MongoDB collection `scheduled`). (3) Upload satu per satu pada jadwal optimal (peak viewing times). (4) Cron job terpisah untuk upload dari queue. |

### 4.3 Analytics Dashboard

| Item | Detail |
| :--- | :--- |
| **Target** | `src/analytics.py` (file baru) |
| **Scope** | Query MongoDB untuk generate laporan: (1) Total videos per minggu/bulan. (2) Language distribution pie chart. (3) Content type distribution. (4) Average pipeline latency trend. (5) Success/failure rate. Output sebagai Markdown report atau simple HTML. |

### 4.4 Template / Theme System

| Item | Detail |
| :--- | :--- |
| **Target** | `src/renderer.py`, `src/config.py` |
| **Scope** | Pisahkan visual config ke theme files (`themes/github_dark.json`, `themes/monokai.json`, dll). Renderer membaca theme dari config. Bisa rotate themes secara otomatis. |

### 4.5 Plugin Architecture

| Item | Detail |
| :--- | :--- |
| **Target** | `src/plugins/` (directory baru) |
| **Scope** | Hook system: `on_content_generated`, `on_video_rendered`, `on_uploaded`, `on_error`. Plugin bisa: auto-post ke Twitter/X, send ke Discord webhook, generate thumbnail, dll. Plugin discovery via `src/plugins/__init__.py`. |

### 4.6 Multi-Language Narration

| Item | Detail |
| :--- | :--- |
| **Target** | `src/tts.py`, `src/llm.py`, `src/config.py` |
| **Scope** | Support generate konten dalam bahasa lain (Indonesia, Spanish, dll). LLM prompt disesuaikan per bahasa. TTS voice dipilih berdasarkan bahasa narration. Config: `NARRATION_LANGUAGE=en\|id\|es`. |

### 4.7 Thumbnail Generation

| Item | Detail |
| :--- | :--- |
| **Target** | `src/thumbnail.py` (file baru) |
| **Scope** | Auto-generate YouTube thumbnail: (1) Code snippet preview. (2) Title text overlay. (3) Language icon. (4) Eye-catching gradient + emoji. Upload via YouTube API `thumbnails.set()`. |

---

## 📐 Dependency Risk Matrix

| Dependency | Risk | Mitigation |
| :--- | :---: | :--- |
| `google-genai` (Gemini) | 🟡 Medium | Model bisa deprecated → pin model version, monitor changelog |
| `edge-tts` | 🔴 High | Unofficial, bisa break tanpa warning → siapkan fallback (gTTS, Coqui) |
| `moviepy 2.x` | 🟡 Medium | Major version masih fresh → pin exact version |
| `pymongo` | 🟢 Low | Stable, well-maintained |
| `google-api-python-client` | 🟢 Low | Official Google library |
| GitHub Actions M0 | 🟡 Medium | Free tier bisa berubah → architecture sudah portable |
| MongoDB Atlas M0 | 🟡 Medium | Free tier limit 512MB → monitor usage, archive old records |

---

## 📝 Notes

- Setiap phase sebaiknya di-commit dan di-push sebelum memulai phase berikutnya
- Phase bisa dijalankan secara paralel jika task-nya independent
- Priority dalam setiap phase: **High 🔴 → Medium 🟡 → Low 🟢**
- Semua perubahan harus lolos syntax check (`py_compile`) sebelum commit
- Phase 2 (testing) sangat disarankan sebelum Phase 3-4 untuk mencegah regressions
