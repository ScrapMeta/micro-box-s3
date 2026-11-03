# SPDX-License-Identifier: Apache-2.0
"""Static micro-box-s3 DMA lifetime contracts; no firmware or device execution.

These check source structure, not actual DMA completion or SPI fault injection.
Run: python -B -m unittest discover -s tests -p test_display_dma_contract.py -v
"""

from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]
DISPLAY = ROOT / "examples/xiaozhi/main/display"


def without_comments(source):
    return re.sub(r"//[^\n]*|/\*.*?\*/", "", source, flags=re.DOTALL)


def compact(source):
    return re.sub(r"\s+", "", source)


def function_body(source, signature):
    start = source.find(signature)
    if start < 0:
        raise AssertionError(f"missing function: {signature}")
    opening = source.index("{", start)
    depth = 1
    for offset in range(opening + 1, len(source)):
        depth += (source[offset] == "{") - (source[offset] == "}")
        if depth == 0:
            return source[opening + 1:offset]
    raise AssertionError(f"unclosed function: {signature}")


class DisplayDmaContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = without_comments((DISPLAY / "lcd_display.cc").read_text(encoding="utf-8"))
        cls.header = without_comments((DISPLAY / "lcd_display.h").read_text(encoding="utf-8"))

    def test_constructor_owns_distinct_empty_completion_semaphores(self):
        constructor = compact(function_body(self.source, "LcdDisplay::LcdDisplay("))
        self.assertIn("eye_mutex=xSemaphoreCreateMutex();", constructor)
        for done in ("panel_done_", "panel_done_2"):
            with self.subTest(completion=done):
                self.assertIn(f"SemaphoreHandle_t{done}=nullptr;", compact(self.header))
                self.assertIn(f"{done}=xSemaphoreCreateBinary();", constructor)
                self.assertIn(
                    f"CheckDisplayResult({done}!=nullptr?ESP_OK:ESP_ERR_NO_MEM);", constructor
                )
                self.assertNotIn(f"xSemaphoreGive({done})", constructor)
        self.assertIn(
            "CheckDisplayResult(eye_mutex!=nullptr?ESP_OK:ESP_ERR_NO_MEM);", constructor
        )

    def test_both_io_callbacks_are_registered_with_matching_contexts(self):
        constructor = compact(function_body(self.source, "LcdDisplay::LcdDisplay("))
        self.assertIn(".on_color_trans_done=EyeColorTransferDone", constructor)
        for io, done in (("panel_io_", "panel_done_"), ("panel_io_2", "panel_done_2")):
            with self.subTest(io=io):
                registration = (
                    f"CheckDisplayResult(esp_lcd_panel_io_register_event_callbacks({io},&callbacks,{done}));"
                )
                self.assertIn(registration, constructor)
                self.assertLess(constructor.index(f"{done}=xSemaphoreCreateBinary();"),
                                constructor.index(registration))

    def test_completion_callback_only_signals_from_isr(self):
        callback = compact(function_body(self.source, "EyeColorTransferDone("))
        self.assertIn("BaseType_thigher_priority_task_woken=pdFALSE;", callback)
        self.assertIn(
            "xSemaphoreGiveFromISR(static_cast<SemaphoreHandle_t>(user_ctx),&higher_priority_task_woken);",
            callback,
        )
        self.assertIn("returnhigher_priority_task_woken==pdTRUE;", callback)
        self.assertNotRegex(callback, r"ESP_LOG|malloc|calloc|\bnew\b|xSemaphoreTake|xSemaphoreGive\(")

    def test_set_eye_serializes_checked_submissions_and_waits_before_return(self):
        body = compact(function_body(self.source, "void LcdDisplay::SetEye("))
        lock = "CheckDisplayResult(xSemaphoreTake(eye_mutex,portMAX_DELAY)==pdTRUE?ESP_OK:ESP_ERR_TIMEOUT);"
        unlock = "CheckDisplayResult(xSemaphoreGive(eye_mutex)==pdTRUE?ESP_OK:ESP_FAIL);"
        self.assertIn(lock, body, "SetEye must serialize independently of the no-op UI lock")
        self.assertIn(unlock, body)
        previous = body.index(lock)
        self.assertEqual(body.count("esp_lcd_panel_draw_bitmap("), 2)
        for panel, done in (("panel_", "panel_done_"), ("panel_2", "panel_done_2")):
            with self.subTest(panel=panel):
                draw = (
                    f"CheckDisplayResult(esp_lcd_panel_draw_bitmap({panel},x_start,y_start,x_end,y_end,color_data));"
                )
                wait = (
                    f"CheckDisplayResult(xSemaphoreTake({done},pdMS_TO_TICKS(2000))==pdTRUE?ESP_OK:ESP_ERR_TIMEOUT);"
                )
                self.assertIn(draw, body, "submission errors must fail closed")
                self.assertIn(wait, body, "timeout must abort, never return a DMA-owned buffer")
                self.assertLess(previous, body.index(draw))
                self.assertLess(body.index(draw), body.index(wait))
                previous = body.index(wait)
        self.assertLess(previous, body.index(unlock))
        self.assertNotIn("return", body)
        self.assertNotIn("Lock(", body)
        self.assertNotIn("Unlock(", body)

    def test_teardown_removes_both_io_before_deleting_callback_contexts(self):
        body = compact(function_body(self.source, "LcdDisplay::~LcdDisplay("))
        lock = "CheckDisplayResult(xSemaphoreTake(eye_mutex,portMAX_DELAY)==pdTRUE?ESP_OK:ESP_ERR_TIMEOUT);"
        self.assertIn(lock, body)
        io_deletions = []
        for panel, io in (("panel_", "panel_io_"), ("panel_2", "panel_io_2")):
            panel_del = f"CheckDisplayResult(esp_lcd_panel_del({panel}));"
            io_del = f"CheckDisplayResult(esp_lcd_panel_io_del({io}));"
            self.assertIn(panel_del, body)
            self.assertIn(io_del, body, "I/O deletion must drain callbacks before their contexts are freed")
            self.assertLess(body.index(lock), body.index(panel_del))
            self.assertLess(body.index(panel_del), body.index(io_del))
            io_deletions.append(body.index(io_del))
        for done in ("panel_done_", "panel_done_2"):
            deletion = f"vSemaphoreDelete({done});"
            self.assertIn(deletion, body)
            self.assertLess(max(io_deletions), body.index(deletion))
            self.assertLess(body.index(deletion), body.index("vSemaphoreDelete(eye_mutex);"))
        self.assertIn("CheckDisplayResult(xSemaphoreGive(eye_mutex)==pdTRUE?ESP_OK:ESP_FAIL);", body)

    def test_checked_failures_abort_even_with_assertions_disabled(self):
        self.assertIn("#include <cstdlib>", self.source)
        body = compact(function_body(self.source, "CheckDisplayResult("))
        self.assertEqual(body, "if(result!=ESP_OK){ESP_ERROR_CHECK(result);std::abort();}")
        for signature in ("LcdDisplay::LcdDisplay(", "LcdDisplay::~LcdDisplay(", "void LcdDisplay::SetEye("):
            checked = compact(function_body(self.source, signature))
            self.assertIn("CheckDisplayResult(", checked)
            self.assertNotIn("ESP_ERROR_CHECK(", checked, "NDEBUG removes ESP_ERROR_CHECK termination")

    def test_existing_void_api_and_no_op_ui_guards_are_preserved(self):
        self.assertRegex(self.header, r"virtual\s+void\s+SetEye\s*\(")
        self.assertEqual(compact(function_body(self.source, "bool LcdDisplay::Lock(")), "returntrue;")
        self.assertEqual(compact(function_body(self.source, "void LcdDisplay::Unlock(")), "")
        self.assertEqual(compact(function_body(self.source, "void LcdDisplay::SetupUI(")), "")


if __name__ == "__main__":
    unittest.main()
