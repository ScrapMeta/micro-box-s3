#include "lcd_display.h"

#include <vector>
#include <algorithm>
#include <font_awesome_symbols.h>
#include <esp_log.h>
#include <esp_err.h>
#include <esp_heap_caps.h>
#include "assets/lang_config.h"
#include <cstring>
#include <cstdlib>
#include "settings.h"

#include "board.h"

#include "application.h"

#define TAG "LcdDisplay"

static void CheckDisplayResult(esp_err_t result) {
    if (result != ESP_OK) {
        ESP_ERROR_CHECK(result);
        // ESP_ERROR_CHECK does not abort when NDEBUG is defined.
        std::abort();
    }
}

static bool EyeColorTransferDone(esp_lcd_panel_io_handle_t,
                                 esp_lcd_panel_io_event_data_t*, void* user_ctx) {
    BaseType_t higher_priority_task_woken = pdFALSE;
    xSemaphoreGiveFromISR(static_cast<SemaphoreHandle_t>(user_ctx),
                          &higher_priority_task_woken);
    return higher_priority_task_woken == pdTRUE;
}

// Color definitions for dark theme
#define DARK_BACKGROUND_COLOR       lv_color_hex(0x121212)     // Dark background
#define DARK_TEXT_COLOR             lv_color_white()           // White text
#define DARK_CHAT_BACKGROUND_COLOR  lv_color_hex(0x1E1E1E)     // Slightly lighter than background
#define DARK_USER_BUBBLE_COLOR      lv_color_hex(0x1A6C37)     // Dark green
#define DARK_ASSISTANT_BUBBLE_COLOR lv_color_hex(0x333333)     // Dark gray
#define DARK_SYSTEM_BUBBLE_COLOR    lv_color_hex(0x2A2A2A)     // Medium gray
#define DARK_SYSTEM_TEXT_COLOR      lv_color_hex(0xAAAAAA)     // Light gray text
#define DARK_BORDER_COLOR           lv_color_hex(0x333333)     // Dark gray border
#define DARK_LOW_BATTERY_COLOR      lv_color_hex(0xFF0000)     // Red for dark mode

// Color definitions for light theme
#define LIGHT_BACKGROUND_COLOR       lv_color_white()           // White background
#define LIGHT_TEXT_COLOR             lv_color_black()           // Black text
#define LIGHT_CHAT_BACKGROUND_COLOR  lv_color_hex(0xE0E0E0)     // Light gray background
#define LIGHT_USER_BUBBLE_COLOR      lv_color_hex(0x95EC69)     // WeChat green
#define LIGHT_ASSISTANT_BUBBLE_COLOR lv_color_white()           // White
#define LIGHT_SYSTEM_BUBBLE_COLOR    lv_color_hex(0xE0E0E0)     // Light gray
#define LIGHT_SYSTEM_TEXT_COLOR      lv_color_hex(0x666666)     // Dark gray text
#define LIGHT_BORDER_COLOR           lv_color_hex(0xE0E0E0)     // Light gray border
#define LIGHT_LOW_BATTERY_COLOR      lv_color_black()           // Black for light mode


// Define dark theme colors
const ThemeColors DARK_THEME = {
    .background = DARK_BACKGROUND_COLOR,
    .text = DARK_TEXT_COLOR,
    .chat_background = DARK_CHAT_BACKGROUND_COLOR,
    .user_bubble = DARK_USER_BUBBLE_COLOR,
    .assistant_bubble = DARK_ASSISTANT_BUBBLE_COLOR,
    .system_bubble = DARK_SYSTEM_BUBBLE_COLOR,
    .system_text = DARK_SYSTEM_TEXT_COLOR,
    .border = DARK_BORDER_COLOR,
    .low_battery = DARK_LOW_BATTERY_COLOR
};

// Define light theme colors
const ThemeColors LIGHT_THEME = {
    .background = LIGHT_BACKGROUND_COLOR,
    .text = LIGHT_TEXT_COLOR,
    .chat_background = LIGHT_CHAT_BACKGROUND_COLOR,
    .user_bubble = LIGHT_USER_BUBBLE_COLOR,
    .assistant_bubble = LIGHT_ASSISTANT_BUBBLE_COLOR,
    .system_bubble = LIGHT_SYSTEM_BUBBLE_COLOR,
    .system_text = LIGHT_SYSTEM_TEXT_COLOR,
    .border = LIGHT_BORDER_COLOR,
    .low_battery = LIGHT_LOW_BATTERY_COLOR
};


LV_FONT_DECLARE(font_awesome_30_4);


