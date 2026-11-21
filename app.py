"""ClipForge Studio - local, permission-based YouTube/video clipper."""
from __future__ import annotations

import json
import base64
import hmac
import math
import os
import re
import shutil
import subprocess
import threading
import uuid
import zipfile
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from fastapi import FastAPI, File, Form, HTTPException, UploadFile, Request
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from smart_clip import analyze_video, retention_csv, speech_available

ROOT = Path(__file__).resolve().parent
STORAGE = Path(os.getenv("CLIPFORGE_DATA_DIR", ROOT / "data")).resolve()
STORAGE.mkdir(parents=True, exist_ok=True)
STATIC = ROOT / "static"
MAX_UPLOAD_BYTES = 700 * 1024 * 1024
MAX_SOURCE_SECONDS = 3 * 60 * 60
MAX_CLIP_SECONDS = 180
ALLOWED_SUFFIXES = {".mp4", ".mov", ".m4v", ".webm", ".mkv", ".avi"}
ALLOWED_YT_HOSTS = {"youtube.com", "www.youtube.com", "m.youtube.com", "music.youtube.com", "youtu.be", "www.youtu.be"}

app = FastAPI(title="ClipForge Web — AI Auto Viral Clipper", version="3.0.0")

# Require a password on public deployments. Local use still works without it.
ACCESS_USER = os.getenv("CLIPFORGE_WEB_USER", "clipforge")
ACCESS_PASSWORD = os.getenv("CLIPFORGE_WEB_PASSWORD", "")
if os.getenv("CLIPFORGE_PUBLIC") == "1" and not ACCESS_PASSWORD:
    raise RuntimeError("CLIPFORGE_WEB_PASSWORD wajib disetel untuk website publik.")

@app.middleware("http")
async def protect_web(request: Request, call_next):
    if ACCESS_PASSWORD and request.url.path != "/api/health":
        raw = request.headers.get("authorization", "")
        try:
            scheme, encoded = raw.split(" ", 1)
            username, password = base64.b64decode(encoded, validate=True).decode("utf-8").split(":", 1)
            allowed = scheme.lower() == "basic" and hmac.compare_digest(username, ACCESS_USER) and hmac.compare_digest(password, ACCESS_PASSWORD)
        except (ValueError, UnicodeError, IndexError):
            allowed = False
        if not allowed:
            return Response("Akses ClipForge memerlukan login.", status_code=401, headers={"WWW-Authenticate": 'Basic realm="ClipForge Studio", charset="UTF-8"'})
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    if request.url.path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-store"
    return response

app.mount("/static", StaticFiles(directory=STATIC), name="static")
source_lock = threading.Lock()
job_lock = threading.Lock()
sources: dict[str, dict[str, Any]] = {}
jobs: dict[str, dict[str, Any]] = {}
analyses: dict[str, dict[str, Any]] = {}
analysis_lock = threading.Lock()
import_lock = threading.Lock()
import_jobs: dict[str, dict[str, Any]] = {}
executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="clipforge")


def need_ffmpeg() -> None:
    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        raise HTTPException(status_code=503, detail="FFmpeg / ffprobe belum terpasang. Ikuti README untuk instalasi.")


def probe(path: Path) -> dict[str, Any]:
    need_ffmpeg()
    proc = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration:stream=codec_type,width,height", "-of", "json", str(path)],
        capture_output=True, text=True, timeout=30,
    )
    if proc.returncode:
        raise ValueError("Video tidak bisa dibaca oleh FFmpeg.")
    info = json.loads(proc.stdout)
    stream = next((s for s in info.get("streams", []) if s.get("codec_type") == "video"), None)
    if not stream:
        raise ValueError("File ini tidak memiliki track video.")
    duration = float(info.get("format", {}).get("duration") or 0)
    if duration <= 0 or duration > MAX_SOURCE_SECONDS:
        raise ValueError("Durasi video harus antara 1 detik sampai 3 jam.")
    return {"duration": round(duration, 3), "width": stream.get("width"), "height": stream.get("height")}


