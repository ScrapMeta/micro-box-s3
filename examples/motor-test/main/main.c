// SPDX-License-Identifier: MIT
#include <inttypes.h>
#include <stdint.h>
#include <stdbool.h>
#include <stdlib.h>
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "freertos/semphr.h"
#include "driver/gpio.h"
#include "driver/usb_serial_jtag.h"
#include "esp_timer.h"
#include "esp_log.h"
#include "motor_gate.h"
#define MOTOR_GPIO GPIO_NUM_14
#define PULSE_US 200000
static const char *TAG="motor-test";
static SemaphoreHandle_t gate_mutex;
static esp_timer_handle_t stop_timer;
static unsigned int used;
static bool active;
static int64_t started;
static void off_callback(void *arg){
    (void)arg;
    xSemaphoreTake(gate_mutex,portMAX_DELAY);
    ESP_ERROR_CHECK(gpio_set_level(MOTOR_GPIO,0));
    int64_t elapsed=esp_timer_get_time()-started;
    active=false;
    xSemaphoreGive(gate_mutex);
    ESP_LOGI(TAG,"MOTOR_OFF elapsed_us=%"PRId64" used=1",elapsed);
}
static void pulse_once(void){
    xSemaphoreTake(gate_mutex,portMAX_DELAY);
    if(!motor_take(&used)){
        xSemaphoreGive(gate_mutex);
        ESP_LOGW(TAG,"REJECT already used; no second pulse this boot");
        return;
    }
    esp_err_t err=esp_timer_start_once(stop_timer,PULSE_US);
    if(err!=ESP_OK){
        gpio_set_level(MOTOR_GPIO,0);
        xSemaphoreGive(gate_mutex);
        ESP_LOGE(TAG,"REJECT timer not armed; output stays OFF");
        return;
    }
    started=esp_timer_get_time();
    err=gpio_set_level(MOTOR_GPIO,1);
    active=(err==ESP_OK);
    if(err!=ESP_OK)gpio_set_level(MOTOR_GPIO,0);
    xSemaphoreGive(gate_mutex);
    if(err==ESP_OK)ESP_LOGI(TAG,"MOTOR_ON requested_us=200000 single_shot=1");
    else ESP_LOGE(TAG,"MOTOR_ON failed");
}
void app_main(void){
    ESP_ERROR_CHECK(gpio_reset_pin(MOTOR_GPIO));
    ESP_ERROR_CHECK(gpio_set_level(MOTOR_GPIO,0));
    gpio_config_t output={.pin_bit_mask=1ULL<<MOTOR_GPIO,.mode=GPIO_MODE_OUTPUT,
        .pull_up_en=GPIO_PULLUP_DISABLE,.pull_down_en=GPIO_PULLDOWN_ENABLE,.intr_type=GPIO_INTR_DISABLE};
    ESP_ERROR_CHECK(gpio_config(&output));
    ESP_ERROR_CHECK(gpio_set_level(MOTOR_GPIO,0));
    gpio_config_t inputs={.pin_bit_mask=(1ULL<<GPIO_NUM_11)|(1ULL<<GPIO_NUM_12)|(1ULL<<GPIO_NUM_13),
        .mode=GPIO_MODE_INPUT,.pull_up_en=GPIO_PULLUP_DISABLE,.pull_down_en=GPIO_PULLDOWN_DISABLE,.intr_type=GPIO_INTR_DISABLE};
    ESP_ERROR_CHECK(gpio_config(&inputs));
    gate_mutex=xSemaphoreCreateMutex();
    if(!gate_mutex)abort();
    esp_timer_create_args_t timer_args={.callback=off_callback,.name="motor_stop"};
    ESP_ERROR_CHECK(esp_timer_create(&timer_args,&stop_timer));
    usb_serial_jtag_driver_config_t usb={.tx_buffer_size=1024,.rx_buffer_size=256};
    ESP_ERROR_CHECK(usb_serial_jtag_driver_install(&usb));
    ESP_LOGI(TAG,"REV=motor-once-v1 READY GPIO14=0 commands: S=status V=one200ms X=off; no auto pulse");
    for(;;){
        uint8_t command=0;
        int n=usb_serial_jtag_read_bytes(&command,1,pdMS_TO_TICKS(50));
        if(n==1 && command=='V')pulse_once();
        else if(n==1 && command=='X'){
            xSemaphoreTake(gate_mutex,portMAX_DELAY);
            ESP_ERROR_CHECK(gpio_set_level(MOTOR_GPIO,0));
            active=false;
            xSemaphoreGive(gate_mutex);
            ESP_LOGI(TAG,"EMERGENCY_OFF");
        }else if(n==1 && command=='S'){
            xSemaphoreTake(gate_mutex,portMAX_DELAY);
            bool state=active;unsigned int count=used;
            xSemaphoreGive(gate_mutex);
            ESP_LOGI(TAG,"MOTOR_STATUS active=%u used=%u pulse_us=200000",(unsigned)state,count);
        }
        vTaskDelay(pdMS_TO_TICKS(5));
    }
}
