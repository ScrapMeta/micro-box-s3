// SPDX-License-Identifier: MIT
#pragma once
#include "driver/gpio.h"
#include "esp_err.h"
#include "esp_lcd_panel_io.h"
#include "esp_lcd_panel_ops.h"
#include "esp_camera.h"
#ifdef __cplusplus
extern "C" {
#endif
#define MICRO_BOX_S3_NAME "micro-box-s3"
#define MICRO_BOX_S3_LCD_WIDTH 160
#define MICRO_BOX_S3_LCD_HEIGHT 160
#define MICRO_BOX_S3_AUDIO_TX GPIO_NUM_45
#define MICRO_BOX_S3_AUDIO_RX GPIO_NUM_48
#include "micro_box_s3_pins.h"
// index 0/1 owns a separate SPI bus. Call only once per index.
esp_err_t micro_box_s3_lcd_init(unsigned index, esp_lcd_panel_handle_t *panel, esp_lcd_panel_io_handle_t *io);
// RGB565 VGA, one PSRAM framebuffer. Caller invokes esp_camera_init().
camera_config_t micro_box_s3_camera_config(void);
#ifdef __cplusplus
}
#endif