def public_source(s: dict[str, Any]) -> dict[str, Any]:
    return {**{key: s[key] for key in ("id", "title", "duration", "width", "height", "origin")}, "heatmap_available": bool(s.get("heatmap"))}


def save_source(folder: Path, title: str, origin: str, path: Path) -> dict[str, Any]:
    try:
        info = probe(path)
        s = {"id": folder.name, "title": title[:160], "origin": origin, "path": path, **info}
        with source_lock:
            sources[s["id"]] = s
        return public_source(s)
    except Exception:
        shutil.rmtree(folder, ignore_errors=True)
        raise


def get_source(source_id: str) -> dict[str, Any]:
    with source_lock:
        result = sources.get(source_id)
    if not result:
        raise HTTPException(404, "Sumber video tidak ditemukan. Impor kembali videonya.")
    return result


@app.get("/")
def index():
    return FileResponse(STATIC / "index.html")


@app.get("/api/health")
def health():
    return {"status": "ok", "ffmpeg": bool(shutil.which("ffmpeg") and shutil.which("ffprobe")), "youtube": _has_ytdlp(), "ai_transcript": speech_available()}


def _has_ytdlp() -> bool:
    try:
        import yt_dlp  # noqa: F401
        return True
    except ImportError:
        return False


@app.post("/api/sources/upload")
async def upload_video(file: UploadFile = File(...)):
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in ALLOWED_SUFFIXES:
        raise HTTPException(400, "Format tidak didukung. Gunakan MP4, MOV, M4V, WEBM, MKV, atau AVI.")
    folder = STORAGE / uuid.uuid4().hex
    folder.mkdir()
    target = folder / f"source{suffix}"
    size = 0
    try:
        with target.open("wb") as out:
            while chunk := await file.read(1024 * 1024):
                size += len(chunk)
                if size > MAX_UPLOAD_BYTES:
                    raise HTTPException(413, "Video maksimal 700 MB.")
                out.write(chunk)
        try:
            return save_source(folder, Path(file.filename or "Video upload").stem, "upload", target)
        except ValueError as e:
            raise HTTPException(400, str(e)) from e
    except Exception:
        shutil.rmtree(folder, ignore_errors=True)
        raise
    finally:
        await file.close()


class YouTubeInput(BaseModel):
    url: str = Field(min_length=10, max_length=2000)
    have_rights: bool = False


