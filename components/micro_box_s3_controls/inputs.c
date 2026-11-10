// SPDX-License-Identifier: MIT
#include "micro_box_s3_inputs.h"
#include "micro_box_s3_pins.h"
#include "inputs_logic.h"

#include <stdlib.h>
#include "driver/gpio.h"
#include "driver/touch_pad.h"
#include "esp_log.h"
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/semphr.h"
#include "freertos/task.h"

_Static_assert(MICRO_BOX_S3_TOUCH_GPIO == 11, "This component scans only GPIO11");
_Static_assert(TOUCH_PAD_THRESHOLD_MAX == MB3_TOUCH_RAW_LIMIT, "S3 touch validity limit mismatch");

struct micro_box_s3_inputs {
    micro_box_s3_inputs_config_t config;
    micro_box_s3_inputs_snapshot_t snapshot;
    mb3_input_state_t states[3];
    mb3_touch_calibration_t calibration;
    TaskHandle_t worker;
    SemaphoreHandle_t start;
    SemaphoreHandle_t finished;
    bool stop; /* s_guard protects stop and snapshot, including API readers. */
    bool publisher_finished;
    bool worker_finished;
    bool buttons_initialized;
    bool touch_initialized;
    bool touch_started;
};

/* Static lifetime lock protects registry, snapshots and stop flags. Readers
 * validate before dereferencing: deletion cannot free an in-flight snapshot.
 * s_busy reserves the singleton throughout creation and deletion.
 */
static portMUX_TYPE s_guard = portMUX_INITIALIZER_UNLOCKED;
static micro_box_s3_inputs_handle_t s_instance;
static bool s_busy;

static uint32_t now_ms(void)
{
    return (uint32_t)(esp_timer_get_time() / 1000);
}

static bool stop_requested(micro_box_s3_inputs_handle_t handle)
{
    portENTER_CRITICAL(&s_guard);
    const bool stop = handle->stop;
    portEXIT_CRITICAL(&s_guard);
    return stop;
}

static void keep_first_error(esp_err_t *first, esp_err_t error)
{
    if (*first == ESP_OK && error != ESP_OK) {
        *first = error;
    }
}

static esp_err_t release_hardware(micro_box_s3_inputs_handle_t handle)
{
    esp_err_t result = ESP_OK;
    if (handle->touch_initialized) {
        if (handle->touch_started) {
            keep_first_error(&result, touch_pad_fsm_stop());
        }
        keep_first_error(&result, touch_pad_deinit());
        keep_first_error(&result, gpio_reset_pin((gpio_num_t)MICRO_BOX_S3_TOUCH_GPIO));
    }
    if (handle->buttons_initialized) {
        keep_first_error(&result, gpio_reset_pin((gpio_num_t)MICRO_BOX_S3_BUTTON_A_GPIO));
        keep_first_error(&result, gpio_reset_pin((gpio_num_t)MICRO_BOX_S3_BUTTON_B_GPIO));
    }
    return result;
}

static void release_storage(micro_box_s3_inputs_handle_t handle)
{
    if (handle->start != NULL) {
        vSemaphoreDelete(handle->start);
    }
    if (handle->finished != NULL) {
        vSemaphoreDelete(handle->finished);
    }
    free(handle);
}

