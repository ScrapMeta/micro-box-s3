// SPDX-License-Identifier: MIT
#include <inttypes.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdlib.h>
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "freertos/semphr.h"
#include "driver/gpio.h"
#include "driver/ledc.h"
#include "driver/usb_serial_jtag.h"
#include "esp_log.h"
#include "esp_timer.h"
#include "patterns.h"
#define MOTOR_GPIO GPIO_NUM_14
#define MODE LEDC_LOW_SPEED_MODE
#define CHANNEL LEDC_CHANNEL_1
#define TIMER LEDC_TIMER_1
#define COOLDOWN_US 3000000
#define BOOST_US 40000
static const char *TAG="motor-patterns";
static SemaphoreHandle_t mutex;
static esp_timer_handle_t stop_timer,boost_timer;
static unsigned used_mask,current_case;
static bool active;
static int64_t started,deadline,last_off;
static esp_err_t set_percent(unsigned percent){
    esp_err_t e=ledc_set_duty(MODE,CHANNEL,percent*1024U/100U);
    if(e==ESP_OK)e=ledc_update_duty(MODE,CHANNEL);
    return e;
}
static void stop_locked(const char *reason){
    ESP_ERROR_CHECK(ledc_stop(MODE,CHANNEL,0));
    if(!active)return;
    int64_t elapsed=esp_timer_get_time()-started;
    active=false;last_off=esp_timer_get_time();
    esp_timer_stop(boost_timer);
    ESP_LOGI(TAG,"MOTOR_OFF case=%u elapsed_us=%"PRId64" reason=%s",current_case+1,elapsed,reason);
}
static void stop_callback(void *arg){
    (void)arg;xSemaphoreTake(mutex,portMAX_DELAY);
    stop_locked("timer");xSemaphoreGive(mutex);
}
static void boost_callback(void *arg){
    (void)arg;xSemaphoreTake(mutex,portMAX_DELAY);
    if(active){
        if(esp_timer_get_time()>=deadline)stop_locked("deadline");
        else{
            esp_err_t e=set_percent(patterns[current_case].duty);
            if(e!=ESP_OK)stop_locked("pwm_error");
            else ESP_LOGI(TAG,"PWM_STAGE case=%u duty_percent=%u",current_case+1,patterns[current_case].duty);
        }
    }
    xSemaphoreGive(mutex);
}
static void pulse(unsigned index){
    xSemaphoreTake(mutex,portMAX_DELAY);
    if(active || esp_timer_get_time()-last_off<COOLDOWN_US){
        xSemaphoreGive(mutex);ESP_LOGW(TAG,"REJECT busy_or_cooldown");return;
    }
    if(!pattern_take(&used_mask,index)){
        xSemaphoreGive(mutex);ESP_LOGW(TAG,"REJECT invalid_or_used_case");return;
    }
    current_case=index;
    esp_err_t e=esp_timer_start_once(stop_timer,patterns[index].duration_ms*1000ULL);
    if(e!=ESP_OK){ledc_stop(MODE,CHANNEL,0);xSemaphoreGive(mutex);ESP_LOGE(TAG,"REJECT stop_timer_failed");return;}
    started=esp_timer_get_time();deadline=started+patterns[index].duration_ms*1000ULL;active=true;
    e=set_percent(100);
    if(e==ESP_OK && patterns[index].duty<100)e=esp_timer_start_once(boost_timer,BOOST_US);
    if(e!=ESP_OK){stop_locked("start_error");esp_timer_stop(stop_timer);}
    else ESP_LOGI(TAG,"MOTOR_ON case=%u duration_ms=%u duty_percent=%u boost_ms=%u pwm_hz=200",index+1,patterns[index].duration_ms,patterns[index].duty,patterns[index].duty<100?40U:0U);
    xSemaphoreGive(mutex);
}
void app_main(void){
    ESP_ERROR_CHECK(gpio_reset_pin(MOTOR_GPIO));
    ESP_ERROR_CHECK(gpio_set_level(MOTOR_GPIO,0));
    gpio_config_t cfg={.pin_bit_mask=1ULL<<MOTOR_GPIO,.mode=GPIO_MODE_OUTPUT,.pull_up_en=GPIO_PULLUP_DISABLE,.pull_down_en=GPIO_PULLDOWN_ENABLE,.intr_type=GPIO_INTR_DISABLE};
    ESP_ERROR_CHECK(gpio_config(&cfg));ESP_ERROR_CHECK(gpio_set_level(MOTOR_GPIO,0));
    mutex=xSemaphoreCreateMutex();if(!mutex)abort();
    ledc_timer_config_t timer={.speed_mode=MODE,.duty_resolution=LEDC_TIMER_10_BIT,.timer_num=TIMER,.freq_hz=200,.clk_cfg=LEDC_AUTO_CLK};
    ESP_ERROR_CHECK(ledc_timer_config(&timer));
    ledc_channel_config_t channel={.gpio_num=MOTOR_GPIO,.speed_mode=MODE,.channel=CHANNEL,.intr_type=LEDC_INTR_DISABLE,.timer_sel=TIMER,.duty=0,.hpoint=0};
    ESP_ERROR_CHECK(ledc_channel_config(&channel));ESP_ERROR_CHECK(ledc_stop(MODE,CHANNEL,0));
    esp_timer_create_args_t stop_args={.callback=stop_callback,.name="motor_stop"};
    esp_timer_create_args_t boost_args={.callback=boost_callback,.name="motor_stage"};
    ESP_ERROR_CHECK(esp_timer_create(&stop_args,&stop_timer));ESP_ERROR_CHECK(esp_timer_create(&boost_args,&boost_timer));
    usb_serial_jtag_driver_config_t usb={.tx_buffer_size=1024,.rx_buffer_size=256};ESP_ERROR_CHECK(usb_serial_jtag_driver_install(&usb));
    ESP_LOGI(TAG,"REV=motor-patterns-v1 READY no_auto_pulse max400ms cases_once cooldown3s");
    for(;;){
        uint8_t command=0;int n=usb_serial_jtag_read_bytes(&command,1,pdMS_TO_TICKS(50));
        if(n==1 && command>='1' && command<='6')pulse(command-'1');
        else if(n==1 && command=='X'){
            xSemaphoreTake(mutex,portMAX_DELAY);stop_locked("host_off");esp_timer_stop(stop_timer);xSemaphoreGive(mutex);
            ESP_LOGI(TAG,"EMERGENCY_OFF");
        }else if(n==1 && command=='S'){
            xSemaphoreTake(mutex,portMAX_DELAY);ESP_LOGI(TAG,"STATUS active=%u mask=%u",(unsigned)active,used_mask);xSemaphoreGive(mutex);
        }
        vTaskDelay(pdMS_TO_TICKS(5));
    }
}
