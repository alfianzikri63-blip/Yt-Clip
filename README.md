# ClipForge Web v3

**Baca README-WEB.md untuk versi online / HP.**

# ClipForge AI Studio v2.1 — YouTube Auto Viral Clipper

Aplikasi web lokal untuk memotong video yang Anda miliki/berizin menjadi MP4 untuk YouTube Shorts, TikTok, dan Reels. **v2.1 menyediakan mode SATU KLIK dari URL YouTube: tempel link → impor → analisis momen → auto-klip → ekspor MP4. Tanpa perlu mengunggah file secara manual.**

> **Penting:** Tidak ada API publik yang dapat memberi jumlah views dari setiap detik video YouTube orang lain. Angka **Skor 0–100** di aplikasi adalah *peringkat potensi highlight relatif dalam satu video*, bukan views sesungguhnya, view rate, probabilitas viral, maupun janji video akan viral. Jika mempunyai data audience retention video dari channel sendiri, Anda bisa mengimpor CSV agar rekomendasi lebih berdasarkan performa penonton yang nyata.

## Mulai dari link YouTube, tanpa upload file

1. Jalankan `run-ai.bat` (Windows) atau `./run-ai.sh` (Linux/macOS) dan buka `http://127.0.0.1:8000`.
2. Pada **Masukkan video**, pilih **Link YouTube** dan tempel URL `https://www.youtube.com/watch?v=...`, `https://youtu.be/...`, atau URL YouTube Shorts.
3. Centang bahwa video milik Anda atau Anda mempunyai izin mengunduh/menggunakan. **Mode 1 klik** aktif secara default.
4. Sebelum mulai, atur **durasi per clip** dan **jumlah clip** di panel **AI Auto Viral Clipper**, serta centang **Langsung ekspor**.
5. Klik **✦ Analisis dari Link & Auto Clip**. Aplikasi mengunduh video yang dapat diakses, menganalisis heatmap *Most Replayed* jika ada, lalu membuat dan menyiapkan hasil MP4/ZIP untuk diunduh.
6. Jika ingin mengimpor saja tanpa langsung clipping, nonaktifkan **Mode 1 klik**.

Impor dari URL memerlukan internet dan `yt-dlp`. YouTube dapat membatasi video tertentu dan fitur ini tidak bisa melewati pembatasan akses/DRM. Jika video tidak punya grafik Most Replayed, aplikasi memberi peringkat estimasi dari isi video (dan AI Whisper jika terpasang). Data views per detik video publik **tidak tersedia**.

## Fitur v2.1

- **AI Auto Viral Clipper**: unggah video atau impor URL YouTube (khusus video dengan hak pakai), pilih durasi **15 / 30 / 45 / 60 detik** dan jumlah clip **3 / 5 / 10**.
- **YouTube Most Replayed:** jika metadata heatmap tersedia saat impor, gunakan intensitas bagian yang paling sering diputar ulang sebagai sinyal utama. Angka ini relatif (0–1), bukan jumlah views, dan tidak selalu tersedia.
- **Ranking momen** yang memanfaatkan dinamika audio dan perubahan gambar. Menampilkan rentang waktu, alasan pemilihan, dan skor potensi 0–100.
- **AI ucapan (opsional):** jika `faster-whisper` terpasang, speech-to-text lokal mengenali ucapan (mendukung bahasa Indonesia dan bahasa lainnya), lalu mengidentifikasi hook/pertanyaan/kata pemicu. Transkrip yang relevan muncul di hasil analisis. Perlu mengunduh model Whisper pada penggunaan pertama.
- **Fallback otomatis**: apabila model tidak dipasang/tersedia, analisis sinyal audio/visual tetap bekerja. UI akan memberi tahu mode analisis yang benar-benar dipakai.
- **Retensi asli (opsional):** masukkan `elapsedVideoTimeRatio` dan `audienceWatchRatio` dari data YouTube Analytics milik channel Anda dalam CSV. Analisis memprioritaskan bagian dengan retensi yang relatif tinggi. Ini bukan akses otomatis ke Analytics Anda.
- **Auto-Clip + auto-ekspor**: sistem memilih rentang yang tidak terlalu saling tumpang-tindih, mengisi daftar clip, dan otomatis membuat MP4 jika opsi ekspor otomatis dicentang. Hasil MP4 bisa diunduh per video atau sebagai ZIP.
- Semua fitur v1 tetap ada: potong manual, preview, format 9:16, 1:1, atau original; crop tengah dan background blur; kualitas 720p/1080p; maksimal 10 potongan per ekspor, 0,5–180 detik per potongan.

