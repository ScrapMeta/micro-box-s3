// SPDX-License-Identifier: MIT
#include "micro_box_s3_motor.h"
#include "micro_box_s3_motor_policy.h"
#include "micro_box_s3_pins.h"
#include "driver/gpio.h"
#include "driver/ledc.h"
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/semphr.h"
#include <stddef.h>

_Static_assert(MICRO_BOX_S3_MOTOR_MAX_MS == MICRO_BOX_S3_MOTOR_POLICY_MAX_MS,
               "board motor limit and host-tested policy must agree");

struct micro_box_s3_motor {
    SemaphoreHandle_t lock;
    SemaphoreHandle_t drained;
    esp_timer_handle_t off_timer;
    esp_timer_handle_t boost_timer;
    esp_timer_handle_t drain_timer;
    micro_box_s3_motor_policy_t policy;
    micro_box_s3_motor_policy_ops_t ops;
    esp_err_t io_error;
    bool ready;
    bool closing;
    bool timer_configured;
    bool channel_touched;
    bool detached;
};

// Static context also closes the callback-entry-before-refcount race. It is
// never freed. Its lock/semaphore are released ONLY after the dispatch barrier.
static struct micro_box_s3_motor s_motor;
static portMUX_TYPE s_claim_lock = portMUX_INITIALIZER_UNLOCKED;
static bool s_claimed;

static bool remember(struct micro_box_s3_motor *motor, esp_err_t error)
{
    if (error != ESP_OK && motor->io_error == ESP_OK) {
        motor->io_error = error;
    }
    return error == ESP_OK;
}

static esp_err_t configure_gpio_low(void)
{
    // Set the output latch BEFORE switching the matrix to ordinary GPIO.
    esp_err_t latch = gpio_set_level(MICRO_BOX_S3_MOTOR_GPIO, 0);
    const gpio_config_t config = {
        .pin_bit_mask = UINT64_C(1) << MICRO_BOX_S3_MOTOR_GPIO,
        .mode = GPIO_MODE_OUTPUT,
        .pull_up_en = GPIO_PULLUP_DISABLE,
        .pull_down_en = GPIO_PULLDOWN_DISABLE,
        .intr_type = GPIO_INTR_DISABLE,
    };
    esp_err_t configured = gpio_config(&config);
    esp_err_t low = gpio_set_level(MICRO_BOX_S3_MOTOR_GPIO, 0);
    return latch != ESP_OK ? latch : (configured != ESP_OK ? configured : low);
}

static bool output(void *context, unsigned duty)
{
    struct micro_box_s3_motor *motor = context;
    if (duty == 0) {
        esp_err_t stopped = ESP_OK;
        if (motor->channel_touched) {
            stopped = ledc_stop(LEDC_LOW_SPEED_MODE,
                               MICRO_BOX_S3_MOTOR_PWM_CHANNEL, 0);
        }
        if (stopped != ESP_OK || motor->detached) {
            // GPIO output-enable resets the matrix route in IDF 5.4.3.
            // No future pulse may reconnect a pin after this emergency detach.
            motor->detached = true;
            (void)remember(motor, stopped);
            esp_err_t low = configure_gpio_low();
            return remember(motor, low) && stopped == ESP_OK;
        }
        return true;
    }
    if (motor->detached) {
        return remember(motor, ESP_ERR_INVALID_STATE);
    }
    // Our task mutex serializes both calls and all stop/boost callbacks. Using
    // set+update avoids fade-service allocation; no fading driver may share it.
    // 2^10 is supported at 10-bit resolution on ESP32-S3 and is true 100%.
    uint32_t ticks = ((UINT32_C(1) << 10) * duty + 50u) / 100u;
    if (!remember(motor, ledc_set_duty(LEDC_LOW_SPEED_MODE,
                                     MICRO_BOX_S3_MOTOR_PWM_CHANNEL, ticks))) {
        return false;
    }
    return remember(motor, ledc_update_duty(LEDC_LOW_SPEED_MODE,
                                          MICRO_BOX_S3_MOTOR_PWM_CHANNEL));
}

