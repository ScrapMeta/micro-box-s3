// SPDX-License-Identifier: MIT
#include "micro_box_s3.h"
#include "driver/spi_master.h"
#include "esp_lcd_gc9a01.h"

esp_err_t micro_box_s3_lcd_init(unsigned index, esp_lcd_panel_handle_t *panel, esp_lcd_panel_io_handle_t *io) {
    if (index > 1 || panel == NULL || io == NULL) return ESP_ERR_INVALID_ARG;
    const spi_host_device_t hosts[2] = {SPI3_HOST, SPI2_HOST};
    const int sclk[2] = {42, 38}, mosi[2] = {2, 39}, rst[2] = {1, 40}, dc[2] = {41, 0};
    *panel = NULL; *io = NULL;
    spi_bus_config_t bus = {.mosi_io_num=mosi[index], .miso_io_num=-1, .sclk_io_num=sclk[index],
        .quadwp_io_num=-1, .quadhd_io_num=-1, .max_transfer_sz=160*160*2};
    esp_err_t err = spi_bus_initialize(hosts[index], &bus, SPI_DMA_CH_AUTO);
    if (err != ESP_OK) return err;
    esp_lcd_panel_io_spi_config_t cfg = {.cs_gpio_num=-1, .dc_gpio_num=dc[index], .spi_mode=0,
        .pclk_hz=20000000, .trans_queue_depth=10, .lcd_cmd_bits=8, .lcd_param_bits=8};
    err = esp_lcd_new_panel_io_spi((esp_lcd_spi_bus_handle_t)hosts[index], &cfg, io);
    if (err != ESP_OK) goto fail;
    esp_lcd_panel_dev_config_t dev = {.reset_gpio_num=rst[index], .rgb_ele_order=LCD_RGB_ELEMENT_ORDER_RGB, .bits_per_pixel=16};
    err = esp_lcd_new_panel_gc9a01(*io, &dev, panel);
    if (err == ESP_OK) err = esp_lcd_panel_reset(*panel);
    if (err == ESP_OK) err = esp_lcd_panel_init(*panel);
    if (err == ESP_OK) err = esp_lcd_panel_invert_color(*panel, false);
    if (err == ESP_OK) err = esp_lcd_panel_disp_on_off(*panel, true);
    if (err == ESP_OK) return ESP_OK;
fail:
    if (*panel) {esp_lcd_panel_del(*panel); *panel=NULL;}
    if (*io) {esp_lcd_panel_io_del(*io); *io=NULL;}
    spi_bus_free(hosts[index]);
    return err;
}

camera_config_t micro_box_s3_camera_config(void) {
    camera_config_t c = {0};
    c.ledc_channel=LEDC_CHANNEL_0; c.ledc_timer=LEDC_TIMER_0;
    c.pin_d0=21; c.pin_d1=9; c.pin_d2=3; c.pin_d3=10;
    c.pin_d4=47; c.pin_d5=18; c.pin_d6=17; c.pin_d7=15;
    c.pin_xclk=16; c.pin_pclk=8; c.pin_vsync=6; c.pin_href=7;
    c.pin_sccb_sda=4; c.pin_sccb_scl=5; c.pin_pwdn=-1; c.pin_reset=-1;
    c.xclk_freq_hz=20000000; c.pixel_format=PIXFORMAT_RGB565; c.frame_size=FRAMESIZE_VGA;
    c.jpeg_quality=10; c.fb_count=1; c.fb_location=CAMERA_FB_IN_PSRAM; c.grab_mode=CAMERA_GRAB_WHEN_EMPTY;
    return c;
}
