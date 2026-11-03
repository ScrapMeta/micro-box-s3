# SPDX-License-Identifier: Apache-2.0
# micro-box-s3 modification notice (2026-11-03):
# Add a static contract for GC9A01 160x160 initialization error propagation.
"""Check actual C source; no SPI fault injection or hardware execution."""

from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "components/esp_lcd_gc9a01/esp_lcd_gc9a01.c"


class LcdErrorContract(unittest.TestCase):
    def test_all_three_160x160_reset_commands_propagate_errors(self):
        source = SOURCE.read_text(encoding="utf-8")
        branch_match = re.search(
            r"^[ \t]*#elif[ \t]+CONFIG_LCD_GC9A01_160X160[ \t]*\n"
            r"(.*?)^[ \t]*#endif\b",
            source,
            re.MULTILINE | re.DOTALL,
        )
        self.assertIsNotNone(branch_match, "missing 160x160 initialization branch")
        branch = re.sub(
            r"//[^\n]*|/\*.*?\*/", "", branch_match.group(1), flags=re.DOTALL
        )
        call_pattern = (
            r"esp_lcd_panel_io_tx_param\s*\(\s*io\s*,\s*0[xX][aA]0\s*,"
            r"\s*NULL\s*,\s*0\s*\)"
        )
        calls = list(re.finditer(call_pattern, branch))
        self.assertEqual(len(calls), 3, "expected exactly three 0xA0 reset calls")
        guarded_calls = {
            match.span("call")
            for match in re.finditer(
                r"ESP_RETURN_ON_ERROR\s*\(\s*(?P<call>"
                + call_pattern
                + r')\s*,\s*TAG\s*,\s*"send command failed"\s*\)\s*;',
                branch,
            )
        }
        for ordinal, call in enumerate(calls, start=1):
            with self.subTest(reset_call=ordinal):
                self.assertIn(
                    call.span(),
                    guarded_calls,
                    f"0xA0 reset call {ordinal} is missing ESP_RETURN_ON_ERROR guard",
                )


if __name__ == "__main__":
    unittest.main()
