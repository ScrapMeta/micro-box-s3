// SPDX-License-Identifier: MIT
#pragma once

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include "esp_err.h"

#ifdef __cplusplus
extern "C" {
#endif

typedef struct micro_box_s3_inputs *micro_box_s3_inputs_handle_t;

typedef enum {
    MICRO_BOX_S3_INPUT_TOUCH = 0,
    MICRO_BOX_S3_INPUT_BUTTON_A = 1,
    MICRO_BOX_S3_INPUT_BUTTON_B = 2,
} micro_box_s3_input_t;

typedef enum {
    MICRO_BOX_S3_INPUT_PRESS = 0,
    MICRO_BOX_S3_INPUT_RELEASE = 1,
    MICRO_BOX_S3_INPUT_LONG_PRESS = 2,
} micro_box_s3_input_event_t;

/** Poll-task callback; never under component locks or in an ISR.
 * Keep it nonblocking: enqueue work or log only. Do not call delete() here
 * (INVALID_STATE); request deletion from another task. get_snapshot() is allowed.
 * No short-press business action is bound by this component.
 */
typedef void (*micro_box_s3_input_callback_t)(micro_box_s3_input_t input,
                                            micro_box_s3_input_event_t event,
                                            void *user_data);

typedef struct {
    bool enable_touch;   /**< Only GPIO11 / TOUCH_PAD_NUM11. */
    bool enable_buttons; /**< GPIO12/13, internal pull-ups, pressed when LOW. */
    unsigned long_press_ms; /**< Once per debounced hold; 0 disables; <= INT32_MAX. */
    micro_box_s3_input_callback_t callback;
    void *user_data;
    /** Optional positive delta percentages. 0 selects 10/5 defaults.
     * 1 <= release < press <= 1000; ignored when touch disabled.
     * S3 raw increases on touch. +10% press/+5% release are starting values,
     * not board-independent guarantees; tune using real electrode readings.
     */
    unsigned touch_press_percent;
    unsigned touch_release_percent;
} micro_box_s3_inputs_config_t;

#define MICRO_BOX_S3_INPUTS_DEFAULT_CONFIG() { \
    .enable_touch = true, .enable_buttons = true, .long_press_ms = 2000U, \
    .callback = NULL, .user_data = NULL, \
    .touch_press_percent = 10U, .touch_release_percent = 5U \
}

typedef struct {
    bool calibrated; /**< Baseline ready; also true when touch disabled. */
    bool touch_pressed;
    bool button_a_pressed;
    bool button_b_pressed;
    uint32_t touch_raw; /**< Latest raw; 0 on SDK read error; invalid sentinel retained. */
    uint32_t touch_baseline;
    bool touch_valid; /**< Latest raw and calibrated baseline both valid. */
    uint32_t sampled_at_ms; /**< Wrapping monotonic milliseconds, not wall time. */
} micro_box_s3_inputs_snapshot_t;

/** Create asynchronous polling task; never waits for calibration or network.
 * Keep fingers OFF copper for the first 3 seconds. First second is settling;
 * average valid readings thereafter. Calibration extends beyond 3 seconds if
 * fewer than 50 valid samples arrived. Buttons work immediately.
 * Debounce: buttons 25ms, touch 35ms. Poll cadence: 5ms or at least one tick.
 * Long press starts at debounced PRESS. Invalid touch samples discard pending
 * debounce/hold timing without inventing RELEASE or repeating LONG_PRESS.
 *
 * One live instance including creation/deletion; second create -> INVALID_STATE,
 * even when only a subset is enabled. Touch requires exclusive legacy touch
 * peripheral ownership: do not mix other legacy/new touch clients with it.
 * Touch disabled: NO legacy touch calls. Buttons disabled: NO button GPIO init.
 * Both disabled -> INVALID_ARG. Config is copied. callback/user_data must remain
 * usable until delete returns. Callback may run before create returns.
 * Task context only. On failure *out is NULL and owned resources unwind.
 */
esp_err_t micro_box_s3_inputs_create(const micro_box_s3_inputs_config_t *config,
                                     micro_box_s3_inputs_handle_t *out);

/** External-task-only cooperative stop/join. Never forcibly deletes worker.
 * Waits for current callback and worker completion ACK, then frees resources.
 * A blocking callback blocks delete. Concurrent/recursive/self delete returns
 * INVALID_STATE. Snapshot reads racing deletion return INVALID_STATE; already
 * copied snapshots remain usable. Caller must serialize handle ownership:
 * never use a stale handle after deletion or race reuse in application code.
 * Handle is invalid afterward even when hardware cleanup returns an error.
 * Never call in ISR or while holding a lock needed by the callback.
 */
esp_err_t micro_box_s3_inputs_delete(micro_box_s3_inputs_handle_t handle);

/** Coherent snapshot under short critical section; allowed in callback.
 * Task context only. NULL -> INVALID_ARG; nonlive/deleting -> INVALID_STATE.
 */
esp_err_t micro_box_s3_inputs_get_snapshot(micro_box_s3_inputs_handle_t handle,
                                           micro_box_s3_inputs_snapshot_t *out);

#ifdef __cplusplus
}
#endif