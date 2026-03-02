# 🗺️ Development Roadmap — Auto-Content Pipeline

> **Document ini mencatat seluruh rencana pengembangan berdasarkan hasil audit arsitektur profesional.**
> Dibuat setelah analisis mendalam terhadap 13 file / 2.680+ baris kode.
>
> **Last updated:** 6 Maret 2026

---

## 📊 Progress Overview

| Phase | Nama | Status | Tasks |
| :---: | :--- | :---: | :---: |
| 1 | Stabilization & Security | ✅ Complete | 7/7 |
| 2 | Observability & Testing | ✅ Complete | 7/7 |
| 3 | Feature Hardening | ✅ Complete | 7/7 |
| 4 | Scale & Extensibility | 🔄 In Progress | 5/6 |

**Total: 27 tasks** — 26 completed, 1 remaining

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

## ✅ Phase 2 — Observability & Testing

> **Goal:** Tambahkan unit test, structured logging, dan monitoring agar pipeline bisa dipercaya dalam jangka panjang.
>
> **Status:** ✅ Complete
>
> **Files changed:** `src/main.py`, `src/db.py`, `.github/workflows/ci.yml`, `pytest.ini`, `tests/` (6 new files)

### 2.1 Unit Tests — Core Modules ✅

| Item | Detail |
| :--- | :--- |
| **Target** | `tests/test_llm.py`, `tests/test_code_runner.py`, `tests/test_renderer.py` |
| **Scope** | (1) `_repair_json()` — 9 edge cases (truncated, unescaped newlines, missing braces, regex fallback). (2) `_validate_content()` — 12 tests (missing fields, defaults, type normalization). (3) `_is_python_safe_ast()` — 22 tests (banned imports, builtins, attributes + safe code). (4) JS/Bash safety — 19 tests. (5) `FrameRenderer` — gradient dtype/shape, char_data, easing, frame rendering. |
| **Framework** | `pytest 9.0.2` + `pytest-cov 7.0.0` — **135 tests, all passing** |

### 2.2 Unit Tests — Safety Filter & CredentialFilter ✅

| Item | Detail |
| :--- | :--- |
| **Target** | `tests/test_main.py` |
| **Scope** | `CredentialFilter` — 8 tests (MongoDB URI, API key, OAuth/refresh token, normal msg unchanged, args=None). `_is_content_safe()` — 10 tests (4 blocked categories, code/expected_output, case insensitive, missing fields). |

### 2.3 Integration Test — Pipeline Dry-Run ✅

| Item | Detail |
| :--- | :--- |
| **Target** | `tests/test_integration.py` |
| **Scope** | 7 tests with full mock pipeline: success run (all steps called), youtube_id in record, notification sent, safety blocks unsafe, missing keys exit, generation failure saves error. Config attributes patched to avoid import-time env caching. |

### 2.4 Structured JSON Logging ✅

| Item | Detail |
| :--- | :--- |
| **Target** | `src/main.py` — `_JsonFormatter` class |
| **Scope** | `LOG_FORMAT=json` env variable activates JSON output: `{"timestamp", "level", "module", "message"}`. Default remains human-readable. 5 unit tests for schema validation. |

### 2.5 Pipeline Metrics Tracking ✅

| Item | Detail |
| :--- | :--- |
| **Target** | `src/main.py` + `src/db.py` |
| **Scope** | `time.perf_counter()` around every step. Tracked: `gemini_latency_ms`, `tts_latency_ms`, `render_latency_ms`, `upload_latency_ms`, `total_latency_ms`. Saved in `record["metrics"]` → MongoDB. Summary logged on success banner. |

### 2.6 GitHub Actions CI Workflow ✅

| Item | Detail |
| :--- | :--- |
| **Target** | `.github/workflows/ci.yml` |
| **Scope** | Triggers on push/PR to `main`. Steps: (1) `py_compile src/*.py`, (2) `ruff check src/ tests/`, (3) `pytest -m "not integration" --cov=src`. Uploads JUnit XML as artifact. All action SHAs pinned. |

### 2.7 Health Check Endpoint ✅

| Item | Detail |
| :--- | :--- |
| **Target** | `src/main.py` — `_health_check()` + `--health` CLI flag |
| **Scope** | `python -m src.main --health` checks: (1) MongoDB ping, (2) Gemini API key + list-models call, (3) YouTube OAuth creds present, (4) edge-tts importable. Returns exit code 0 (all OK) or 1 (failure). 2 unit tests. |

---

## ✅ Phase 3 — Feature Hardening