## Cara instalasi di Windows

Prasyarat: **Python 3.10–3.12** dan **FFmpeg + ffprobe** di PATH.

1. Ekstrak ZIP proyek.
2. Pasang FFmpeg (`winget install Gyan.FFmpeg` atau pasang manual), lalu restart terminal.
3. Untuk **AI transkrip Whisper**, klik `run-ai.bat`. Ini memasang kebutuhan AI dan menjalankan aplikasi. Saat pertama kali menganalisis, model Whisper `tiny` diunduh otomatis lewat internet. Untuk versi ringan tanpa AI ucapan, klik `run.bat`.
4. Buka `http://127.0.0.1:8000` jika browser tidak otomatis terbuka.

Atau jalankan dari command line:

```powershell
python -m pip install -r requirements-ai.txt
python -m uvicorn app:app --host 127.0.0.1 --port 8000
```

Jika tidak perlu AI transkrip, ganti `requirements-ai.txt` dengan `requirements.txt`. **Analisis audio/visual tetap bekerja** tanpa `faster-whisper`.

## Linux / macOS

```bash
# Ubuntu/Debian: sudo apt install ffmpeg
# macOS/Homebrew: brew install ffmpeg
python3 -m pip install -r requirements-ai.txt
./run-ai.sh
# Buka http://127.0.0.1:8000
```

`run-ai.sh` juga memasang paket AI. Untuk versi ringan, gunakan `./run.sh`.

## Workflow AI

1. Buka ClipForge dan tempel link YouTube milik Anda/berizin. Mode 1 klik otomatis melakukan langkah analisis dan ekspor berikutnya; jika mode tersebut dimatikan, gunakan alur manual di bawah.
2. Pada panel **AI Auto Viral Clipper**, atur panjang clip dan jumlah hasil.
3. (Opsional) Centang **Gunakan AI transkrip** bila ingin menilai ucapan/hook (perlu `requirements-ai.txt`).
4. (Opsional) Unggah data retensi channel sendiri (contoh di `static/contoh-retensi.csv`).
5. Jika grafik **Most Replayed** tersedia, aplikasi menggunakannya otomatis. Centang **Langsung ekspor ke MP4** dan tekan **Analisis & Auto-Clip Video** apabila menjalankan mode impor manual.
6. Preview rekomendasi, edit daftar clip jika perlu, dan unduh MP4/ZIP dari panel hasil ekspor.

## Format CSV retensi (milik channel sendiri)

Contoh isi CSV:

```csv
elapsedVideoTimeRatio,audienceWatchRatio
0.01,0.96
0.02,0.91
0.03,0.89
0.04,0.92
0.05,0.84
```

