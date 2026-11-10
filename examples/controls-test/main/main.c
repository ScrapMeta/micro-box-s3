// SPDX-License-Identifier: MIT
#include <inttypes.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "driver/gpio.h"
#include "driver/touch_pad.h"
#include "esp_log.h"
#include "esp_timer.h"
#include "input_logic.h"
#define MOTOR_GPIO GPIO_NUM_14
#define TOUCH_CHANNEL TOUCH_PAD_NUM11
static const char *TAG="controls-test";
static uint32_t now_ms(void){return (uint32_t)(esp_timer_get_time()/1000);}
static bool touch_read(uint32_t *raw){
    return touch_pad_read_raw_data(TOUCH_CHANNEL,raw)==ESP_OK && *raw>0 && *raw<TOUCH_PAD_THRESHOLD_MAX;
}
static void motor_locked(void){
    ESP_ERROR_CHECK(gpio_reset_pin(MOTOR_GPIO));
    ESP_ERROR_CHECK(gpio_set_level(MOTOR_GPIO,0));
    gpio_config_t cfg={.pin_bit_mask=1ULL<<MOTOR_GPIO,.mode=GPIO_MODE_OUTPUT,
        .pull_up_en=GPIO_PULLUP_DISABLE,.pull_down_en=GPIO_PULLDOWN_ENABLE,.intr_type=GPIO_INTR_DISABLE};
    ESP_ERROR_CHECK(gpio_config(&cfg));
    ESP_ERROR_CHECK(gpio_set_level(MOTOR_GPIO,0));
}
static void input_setup(void){
    gpio_config_t cfg={.pin_bit_mask=(1ULL<<GPIO_NUM_12)|(1ULL<<GPIO_NUM_13),.mode=GPIO_MODE_INPUT,
        .pull_up_en=GPIO_PULLUP_ENABLE,.pull_down_en=GPIO_PULLDOWN_DISABLE,.intr_type=GPIO_INTR_DISABLE};
    ESP_ERROR_CHECK(gpio_config(&cfg));
    ESP_ERROR_CHECK(touch_pad_init());
    ESP_ERROR_CHECK(touch_pad_config(TOUCH_CHANNEL));
    touch_pad_denoise_t denoise={.grade=TOUCH_PAD_DENOISE_BIT4,.cap_level=TOUCH_PAD_DENOISE_CAP_L4};
    ESP_ERROR_CHECK(touch_pad_denoise_set_config(&denoise));
    ESP_ERROR_CHECK(touch_pad_denoise_enable());
    ESP_ERROR_CHECK(touch_pad_set_fsm_mode(TOUCH_FSM_MODE_TIMER));
    ESP_ERROR_CHECK(touch_pad_fsm_start());
}
void app_main(void){
    motor_locked();
    ESP_LOGI(TAG,"REV=controls-inputs-v1 MOTOR_LOCKED GPIO14=0; NO MOTOR COMMANDS");
    ESP_LOGI(TAG,"GPIO12=BUTTON_A GPIO13=BUTTON_B GPIO11=TOUCH; offline, no display/audio/network");
    input_setup();
    ESP_LOGW(TAG,"CALIBRATING: keep fingers off the electrode for 3 seconds");
    uint64_t sum=0;uint32_t count=0,raw=0;
    for(unsigned i=0;i<150;i++){
        vTaskDelay(pdMS_TO_TICKS(20));
        if(i>=50 && touch_read(&raw)){sum+=raw;count++;}
    }
    if(count<50){ESP_LOGE(TAG,"TOUCH_FAULT: insufficient valid samples; buttons still available");}
    uint32_t base=count>=50?(uint32_t)(sum/count):0;
    input_state_t a,b,t;uint32_t now=now_ms();
    input_init(&a,(uint32_t)gpio_get_level(GPIO_NUM_12),now);
    input_init(&b,(uint32_t)gpio_get_level(GPIO_NUM_13),now);
    input_init(&t,0,now);
    uint32_t ac=0,bc=0,tc=0,last=now;
    ESP_LOGI(TAG,"READY base=%"PRIu32" proposed thresholds +10%% press / +5%% release; A=%"PRIu32" B=%"PRIu32,base,a.stable,b.stable);
    for(;;){
        now=now_ms();
        if(input_step(&a,(uint32_t)gpio_get_level(GPIO_NUM_12),now,25)){
            if(!a.stable)ac++;
            ESP_LOGI(TAG,"BUTTON_A GPIO12 %s count=%"PRIu32,a.stable?"RELEASE":"PRESS",ac);
        }
        if(input_step(&b,(uint32_t)gpio_get_level(GPIO_NUM_13),now,25)){
            if(!b.stable)bc++;
            ESP_LOGI(TAG,"BUTTON_B GPIO13 %s count=%"PRIu32,b.stable?"RELEASE":"PRESS",bc);
        }
        bool valid=touch_read(&raw);
        if(valid && base && input_step(&t,touch_candidate(base,raw,t.stable),now,35)){
            if(t.stable)tc++;
            ESP_LOGI(TAG,"TOUCH GPIO11 %s raw=%"PRIu32" base=%"PRIu32" count=%"PRIu32,t.stable?"PRESS":"RELEASE",raw,base,tc);
        }
        if((uint32_t)(now-last)>=500){
            int32_t delta=base?(int32_t)(((int64_t)raw-(int64_t)base)*1000/base):0;
            ESP_LOGI(TAG,"SAMPLE raw=%"PRIu32" base=%"PRIu32" delta_permille=%"PRId32" valid=%u A=%"PRIu32" B=%"PRIu32" TOUCH=%"PRIu32" counts=%"PRIu32",%"PRIu32",%"PRIu32" MOTOR_LOCKED=1",raw,base,delta,(unsigned)valid,a.stable,b.stable,t.stable,ac,bc,tc);
            last=now;
        }
        vTaskDelay(pdMS_TO_TICKS(5));
    }
}