static bool cancel_one(struct micro_box_s3_motor *motor, esp_timer_handle_t timer)
{
    if (!timer) {
        return true;
    }
    esp_err_t error = esp_timer_stop(timer);
    // One-shot may already have been selected for dispatch. This is NOT drain.
    return error == ESP_ERR_INVALID_STATE || remember(motor, error);
}

static bool cancel_timers(void *context)
{
    struct micro_box_s3_motor *motor = context;
    bool off = cancel_one(motor, motor->off_timer);
    bool boost = cancel_one(motor, motor->boost_timer);
    return off && boost;
}

static bool arm_off(void *context, uint64_t delay)
{
    struct micro_box_s3_motor *motor = context;
    return remember(motor, esp_timer_start_once(motor->off_timer, delay));
}

static bool arm_boost(void *context, uint64_t delay)
{
    struct micro_box_s3_motor *motor = context;
    return remember(motor, esp_timer_start_once(motor->boost_timer, delay));
}

static uint64_t now_us(void *context)
{
    (void)context;
    return (uint64_t)esp_timer_get_time();
}

static esp_err_t result(struct micro_box_s3_motor *motor, int policy_result)
{
    switch (policy_result) {
    case MICRO_BOX_S3_MOTOR_POLICY_OK: return ESP_OK;
    case MICRO_BOX_S3_MOTOR_POLICY_INVALID_ARG: return ESP_ERR_INVALID_ARG;
    case MICRO_BOX_S3_MOTOR_POLICY_INVALID_STATE: return ESP_ERR_INVALID_STATE;
    default: return motor->io_error != ESP_OK ? motor->io_error : ESP_FAIL;
    }
}

static void off_callback(void *context)
{
    struct micro_box_s3_motor *motor = context;
    xSemaphoreTake(motor->lock, portMAX_DELAY);
    if (!motor->closing) {
        motor->io_error = ESP_OK;
        (void)micro_box_s3_motor_policy_off(&motor->policy, &motor->ops,
                                          (uint64_t)esp_timer_get_time());
    }
    xSemaphoreGive(motor->lock);
}

static void boost_callback(void *context)
{
    struct micro_box_s3_motor *motor = context;
    xSemaphoreTake(motor->lock, portMAX_DELAY);
    if (!motor->closing) {
        motor->io_error = ESP_OK;
        (void)micro_box_s3_motor_policy_boost(&motor->policy, &motor->ops,
                                            (uint64_t)esp_timer_get_time());
    }
    xSemaphoreGive(motor->lock);
}

static void drain_callback(void *context)
{
    struct micro_box_s3_motor *motor = context;
    // FINAL context access. No mutex acquisition: the deleter waits unlocked.
    xSemaphoreGive(motor->drained);
}

static esp_err_t delete_timer(esp_timer_handle_t *timer)
{
    if (!*timer) {
        return ESP_OK;
    }
    esp_err_t error = esp_timer_delete(*timer);
    if (error == ESP_OK) {
        *timer = NULL;
    }
    return error;
}

static esp_err_t release_pwm(struct micro_box_s3_motor *motor)
{
    esp_err_t low = configure_gpio_low();
    motor->detached = true;
    if (low != ESP_OK) {
        return low;
    }
    if (motor->timer_configured) {
        esp_err_t error = ledc_timer_pause(LEDC_LOW_SPEED_MODE,
                                         MICRO_BOX_S3_MOTOR_PWM_TIMER);
        if (error != ESP_OK) {
            return error;
        }
        const ledc_timer_config_t config = {
            .speed_mode = LEDC_LOW_SPEED_MODE,
            .timer_num = MICRO_BOX_S3_MOTOR_PWM_TIMER,
            .deconfigure = true,
        };
        error = ledc_timer_config(&config);
        if (error != ESP_OK) {
            return error;
        }
        motor->timer_configured = false;
    }
    return ESP_OK;
}

static void unclaim(void)
{
    portENTER_CRITICAL(&s_claim_lock);
    s_claimed = false;
    portEXIT_CRITICAL(&s_claim_lock);
}

