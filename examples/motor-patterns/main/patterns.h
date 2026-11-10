// SPDX-License-Identifier: MIT
#pragma once
typedef struct {unsigned duration_ms,duty;} motor_pattern_t;
static const motor_pattern_t patterns[6]={{100,100},{200,100},{400,100},{400,30},{400,60},{400,100}};
static inline int pattern_take(unsigned *mask,unsigned index){
    if(index>=6 || (*mask&(1U<<index)))return 0;
    *mask|=1U<<index;
    return 1;
}
