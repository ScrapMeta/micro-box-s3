// SPDX-License-Identifier: MIT
#pragma once
#include <stdint.h>
typedef struct {uint32_t stable,candidate,changed_at;} input_state_t;
static inline void input_init(input_state_t*s,uint32_t value,uint32_t now) {
    s->stable=value;s->candidate=value;s->changed_at=now;
}
static inline int input_step(input_state_t*s,uint32_t value,uint32_t now,uint32_t debounce_ms) {
    if(value!=s->candidate){s->candidate=value;s->changed_at=now;}
    if(value!=s->stable && (uint32_t)(now-s->changed_at)>=debounce_ms){s->stable=value;return 1;}
    return 0;
}
static inline uint32_t touch_candidate(uint32_t base,uint32_t raw,uint32_t pressed){
    if(!base)return 0;
    uint32_t percent=pressed?5U:10U;
    uint32_t margin=(uint32_t)(((uint64_t)base*percent+99U)/100U);
    if(margin<20U)margin=20U;
    return (uint64_t)raw>=(uint64_t)base+margin;
}