LcdDisplay::LcdDisplay(esp_lcd_panel_io_handle_t panel_io, esp_lcd_panel_handle_t panel,
            esp_lcd_panel_io_handle_t panel_io2, esp_lcd_panel_handle_t panel2, DisplayFonts fonts, int width, int height)
    :panel_io_(panel_io), panel_(panel),panel_io_2(panel_io2),panel_2(panel2),fonts_(fonts) {
    width_ = width;
    height_ = height;

    eye_mutex = xSemaphoreCreateMutex();
    CheckDisplayResult(eye_mutex != nullptr ? ESP_OK : ESP_ERR_NO_MEM);
    panel_done_ = xSemaphoreCreateBinary();
    CheckDisplayResult(panel_done_ != nullptr ? ESP_OK : ESP_ERR_NO_MEM);
    panel_done_2 = xSemaphoreCreateBinary();
    CheckDisplayResult(panel_done_2 != nullptr ? ESP_OK : ESP_ERR_NO_MEM);

    const esp_lcd_panel_io_callbacks_t callbacks = {
        .on_color_trans_done = EyeColorTransferDone,
    };
    CheckDisplayResult(esp_lcd_panel_io_register_event_callbacks(panel_io_, &callbacks, panel_done_));
    CheckDisplayResult(esp_lcd_panel_io_register_event_callbacks(panel_io_2, &callbacks, panel_done_2));

    // Load theme from settings
    Settings settings("display", false);
    current_theme_name_ = settings.GetString("theme", "light");

    // Update the theme
    if (current_theme_name_ == "dark") {
        current_theme_ = DARK_THEME;
    } else if (current_theme_name_ == "light") {
        current_theme_ = LIGHT_THEME;
    }
}



DualScreenDisplay::DualScreenDisplay(esp_lcd_panel_io_handle_t panel_io1, esp_lcd_panel_handle_t panel1,
    esp_lcd_panel_io_handle_t panel_io2, esp_lcd_panel_handle_t panel2,
    int width, int height, int offset_x, int offset_y,
    bool mirror_x, bool mirror_y, bool swap_xy,
    DisplayFonts fonts)
    : LcdDisplay(panel_io1, panel1, panel_io2, panel2, fonts,width,height) {

    SetupUI();
}

// RGB LCD实现




LcdDisplay::~LcdDisplay() {
    // Owners must stop new display calls before destruction. Wait for any active SetEye.
    CheckDisplayResult(xSemaphoreTake(eye_mutex, portMAX_DELAY) == pdTRUE ? ESP_OK : ESP_ERR_TIMEOUT);

    // 然后再清理 LVGL 对象
    if (content_ != nullptr) {
        lv_obj_del(content_);
    }
    if (status_bar_ != nullptr) {
        lv_obj_del(status_bar_);
    }
    if (side_bar_ != nullptr) {
        lv_obj_del(side_bar_);
    }
    if (container_ != nullptr) {
        lv_obj_del(container_);
    }
    if (display_ != nullptr) {
        lv_display_delete(display_);
    }

    if (panel_ != nullptr) {
        CheckDisplayResult(esp_lcd_panel_del(panel_));
    }
    if (panel_2 != nullptr) {
        CheckDisplayResult(esp_lcd_panel_del(panel_2));
    }
    // SPI I/O deletion drains queued transfers and removes their callbacks.
    // Keep both completion contexts alive until both I/O handles are gone.
    if (panel_io_ != nullptr) {
        CheckDisplayResult(esp_lcd_panel_io_del(panel_io_));
    }
    if (panel_io_2 != nullptr) {
        CheckDisplayResult(esp_lcd_panel_io_del(panel_io_2));
    }
    vSemaphoreDelete(panel_done_);
    vSemaphoreDelete(panel_done_2);
    CheckDisplayResult(xSemaphoreGive(eye_mutex) == pdTRUE ? ESP_OK : ESP_FAIL);
    vSemaphoreDelete(eye_mutex);
}

bool LcdDisplay::Lock(int timeout_ms) {
        // if (xSemaphoreTake(eye_mutex, timeout_ms) != pdTRUE) {
        //     ESP_LOGE("LCD", "Failed to acquire LCD mutex");
        //     return ESP_FAIL;
        // }
        return true;
}

void LcdDisplay::Unlock() {
        // xSemaphoreGive(eye_mutex);
}

//用于触发魔眼动画
void LcdDisplay::SetupUI() {
    // xTaskCreatePinnedToCore( task_eye_update, "task_eye_update", 1024*4, NULL, 4, &task_update_eye_handler,0);
}