esp_err_t micro_box_s3_motor_create(micro_box_s3_motor_handle_t *out_handle)
{
    if (!out_handle) {
        return ESP_ERR_INVALID_ARG;
    }
    // Do not overwrite the existing owner handle on a failed second create.
    portENTER_CRITICAL(&s_claim_lock);
    if (s_claimed) {
        portEXIT_CRITICAL(&s_claim_lock);
        return ESP_ERR_INVALID_STATE;
    }
    s_claimed = true;
    portEXIT_CRITICAL(&s_claim_lock);
    *out_handle = NULL;
    s_motor = (struct micro_box_s3_motor){0};
    struct micro_box_s3_motor *motor = &s_motor;
    motor->ops = (micro_box_s3_motor_policy_ops_t){
        arm_off, arm_boost, cancel_timers, output, motor, now_us
    };
    micro_box_s3_motor_policy_init(&motor->policy);
    esp_err_t error = configure_gpio_low();
    if (error != ESP_OK) {
        goto fail;
    }
    motor->lock = xSemaphoreCreateMutex();
    motor->drained = xSemaphoreCreateBinary();
    if (!motor->lock || !motor->drained) {
        error = ESP_ERR_NO_MEM;
        goto fail;
    }
    const ledc_timer_config_t timer_config = {
        .speed_mode = LEDC_LOW_SPEED_MODE,
        .duty_resolution = LEDC_TIMER_10_BIT,
        .timer_num = MICRO_BOX_S3_MOTOR_PWM_TIMER,
        .freq_hz = MICRO_BOX_S3_MOTOR_PWM_HZ,
        .clk_cfg = LEDC_AUTO_CLK,
    };
    error = ledc_timer_config(&timer_config);
    if (error != ESP_OK) {
        goto fail;
    }
    motor->timer_configured = true;
    const ledc_channel_config_t channel_config = {
        .gpio_num = MICRO_BOX_S3_MOTOR_GPIO,
        .speed_mode = LEDC_LOW_SPEED_MODE,
        .channel = MICRO_BOX_S3_MOTOR_PWM_CHANNEL,
        .intr_type = LEDC_INTR_DISABLE,
        .timer_sel = MICRO_BOX_S3_MOTOR_PWM_TIMER,
        .duty = 0,
        .hpoint = 0,
    };
    motor->channel_touched = true; // rollback even a partially configured channel
    error = ledc_channel_config(&channel_config);
    if (error != ESP_OK || !output(motor, 0)) {
        if (error == ESP_OK) error = motor->io_error;
        goto fail;
    }
    const esp_timer_create_args_t off_args = {
        .callback = off_callback, .arg = motor,
        .dispatch_method = ESP_TIMER_TASK, .name = "motor_off",
    };
    const esp_timer_create_args_t boost_args = {
        .callback = boost_callback, .arg = motor,
        .dispatch_method = ESP_TIMER_TASK, .name = "motor_boost",
    };
    const esp_timer_create_args_t drain_args = {
        .callback = drain_callback, .arg = motor,
        .dispatch_method = ESP_TIMER_TASK, .name = "motor_drain",
    };
    error = esp_timer_create(&off_args, &motor->off_timer);
    if (error != ESP_OK) goto fail;
    error = esp_timer_create(&boost_args, &motor->boost_timer);
    if (error != ESP_OK) goto fail;
    error = esp_timer_create(&drain_args, &motor->drain_timer);
    if (error != ESP_OK) goto fail;
    motor->ready = true;
    *out_handle = motor;
    return ESP_OK;

fail:
    // None of these timers has ever been armed, so no callback can exist.
    // IDF 5.4.3 delete of a valid unarmed timer always queues its deletion.
    (void)output(motor, 0);
    (void)delete_timer(&motor->off_timer);
    (void)delete_timer(&motor->boost_timer);
    (void)delete_timer(&motor->drain_timer);
    (void)release_pwm(motor);
    if (motor->drained) vSemaphoreDelete(motor->drained);
    if (motor->lock) vSemaphoreDelete(motor->lock);
    motor->ready = false;
    unclaim();
    return error;
}

static bool valid(micro_box_s3_motor_handle_t handle)
{
    // Owner excludes create/delete during regular API entry (see header).
    return handle == &s_motor && s_motor.ready;
}

