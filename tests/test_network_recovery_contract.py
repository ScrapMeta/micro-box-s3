"""Static recovery contract; not an RTOS or network fault-injection test."""
from pathlib import Path
import os
import re
import unittest

ROOT=Path(__file__).resolve().parents[1]
DEFAULT=ROOT/'examples/xiaozhi/main/boards/micro-box-s3/micro-box-s3.cc'

class NetworkRecoveryContract(unittest.TestCase):
    def test_recovery_is_independent_and_nonblocking(self):
        source=Path(os.environ.get('MICRO_BOX_S3_RECOVERY_SOURCE',str(DEFAULT))).read_text(encoding='utf-8')
        self.assertNotIn('app.Schedule(',source)
        self.assertIn('std::atomic<bool>',source)
        self.assertIn('wifi_reset_pending_.exchange(true)',source)
        self.assertIn('xTaskCreate(',source)
        self.assertIn('result != pdPASS',source)
        self.assertGreaterEqual(source.count('wifi_reset_pending_.store(false)'),2)
        task=re.search(r'static void WifiConfigurationTask\(void\* arg\)\s*\{(.*?)\n    \}',source,re.S)
        self.assertIsNotNone(task)
        self.assertIn('board->ResetWifiConfiguration()',task.group(1))
        self.assertIn('vTaskDelete(nullptr)',task.group(1))
        command=re.search(r'else if \(command == "开始配网"\)\s*\{(.*?)\n            \}',source,re.S)
        self.assertIsNotNone(command)
        self.assertIn('RequestWifiConfiguration()',command.group(1))
        self.assertNotIn('vTaskDelay',command.group(1))
        self.assertNotIn('esp_restart',command.group(1))

if __name__=='__main__':
    unittest.main()
