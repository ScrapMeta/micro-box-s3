// SPDX-License-Identifier: MIT
#pragma once
static inline int motor_take(unsigned int *used){
    if(*used)return 0;
    *used=1;
    return 1;
}
