# 🚀 Panduan Setup Lengkap — Automated Coding Shorts Pipeline

> **Penting**: Ikuti urutan step ini dari atas ke bawah. Jangan skip.
> Estimasi waktu total: **30–45 menit** (sekali saja, setelah itu full otomatis).

---

## TAHAP 1: Buat Repository GitHub (5 menit)

### Step 1.1 — Buat repo baru di GitHub
1. Buka https://github.com/new
2. Isi:
   - **Repository name**: `sistem-konten-auto` (atau nama lain terserah)
   - **Description**: `Automated coding shorts pipeline`
   - **Visibility**: pilih **Public** (supaya GitHub Actions gratis unlimited)
   - ❌ JANGAN centang "Add a README file" (kita sudah punya file lokal)
3. Klik **Create repository**
4. Akan muncul halaman dengan instruksi — **jangan tutup**, kita butuh URL repo-nya nanti

### Step 1.2 — Push kode lokal ke GitHub
Buka terminal/PowerShell di folder `r:\sistem konten auto\`, lalu jalankan:

```powershell
cd "r:\sistem konten auto"
git init
git add .
git commit -m "feat: initial automated coding shorts pipeline"
git branch -M main
git remote add origin https://github.com/USERNAMU_KAMU/sistem-konten-auto.git
git push -u origin main
```

> ⚠️ Ganti `USERNAME_KAMU` dengan username GitHub kamu yang asli.

**Verifikasi**: Buka repo di browser, pastikan semua file sudah muncul:
- `.github/workflows/generate.yml`
- `src/` folder dengan semua `.py` files
- `assets/fonts/` dengan 2 file `.ttf`
- `requirements.txt`

---

## TAHAP 2: Setup MongoDB Atlas — Database Gratis (10 menit)

> MongoDB Atlas M0 = **100% GRATIS**, tidak perlu kartu kredit, tidak perlu kode apapun.
> Storage: 512MB (cukup untuk puluhan ribu records pipeline kita).

### Step 2.1 — Daftar akun MongoDB Atlas
1. Buka https://www.mongodb.com/cloud/atlas/register
2. Daftar dengan **Google account** atau email biasa
3. Yang ditanyain saat onboarding:
   - "What is your goal?" → pilih **Learn MongoDB** (atau apapun)
   - "What type of application?" → pilih **I'm building a personal project**
   - Deploy type → Pilih **M0 FREE** (ada tulisan "Free forever")
4. Klik **Create Deployment**

### Step 2.2 — Pilih provider & region
1. Provider: pilih **AWS** (paling stabil)
2. Region: pilih yang paling dekat, contoh:
   - `Singapore (ap-southeast-1)` — terbaik untuk Indonesia
   - Atau `us-east-1` — juga oke
3. Cluster name: biarkan default (`Cluster0`) atau ganti ke `content-pipeline`
4. Klik **Create Deployment**
5. Tunggu 1-3 menit sampai cluster ready (icon hijau ✅)

### Step 2.3 — Buat Database User
Setelah cluster dibuat, MongoDB meminta kamu buat user:
1. **Username**: `pipeline` (atau terserah)
2. **Password**: klik **Autogenerate Secure Password**
3. **⚠️ COPY PASSWORD INI** — simpan di Notepad dulu, kamu butuh nanti!
4. Klik **Create Database User**

### Step 2.4 — Whitelist IP Address
Supaya GitHub Actions (server clouded) bisa akses database kamu:
1. Di sidebar kiri, klik **Network Access** (dibawah Security)
2. Klik **+ Add IP Address**
3. Klik **ALLOW ACCESS FROM ANYWHERE** (ini isi `0.0.0.0/0`)
   > Ini aman karena tetap butuh username+password untuk akses
4. Klik **Confirm**

### Step 2.5 — Dapatkan Connection String
1. Di sidebar kiri, klik **Database** (di bawah Deployment)
2. Klik tombol **Connect** di cluster kamu
3. Pilih **Drivers**
4. Copy connection string-nya, contoh:
   ```
   mongodb+srv://pipeline:<password>@cluster0.xxxxx.mongodb.net/?retryWrites=true&w=majority
   ```
5. **GANTI `<password>`** dengan password yang kamu copy di Step 2.3
6. **TAMBAHKAN nama database** sebelum `?`:
   ```
   mongodb+srv://pipeline:PASSWORD_KAMU@cluster0.xxxxx.mongodb.net/content_pipeline?retryWrites=true&w=majority
   ```

> 📝 Simpan connection string lengkap ini — kita butuh di Step 4.

---

## TAHAP 3: Dapatkan Gemini API Key — Gratis (3 menit)

### Step 3.1 — Buka Google AI Studio
1. Buka https://aistudio.google.com/apikey
2. Login dengan Google account kamu
3. Klik **Create API Key**
4. Pilih project (buat baru jika perlu, atau pakai yang ada)
5. **COPY API KEY** yang muncul

> 📝 Simpan API key ini — kita butuh di Step 4.

> ℹ️ Gemini API gratis: 1,500 request/hari untuk Gemini Pro. Pipeline kita cuma pakai 2 request/hari. Sangat lebih dari cukup.

---

## TAHAP 4: Setup YouTube Upload (15 menit)

> Ini bagian yang paling panjang, tapi cuma perlu dilakukan SEKALI.
> 
> ⚠️ **PENTING tentang beda email**:
> - Google Cloud Console + YouTube → login pakai **email YouTube channel kamu**
> - Ini BOLEH beda dari email GitHub/MongoDB kamu, tidak masalah
> - Yang penting: email Google Cloud = email pemilik YouTube channel

### Step 4.1 — Buat Project di Google Cloud Console
1. Buka https://console.cloud.google.com/
2. **Login dengan email yang SAMA dengan akun YouTube channel kamu**
   (bukan email GitHub/MongoDB — boleh beda)
3. Di navbar atas, klik dropdown project → **New Project**
4. Isi:
   - **Project name**: `Coding Shorts Pipeline`
   - **Organization**: biarkan default (kalau tidak muncul, abaikan saja)
5. Klik **Create** → tunggu beberapa detik
6. Pastikan project baru ini sudah terpilih di dropdown atas

### Step 4.2 — Enable YouTube Data API
1. Buka https://console.cloud.google.com/apis/library/youtube.googleapis.com
2. Pastikan project **"Coding Shorts Pipeline"** terpilih di dropdown atas
3. Klik tombol biru **ENABLE**
4. Tunggu sampai muncul halaman dashboard API (artinya sudah aktif)

### Step 4.3 — Buat OAuth Consent Screen (UI baru Google Auth Platform)

> Ini adalah halaman "izin" yang muncul saat kamu authorize app.
> Google sudah update tampilan — sekarang langsung form 4 langkah.

1. Buka https://console.cloud.google.com/auth/overview/create
2. Pastikan project **"Coding Shorts Pipeline"** terpilih di atas

3. **Langkah 1 — App Information:**
   - **App name**: ketik `Coding Shorts Bot`
   - **User support email**: klik dropdown → pilih email kamu
   - Klik **Next**

4. **Langkah 2 — Audience:**
   - Pilih **External**
   - Klik **Next**

5. **Langkah 3 — Contact Information:**
   - Ketik **email kamu** (boleh sama dengan di atas)
   - Klik **Next**

6. **Langkah 4 — Finish:**
   - Klik **Create**

### Step 4.4 — ⚠️ PUBLISH Consent Screen (SANGAT PENTING!)

> Tanpa step ini, token kamu akan EXPIRE setelah 7 hari dan pipeline berhenti.

1. Setelah create, kamu kembali ke halaman **Overview**
2. Klik **Audience** di sidebar kiri
3. Cari bagian **"Publishing status"** → statusnya masih **"Testing"**
4. Klik tombol **PUBLISH APP**
5. Muncul popup konfirmasi → klik **CONFIRM**
6. Status berubah jadi **"In production"** ← ini yang benar

> ❓ "Apakah Google akan review app saya?"
> → TIDAK. App kamu tetap berstatus "unverified" dan itu 100% oke.
> → Saat authorize nanti, muncul warning "app isn't verified" — itu normal,
>   tinggal klik Advanced → Go to app. Untuk pemakaian personal, ini aman.

### Step 4.5 — Buat OAuth Client ID
1. Klik **Clients** di sidebar kiri
2. Klik **+ CREATE CLIENT** (atau **+ Create OAuth client ID**)
3. **Application type**: pilih **Desktop app**
4. **Name**: ketik `Pipeline Desktop Client` (nama bebas)
5. Klik **Create**
6. Muncul popup/halaman dengan **Client ID** dan **Client Secret**
7. **COPY KEDUA-DUANYA** → simpan ke Notepad dulu!
   - Client ID bentuknya: `xxxxx.apps.googleusercontent.com`
   - Client Secret bentuknya: `GOCSPX-xxxxx`

### Step 4.6 — Jalankan OAuth Authorization (di komputer lokal)
Buka terminal di folder project:

```powershell
cd "r:\sistem konten auto"
python -m scripts.auth_youtube
```

1. Script akan minta **Client ID** → paste yang kamu copy di Step 4.5
2. Script akan minta **Client Secret** → paste yang kamu copy di Step 4.5
3. Browser otomatis terbuka → login Google account channel YouTube kamu
4. Muncul warning "Google hasn't verified this app" → klik **Advanced** → **Go to Coding Shorts Bot (unsafe)**
5. Klik **Continue** / **Allow** untuk memberikan izin upload
6. Terminal akan tampilkan **3 nilai** yang perlu disimpan:
   - `YOUTUBE_CLIENT_ID`
   - `YOUTUBE_CLIENT_SECRET`
   - `YOUTUBE_REFRESH_TOKEN`

> 📝 Simpan ketiga nilai ini — kita masukkan sebagai GitHub Secrets di Step 5.

---

## TAHAP 5: Masukkan Semua Secrets ke GitHub (5 menit)

### Step 5.1 — Buka halaman Secrets
1. Buka repository kamu di GitHub
2. Klik tab **Settings** (paling kanan di tab bar)
3. Di sidebar kiri, klik **Secrets and variables** → **Actions**
4. Klik **New repository secret**

### Step 5.2 — Tambahkan secrets satu per satu
Tambahkan **5 secrets** berikut (klik "New repository secret" untuk setiap satu):

| Name | Value | Dari Tahap |
|------|-------|------------|
| `GEMINI_API_KEY` | API key dari Google AI Studio | Tahap 3 |
| `MONGODB_URI` | Connection string lengkap (yang sudah diganti password) | Tahap 2 |
| `YOUTUBE_CLIENT_ID` | OAuth Client ID | Tahap 4 |
| `YOUTUBE_CLIENT_SECRET` | OAuth Client Secret | Tahap 4 |
| `YOUTUBE_REFRESH_TOKEN` | Refresh token dari script auth | Tahap 4 |

### Step 5.3 — (Opsional) Tambahkan Variables

> **Apa bedanya Secrets vs Variables?**
> - **Secrets** (Step 5.2) = data sensitif (password, API key, token) — **WAJIB** diisi
> - **Variables** (Step 5.3) = pengaturan tampilan/preferensi — **OPSIONAL**, kalau tidak diisi pakai default

**Cara menambahkan:**
1. Masih di halaman **Settings → Secrets and variables → Actions**
2. Klik tab **Variables** (letaknya di sebelah tab "Secrets" di bagian atas)
3. Klik **New repository variable**
4. Isi **Name** dan **Value**, lalu klik **Add variable**
5. Ulangi untuk variable lain jika perlu

**Daftar variables yang tersedia:**

| Name | Value | Default (kalau tidak diisi) | Perlu diisi? |
|------|-------|----------------------------|-------------|
| `CHANNEL_NAME` | `@DevInSeconds` | `@DevInSeconds` | ❌ Sudah default |
| `GEMINI_MODEL` | `gemini-2.0-flash` | `gemini-2.0-flash` | ❌ Sudah default |
| `TTS_VOICE` | `en-US-GuyNeural` | `en-US-GuyNeural` | ❌ Sudah default |

> ✅ **Untuk kamu**: Semua default sudah sesuai (channel = @DevInSeconds, suara pria, Gemini 2.0 Flash).
> **Kamu bisa SKIP step 5.3 ini sepenuhnya** — langsung lanjut ke Tahap 6.

---

## TAHAP 6: Test Pipeline! (3 menit)

### Step 6.1 — Trigger Manual Pertama
1. Buka repository di GitHub
2. Klik tab **Actions**
3. Di sidebar kiri, klik **"Generate & Upload Coding Short"**
4. Klik tombol **"Run workflow"** (dropdown biru di kanan)
5. Klik **"Run workflow"** (tombol hijau)

### Step 6.2 — Pantau Proses
1. Klik pada workflow run yang baru muncul (ada icon kuning ⏳ berputar)
2. Klik pada job **"generate"**
3. Kamu bisa lihat setiap step secara real-time:
   - ✅ Checkout repository
   - ✅ Set up Python
   - ✅ Install FFmpeg
   - ✅ Install Python dependencies
   - ⏳ Run content pipeline ← ini yang paling lama (~2-5 menit)
   - ✅ Keep repository active

4. Di step "Run content pipeline", kamu akan lihat log seperti:
   ```
   STEP 1/5 │ Generating content with Gemini Pro...
     ✓ Title:    CSS Grid One-Line Centering Trick #Shorts
     ✓ Language: css
   STEP 2/5 │ Generating voiceover with edge-tts...
     ✓ Timestamps: 24 words
   STEP 3/5 │ Rendering video...
     ✓ Video: output/video.mp4
   STEP 4/5 │ Uploading to YouTube Shorts...
     ✓ YouTube: https://youtube.com/shorts/xxxxx
   STEP 5/5 │ Saving record to MongoDB Atlas...
     ✓ MongoDB: 65f2a1b3...
   ✅ Pipeline completed successfully!
   ```

### Step 6.3 — Cek Hasil
1. Buka **YouTube Studio** (https://studio.youtube.com)
2. Di tab **Content**, kamu harusnya lihat video baru yang sudah terupload
3. Klik video → pastikan:
   - ✅ Format vertikal (9:16 Shorts)
   - ✅ Ada animasi typing code
   - ✅ Ada narasi suara
   - ✅ Ada subtitle yang sync
   - ✅ Judul dan hashtag sudah terisi

---

## TAHAP 7: Selesai! Sistem Sekarang Full Otomatis 🎉

Setelah test berhasil, **kamu tidak perlu melakukan apa-apa lagi**.

Pipeline akan berjalan otomatis:
- 🕗 Setiap jam **08:00 UTC** (15:00 WIB)
- 🕗 Setiap jam **20:00 UTC** (03:00 WIB)

Setiap run menghasilkan:
1. Topik coding baru (tidak pernah mengulang berkat MongoDB history)
2. Video 1080×1920 dengan typing animation + syntax highlighting
3. Voiceover AI natural
4. Subtitle word-by-word yang sync
5. Auto-upload ke YouTube Shorts

### Monitoring
- **GitHub Actions tab** → lihat status setiap run (✅ hijau = sukses, ❌ merah = gagal)
- **YouTube Studio** → lihat video yang terupload
- **MongoDB Atlas** → Collections → `content_pipeline.history` → lihat semua records

---

## TROUBLESHOOTING — Kalau Ada Error

### ❌ "GEMINI_API_KEY is not configured"
→ Cek GitHub Secrets: pastikan nama persis `GEMINI_API_KEY` (case-sensitive)

### ❌ "MongoDB unreachable"
→ Cek: (1) Connection string sudah benar? (2) Password sudah diganti? (3) Network Access sudah `0.0.0.0/0`?

### ❌ "YOUTUBE_REFRESH_TOKEN not configured"
→ Cek: Sudah jalankan `python -m scripts.auth_youtube`? Sudah save refresh token ke GitHub Secrets?

### ❌ YouTube upload error "Token has been expired or revoked"
→ OAuth consent screen BELUM di-publish (masih "Testing"). Ulangi Step 4.4, lalu ulangi Step 4.6 untuk dapat refresh token baru.

### ❌ "This app isn't verified" saat OAuth
→ Ini NORMAL. Klik **Advanced** → **Go to [app name] (unsafe)**. Aman untuk personal use.

### ❌ Video tidak muncul sebagai Shorts
→ Pastikan judul mengandung `#Shorts` dan durasi ≤ 60 detik. Sistem sudah handle ini otomatis.

### ❌ GitHub Actions schedule tidak jalan
→ Scheduled workflows bisa delay 5-30 menit (normal). Kalau tidak jalan sama sekali setelah 1 jam, cek apakah workflow file ada di branch `main`.

### 💡 Mau ganti jadwal?
Edit file `.github/workflows/generate.yml`, ubah baris cron:
```yaml
schedule:
  - cron: '0 8 * * *'    # Ganti jam di sini (format UTC)
  - cron: '0 20 * * *'   # Ini jadwal kedua
```
Contoh jadwal lain:
- `'0 6 * * *'` = jam 06:00 UTC (13:00 WIB) sekali sehari
- `'0 */8 * * *'` = setiap 8 jam (3x sehari)
- `'0 12 * * 1-5'` = jam 12:00 UTC, Senin-Jumat saja
