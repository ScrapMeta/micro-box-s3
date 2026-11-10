// SPDX-License-Identifier: MIT
#pragma once

/* SDK-independent logic shared verbatim by firmware and host C tests. */
#include <stdbool.h>
#include <stdint.h>

#define MB3_INPUT_PRESS 1U
#define MB3_INPUT_RELEASE 2U
#define MB3_INPUT_LONG_PRESS 4U

/* Conservative usable ceiling matches S3 legacy TOUCH_PAD_THRESHOLD_MAX.
 * Also rejects the wider hardware all-ones/not-ready raw value.
 */
#define MB3_TOUCH_RAW_LIMIT UINT32_C(0x1fffff)
#define MB3_TOUCH_WARMUP_MS 1000U
#define MB3_TOUCH_CALIBRATION_MS 3000U
#define MB3_TOUCH_MIN_SAMPLES 50U

static inline bool mb3_touch_raw_valid(uint32_t raw)
{
    return raw > 0 && raw < MB3_TOUCH_RAW_LIMIT;
}

static inline bool mb3_touch_candidate(uint32_t baseline, uint32_t raw,
                                       bool pressed, unsigned press_percent,
                                       unsigned release_percent)
{
    if (!mb3_touch_raw_valid(baseline) || !mb3_touch_raw_valid(raw)) {
        return false;
    }
    const unsigned percent = pressed ? release_percent : press_percent;
    const uint64_t margin = ((uint64_t)baseline * percent + 99U) / 100U;
    return (uint64_t)raw >= (uint64_t)baseline + margin;
}

typedef struct {
    uint64_t sum;
    uint32_t count;
    uint32_t started_at;
    uint32_t baseline;
} mb3_touch_calibration_t;

static inline void mb3_touch_calibration_init(mb3_touch_calibration_t *state,
                                              uint32_t now)
{
    const mb3_touch_calibration_t initial = {0, 0, 0, 0};
    *state = initial;
    state->started_at = now;
}

static inline uint32_t mb3_touch_calibration_step(mb3_touch_calibration_t *state,
                                                 uint32_t raw, bool valid,
                                                 uint32_t now)
{
    if (state->baseline != 0) {
        return state->baseline;
    }
    const uint32_t elapsed = (uint32_t)(now - state->started_at);
    if (elapsed < MB3_TOUCH_WARMUP_MS) {
        return 0;
    }
    if (valid && mb3_touch_raw_valid(raw) && state->count != UINT32_MAX) {
        state->sum += raw;
        state->count++;
    }
    /* Insufficient valid samples extend calibration, without blocking buttons. */
    if (elapsed >= MB3_TOUCH_CALIBRATION_MS && state->count >= MB3_TOUCH_MIN_SAMPLES) {
        state->baseline = (uint32_t)(state->sum / state->count);
    }
    return state->baseline;
}

typedef struct {
    bool pressed;
    bool candidate;
    bool candidate_valid;
    bool long_sent;
    bool long_tracking;
    uint32_t changed_at;
    uint32_t pressed_at;
} mb3_input_state_t;

static inline void mb3_input_init(mb3_input_state_t *state, uint32_t now)
{
    const mb3_input_state_t initial = {false, false, false, false, false, 0, 0};
    *state = initial;
    state->changed_at = now;
}

static inline unsigned mb3_input_step(mb3_input_state_t *state,
                                     bool pressed, bool valid, uint32_t now,
                                     uint32_t debounce_ms, uint32_t long_ms)
{
    if (!valid) {
        state->candidate_valid = false;
        state->long_tracking = false;
        return 0;
    }
    if (!state->candidate_valid || pressed != state->candidate) {
        state->candidate = pressed;
        state->candidate_valid = true;
        state->changed_at = now;
    }
    if (pressed != state->pressed &&
        (uint32_t)(now - state->changed_at) >= debounce_ms) {
        state->pressed = pressed;
        state->long_sent = false;
        state->long_tracking = pressed;
        state->pressed_at = now;
        return pressed ? MB3_INPUT_PRESS : MB3_INPUT_RELEASE;
    }
    if (state->pressed && pressed && !state->long_tracking) {
        state->long_tracking = true;
        state->pressed_at = now;
    }
    /* A release candidate suppresses LONG_PRESS before release debounce finishes. */
    if (state->pressed && pressed && !state->long_sent && long_ms != 0 &&
        (uint32_t)(now - state->pressed_at) >= long_ms) {
        state->long_sent = true;
        return MB3_INPUT_LONG_PRESS;
    }
    return 0;
}