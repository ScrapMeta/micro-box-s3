// SPDX-License-Identifier: MIT
#pragma once
#include <stdbool.h>
#include <stdint.h>
#include "esp_err.h"

#ifdef __cplusplus
extern "C" {
#endif

typedef struct micro_box_s3_motor *micro_box_s3_motor_handle_t;
typedef struct {
    bool active;
    unsigned duty_percent;  // Requested steady duty; boost temporarily uses 100%.
    unsigned duration_ms;   // Requested TOTAL duration, including boost.
    uint32_t pulses_started; // Successfully started pulses; wraps modulo 2^32.
    bool faulted;           // Cleanup/output failure; do not assume pin state.
} micro_box_s3_motor_state_t;

/**
 * Singleton owner of GPIO14 and low-speed LEDC timer1/channel1, 10-bit 200 Hz.
 * create leaves output low and does not vibrate. Do not share these resources
 * with another driver; camera timer0/channel0 is not modified.
 *
 * Lifecycle contract: create/delete are OWNER-TASK operations, externally
 * serialized against ALL public calls and other create/delete calls. Before
 * delete the owner must stop/join producers so no new API call can enter.
 * pulse/stop/get_state may otherwise be called concurrently from tasks.
 * No public API may run in ISR or esp_timer callback/task context: delete
 * waits for a callback barrier in that task and would deadlock there.
 * Handles become invalid after successful delete; stale-handle reuse is not
 * detected across a later create. The singleton callback context has static
 * lifetime, and delete explicitly drains pending/running motor callbacks.
 *
 * Software limits are not hardware protection. Task scheduling delays can
 * extend the actual pulse; reset/boot/brownout pin transients are NOT covered.
 * Input electrical margins, full battery range and temperature remain untested.
 */
esp_err_t micro_box_s3_motor_create(micro_box_s3_motor_handle_t *out_handle);

/** duration 1..400 ms, duty 1..100%, boost 0..min(duration,40) ms.
 * First pulse is allowed immediately. Active/cooling/faulted requests return
 * ESP_ERR_INVALID_STATE without extending/restarting a pulse. Cooldown is
 * >=3000 ms measured from actual software stop, not the intended deadline.
 * Invalid arguments/state do not change output or state. Execution failures
 * cancel both timers and attempt PWM-low/GPIO-low rollback. If low/cancel
 * fails, faulted is latched; an emergency GPIO detach requires delete/create.
 * An esp_err_t failure cannot prove physical hardware has switched off.
 */
esp_err_t micro_box_s3_motor_pulse(micro_box_s3_motor_handle_t handle,
    unsigned duration_ms, unsigned duty_percent, unsigned boost_ms);

/** Explicit LEDC stop, idle LOW. Repeated idle stop does not extend cooldown. */
esp_err_t micro_box_s3_motor_stop(micro_box_s3_motor_handle_t handle);
esp_err_t micro_box_s3_motor_get_state(micro_box_s3_motor_handle_t handle,
    micro_box_s3_motor_state_t *out_state);

/** Stop, drain callbacks, release timers/PWM, leave GPIO14 driven low.
 * On failure the handle remains owned (possibly closing); stop/get_state and
 * delete retry are permitted, pulse is rejected. Never abandon a failed delete.
 * esp_timer_delete itself is asynchronous and is NOT used as a drain primitive.
 */
esp_err_t micro_box_s3_motor_delete(micro_box_s3_motor_handle_t handle);

#ifdef __cplusplus
}
#endif
