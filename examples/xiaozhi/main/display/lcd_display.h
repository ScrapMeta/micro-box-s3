#ifndef LCD_DISPLAY_H
#define LCD_DISPLAY_H

#include "display.h"

#include <esp_lcd_panel_io.h>
#include <esp_lcd_panel_ops.h>
#include <font_emoji.h>

#include <atomic>
#include <freertos/FreeRTOS.h>
#include <freertos/semphr.h>

// Theme color structure
struct ThemeColors {
    lv_color_t background;
    lv_color_t text;
    lv_color_t chat_background;
    lv_color_t user_bubble;
    lv_color_t assistant_bubble;
    lv_color_t system_bubble;
    lv_color_t system_text;
    lv_color_t border;
    lv_color_t low_battery;
};


class LcdDisplay : public Display {
protected:
    esp_lcd_panel_io_handle_t panel_io_ = nullptr;
    esp_lcd_panel_handle_t panel_ = nullptr;
    
        esp_lcd_panel_io_handle_t panel_io_2 = nullptr;
        esp_lcd_panel_handle_t panel_2 = nullptr;

        SemaphoreHandle_t eye_mutex = NULL; // 魔眼互斥锁
    SemaphoreHandle_t panel_done_ = nullptr;
    SemaphoreHandle_t panel_done_2 = nullptr;

    lv_draw_buf_t draw_buf_;
    lv_obj_t* status_bar_ = nullptr;
    lv_obj_t* content_ = nullptr;
    lv_obj_t* container_ = nullptr;
    lv_obj_t* side_bar_ = nullptr;
    lv_obj_t* preview_image_ = nullptr;

    DisplayFonts fonts_;
    ThemeColors current_theme_;


    void SetupUI();
    virtual bool Lock(int timeout_ms = 0) override;
    virtual void Unlock() override;

protected:
    // 添加protected构造函数
     // 添加protected构造函数
        LcdDisplay(esp_lcd_panel_io_handle_t panel_io, esp_lcd_panel_handle_t panel,
            esp_lcd_panel_io_handle_t panel_io2, esp_lcd_panel_handle_t panel2, DisplayFonts fonts,int width, int height);
    
public:
    ~LcdDisplay();
    virtual void SetEmotion(const char* emotion) override;
    virtual void SetIcon(const char* icon) override;
    virtual void SetPreviewImage(const lv_img_dsc_t* img_dsc) override;

    // Add theme switching function
    virtual void SetTheme(const std::string& theme_name) override;
        virtual void SetEye(int x_start, int y_start, int x_end, int y_end, const void *color_data) override; // 设置眼睛
};

// RGB LCD显示器

// MIPI LCD显示器

// // SPI LCD显示器

//SPI双屏驱动
class DualScreenDisplay:public LcdDisplay {
public:
DualScreenDisplay(esp_lcd_panel_io_handle_t panel_io1, esp_lcd_panel_handle_t panel1,
    esp_lcd_panel_io_handle_t panel_io2, esp_lcd_panel_handle_t panel2,
    int width, int height, int offset_x, int offset_y,
    bool mirror_x, bool mirror_y, bool swap_xy,
    DisplayFonts fonts);
};

// QSPI LCD显示器

// MCU8080 LCD显示器
#endif // LCD_DISPLAY_H