@app.post("/api/sources/youtube")
def import_youtube(payload: YouTubeInput):
    if not payload.have_rights:
        raise HTTPException(400, "Konfirmasi bahwa Anda memiliki hak/izin menggunakan video terlebih dahulu.")
    parts = urlsplit(payload.url.strip())
    if parts.scheme not in ("https", "http") or parts.hostname not in ALLOWED_YT_HOSTS or parts.username or parts.password:
        raise HTTPException(400, "Masukkan link video YouTube yang valid (youtube.com atau youtu.be).")
    if not _has_ytdlp():
        raise HTTPException(503, "yt-dlp belum terpasang. Jalankan: pip install -r requirements.txt")
    need_ffmpeg()
    import yt_dlp

    folder = STORAGE / uuid.uuid4().hex
    folder.mkdir()
    options: dict[str, Any] = {
        "format": "bv*[height<=1080][ext=mp4]+ba[ext=m4a]/b[ext=mp4]/bv*[height<=1080]+ba/b",
        "outtmpl": str(folder / "source.%(ext)s"),
        "merge_output_format": "mp4", "noplaylist": True,
        "max_filesize": MAX_UPLOAD_BYTES,
        "quiet": True, "no_warnings": True, "retries": 2, "fragment_retries": 2,
        "socket_timeout": 20, "cachedir": False, "ignoreerrors": False,
        "playlistend": 1,
    }
    try:
        with yt_dlp.YoutubeDL(options) as ydl:
            info = ydl.extract_info(payload.url.strip(), download=True)
        if not info or info.get("_type") == "playlist":
            raise ValueError("Tautan harus menuju satu video, bukan playlist.")
        duration = info.get("duration")
        if duration and float(duration) > MAX_SOURCE_SECONDS:
            raise ValueError("Durasi video maksimal 3 jam.")
        candidates = [p for p in folder.iterdir() if p.is_file() and p.suffix.lower() in ALLOWED_SUFFIXES]
        if not candidates:
            raise ValueError("Video tidak berhasil disimpan. Coba upload file videonya.")
        path = max(candidates, key=lambda p: p.stat().st_size)
        if path.stat().st_size > MAX_UPLOAD_BYTES:
            raise ValueError("Video lebih besar dari 700 MB. Pilih video lebih kecil.")
        response = save_source(folder, info.get("title") or "Video YouTube", "youtube", path)
        # Some public YouTube videos expose normalized "Most Replayed" intensity.
        # The value is NOT a raw number of views and may be unavailable.
        replay = []
        for item in (info.get('heatmap') or [])[:2000]:
            try:
                start, end, value = float(item['start_time']), float(item['end_time']), float(item['value'])
                if all(math.isfinite(v) for v in (start, end, value)) and 0 <= start < end <= response['duration'] + 1 and 0 <= value <= 1:
                    replay.append({'start_time': start, 'end_time': end, 'value': value})
            except (TypeError, ValueError, KeyError):
                continue
        if replay:
            with source_lock:
                sources[response['id']]['heatmap'] = replay
            response['heatmap_available'] = True
        return response
    except Exception as err:
        shutil.rmtree(folder, ignore_errors=True)
        if isinstance(err, ValueError):
            raise HTTPException(400, str(err)) from err
        # We deliberately do not surface full yt-dlp messages / filesystem paths.
        raise HTTPException(422, "Tidak bisa mengimpor video ini. Video mungkin privat, terbatas, atau dibatasi oleh YouTube. Coba unggah file video yang Anda miliki.") from err


# Cloud-safe import: return an ID immediately instead of keeping an HTTP request
# open throughout a potentially long YouTube download.
def _validate_yt_request(payload: YouTubeInput) -> None:
    if not payload.have_rights:
        raise HTTPException(400, "Konfirmasi kepemilikan/hak penggunaan video dahulu.")
    parts = urlsplit(payload.url.strip())
    if parts.scheme not in ("https", "http") or parts.hostname not in ALLOWED_YT_HOSTS or parts.username or parts.password:
        raise HTTPException(400, "Link harus video YouTube yang valid.")


def _import_in_worker(import_id: str, payload: YouTubeInput) -> None:
    try:
        with import_lock:
            import_jobs[import_id].update(status="processing", message="Mengambil video dari YouTube…")
        result = import_youtube(payload)
        with import_lock:
            import_jobs[import_id].update(status="done", message="Video siap dianalisis.", source=result)
    except HTTPException as err:
        with import_lock:
            import_jobs[import_id].update(status="error", message=str(err.detail))
    except Exception:
        with import_lock:
            import_jobs[import_id].update(status="error", message="Impor video gagal. Coba lagi atau gunakan file berizin.")


@app.post("/api/imports/youtube")
def start_youtube_import(payload: YouTubeInput):
    _validate_yt_request(payload)
    with import_lock:
        active = sum(job["status"] in ("queued", "processing") for job in import_jobs.values())
        if active >= 2:
            raise HTTPException(429, "Server sedang memproses dua impor. Coba kembali setelah proses selesai.")
        import_id = uuid.uuid4().hex
        import_jobs[import_id] = {"id": import_id, "status": "queued", "message": "Menunggu giliran impor…", "source": None}
    executor.submit(_import_in_worker, import_id, payload)
    return {"import_id": import_id}


@app.get("/api/imports/{import_id}")
def get_youtube_import(import_id: str):
    with import_lock:
        result = import_jobs.get(import_id)
    if not result:
        raise HTTPException(404, "Proses impor tidak ditemukan.")
    return result


@app.get("/api/sources/{source_id}/media")
def source_media(source_id: str):
    s = get_source(source_id)
    return FileResponse(s["path"], media_type="video/mp4" if s["path"].suffix.lower() == ".mp4" else None)


