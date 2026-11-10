// SPDX-License-Identifier: MIT
#pragma once
#include "micro_box_s3_inputs.h"
#include "micro_box_s3_motor.h"
// Process-lifetime board adapter: events are intentionally not bound to business actions.
class TouchButton {
public:
    TouchButton();
    ~TouchButton();
    TouchButton(const TouchButton&)=delete;
    TouchButton& operator=(const TouchButton&)=delete;
private:
    static void OnInput(micro_box_s3_input_t input,micro_box_s3_input_event_t event,void *arg);
    micro_box_s3_inputs_handle_t inputs_=nullptr;
    micro_box_s3_motor_handle_t motor_=nullptr;
};
