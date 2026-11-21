"""Run with: python -m unittest discover -s tests"""
import unittest

from smart_clip import candidate_windows, derive_seconds, retention_csv


class SmartClipTests(unittest.TestCase):
    def test_retention_csv(self):
        points = retention_csv(b'elapsedVideoTimeRatio,audienceWatchRatio\n0.1,0.7\n0.5,1.2\n0.9,0.5\n')
        self.assertEqual(len(points), 3)
        self.assertAlmostEqual(points[1]['watch_ratio'], 1.2)

    def test_wrong_retention_schema(self):
        with self.assertRaises(ValueError):
            retention_csv(b'time,value\n0.1,0.7\n0.5,1.2\n0.9,0.5\n')

    def test_short_video_window(self):
        self.assertEqual(candidate_windows(4, 30), [(0.0, 4)])

    def test_heatmap_peak(self):
        heatmap = [{'start_time': 0.0, 'end_time': 10.0, 'value': 0.1},
                   {'start_time': 10.0, 'end_time': 20.0, 'value': 0.9}]
        signals = derive_seconds(20, [], [], [], None, heatmap)
        self.assertLess(signals['replay'][4], signals['replay'][14])


if __name__ == '__main__':
    unittest.main()