static void poll_inputs(micro_box_s3_inputs_handle_t handle, uint32_t now)
{
    micro_box_s3_inputs_snapshot_t next = {0};
    unsigned events[3] = {0, 0, 0};
    next.calibrated = !handle->config.enable_touch;
    next.sampled_at_ms = now;
    if (handle->config.enable_touch) {
        uint32_t raw = 0;
        const esp_err_t read_result = touch_pad_read_raw_data(TOUCH_PAD_NUM11, &raw);
        if (read_result != ESP_OK) {
            raw = 0;
        }
        const bool raw_valid = read_result == ESP_OK && mb3_touch_raw_valid(raw);
        const bool was_calibrated = handle->calibration.baseline != 0;
        const uint32_t baseline = mb3_touch_calibration_step(&handle->calibration,
                                                             raw, raw_valid, now);
        next.calibrated = baseline != 0;
        next.touch_raw = raw;
        next.touch_baseline = baseline;
        next.touch_valid = raw_valid && mb3_touch_raw_valid(baseline);
        const bool pressed = mb3_touch_candidate(baseline, raw,
            handle->states[MICRO_BOX_S3_INPUT_TOUCH].pressed,
            handle->config.touch_press_percent, handle->config.touch_release_percent);
        /* Step on invalid raw/baseline too, to discard stale candidate timers. */
        events[MICRO_BOX_S3_INPUT_TOUCH] = mb3_input_step(
            &handle->states[MICRO_BOX_S3_INPUT_TOUCH], pressed, next.touch_valid,
            now, 35U, handle->config.long_press_ms);
        next.touch_pressed = handle->states[MICRO_BOX_S3_INPUT_TOUCH].pressed;
        if (!was_calibrated && next.calibrated) {
            ESP_LOGI("micro-box-inputs", "Touch baseline ready: %lu", (unsigned long)baseline);
        }
    }
    if (handle->config.enable_buttons) {
        events[MICRO_BOX_S3_INPUT_BUTTON_A] = mb3_input_step(
            &handle->states[MICRO_BOX_S3_INPUT_BUTTON_A],
            gpio_get_level((gpio_num_t)MICRO_BOX_S3_BUTTON_A_GPIO) == 0, true,
            now, 25U, handle->config.long_press_ms);
        events[MICRO_BOX_S3_INPUT_BUTTON_B] = mb3_input_step(
            &handle->states[MICRO_BOX_S3_INPUT_BUTTON_B],
            gpio_get_level((gpio_num_t)MICRO_BOX_S3_BUTTON_B_GPIO) == 0, true,
            now, 25U, handle->config.long_press_ms);
        next.button_a_pressed = handle->states[MICRO_BOX_S3_INPUT_BUTTON_A].pressed;
        next.button_b_pressed = handle->states[MICRO_BOX_S3_INPUT_BUTTON_B].pressed;
    }
    portENTER_CRITICAL(&s_guard);
    handle->snapshot = next;
    portEXIT_CRITICAL(&s_guard);

    /* User code is outside all component locks and only on this worker task. */
    if (handle->config.callback != NULL) {
        for (unsigned i = 0; i < 3U; ++i) {
            if (stop_requested(handle)) {
                break;
            }
            if (events[i] != 0U) {
                const micro_box_s3_input_event_t event = events[i] == MB3_INPUT_PRESS
                    ? MICRO_BOX_S3_INPUT_PRESS : events[i] == MB3_INPUT_RELEASE
                    ? MICRO_BOX_S3_INPUT_RELEASE : MICRO_BOX_S3_INPUT_LONG_PRESS;
                handle->config.callback((micro_box_s3_input_t)i, event,
                                         handle->config.user_data);
            }
        }
    }
}

static void input_worker(void *arg)
{
    micro_box_s3_inputs_handle_t handle = arg;
    /* create publishes registry/output before allowing any callback. */
    xSemaphoreTake(handle->start, portMAX_DELAY);
    const uint32_t started = now_ms();
    mb3_touch_calibration_init(&handle->calibration, started);
    for (unsigned i = 0; i < 3U; ++i) {
        mb3_input_init(&handle->states[i], started);
    }
    TickType_t delay = pdMS_TO_TICKS(5U);
    if (delay < 1U) {
        delay = 1U;
    }
    while (!stop_requested(handle)) {
        poll_inputs(handle, now_ms());
        vTaskDelay(delay);
    }
    /* The waiter can wake before xSemaphoreGive returns on another core.
     * Publish the final ACK only after give returns; no handle use after unlock.
     * Only this worker self-deletes; the deleter never interrupts user code.
     */
    SemaphoreHandle_t finished = handle->finished;
    xSemaphoreGive(finished);
    portENTER_CRITICAL(&s_guard);
    handle->worker_finished = true;
    portEXIT_CRITICAL(&s_guard);
    vTaskDelete(NULL);
}