class ClipInput(BaseModel):
    title: str = Field(min_length=1, max_length=90)
    start: float = Field(ge=0)
    end: float = Field(gt=0)


class ExportInput(BaseModel):
    source_id: str
    clips: list[ClipInput] = Field(min_length=1, max_length=10)
    aspect: str = "vertical"
    framing: str = "crop"
    quality: str = "1080"


def clip_filter(aspect: str, framing: str, quality: str) -> tuple[list[str], list[str]]:
    """Return filter args and output mapping args."""
    edge = 1080 if quality == "1080" else 720
    if aspect == "original":
        # Keep native framing, even dimensions for universal H.264 support.
        return ["-vf", "scale=trunc(iw/2)*2:trunc(ih/2)*2,setsar=1,format=yuv420p"], ["-map", "0:v:0", "-map", "0:a:0?"]
    w, h = (edge, edge * 16 // 9) if aspect == "vertical" else (edge, edge)
    if framing == "blur":
        filter_graph = (
            f"[0:v]split=2[bg][fg];"
            f"[bg]scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},boxblur=20:1[back];"
            f"[fg]scale={w}:{h}:force_original_aspect_ratio=decrease[front];"
            f"[back][front]overlay=(W-w)/2:(H-h)/2,setsar=1,format=yuv420p[outv]"
        )
        return ["-filter_complex", filter_graph], ["-map", "[outv]", "-map", "0:a:0?"]
    return ["-vf", f"scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},setsar=1,format=yuv420p"], ["-map", "0:v:0", "-map", "0:a:0?"]


def update_job(job_id: str, **kwargs: Any) -> None:
    with job_lock:
        jobs[job_id].update(kwargs)


def safe_title(name: str) -> str:
    result = re.sub(r"[^a-zA-Z0-9_-]+", "-", name.strip()).strip("-")
    return (result or "clip")[:42]


def run_export(job_id: str, source: dict[str, Any], clips: list[dict[str, Any]], aspect: str, framing: str, quality: str) -> None:
    folder = STORAGE / f"export_{job_id}"
    folder.mkdir(exist_ok=True)
    outputs: list[dict[str, Any]] = []
    try:
        filter_args, map_args = clip_filter(aspect, framing, quality)
        for idx, clip in enumerate(clips, 1):
            update_job(job_id, progress=round((idx - 1) / len(clips) * 100), message=f"Memproses clip {idx} dari {len(clips)}…")
            filename = f"{idx:02d}_{safe_title(clip['title'])}.mp4"
            target = folder / filename
            cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-ss", str(clip["start"]), "-i", str(source["path"]),
                   "-t", str(clip["end"] - clip["start"]), *filter_args, *map_args,
                   "-c:v", "libx264", "-preset", "veryfast", "-crf", "22", "-r", "30",
                   "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart", "-threads", "2", str(target)]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
            if result.returncode or not target.exists() or target.stat().st_size < 200:
                raise RuntimeError(f"FFmpeg gagal memproses clip {idx}: {result.stderr[-400:]}")
            outputs.append({"name": filename, "url": f"/api/jobs/{job_id}/files/{filename}", "size": target.stat().st_size})
        zip_path = folder / "semua-clips.zip"
        with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_STORED) as archive:
            for item in outputs:
                archive.write(folder / item["name"], arcname=item["name"])
        update_job(job_id, status="done", progress=100, message="Semua clip berhasil dibuat!", files=outputs,
                   zip_url=f"/api/jobs/{job_id}/files/semua-clips.zip")
    except Exception as err:
        update_job(job_id, status="error", message=str(err)[:500])


