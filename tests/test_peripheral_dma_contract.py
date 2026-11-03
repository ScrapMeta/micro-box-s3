from pathlib import Path
import re
import unittest

ROOT=Path(__file__).resolve().parents[1]

class PeripheralDmaContract(unittest.TestCase):
    def test_dma_wait_and_allocation_checks_survive_ndebug(self):
        source=(ROOT/'examples/peripherals/main/main.c').read_text(encoding='utf-8')
        self.assertNotRegex(source,r'configASSERT\s*\(\s*xSemaphoreTake')
        self.assertRegex(source,r'if\s*\(xSemaphoreTake\(done\[i\],pdMS_TO_TICKS\(2000\)\)\s*!=\s*pdTRUE\)\s*abort\(\)')
        self.assertRegex(source,r'if\s*\(!done\[i\]\)\s*abort\(\)')

if __name__=='__main__':
    unittest.main()
