// SPDX-License-Identifier: MIT
#include "touch_button.h"
#include <esp_log.h>
static const char *TAG="LocalControls";
TouchButton::TouchButton(){
    ESP_ERROR_CHECK(micro_box_s3_motor_create(&motor_));
    micro_box_s3_inputs_config_t cfg=MICRO_BOX_S3_INPUTS_DEFAULT_CONFIG();
    cfg.callback=OnInput;
    cfg.user_data=this;
    ESP_ERROR_CHECK(micro_box_s3_inputs_create(&cfg,&inputs_));
    ESP_LOGI(TAG,"one touch GPIO11, buttons GPIO12/13; motor GPIO14 idle; no automatic actions");
}
TouchButton::~TouchButton(){
    if(inputs_)ESP_ERROR_CHECK(micro_box_s3_inputs_delete(inputs_));
    if(motor_)ESP_ERROR_CHECK(micro_box_s3_motor_delete(motor_));
}
void TouchButton::OnInput(micro_box_s3_input_t input,micro_box_s3_input_event_t event,void *arg){
    (void)arg;
    const char *name=input==MICRO_BOX_S3_INPUT_TOUCH?"touch":input==MICRO_BOX_S3_INPUT_BUTTON_A?"button_a":"button_b";
    const char *kind=event==MICRO_BOX_S3_INPUT_PRESS?"press":event==MICRO_BOX_S3_INPUT_RELEASE?"release":"long_press";
    ESP_LOGI(TAG,"%s %s",name,kind);
    // Business actions are intentionally unassigned: no reset, eye-style change or vibration.
}
