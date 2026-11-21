# ClipForge Web v3 — Website online dulu, APK nanti

**Status:** Kode aplikasi website siap untuk di-deploy. File ZIP **bukan URL website aktif**. Website akan online setelah dipasang di layanan hosting. Proyek ini mengembangkan ClipForge v2.1.

## Fitur
- Browser HP Android / laptop. Halaman responsive dan manifest instalasi web (PWA shell); tidak perlu Android APK.
- Tempel link YouTube **yang dimiliki/berizin** → buat pekerjaan impor di background → analisis rekomendasi → auto ekspor MP4 9:16.
- Sinyal heatmap YouTube Most Replayed bila tersedia; audio/visual; Whisper untuk analisis ucapan bila model dapat diunduh. Skor 0–100 relatif, **bukan views per detik ataupun probabilitas viral**.
- Preview, manual trim, pilihan 3/5/10 clip berdurasi 15–60 detik, ekspor ZIP, retensi CSV channel sendiri.
- Website dilindungi password HTTP Basic agar pihak luar tidak membebani CPU/server atau membuka hasil.

## Online dengan GitHub + Render
1. Buat repository **private** baru di GitHub, upload semua file dalam folder ini sebagai root repository (`app.py`, `Dockerfile`, `render.yaml`, dst). Jangan upload file video ke repository.
2. Di Render: **New → Blueprint**, hubungkan repo tersebut. Render membaca `render.yaml` untuk membuat Docker web service dengan FFmpeg, Whisper, dan disk persistent 10 GB. Blueprint default menggunakan layanan berbayar kelas Standard yang sesuai untuk komputasi video, periksa harga di Render saat deployment.
3. Saat diminta env var **CLIPFORGE_WEB_PASSWORD**, buat password kuat dan simpan. `CLIPFORGE_WEB_USER` disetel `clipforge`. Jangan simpan password dalam repo GitHub.
4. Setelah deploy sukses, Render memberikan URL HTTPS `https://...onrender.com`. Buka lewat Chrome di HP dan masukkan username/password. URL dibuat Render; file ini tidak mengandung URL palsu.
5. Tempel link video berizin, centang hak penggunaan, pilih jumlah/durasi, klik Analisis dari Link & Auto Clip, lalu download MP4/ZIP.

**Catatan operasional:** Download YouTube melalui server cloud tidak dijamin berhasil. Beberapa video dibatasi YouTube (privasi/usia/wilayah/anti-otomasi). Kode tidak mengatasi DRM/akses terlarang. Whisper menggunakan CPU server dan perlu mengunduh model pertama kali. Hosting berbasis container membutuhkan RAM/CPU/disk; layanan hosting berbayar mungkin diperlukan dan dapat mengenakan biaya besar untuk video panjang. Jangan mengandalkan instance free / hosting HTML statis saja untuk menjalankan FFmpeg, yt-dlp, dan AI.

**Keamanan:** Gunakan HTTPS dan password kuat, batasi akses ke orang yang dipercaya. Password HTTP Basic melindungi seluruh situs, API dan file hasil, selain health check. Tidak menyediakan akun multi-user/kuota/penagihan. URL acak bukan perlindungan pengganti autentikasi. Jangan mempublikasikan website secara bebas tanpa menambahkan akun pengguna, batas job/kuota, pembatasan trafik dan kebijakan penghapusan otomatis. Data di disk tersimpan sampai dihapus manual dan metadata pekerjaan in-memory hilang setelah server restart.

## Uji lokal di PC (opsional)
```bash
# Python 3.10-3.12 dan FFmpeg diperlukan
pip install -r requirements-ai.txt
# Linux/macOS:
CLIPFORGE_WEB_PASSWORD='passwordkuat' uvicorn app:app --host 127.0.0.1 --port 8000
# Windows PowerShell:
$env:CLIPFORGE_WEB_PASSWORD='passwordkuat'; python -m uvicorn app:app --host 127.0.0.1 --port 8000
```
Buka `http://127.0.0.1:8000` (lokal saja). Cloud web memakai `Dockerfile`.

## Roadmap APK
Sesudah website terbukti stabil, web bisa dibungkus dengan **Trusted Web Activity atau Capacitor**. Koneksi internet tetap dibutuhkan; AI dan FFmpeg berjalan di server, bukan di HP. Paket APK harus didistribusikan/ditandatangani secara benar. Tidak perlu menduplikasi backend.

## Batasan
- Belum ada deployment online (URL live) di dalam paket; kamu perlu akun hosting.
- Most Replayed tidak selalu disediakan YouTube. Audience retention nyata milik channel sendiri harus diimpor manual CSV.
- Impor link video panjang bisa gagal atau lambat karena perubahan YouTube / limit server. Tidak ada garansi skor 90/100 menghasilkan viral.
- Video di server dianggap privat untuk pemegang password saja, bukan jaminan privasi enterprise.
