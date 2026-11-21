"""Local, explainable clip candidate ranking.

Scores are RELATIVE editorial potential, not predicted view counts or probabilities.
Optional Whisper transcription is a local machine-learning component; without it,
the analyzer uses audio dynamics and frame changes (signal-based fallback).
"""
from __future__ import annotations

import bisect
import csv
import io
import math
import shutil
import subprocess
from array import array
from pathlib import Path
from typing import Any, Callable

SAMPLE_RATE = 8000
IMAGE_W, IMAGE_H = 72, 40
FPS_INTERVAL = 2
HOOK_WORDS = (
    'ternyata', 'tapi', 'rahasia', 'jangan', 'kenapa', 'mengapa', 'bagaimana',
    'gimana', 'caranya', 'tips', 'trik', 'penting', 'fakta', 'bahaya', 'viral',
    'kaget', 'akhirnya', 'beneran', 'serius', 'perhatikan', 'wajib', 'pertama',
    'bayangkan', 'ini dia', 'nggak nyangka', 'gak nyangka', 'enggak', 'solusi',
    'sebenarnya', 'kesalahan', 'terbukti', 'sekarang', 'lihat ini', 'coba lihat',
    'why', 'how', 'secret', 'never', 'always', 'mistake', 'here is',
    'imagine', 'surprising', 'actually', 'wait', 'watch', 'revealed', 'important',
)


def speech_available() -> bool:
    try:
        import faster_whisper  # noqa: F401
        return True
    except (ImportError, OSError):
        return False


def clamp(value: float, low: float = 0, high: float = 1) -> float:
    return max(low, min(high, value))


def normalize(values: list[float], low: float = 0.1, high: float = 0.9) -> list[float]:
    """Clip outliers, preserve neutral scores if there is no variation."""
    if not values:
        return []
    ordered = sorted(values)
    lo = ordered[int((len(ordered) - 1) * low)]
    hi = ordered[int((len(ordered) - 1) * high)]
    if hi - lo < 1e-6:
        return [0.35 if hi > 0 else 0.0 for _ in values]
    return [clamp((v - lo) / (hi - lo)) for v in values]


