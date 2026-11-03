"""Static integration contract for the single-board Xiaozhi example."""
from pathlib import Path
import re
import subprocess
import unittest


class XiaozhiContract(unittest.TestCase):
    def test_single_board_application_contract(self):
        root = Path(__file__).resolve().parents[1]
        app = root / "examples" / "xiaozhi"
        self.assertTrue((app / "CMakeLists.txt").is_file(), "Xiaozhi ESP-IDF application is missing")
        cmake = (app / "CMakeLists.txt").read_text(encoding="utf-8")
        self.assertRegex(cmake, r"project\(micro-box-s3\)")
        self.assertIn("EXTRA_COMPONENT_DIRS", cmake)
        self.assertIn("../../components", cmake)
        self.assertIn('"${IDF_VERSION_MAJOR}.${IDF_VERSION_MINOR}.${IDF_VERSION_PATCH}"', cmake)

        boards = app / "main" / "boards"
        self.assertEqual({p.name for p in boards.iterdir() if p.is_dir()}, {"common", "micro-box-s3"})
        self.assertIn("Application::GetInstance().Start()",  (app / "main" / "main.cc").read_text(encoding="utf-8"))
        self.assertGreater((app / "main" / "application.cc").stat().st_size, 20000)
        self.assertIn("#include <functional>", (app / "main" / "background_task.h").read_text(encoding="utf-8"))
        self.assertIn("#include <vector>", (app / "main" / "ota.h").read_text(encoding="utf-8"))
        main_cmake = (app / "main" / "CMakeLists.txt").read_text(encoding="utf-8")
        self.assertIn('set(BOARD_TYPE "micro-box-s3")', main_cmake)
        for source in re.findall(r'"([^"\n]+\.(?:cc|c))"', main_cmake):
            self.assertTrue((app / "main" / source).is_file(), source)
        kconfig = (app / "main" / "Kconfig.projbuild").read_text(encoding="utf-8")
        self.assertEqual(re.findall(r"^\s*config (BOARD_TYPE_\w+)", kconfig, re.M), ["BOARD_TYPE_MICRO_BOX_S3"])
        defaults = (app / "sdkconfig.defaults").read_text(encoding="utf-8")
        for setting in ("BOARD_TYPE_MICRO_BOX_S3=y", "LCD_GC9A01_160X160=y", "USE_EYE_STYLE_VB6824=y", "LANGUAGE_ZH_CN=y", "USE_SOFTAP_NET_CONFIGURING=y", "USE_AUDIO_CODEC_ENCODE_OPUS=y", "ESPTOOLPY_FLASHSIZE_16MB=y", "ESPTOOLPY_FLASHMODE_QIO=y", "ESPTOOLPY_FLASHFREQ_80M=y", "SPIRAM_MODE_OCT=y", "SPIRAM_SPEED_80M=y", "OV3660_SUPPORT=y"):
            self.assertIn("CONFIG_" + setting, defaults)
        self.assertIn("# CONFIG_VB6824_OTA_SUPPORT is not set", defaults)
        self.assertNotIn("CONFIG_VB6824_OTA_SUPPORT=y", defaults)
        config = (boards / "micro-box-s3" / "config.h").read_text(encoding="utf-8")
        self.assertRegex(config, r"#define\s+DISPLAY_WIDTH\s+160\b")
        self.assertRegex(config, r"#define\s+DISPLAY_HEIGHT\s+160\b")
        self.assertRegex(config, r"#define\s+CODEC_TX_GPIO\s+GPIO_NUM_45")
        self.assertRegex(config, r"#define\s+CODEC_RX_GPIO\s+GPIO_NUM_48")
        board = (boards / "micro-box-s3" / "micro-box-s3.cc").read_text(encoding="utf-8")
        for feature in ("DualScreenDisplay", "Esp32Camera", "OnWakeUp", "WakeWordInvoke", "开始配网"):
            self.assertIn(feature, board)
        self.assertTrue((app / "main" / "protocols" / "websocket_protocol.cc").is_file())
        self.assertTrue((app / "main" / "protocols" / "mqtt_protocol.cc").is_file())
        self.assertIn("self.camera.take_photo", (app / "main" / "mcp_server.cc").read_text(encoding="utf-8"))
        camera = (boards / "common" / "esp32_camera.cc").read_text(encoding="utf-8")
        self.assertIn("JpegChunk end_chunk{};", camera)
        self.assertIn("xQueueSend(jpeg_queue, &end_chunk, portMAX_DELAY)", camera)
        self.assertIn("lv_img_dsc_t preview_image_{};", (boards / "common" / "esp32_camera.h").read_text(encoding="utf-8"))
        self.assertEqual({p.name for p in (app / "main" / "eye_data").iterdir()}, {"160_160"})
        self.assertEqual({p.name for p in (app / "main" / "assets").iterdir() if p.is_dir()}, {"zh-CN", "common"})
        self.assertGreater(len(list((app / "main" / "assets" / "zh-CN").glob("*.p3"))), 0)
        self.assertIn('CODE = "zh-CN"', (app / "main" / "assets" / "lang_config.h").read_text(encoding="utf-8"))
        manifest = (app / "main" / "idf_component.yml").read_text(encoding="utf-8")
        self.assertIn('version: "==5.4.3"', manifest)
        self.assertNotRegex(manifest, r"[~^*]|latest|git:")
        for source in (app / "main").rglob("*"):
            if source.suffix not in {".cc", ".c", ".h"}:
                continue
            text = source.read_text(encoding="utf-8")
            self.assertNotIn("240_240/", text, str(source))
            self.assertNotIn("vb_ota.h", text, str(source))
            self.assertNotRegex(text, r"\bjl_ws_\w+", str(source))
        self.assertIn("Copyright (c) 2025 yichone", (app / "LICENSE").read_text(encoding="utf-8"))
        generated=['examples/xiaozhi/dependencies.lock','examples/xiaozhi/sdkconfig']
        ignored=subprocess.run(['git','check-ignore','--no-index']+generated,cwd=root,stdout=subprocess.PIPE,text=True)
        self.assertEqual(ignored.returncode,0)
        self.assertEqual(set(ignored.stdout.splitlines()),set(generated))
        tracked=subprocess.run(['git','ls-files','--']+generated,cwd=root,stdout=subprocess.PIPE,text=True,check=True)
        self.assertEqual(tracked.stdout,'')


if __name__ == "__main__":
    unittest.main()
