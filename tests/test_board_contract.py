import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]

class BoardContract(unittest.TestCase):
    def test_board_definition_matches_verified_hardware(self):
        path = ROOT / 'board.json'
        self.assertTrue(path.is_file(), 'missing micro-box-s3 board definition')
        data = json.loads(path.read_text(encoding='utf-8'))
        self.assertEqual(data['name'], 'micro-box-s3')
        self.assertEqual(data['target'], 'esp32s3')
        self.assertEqual(data['flash_mb'], 16)
        self.assertEqual(data['psram_mb'], 8)
        self.assertEqual(data['display']['width'], 160)
        self.assertEqual(data['display']['height'], 160)
        self.assertEqual(data['display']['panels'], [
            {'host': 'SPI3_HOST', 'sclk': 42, 'mosi': 2, 'rst': 1, 'dc': 41},
            {'host': 'SPI2_HOST', 'sclk': 38, 'mosi': 39, 'rst': 40, 'dc': 0},
        ])
        self.assertEqual(data['audio'], {'chip': 'VB6824', 'tx': 45, 'rx': 48, 'baud': 2000000})
        self.assertEqual(data['touch_channels'], [14, 13, 12, 11])
        self.assertTrue((ROOT / 'components/micro_box_s3/include/micro_box_s3.h').is_file())

if __name__ == '__main__':
    unittest.main()