def audio_rms(path: Path, duration: float, progress: Callable[[int, str], None]) -> list[float]:
    """Process streamed mono 8k samples in 1-second blocks, bounded RAM."""
    cmd = ["ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error", "-i", str(path),
           "-map", "0:a:0?", "-vn", "-ac", "1", "-ar", str(SAMPLE_RATE),
           "-f", "s16le", "-acodec", "pcm_s16le", "pipe:1"]
    dbs: list[float] = []
    with subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL) as p:
        assert p.stdout is not None
        while True:
            raw = p.stdout.read(SAMPLE_RATE * 2)
            if not raw:
                break
            samples = array('h')
            samples.frombytes(raw[:len(raw) // 2 * 2])
            if not samples:
                break
            rms = math.sqrt(sum(x * x for x in samples) / len(samples)) / 32768
            dbs.append(20 * math.log10(max(rms, 1e-8)))
            if len(dbs) % 15 == 0:
                progress(5 + round(min(1, len(dbs) / max(1, duration)) * 35), 'Mengukur dinamika audio…')
        p.wait()
        # Some legal videos have no audio. We intentionally allow this fallback.
    return dbs


def visual_activity(path: Path, duration: float, progress: Callable[[int, str], None]) -> list[float]:
    """Downsample to grayscale every 2 sec and score frame-to-frame differences."""
    cmd = ["ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error", "-threads", "2", "-i", str(path),
           "-an", "-vf", f"fps=1/{FPS_INTERVAL},scale={IMAGE_W}:{IMAGE_H},format=gray",
           "-f", "rawvideo", "-pix_fmt", "gray", "pipe:1"]
    values: list[float] = []
    previous: bytes | None = None
    frame_size = IMAGE_W * IMAGE_H
    with subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL) as p:
        assert p.stdout is not None
        while True:
            frame = p.stdout.read(frame_size)
            if len(frame) != frame_size:
                break
            if previous is None:
                values.append(0.0)
            else:
                diff = sum(abs(a - b) for a, b in zip(frame, previous)) / (frame_size * 255)
                values.append(diff)
            previous = frame
            if len(values) % 12 == 0:
                progress(40 + round(min(1, len(values) * FPS_INTERVAL / max(1, duration)) * 27), 'Membaca perubahan visual…')
        p.wait()
    return values


def transcription(path: Path, duration: float, progress: Callable[[int, str], None]) -> list[dict[str, Any]]:
    from faster_whisper import WhisperModel

    # Download of the selected model is handled by faster-whisper on first run.
    # No user files are uploaded by this code; inference is local.
    import os
    model_name = os.getenv('CLIPFORGE_WHISPER_MODEL', 'tiny')
    if model_name not in ('tiny', 'base', 'small', 'medium', 'large-v3', 'turbo'):
        model_name = 'tiny'
    progress(67, f'Menyiapkan AI Whisper ({model_name})…')
    model = WhisperModel(model_name, device='cpu', compute_type='int8')
    segments, _info = model.transcribe(str(path), beam_size=1, vad_filter=True)
    results: list[dict[str, Any]] = []
    for seg in segments:
        text = seg.text.strip()
        if text:
            results.append({'start': float(seg.start), 'end': float(seg.end), 'text': text})
        if len(results) % 8 == 0:
            progress(68 + round(min(1, float(seg.end) / max(1, duration)) * 17), 'AI membaca isi percakapan…')
    return results


def retention_csv(raw: bytes) -> list[dict[str, float]]:
    """Accept 2-column Youtube Analytics-style CSV: elapsedVideoTimeRatio,audienceWatchRatio.

    Audience retention is measured data belonging to the video owner. This is
    *not* public per-segment views and is not automatically accessible by URL.
    """
    if not raw or len(raw) > 1024 * 1024:
        raise ValueError('CSV retensi harus berisi data dan maksimal 1 MB.')
    try:
        txt = raw.decode('utf-8-sig')
    except UnicodeDecodeError as e:
        raise ValueError('Gunakan file CSV UTF-8.') from e
    reader = csv.DictReader(io.StringIO(txt))
    headers = reader.fieldnames or []
    clean = {h.strip().lower().replace(' ', '').replace('_', ''): h for h in headers}
    x_header = clean.get('elapsedvideotimeratio')
    y_header = clean.get('audiencewatchratio')
    if not x_header or not y_header:
        raise ValueError('CSV memerlukan kolom elapsedVideoTimeRatio dan audienceWatchRatio (YouTube Analytics).')
    points = []
    for row in reader:
        if len(points) >= 1000:
            raise ValueError('CSV retensi maksimal 1.000 baris.')
        try:
            def to_number(val: str) -> float:
                value = str(val).strip().replace(' ', '')
                if value.endswith('%'):
                    return float(value[:-1].replace(',', '.')) / 100
                return float(value.replace(',', '.'))
            x = to_number(row[x_header])
            y = to_number(row[y_header])
        except (TypeError, ValueError) as e:
            raise ValueError('CSV berisi angka atau persentase tidak valid.') from e
        if not math.isfinite(x) or not math.isfinite(y) or not 0 <= x <= 1 or not 0 <= y <= 50:
            raise ValueError('elapsedVideoTimeRatio harus 0–1 dan audienceWatchRatio harus tidak negatif.')
        points.append({'ratio': x, 'watch_ratio': y})
    if len(points) < 3:
        raise ValueError('Minimal 3 baris data retensi diperlukan.')
    points.sort(key=lambda p: p['ratio'])
    if len(set(round(p['ratio'], 6) for p in points)) != len(points):
        raise ValueError('CSV memiliki titik waktu retensi yang duplikat.')
    return points


def derive_seconds(duration: float, audio: list[float], frames: list[float],
                   transcript: list[dict[str, Any]], retention: list[dict[str, float]] | None,
                   heatmap: list[dict[str, float]] | None = None) -> dict[str, list[float]]:
    n = max(1, math.ceil(duration))
    audio_raw = [clamp((audio[min(i, len(audio)-1)] + 54) / 44) if audio else 0.0 for i in range(n)]
    # Robust within-video dynamics + absolute volume, so a silent video doesn't score as energetic.
    audio_rank = normalize(audio)
    audio_score = [(audio_raw[i] * .55 + (audio_rank[min(i, len(audio_rank)-1)] if audio else 0) * .45) for i in range(n)]
    visual_rank = normalize(frames)
    visual_score = [visual_rank[min(i // FPS_INTERVAL, len(visual_rank)-1)] if frames else 0 for i in range(n)]
    words_score = [0.0] * n
    for seg in transcript:
        text = str(seg['text']).lower()
        matched = sum(1 for word in HOOK_WORDS if word in text)
        emphatic = int('?' in text) + int('!' in text)
        hook = clamp(0.18 + 0.28 * min(matched, 2) + 0.13 * emphatic)
        start = max(0, int(seg['start']))
        end = min(n, max(start + 1, math.ceil(seg['end'])))
        for i in range(start, end):
            words_score[i] = max(words_score[i], hook)
    retain_score = [0.0] * n
    if retention:
        xs = [p['ratio'] for p in retention]
        ys = [p['watch_ratio'] for p in retention]
        # Use absolute retention and relative peaks in the video's own retention curve.
        relative = normalize(ys)
        for i in range(n):
            ratio = (i + 0.5) / duration
            idx = min(len(xs)-1, bisect.bisect_left(xs, ratio))
            retain_score[i] = clamp(0.45 * clamp(ys[idx]) + 0.55 * relative[idx])
    replay_score = [0.0] * n
    if heatmap:
        for point in heatmap:
            start = max(0, int(point['start_time']))
            end = min(n, max(start + 1, math.ceil(point['end_time'])))
            for i in range(start, end):
                replay_score[i] = max(replay_score[i], clamp(point['value']))
    return {'audio': audio_score, 'visual': visual_score, 'speech': words_score,
            'retention': retain_score, 'replay': replay_score}


def avg(a: list[float], start: int, end: int) -> float:
    if not a:
        return 0.0
    start = max(0, min(start, len(a) - 1))
    end = max(start + 1, min(end, len(a)))
    return sum(a[start:end]) / (end - start)


def candidate_windows(duration: float, length: int) -> list[tuple[float, float]]:
    clip_len = min(float(length), duration)
    if clip_len < 0.5:
        return []
    if duration <= clip_len:
        return [(0.0, round(duration, 3))]
    stride = max(3, int(clip_len / 4))
    starts = list(range(0, max(1, math.floor(duration-clip_len))+1, stride))
    final_start = max(0.0, duration - clip_len)
    if not starts or abs(starts[-1] - final_start) > 0.5:
        starts.append(final_start)
    return [(round(float(start), 3), round(float(start+clip_len), 3)) for start in starts]


def analyze_video(path: Path, duration: float, length: int, count: int,
                  use_speech: bool, retention: list[dict[str, float]] | None,
                  progress: Callable[[int, str], None],
                  heatmap: list[dict[str, float]] | None = None) -> dict[str, Any]:
    if not shutil.which('ffmpeg'):
        raise ValueError('FFmpeg belum terpasang.')
    warnings: list[str] = []
    progress(3, 'Membaca sumber video…')
    audio = audio_rms(path, duration, progress)
    progress(40, 'Audio selesai. Mengecek visual…')
    frames = visual_activity(path, duration, progress)
    transcript: list[dict[str, Any]] = []
    if use_speech:
        if speech_available():
            try:
                progress(67, 'Menjalankan AI transkrip lokal…')
                transcript = transcription(path, duration, progress)
                if not transcript:
                    warnings.append('AI tidak menemukan ucapan yang dapat ditranskripsikan; hasil berdasarkan audio/visual.')
            except Exception:
                # Fail softly if Whisper model is not downloaded/network fails.
                warnings.append('Model AI transkrip gagal dimuat. Hasil memakai sinyal audio/visual; lihat README untuk setup AI.')
        else:
            warnings.append('Faster-Whisper belum terpasang. Menggunakan analisis audio/visual; pasang requirements-ai.txt untuk AI transkrip.')
    progress(88, 'Memberi skor dan memilih potongan…')
    sec = derive_seconds(duration, audio, frames, transcript, retention, heatmap)
    length = max(5, length)
    proposals: list[dict[str, Any]] = []
    for start, end in candidate_windows(duration, length):
        s, e = int(start), max(int(start) + 1, math.ceil(end))
        # First ~6s of the clip should grab attention.
        initial = min(e, s + 6)
        audio_score = avg(sec['audio'], s, e)
        visual_score = avg(sec['visual'], s, e)
        speech_score = avg(sec['speech'], s, e)
        retention_score = avg(sec['retention'], s, e)
        replay_score = avg(sec['replay'], s, e)
        hook = 0.55*avg(sec['audio'], s, initial) + 0.45*avg(sec['speech'], s, initial)
        if retention and heatmap:
            total = .48*retention_score + .31*replay_score + .10*audio_score + .05*visual_score + .04*speech_score + .02*hook
        elif retention:
            total = .65*retention_score + .14*audio_score + .08*visual_score + .08*speech_score + .05*hook
        elif heatmap:
            total = .72*replay_score + .13*audio_score + .07*visual_score + .05*speech_score + .03*hook
        elif transcript:
            total = .29*audio_score + .22*visual_score + .37*speech_score + .12*hook
        else:
            total = .53*audio_score + .37*visual_score + .10*hook
        # editorial score 0..100, NOT percentage probability of virality.
        score = round(clamp(total) * 100)
        reasons = []
        if heatmap and replay_score >= 0.5:
            reasons.append('Sering diputar ulang (YouTube Most Replayed)')
        if retention and retention_score >= 0.53:
            reasons.append('Retensi penonton relatif tinggi (data channel)')
        if transcript and speech_score >= 0.3:
            reasons.append('Ucapan berisi hook/pertanyaan yang menarik')
        if audio_score >= 0.48:
            reasons.append('Suara atau dialog lebih aktif')
        if visual_score >= 0.45:
            reasons.append('Perubahan gambar terlihat aktif')
        if not reasons:
            reasons.append('Dipilih berdasarkan kombinasi sinyal video')
        excerpt = ' '.join(seg['text'] for seg in transcript if seg['end'] > start and seg['start'] < end)
        if excerpt and len(excerpt) > 190:
            excerpt = excerpt[:187].rsplit(' ', 1)[0] + '…'
        proposals.append({'start': start, 'end': end, 'score': score,
                          'retention_signal': round(retention_score*100) if retention else None,
                          'replay_signal': round(replay_score*100) if heatmap else None,
                          'audio_signal': round(audio_score*100),
                          'visual_signal': round(visual_score*100),
                          'speech_signal': round(speech_score*100) if transcript else None,
                          'reasons': reasons[:3], 'excerpt': excerpt})
    proposals.sort(key=lambda c: (-c['score'], c['start']))
    selected: list[dict[str, Any]] = []
    for proposal in proposals:
        # Highly overlapping clips have poor content diversity; allow up to 15% overlap.
        overlap = max((max(0.0, min(p['end'], proposal['end']) - max(p['start'], proposal['start'])) for p in selected), default=0.0)
        if overlap <= (proposal['end'] - proposal['start']) * .15:
            selected.append(proposal)
        if len(selected) >= count:
            break
    # Only one candidate for short source videos is correct, rather than duplicates.
    for i, clip in enumerate(selected, 1):
        clip['title'] = f"Auto Viral {i:02d} - Score {clip['score']}"
    method = ('retention+heatmap+whisper' if retention and heatmap and transcript
              else 'retention+heatmap' if retention and heatmap
              else 'retention+whisper' if retention and transcript
              else 'retention+signals' if retention
              else 'heatmap+whisper' if heatmap and transcript
              else 'heatmap+signals' if heatmap
              else 'whisper+signals' if transcript else 'signals')
    progress(100, 'Analisis selesai!')
    return {'method': method, 'score_disclaimer': 'Skor 0–100 adalah ranking potensi highlight relatif dalam video, bukan jumlah views atau probabilitas viral.',
            'warnings': warnings, 'clips': selected, 'transcript_segments': len(transcript),
            'retention_points': len(retention) if retention else 0,
            'most_replayed_points': len(heatmap) if heatmap else 0,
            'seconds_analyzed': math.ceil(duration)}
