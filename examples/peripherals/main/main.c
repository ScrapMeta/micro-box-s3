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
#include <inttypes.h>
#include "micro_box_s3_inputs.h"
#include "micro_box_s3_motor.h"
#include "driver/usb_serial_jtag.h"
static micro_box_s3_motor_handle_t motor;
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

#if CONFIG_MICRO_BOX_S3_DEMO_TOUCH || CONFIG_MICRO_BOX_S3_DEMO_BUTTONS || CONFIG_MICRO_BOX_S3_DEMO_MOTOR || CONFIG_MICRO_BOX_S3_DEMO_CONTROLS
#if !CONFIG_MICRO_BOX_S3_DEMO_MOTOR
static void input_event(micro_box_s3_input_t input,micro_box_s3_input_event_t event,void *arg){
    (void)arg;
    ESP_LOGI(TAG,"INPUT id=%u event=%u (touch=0 A=1 B=2; press=0 release=1 long=2)",(unsigned)input,(unsigned)event);
}
#endif
static void controls_demo(void){
    micro_box_s3_inputs_handle_t inputs=NULL;
#if !CONFIG_MICRO_BOX_S3_DEMO_MOTOR
    micro_box_s3_inputs_config_t cfg=MICRO_BOX_S3_INPUTS_DEFAULT_CONFIG();
#if CONFIG_MICRO_BOX_S3_DEMO_BUTTONS
    cfg.enable_touch=false;
#elif CONFIG_MICRO_BOX_S3_DEMO_TOUCH
    cfg.enable_buttons=false;
#endif
    cfg.callback=input_event;
    ESP_ERROR_CHECK(micro_box_s3_inputs_create(&cfg,&inputs));
#endif
#if CONFIG_MICRO_BOX_S3_DEMO_MOTOR || CONFIG_MICRO_BOX_S3_DEMO_CONTROLS
    usb_serial_jtag_driver_config_t usb={.tx_buffer_size=1024,.rx_buffer_size=256};
    ESP_ERROR_CHECK(usb_serial_jtag_driver_install(&usb));
    ESP_LOGI(TAG,"No automatic vibration. Serial V=one 200ms/100%% pulse; X=stop; S=status. Max400ms, cooldown3s.");
#endif
    for(;;){
#if CONFIG_MICRO_BOX_S3_DEMO_MOTOR || CONFIG_MICRO_BOX_S3_DEMO_CONTROLS
        uint8_t command=0;
        if(usb_serial_jtag_read_bytes(&command,1,pdMS_TO_TICKS(50))==1){
            if(command=='V'){
                esp_err_t e=micro_box_s3_motor_pulse(motor,200,100,0);
                ESP_LOGI(TAG,"motor request result=%s",esp_err_to_name(e));
            }else if(command=='X')ESP_ERROR_CHECK(micro_box_s3_motor_stop(motor));
            else if(command=='S'){
                micro_box_s3_motor_state_t state;
                ESP_ERROR_CHECK(micro_box_s3_motor_get_state(motor,&state));
                ESP_LOGI(TAG,"MOTOR active=%u duty=%u duration_ms=%u count=%"PRIu32,(unsigned)state.active,state.duty_percent,state.duration_ms,state.pulses_started);
            }
        }
#endif
        if(inputs){
            micro_box_s3_inputs_snapshot_t snapshot;
            ESP_ERROR_CHECK(micro_box_s3_inputs_get_snapshot(inputs,&snapshot));
            ESP_LOGI(TAG,"INPUTS calibrated=%u raw=%"PRIu32" base=%"PRIu32" touch=%u A=%u B=%u",(unsigned)snapshot.calibrated,snapshot.touch_raw,snapshot.touch_baseline,(unsigned)snapshot.touch_pressed,(unsigned)snapshot.button_a_pressed,(unsigned)snapshot.button_b_pressed);
        }
        vTaskDelay(pdMS_TO_TICKS(500));
    }
}
#endif

void app_main(void) {
    // Always claim the actuator pin at idle, including input-only examples.
    ESP_ERROR_CHECK(micro_box_s3_motor_create(&motor));
    ESP_LOGI(TAG,"micro-box-s3 peripheral example; motor starts OFF");
#if CONFIG_MICRO_BOX_S3_DEMO_DISPLAY
    display_demo();
#elif CONFIG_MICRO_BOX_S3_DEMO_AUDIO
    audio_demo();
#elif CONFIG_MICRO_BOX_S3_DEMO_CAMERA
    camera_demo();
#elif CONFIG_MICRO_BOX_S3_DEMO_TOUCH || CONFIG_MICRO_BOX_S3_DEMO_BUTTONS || CONFIG_MICRO_BOX_S3_DEMO_MOTOR || CONFIG_MICRO_BOX_S3_DEMO_CONTROLS
    controls_demo();
#endif
}