- `elapsedVideoTimeRatio` adalah posisi dalam video antara **0–1** (misalnya `0.5` artinya di separuh durasi).
- `audienceWatchRatio` adalah proporsi times watched terhadap total views, **bisa >1** jika bagian diputar ulang. Angka ini bukan view rate per-segment yang tersedia secara publik. File juga menerima angka dengan persen seperti `92%`.
- Minimal 3 baris data, maksimum 1.000 baris / 1 MB. Format UTF-8, CSV comma-separated.
- Anda dapat mengambil data retensi video dari **YouTube Analytics API** dengan akun/channel yang berwenang dan menyiapkannya dalam format CSV ini. Tidak semua laporan atau halaman YouTube Studio menawarkan export berformat persis seperti contoh, sehingga kolom mungkin perlu disesuaikan. Tidak perlu membagikan password Google kepada aplikasi.
- Baca dokumentasi resmi: https://developers.google.com/youtube/analytics/channel_reports#audience_retention dan https://developers.google.com/youtube/analytics/dimensions#elapsedVideoTimeRatio
- Metadata heatmap dari yt-dlp: https://github.com/yt-dlp/yt-dlp/blob/master/yt_dlp/extractor/common.py

## Cara kerja dan keterbatasan

- **Dengan AI Whisper:** ucapan ditranskripsikan lewat model machine learning lokal. Algoritme sederhana menggunakan energi suara, aktivitas visual, dan ada/tidaknya hook percakapan untuk menyusun peringkat. Ini bukan model khusus yang dilatih dari data views viral, dan prediksi tidak dijamin akurat.
- **Tanpa AI Whisper:** analisis adalah pemeringkatan sinyal gambar/audio, **bukan analisis semantik AI**. Sistem tetap melakukan auto-clip.
- **Dengan YouTube Most Replayed:** aplikasi membaca metadata heatmap jika tersedia untuk video yang diimpor; pembacaan tergantung YouTube/yt-dlp dan tidak dijamin untuk setiap URL. Nilai menunjukkan popularitas pemutaran ulang relatif, bukan angka views.
- **Dengan retensi channel:** peringkat mempertimbangkan audience retention asli yang diberikan pemilik channel. Ini data histori video panjang, bukan ramalan views dari clip baru.
- Audio visual bisa salah mengutamakan intro ramai dan mengabaikan konten bernilai yang tenang; cek setiap clip sebelum publikasi.
- AI Whisper lokal bisa berat di CPU. Model pertama kali perlu diunduh melalui internet dan cache di komputer. Model default `tiny`, dapat diganti via environment variable `CLIPFORGE_WHISPER_MODEL` (`base`, `small`, dst) jika mesin mendukung.
- Impor YouTube melalui `yt-dlp` mungkin gagal karena pembatasan platform, privasi, DRM, usia, wilayah, atau perubahan layanan. Aplikasi tidak berupaya melewati DRM/akses terlarang. Video harus milik Anda atau mempunyai izin yang sesuai.
- Maksimum impor 700 MB, durasi 3 jam. Export maks. 10 clip, panjang setiap clip 0,5–180 detik. Analisis diproses di komputer sendiri; untuk video panjang atau CPU rendah dapat memakan waktu.
- Saat server direstart, daftar video/jobs aktif dihapus dari memori; file media hasil tetap di `data/` sampai dihapus manual.
- **Tidak ada login** pada server lokal: hanya gunakan melalui `127.0.0.1`. Jangan buka port ke jaringan publik tanpa autentikasi, HTTPS, pembatasan akses, dan resource protection.
- Belum ada subtitle tertanam otomatis, deteksi wajah untuk reframe, publishing ke akun, atau OAuth YouTube Analytics.

## Struktur file

```
app.py                      # Backend FastAPI, impor video, analisis, ekspor
smart_clip.py               # Pemeringkatan momen audio/visual, opsional Whisper, retensi CSV
static/index.html           # Dashboard aplikasi
static/app.js               # UI interaktif, polling AI, auto-ekspor
static/styles.css           # Tampilan responsif dark mode
static/contoh-retensi.csv   # Contoh import audience retention
requirements.txt            # Versi ringan
requirements-ai.txt         # Versi dengan AI Whisper
run.bat / run.sh            # Versi ringan
run-ai.bat / run-ai.sh      # Instal AI + jalankan aplikasi
```

Disusun sebagai proyek lokal yang dapat disunting untuk deployment sendiri.