void LcdDisplay::SetPreviewImage(const lv_img_dsc_t* img_dsc) {

}


    typedef struct {
        const char* name;
        int eyeNewX;
        int eyeNewY;
        bool isBlinking;
        bool isTrack;
    } EmotionConfig;

   
    void LcdDisplay::SetEmotion(const char* emotion) {
        ESP_LOGI(TAG,"%s",emotion);
        
        static const EmotionConfig emotionConfigs[] = {
            {"neutral", 505, 805, true, true}, // 默认表情，眼球居中，正常眨眼"😶" ok
            {"happy", 520, 1005, true, true},   // 眼睛稍微向下看，显得开心"🙂" ok
            {"laughing", 500, 1015, true, true}, // 眼睛向下看，显得大笑"😆"    ok
            {"funny", 520, 25, true, true},   // 眼睛向下看，显得搞笑"😂"
            {"sad",265, 335, true, true},     // 眼睛向上看，显得悲伤"😔" ok
            {"angry", 700, 510, true, true},  // 眼睛向右看，显得生气 "😠"
            {"crying", 514, 100, true, true},  // 眼睛向上看，显得哭泣 "😭"
            {"loving", 510, 540, true, true}, // 眼睛稍微向下看，显得爱慕 "😍"
            {"embarrassed", 1000, 510, true, true}, // 眼睛稍微向上看，显得尴尬 "😳" ok
            {"surprised", 150, 445, true, false}, // 眼睛向右看，显得惊讶    "😯" ok
            {"shocked", 985, 615, true, false},   // 眼睛向右看，显得震惊 "😱"  ok
            {"thinking", 65,670, true, true}, // 眼睛稍微向上看，显得思考 "🤔"
            {"winking", 510, 520, false, true},  // 眼睛眨眼，显得眨眼 "😉"
            {"cool",510, 510, true, true},     // 眼睛正常，显得酷 "😎"
            {"relaxed", 510, 490, true, true},  // 眼睛稍微闭合，显得放松 "😌"
            {"delicious", 510, 490, true, true}, // 眼睛稍微向下看，显得享受美食 "🤤"
            {"kissy", 1015, 510, true, true},    // 眼睛正常，显得亲吻 "😘"
            {"confident", 890, 650, true, true}, // 眼睛正常，显得自信 "😏" ok ?
            {"sleepy", 535, 605, true, true},   // 眼睛稍微闭合，显得困倦 "😴" ok
            {"silly", 515, 750, true, true},    // 眼睛向上看，显得愚蠢 "😜"
            {"confused", 1020, 1020, true, true}  // 眼睛稍微向上看，显得困惑 "🙄"
            // 添加更多表情配置
        };
       // 查找表情配置
    for (size_t i = 0; i < sizeof(emotionConfigs) / sizeof(EmotionConfig); i++) {
        if (strcmp(emotionConfigs[i].name, emotion) == 0) {
            //ESP_LOGI(TAG,"emotion:%s,name:%s,c_eyeX:%d,c_eyeY=%d,eyeX=%d,eyeY=%d,uT=%d,lT=%d",emotion,emotionConfigs[i].name,emotionConfigs[i].eyeX,emotionConfigs[i].eyeY,eyeX,eyeY,uThreshold,lThreshold);
            auto& app = Application::GetInstance();
            //更新眼睛状态x`
            app.eyeNewX= emotionConfigs[i].eyeNewX;
            app.eyeNewY = emotionConfigs[i].eyeNewY;
            app.is_blink = emotionConfigs[i].isBlinking;
            app.is_track = emotionConfigs[i].isTrack;

    // If low power, the material ready event will be triggered by the modem because of a reset
            // ESP_LOGI(TAG,"eyeNewX=%d,eyeNewY=%d,is_blink=%d,is_track=%d",eyeNewX,eyeNewY,is_blink,is_track);
            break;
        }
    }

    }
    void LcdDisplay::SetIcon(const char* icon) {}
    void LcdDisplay::SetTheme(const std::string& theme_name) {}

void LcdDisplay::SetEye(int x_start, int y_start, int x_end, int y_end, const void *color_data) {
    // The UI guards intentionally remain no-ops; serialize only eye transfers.
    CheckDisplayResult(xSemaphoreTake(eye_mutex, portMAX_DELAY) == pdTRUE ? ESP_OK : ESP_ERR_TIMEOUT);

    // A successful submission only queues DMA. Do not release the caller buffer
    // until each panel signals completion; abort on failure instead of returning
    // a buffer that the animation could overwrite or free while DMA still reads it.
    CheckDisplayResult(esp_lcd_panel_draw_bitmap(panel_, x_start, y_start, x_end, y_end, color_data));
    CheckDisplayResult(xSemaphoreTake(panel_done_, pdMS_TO_TICKS(2000)) == pdTRUE ? ESP_OK : ESP_ERR_TIMEOUT);
    CheckDisplayResult(esp_lcd_panel_draw_bitmap(panel_2, x_start, y_start, x_end, y_end, color_data));
    CheckDisplayResult(xSemaphoreTake(panel_done_2, pdMS_TO_TICKS(2000)) == pdTRUE ? ESP_OK : ESP_ERR_TIMEOUT);

    CheckDisplayResult(xSemaphoreGive(eye_mutex) == pdTRUE ? ESP_OK : ESP_FAIL);
}
