// SPDX-License-Identifier: MIT
#include "wifi_board.h"
#include "audio_codecs/vb6824_audio_codec.h"
#include "display/lcd_display.h"
#include "application.h"
#include "config.h"
#include "esp32_camera.h"
#include "iot/thing_manager.h"
#include "freertos/task.h"
#include <atomic>
#include <esp_check.h>
#include <esp_log.h>

class MicroBoxS3 : public WifiBoard {
private:
    VbAduioCodec audio_codec_{CODEC_TX_GPIO, CODEC_RX_GPIO};
    LcdDisplay* display_ = nullptr;
    Esp32Camera* camera_ = nullptr;
    std::atomic<bool> wifi_reset_pending_{false};

    static void WifiConfigurationTask(void* arg) {
        auto* board = static_cast<MicroBoxS3*>(arg);
        board->ResetWifiConfiguration();
        // Normally restarts; allow retry and delete this task if it returns.
        board->wifi_reset_pending_.store(false);
        vTaskDelete(nullptr);
    }

    void RequestWifiConfiguration() {
        if (wifi_reset_pending_.exchange(true)) {
            return;
        }
        // The board singleton outlives the task; no application event loop is needed.
        const BaseType_t result = xTaskCreate(
            WifiConfigurationTask, "micro-box-s3-net", 4096, this, 5, nullptr);
        if (result != pdPASS) {
            wifi_reset_pending_.store(false);
            ESP_LOGE("micro-box-s3", "Failed to create Wi-Fi recovery task");
        }
    }

public:
    MicroBoxS3() {
        esp_lcd_panel_io_handle_t io[2] = {};
        esp_lcd_panel_handle_t panel[2] = {};
        ESP_ERROR_CHECK(micro_box_s3_lcd_init(0, &panel[0], &io[0]));
        ESP_ERROR_CHECK(micro_box_s3_lcd_init(1, &panel[1], &io[1]));
        display_ = new DualScreenDisplay(io[0], panel[0], io[1], panel[1],
            DISPLAY_WIDTH, DISPLAY_HEIGHT, 0, 0, false, false, false, {});
        // OV3660, RGB565 VGA, one framebuffer in PSRAM; no duplicated camera bus setup.
        camera_ = new Esp32Camera(micro_box_s3_camera_config());
        auto& things = iot::ThingManager::GetInstance();
        things.AddThing(iot::CreateThing("Speaker"));
        things.AddThing(iot::CreateThing("Screen"));
        audio_codec_.OnWakeUp([this](const std::string& command) {
            auto& app = Application::GetInstance();
            if (command == vb6824_get_wakeup_word()) {
                if (app.GetDeviceState() != kDeviceStateListening) {
                    app.WakeWordInvoke("你好小智");
                }
            } else if (command == "开始配网") {
                // Do not restart or block the UART receive task inside its callback.
                RequestWifiConfiguration();
            }
        });
    }
    AudioCodec* GetAudioCodec() override { return &audio_codec_; }
    Display* GetDisplay() override { return display_; }
    Camera* GetCamera() override { return camera_; }
};
DECLARE_BOARD(MicroBoxS3);