esp_err_t micro_box_s3_motor_pulse(micro_box_s3_motor_handle_t handle,
    unsigned duration_ms, unsigned duty_percent, unsigned boost_ms)
{
    if (!valid(handle)) return ESP_ERR_INVALID_ARG;
    xSemaphoreTake(handle->lock, portMAX_DELAY);
    handle->io_error = ESP_OK;
    esp_err_t error;
    if (handle->closing || handle->detached) {
        error = ESP_ERR_INVALID_STATE;
    } else {
        error = result(handle, micro_box_s3_motor_policy_pulse(
            &handle->policy, &handle->ops, (uint64_t)esp_timer_get_time(),
            duration_ms, duty_percent, boost_ms));
    }
    xSemaphoreGive(handle->lock);
    return error;
}

esp_err_t micro_box_s3_motor_stop(micro_box_s3_motor_handle_t handle)
{
    if (!valid(handle)) return ESP_ERR_INVALID_ARG;
    xSemaphoreTake(handle->lock, portMAX_DELAY);
    handle->io_error = ESP_OK;
    esp_err_t error = result(handle, micro_box_s3_motor_policy_stop(
        &handle->policy, &handle->ops, (uint64_t)esp_timer_get_time()));
    xSemaphoreGive(handle->lock);
    return error;
}

esp_err_t micro_box_s3_motor_get_state(micro_box_s3_motor_handle_t handle,
    micro_box_s3_motor_state_t *out_state)
{
    if (!valid(handle) || !out_state) return ESP_ERR_INVALID_ARG;
    xSemaphoreTake(handle->lock, portMAX_DELAY);
    *out_state = (micro_box_s3_motor_state_t){
        .active = handle->policy.active,
        .duty_percent = handle->policy.duty_percent,
        .duration_ms = handle->policy.duration_ms,
        .pulses_started = handle->policy.pulses_started,
        .faulted = handle->policy.faulted || handle->detached,
    };
    xSemaphoreGive(handle->lock);
    return ESP_OK;
}

esp_err_t micro_box_s3_motor_delete(micro_box_s3_motor_handle_t handle)
{
    if (!valid(handle)) return ESP_ERR_INVALID_ARG;
    xSemaphoreTake(handle->lock, portMAX_DELAY);
    handle->closing = true;
    handle->io_error = ESP_OK;
    esp_err_t error = result(handle, micro_box_s3_motor_policy_stop(
        &handle->policy, &handle->ops, (uint64_t)esp_timer_get_time()));
    if (error != ESP_OK) {
        xSemaphoreGive(handle->lock);
        return error; // Context and lock remain owned; owner may retry delete.
    }
    // IDF 5.4.3 esp_timer.c: stop removes armed timers but a callback may have
    // been copied before stop; delete merely queues EVENT_ID_DELETE_TIMER.
    // ALL our callbacks dispatch serially on ESP_TIMER_TASK. After canceling
    // both timers, a third one-shot in that SAME dispatch task is a barrier:
    // any callback selected before cancellation must return before it runs.
    // Do not hold the mutex while waiting, or an older callback could deadlock.
    (void)xSemaphoreTake(handle->drained, 0);
    error = esp_timer_start_once(handle->drain_timer, 1);
    xSemaphoreGive(handle->lock);
    if (error != ESP_OK) return error;
    xSemaphoreTake(handle->drained, portMAX_DELAY);

    // No old motor callback can now access the lock/context. Delete queues are
    // allowed to outlive this call: they do not invoke the motor callbacks.
    error = delete_timer(&handle->off_timer);
    if (error != ESP_OK) return error;
    error = delete_timer(&handle->boost_timer);
    if (error != ESP_OK) return error;
    // Keep drain_timer until last so a partially failed delete is retryable.
    error = release_pwm(handle);
    if (error != ESP_OK) return error;
    error = delete_timer(&handle->drain_timer);
    if (error != ESP_OK) return error;
    handle->ready = false;
    vSemaphoreDelete(handle->drained);
    vSemaphoreDelete(handle->lock);
    handle->drained = NULL;
    handle->lock = NULL;
    unclaim();
    return ESP_OK;
}