> **Goal:** Perkuat fitur yang sudah ada — kualitas konten, video rendering, dan error recovery.
>
> **Status:** ✅ Complete
>
> **Files changed:** `src/errors.py` (new), `src/quality.py` (new), `src/rate_limiter.py` (new), `src/main.py`, `src/renderer.py`, `src/video.py`, `src/db.py`, `src/llm.py`, `src/notifier.py`, `tests/test_phase3.py` (new), `tests/test_integration.py`
>
> **Tests:** 200 total (64 new Phase 3 tests)

### 3.1 Content Quality Scoring ✅

| Item | Detail |
| :--- | :--- |
| **File** | `src/quality.py` (new module) |
| **Scope** | `score_content()` returns 0–100 score across 5 dimensions: script word count (25pts), code line count (25pts), hashtag count (15pts), code quality heuristics (20pts — indentation, avg line length, placeholder detection, comments), diversity bonus (15pts). `QUALITY_THRESHOLD = 50`. Pipeline regenerates content up to 2 extra attempts if score < threshold. |
| **Integration** | `src/main.py` calls `score_content()` after generation, logs score breakdown, regenerates if below threshold. |

### 3.2 Video Quality Verification ✅

| Item | Detail |
| :--- | :--- |
| **File** | `src/video.py` — `verify_video()` function |
| **Scope** | Post-render verification: (1) File existence. (2) Size 100KB–50MB. (3) Duration 5s–61s via `ffprobe`. (4) Codec check (`h264`). Graceful degradation if `ffprobe` unavailable — skips duration/codec checks with warnings. Returns dict with `passed`, `file_size`, `duration`, `codec`, `warnings`, `errors`. |
| **Integration** | `src/main.py` aborts upload and saves error to MongoDB if verification fails. |

### 3.3 Smarter Content Deduplication ✅

| Item | Detail |
| :--- | :--- |
| **Files** | `src/db.py` — `_normalize_code()`, `check_code_similarity()`, `get_language_frequency()` |
| **Scope** | (1) Code similarity: normalize (strip comments/whitespace) + Jaccard similarity on token trigrams (>70% = duplicate). (2) Language frequency: query last 20 records, detect overused languages (>40%), suggest `avoid_languages` list. (3) Content type frequency: detect overused types, suggest recent types. |
| **Integration** | `src/llm.py` accepts `avoid_languages` param and adds balancing hint to prompt. `src/main.py` checks similarity post-generation, passes `avoid_languages` from frequency analysis. |

### 3.4 Graceful Degradation ✅

| Item | Detail |
| :--- | :--- |
| **Files** | `src/db.py` — `save_pending_upload()`, `get_pending_uploads()`, `mark_upload_complete()`, `increment_retry_count()`. `src/main.py` — `_retry_pending_uploads()` |
| **Scope** | If YouTube upload fails: (1) Save video path + metadata to `pending_uploads` collection. (2) Set status = `"rendered_not_uploaded"`. (3) Next pipeline run calls `_retry_pending_uploads()` — attempts re-upload of pending items (max 3 retries each). (4) Successful retry marks upload complete and updates original record. |

### 3.5 Dynamic Font Scaling ✅

| Item | Detail |
| :--- | :--- |
| **File** | `src/renderer.py` — `compute_dynamic_font_size()` |
| **Scope** | If code > 12 lines or any line > 45 chars: reduce font size proportionally. Min 16px, max 28px (default). Two scaling factors computed (line count based, char width based), strictest wins. `_load_fonts()` uses dynamic size and logs scaling changes. |

### 3.6 Rate Limiting Awareness ✅

| Item | Detail |
| :--- | :--- |
| **File** | `src/rate_limiter.py` (new module) — `RateLimiter` class |
| **Scope** | (1) Gemini RPM tracking: `pre_gemini_call()` returns delay seconds if approaching limit (15 RPM default). Parses `X-RateLimit-*` headers when available. (2) YouTube quota tracking: `check_youtube_quota()` verifies upload feasibility (10,000 units/day, 1,600/upload). Auto-resets at midnight UTC. |
| **Integration** | `src/main.py` creates `RateLimiter` instance, calls `pre_gemini_call()` before generation, `check_youtube_quota()` before upload. |

### 3.7 Improved Error Classification ✅

