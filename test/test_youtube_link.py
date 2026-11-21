"""Offline integration of the YouTube URL -> heatmap -> automatic clip pipeline.

This test mocks YouTube extraction; it does not assert that all live YouTube
videos are downloadable, since the platform may block some requests.
"""
import shutil
import subprocess
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

import app as service
from smart_clip import analyze_video


@unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'), 'FFmpeg required')
class YoutubeLinkFlowTests(unittest.TestCase):
    def test_link_import_heatmap_analysis_export(self):
        with tempfile.TemporaryDirectory() as directory:
            scratch = Path(directory)
            sample = scratch / 'sample.mp4'
            proc = subprocess.run([
                'ffmpeg', '-hide_banner', '-loglevel', 'error', '-y',
                '-f', 'lavfi', '-i', 'testsrc2=size=240x160:rate=12',
                '-f', 'lavfi', '-i', 'sine=frequency=700:sample_rate=22050',
                '-t', '8', '-c:v', 'libx264', '-preset', 'ultrafast', '-pix_fmt', 'yuv420p',
                '-c:a', 'aac', str(sample)
            ], capture_output=True, text=True, timeout=30)
            self.assertEqual(proc.returncode, 0, proc.stderr)

            class MockYoutubeDL:
                def __init__(self, options):
                    self.options = options
                def __enter__(self):
                    return self
                def __exit__(self, *_args):
                    return None
                def extract_info(self, url, download):
                    assert url == 'https://www.youtube.com/watch?v=Abcdef12345'
                    assert download
                    shutil.copyfile(sample, self.options['outtmpl'].replace('%(ext)s', 'mp4'))
                    return {
                        'title': 'Video YouTube Uji', 'duration': 8,
                        'heatmap': [
                            {'start_time': 0, 'end_time': 3, 'value': 0.1},
                            {'start_time': 3, 'end_time': 8, 'value': 0.95},
                        ]
                    }

            with patch.dict(sys.modules, {'yt_dlp': types.SimpleNamespace(YoutubeDL=MockYoutubeDL)}), \
                    patch.object(service, 'STORAGE', scratch):
                loaded = service.import_youtube(service.YouTubeInput(
                    url='https://www.youtube.com/watch?v=Abcdef12345', have_rights=True
                ))
                self.assertEqual(loaded['origin'], 'youtube')
                self.assertTrue(loaded['heatmap_available'])
                item = service.get_source(loaded['id'])
                self.assertEqual(len(item['heatmap']), 2)
                decisions = analyze_video(
                    item['path'], item['duration'], 5, 1, False, None,
                    lambda *_args: None, item['heatmap']
                )
                self.assertEqual(len(decisions['clips']), 1)
                self.assertIn('heatmap', decisions['method'])
                clip = decisions['clips'][0]
                self.assertGreaterEqual(clip['start'], 0)
                self.assertLessEqual(clip['end'], 8)
                job_id = 'offline_integration_test'
                service.jobs[job_id] = {'status':'processing', 'progress':0, 'message':'', 'files':[]}
                service.run_export(job_id, item, [
                    {'start': clip['start'], 'end': clip['end'], 'title': 'YouTube Viral Highlight'}
                ], 'vertical', 'crop', '720')
                self.assertEqual(service.jobs[job_id]['status'], 'done', service.jobs[job_id]['message'])
                exported = scratch / f'export_{job_id}' / service.jobs[job_id]['files'][0]['name']
                self.assertTrue(exported.is_file())
                self.assertGreater(exported.stat().st_size, 1000)

    def test_invalid_video_url_denied(self):
        from fastapi import HTTPException
        with self.assertRaises(HTTPException) as context:
            service.import_youtube(service.YouTubeInput(url='https://other-site.example/watch?v=12345', have_rights=True))
        self.assertEqual(context.exception.status_code, 400)


if __name__ == '__main__':
    unittest.main()