@app.post("/api/exports")
def create_export(payload: ExportInput):
    need_ffmpeg()
    source = get_source(payload.source_id)
    if payload.aspect not in ("vertical", "square", "original") or payload.framing not in ("crop", "blur") or payload.quality not in ("720", "1080"):
        raise HTTPException(400, "Pilihan format ekspor tidak valid.")
    clips = [clip.model_dump() for clip in payload.clips]
    for c in clips:
        length = c["end"] - c["start"]
        if length < 0.5 or length > MAX_CLIP_SECONDS:
            raise HTTPException(400, "Setiap clip harus berdurasi 0,5–180 detik.")
        if c["end"] > source["duration"] + 0.15:
            raise HTTPException(400, "Waktu akhir clip melebihi durasi video.")
    job_id = uuid.uuid4().hex
    with job_lock:
        jobs[job_id] = {"id": job_id, "status": "processing", "progress": 0, "message": "Memulai ekspor…", "files": [], "zip_url": None}
    executor.submit(run_export, job_id, source, clips, payload.aspect, payload.framing, payload.quality)
    return {"job_id": job_id}


@app.get("/api/jobs/{job_id}")
def get_job(job_id: str):
    with job_lock:
        job = jobs.get(job_id)
    if not job:
        raise HTTPException(404, "Proses ekspor tidak ditemukan.")
    return job


@app.get("/api/jobs/{job_id}/files/{filename}")
def download_clip(job_id: str, filename: str):
    with job_lock:
        job = jobs.get(job_id)
    if not job or job["status"] != "done":
        raise HTTPException(404, "File belum tersedia.")
    valid = {entry["name"] for entry in job["files"]} | {"semua-clips.zip"}
    if filename not in valid or filename != Path(filename).name:
        raise HTTPException(404, "File tidak ditemukan.")
    path = STORAGE / f"export_{job_id}" / filename
    return FileResponse(path, filename=filename, media_type="application/octet-stream")



# --- Auto-clipping / audience retention ---------------------------------------

@app.post("/api/sources/{source_id}/retention")
async def import_retention(source_id: str, file: UploadFile = File(...)):
    """Accept an owner's export of audience retention; no public video metrics inferred."""
    source = get_source(source_id)
    try:
        raw = await file.read(1024 * 1024 + 1)
        try:
            points = retention_csv(raw)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        with source_lock:
            source["retention"] = points
        return {"status": "ok", "points": len(points), "message": "Data retensi channel tersimpan untuk video ini."}
    finally:
        await file.close()


class AnalysisInput(BaseModel):
    source_id: str
    clip_length: int = Field(default=30, ge=5, le=180)
    max_clips: int = Field(default=5, ge=1, le=10)
    use_speech: bool = True


def run_analysis(analysis_id: str, source: dict[str, Any], payload: AnalysisInput) -> None:
    def progress(percent: int, message: str) -> None:
        with analysis_lock:
            analyses[analysis_id].update(progress=percent, message=message)
    try:
        result = analyze_video(source['path'], source['duration'], payload.clip_length,
                               payload.max_clips, payload.use_speech, source.get('retention'), progress, source.get('heatmap'))
        with analysis_lock:
            analyses[analysis_id].update(status="done", progress=100,
                                         message="Rekomendasi clip siap!", result=result)
    except Exception:
        # Avoid leaking local paths/system details in errors.
        with analysis_lock:
            analyses[analysis_id].update(status="error", message="Analisis gagal. Periksa FFmpeg, format video, dan coba lagi.")


@app.post("/api/analyses")
def create_analysis(payload: AnalysisInput):
    need_ffmpeg()
    source = get_source(payload.source_id)
    analysis_id = uuid.uuid4().hex
    with analysis_lock:
        analyses[analysis_id] = {"id": analysis_id, "status": "processing", "progress": 0,
                                 "message": "Menyiapkan video…", "result": None}
    executor.submit(run_analysis, analysis_id, source, payload)
    return {"analysis_id": analysis_id}


@app.get("/api/analyses/{analysis_id}")
def get_analysis(analysis_id: str):
    with analysis_lock:
        result = analyses.get(analysis_id)
    if not result:
        raise HTTPException(404, "Analisis tidak ditemukan.")
    return result

@app.exception_handler(ValueError)
def value_error_handler(_request, exc: ValueError):
    return JSONResponse(status_code=400, content={"detail": str(exc)})