| Item | Detail |
| :--- | :--- |
| **File** | `src/errors.py` (new module) |
| **Scope** | `PipelineError` hierarchy: `TransientError` (API timeout, network), `PermanentError` (invalid creds, quota exceeded), `ContentError` (safety, validation). `classify_error()` uses regex patterns (13 transient, 9 permanent, 9 content patterns) to classify arbitrary exceptions. `is_retryable()` quick check. |
| **Integration** | `src/main.py` exception handler classifies errors, saves `error_class` to MongoDB record. `src/notifier.py` shows error class emoji + actionable advice per class in Telegram notifications. |

---

## 🔄 Phase 4 — Scale & Extensibility

> **Goal:** Skalakan pipeline ke multi-platform, tambahkan scheduling, dan buat arsitektur extensible.
>
> **Status:** 🔄 In Progress — 4.1, 4.2, 4.3, 4.4 & 4.6 complete — 4.5 remaining

### 4.1 Multi-Platform Upload ✅

| Item | Detail |
| :--- | :--- |
| **Target** | `src/uploader_base.py`, `src/uploader_tiktok.py`, `src/uploader_instagram.py` (file baru), update `src/uploader_youtube.py` |
| **Scope** | Abstraksi uploader interface. Upload ke TikTok dan/atau Instagram Reels selain YouTube Shorts. Config via env variable `UPLOAD_TARGETS=youtube,tiktok,instagram`. |
| **Status** | ✅ Complete — Commit `6293959` (3 Maret 2026) — 225 tests passing |
| **Notes** | TikTok & Instagram API credentials setup deferred until all Phase 4 tasks are complete. |

### 4.2 Content Scheduling ✅

| Item | Detail |
| :--- | :--- |
| **Target** | `src/scheduler.py` (baru), `.github/workflows/upload-queue.yml` (baru), update `src/main.py` + `generate.yml` |
| **Scope** | (1) Generate beberapa video sekaligus (batch mode). (2) Simpan di queue (MongoDB collection `scheduled`). (3) Upload satu per satu pada jadwal optimal (peak viewing times). (4) Cron job terpisah untuk upload dari queue. |
| **Status** | ✅ Complete — Commit `de46a16` (6 Maret 2026) — 250 tests passing |
| **Peak slots UTC** | 13:00 (8 AM EST), 18:00 (1 PM EST), 00:00 (7 PM EST) |

### 4.3 Analytics Dashboard ✅

| Item | Detail |
| :--- | :--- |
| **Target** | `src/analytics.py` (file baru), update `src/main.py` |
| **Scope** | Query MongoDB untuk generate laporan: (1) Total videos per minggu/bulan. (2) Language distribution bar chart. (3) Content type distribution. (4) Average pipeline latency trend. (5) Success/failure rate. (6) Schedule queue status. Output sebagai Markdown report. |
| **Status** | ✅ Complete — Commit `d5319c2` (6 Maret 2026) — 288 tests passing |
| **Usage** | `python -m src.main --analytics` (print) · `python -m src.main --analytics --save` (write to `output/`) |

### 4.4 Template / Theme System ✅

| Item | Detail |
| :--- | :--- |
| **Target** | `src/theme_loader.py` (baru), `themes/*.json` (3 themes), `src/renderer.py`, `src/config.py` |
| **Scope** | Pisahkan visual config ke theme files (`themes/github_dark.json`, `themes/monokai.json`, dll). Renderer membaca theme dari config. Bisa rotate themes secara otomatis. |
| **Status** | ✅ Complete — Commit `afac64b` (6 Maret 2026) — 323 tests passing |
| **Usage** | `ACTIVE_THEME=monokai` · `AUTO_ROTATE_THEMES=1` · `THEME_ROTATION_LIST=github_dark,monokai,dracula` |

### 4.5 Plugin Architecture

| Item | Detail |
| :--- | :--- |
| **Target** | `src/plugins/` (directory baru) |
| **Scope** | Hook system: `on_content_generated`, `on_video_rendered`, `on_uploaded`, `on_error`. Plugin bisa: auto-post ke Twitter/X, send ke Discord webhook, generate thumbnail, dll. Plugin discovery via `src/plugins/__init__.py`. |

### 4.6 Thumbnail Generation ✅

| Item | Detail |
| :--- | :--- |
| **Target** | `src/thumbnail.py` (file baru) |
| **Scope** | Auto-generate YouTube thumbnail: (1) Code snippet preview. (2) Title text overlay. (3) Language icon. (4) Eye-catching gradient + emoji. Upload via YouTube API `thumbnails.set()`. |
| **Status** | ✅ Complete — Commit `afac64b` (6 Maret 2026) — 323 tests passing |
| **Usage** | `ENABLE_THUMBNAILS=1` untuk aktifkan thumbnail generation + upload otomatis |

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