esp_err_t micro_box_s3_inputs_create(const micro_box_s3_inputs_config_t *config,
                                     micro_box_s3_inputs_handle_t *out)
{
    if (out == NULL) {
        return ESP_ERR_INVALID_ARG;
    }
    *out = NULL;
    if (config == NULL || (!config->enable_touch && !config->enable_buttons) ||
        config->long_press_ms > INT32_MAX) {
        return ESP_ERR_INVALID_ARG;
    }
    const unsigned press_percent = config->touch_press_percent != 0U
        ? config->touch_press_percent : 10U;
    const unsigned release_percent = config->touch_release_percent != 0U
        ? config->touch_release_percent : 5U;
    if (config->enable_touch &&
        (release_percent >= press_percent || press_percent > 1000U)) {
        return ESP_ERR_INVALID_ARG;
    }
    portENTER_CRITICAL(&s_guard);
    if (s_busy || s_instance != NULL) {
        portEXIT_CRITICAL(&s_guard);
        return ESP_ERR_INVALID_STATE;
    }
    s_busy = true;
    portEXIT_CRITICAL(&s_guard);

    esp_err_t result = ESP_ERR_NO_MEM;
    micro_box_s3_inputs_handle_t handle = calloc(1, sizeof(*handle));
    if (handle == NULL) {
        goto fail;
    }
    handle->config = *config;
    handle->config.touch_press_percent = press_percent;
    handle->config.touch_release_percent = release_percent;
    handle->snapshot.calibrated = !config->enable_touch;
    handle->start = xSemaphoreCreateBinary();
    handle->finished = xSemaphoreCreateBinary();
    if (handle->start == NULL || handle->finished == NULL) {
        goto fail;
    }
    if (config->enable_buttons) {
        const gpio_config_t buttons = {
            .pin_bit_mask = (UINT64_C(1) << MICRO_BOX_S3_BUTTON_A_GPIO) |
                            (UINT64_C(1) << MICRO_BOX_S3_BUTTON_B_GPIO),
            .mode = GPIO_MODE_INPUT,
            .pull_up_en = GPIO_PULLUP_ENABLE,
            .pull_down_en = GPIO_PULLDOWN_DISABLE,
            .intr_type = GPIO_INTR_DISABLE,
        };
        /* gpio_config may fail after changing one pin; reset both on unwind. */
        handle->buttons_initialized = true;
        result = gpio_config(&buttons);
        if (result != ESP_OK) {
            goto fail;
        }
    }
    if (config->enable_touch) {
        result = touch_pad_init();
        if (result != ESP_OK) {
            goto fail;
        }
        handle->touch_initialized = true;
        result = touch_pad_config(TOUCH_PAD_NUM11);
        if (result != ESP_OK) {
            goto fail;
        }
        result = touch_pad_set_fsm_mode(TOUCH_FSM_MODE_TIMER);
        if (result != ESP_OK) {
            goto fail;
        }
        handle->touch_started = true;
        result = touch_pad_fsm_start();
        if (result != ESP_OK) {
            goto fail;
        }
        ESP_LOGW("micro-box-inputs", "Calibrating: keep fingers OFF electrode for 3 seconds");
    }
    result = ESP_ERR_NO_MEM;
    if (xTaskCreate(input_worker, "mb3_inputs", 4096U, handle, 5U,
                    &handle->worker) != pdPASS) {
        goto fail;
    }
    portENTER_CRITICAL(&s_guard);
    s_instance = handle;
    s_busy = false;
    *out = handle;
    portEXIT_CRITICAL(&s_guard);
    xSemaphoreGive(handle->start);
    /* A different task may already be deleting. Keep storage alive until this
     * publisher has also returned from give, then make our last handle access.
     */
    portENTER_CRITICAL(&s_guard);
    handle->publisher_finished = true;
    portEXIT_CRITICAL(&s_guard);
    return ESP_OK;

fail:
    if (handle != NULL) {
        (void)release_hardware(handle);
        release_storage(handle);
    }
    portENTER_CRITICAL(&s_guard);
    s_busy = false;
    portEXIT_CRITICAL(&s_guard);
    return result;
}

esp_err_t micro_box_s3_inputs_delete(micro_box_s3_inputs_handle_t handle)
{
    if (handle == NULL) {
        return ESP_ERR_INVALID_ARG;
    }
    const TaskHandle_t caller = xTaskGetCurrentTaskHandle();
    portENTER_CRITICAL(&s_guard);
    if (s_busy || s_instance != handle || handle->worker == caller) {
        portEXIT_CRITICAL(&s_guard);
        return ESP_ERR_INVALID_STATE;
    }
    s_busy = true;
    handle->stop = true;
    portEXIT_CRITICAL(&s_guard);

    xSemaphoreTake(handle->finished, portMAX_DELAY);
    for (;;) {
        portENTER_CRITICAL(&s_guard);
        const bool joined = handle->worker_finished && handle->publisher_finished;
        portEXIT_CRITICAL(&s_guard);
        if (joined) {
            break;
        }
        vTaskDelay(1U);
    }
    const esp_err_t result = release_hardware(handle);
    release_storage(handle);
    portENTER_CRITICAL(&s_guard);
    s_instance = NULL;
    s_busy = false;
    portEXIT_CRITICAL(&s_guard);
    return result;
}

esp_err_t micro_box_s3_inputs_get_snapshot(micro_box_s3_inputs_handle_t handle,
                                           micro_box_s3_inputs_snapshot_t *out)
{
    if (handle == NULL || out == NULL) {
        return ESP_ERR_INVALID_ARG;
    }
    portENTER_CRITICAL(&s_guard);
    if (s_busy || s_instance != handle) {
        portEXIT_CRITICAL(&s_guard);
        return ESP_ERR_INVALID_STATE;
    }
    *out = handle->snapshot;
    portEXIT_CRITICAL(&s_guard);
    return ESP_OK;
}