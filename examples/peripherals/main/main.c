// SPDX-License-Identifier: MIT
#include <math.h>
#include <stdlib.h>
#include <string.h>
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "freertos/semphr.h"
#include "esp_attr.h"
#include "esp_log.h"
#include "esp_camera.h"
#include "micro_box_s3.h"
#include "vb6824.h"
#include "touch_element/touch_button.h"
static const char *TAG = "micro-box-s3";

#if CONFIG_MICRO_BOX_S3_DEMO_DISPLAY
static SemaphoreHandle_t done[2];
static DMA_ATTR uint16_t stripe[160*10];
static bool color_done(esp_lcd_panel_io_handle_t io, esp_lcd_panel_io_event_data_t *event, void *arg) {
    (void)io; (void)event;
    BaseType_t wake=pdFALSE;
    xSemaphoreGiveFromISR((SemaphoreHandle_t)arg, &wake);
    return wake==pdTRUE;
}
static void display_demo(void) {
    esp_lcd_panel_handle_t panel[2]; esp_lcd_panel_io_handle_t io[2];
    for (unsigned i=0; i<2; ++i) {
        done[i]=xSemaphoreCreateBinary(); if (!done[i]) abort();
        ESP_ERROR_CHECK(micro_box_s3_lcd_init(i,&panel[i],&io[i]));
        esp_lcd_panel_io_callbacks_t cb={.on_color_trans_done=color_done};
        ESP_ERROR_CHECK(esp_lcd_panel_io_register_event_callbacks(io[i],&cb,done[i]));
    }
    // RGB565 bytes are swapped for the SPI wire order.
    const uint16_t colors[]={0x00f8,0xe007,0x1f00};
    for (;;) {
        for (unsigned c=0;c<3;++c) {
            for (unsigned n=0;n<160*10;++n) stripe[n]=colors[c];
            for (unsigned y=0;y<160;y+=10) {
                for (unsigned i=0;i<2;++i) {
                    ESP_ERROR_CHECK(esp_lcd_panel_draw_bitmap(panel[i],0,y,160,y+10,stripe));
                    if (xSemaphoreTake(done[i],pdMS_TO_TICKS(2000)) != pdTRUE) abort();
                }
            }
            ESP_LOGI(TAG,"RGB color %u on both panels",c);
            vTaskDelay(pdMS_TO_TICKS(1000));
        }
    }
}
#endif

#if CONFIG_MICRO_BOX_S3_DEMO_AUDIO
static void voice_command(char *command,uint16_t length,void *arg) {
    (void)arg; ESP_LOGI(TAG,"Wake/command: %.*s",length,command);
}
static void audio_demo(void) {
    vb6824_init(MICRO_BOX_S3_AUDIO_TX,MICRO_BOX_S3_AUDIO_RX);
    vb6824_register_voice_command_cb(voice_command,NULL);
    vb6824_audio_enable_output(true); vb6824_audio_enable_input(true);
    vb6824_audio_set_output_volume(30);
    // 16 kHz signed PCM output. Input uses the chip's OPUS stream, not PCM.
    int16_t tone[160];
    for (unsigned i=0;i<160;++i) tone[i]=(int16_t)(3000*sinf(2*3.14159265359f*1000*i/16000));
    for (unsigned i=0;i<50;++i) vb6824_audio_write((uint8_t*)tone,sizeof(tone));
    ESP_LOGI(TAG,"Tone queued; speak the configured wake word. Input frames are OPUS.");
    uint8_t frame[512];
    for (;;) {uint16_t n=vb6824_audio_read(frame,sizeof(frame)); if(n) ESP_LOGD(TAG,"OPUS input bytes=%u",n);}
}
#endif

#if CONFIG_MICRO_BOX_S3_DEMO_CAMERA
static void camera_demo(void) {
    camera_config_t c=micro_box_s3_camera_config(); ESP_ERROR_CHECK(esp_camera_init(&c));
    for (;;) {
        camera_fb_t *frame=esp_camera_fb_get();
        if(frame) {ESP_LOGI(TAG,"Frame %ux%u, %u bytes",(unsigned)frame->width,(unsigned)frame->height,(unsigned)frame->len);esp_camera_fb_return(frame);}
        else ESP_LOGE(TAG,"Capture failed");
        vTaskDelay(pdMS_TO_TICKS(1000));
    }
}
#endif

#if CONFIG_MICRO_BOX_S3_DEMO_TOUCH
static void touch_event(touch_button_handle_t handle,touch_button_message_t *event,void *arg) {
    (void)handle; ESP_LOGI(TAG,"Touch channel %u event %u",(unsigned)(uintptr_t)arg,(unsigned)event->event);
}
static void touch_demo(void) {
    const touch_pad_t channels[]={TOUCH_PAD_NUM14,TOUCH_PAD_NUM13,TOUCH_PAD_NUM12,TOUCH_PAD_NUM11};
    touch_elem_global_config_t all=TOUCH_ELEM_GLOBAL_DEFAULT_CONFIG(); ESP_ERROR_CHECK(touch_element_install(&all));
    touch_button_global_config_t buttons=TOUCH_BUTTON_GLOBAL_DEFAULT_CONFIG(); ESP_ERROR_CHECK(touch_button_install(&buttons));
    for(unsigned i=0;i<4;++i) {
        touch_button_handle_t h; touch_button_config_t c={.channel_num=channels[i],.channel_sens=0.1F};
        ESP_ERROR_CHECK(touch_button_create(&c,&h));
        ESP_ERROR_CHECK(touch_button_subscribe_event(h,TOUCH_ELEM_EVENT_ON_PRESS|TOUCH_ELEM_EVENT_ON_RELEASE|TOUCH_ELEM_EVENT_ON_LONGPRESS,(void*)(uintptr_t)channels[i]));
        ESP_ERROR_CHECK(touch_button_set_dispatch_method(h,TOUCH_ELEM_DISP_CALLBACK));
        ESP_ERROR_CHECK(touch_button_set_callback(h,touch_event));
        ESP_ERROR_CHECK(touch_button_set_longpress(h,2000));
    }
    touch_element_start();
    for(;;) vTaskDelay(pdMS_TO_TICKS(1000));
}
#endif

void app_main(void) {
    ESP_LOGI(TAG,"micro-box-s3 peripheral example");
#if CONFIG_MICRO_BOX_S3_DEMO_DISPLAY
    display_demo();
#elif CONFIG_MICRO_BOX_S3_DEMO_AUDIO
    audio_demo();
#elif CONFIG_MICRO_BOX_S3_DEMO_CAMERA
    camera_demo();
#elif CONFIG_MICRO_BOX_S3_DEMO_TOUCH
    touch_demo();
#endif
}
