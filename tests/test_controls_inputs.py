"""Exercise reusable inputs' actual SDK-independent C state machines, not a model."""
import ctypes
from functools import lru_cache
from pathlib import Path
import tempfile
import unittest
import re

from test_vb6824_parser import compile_library

ROOT = Path(__file__).resolve().parents[1]
COMPONENT = ROOT / "components/micro_box_s3_controls"
PRESS, RELEASE, LONG_PRESS = 1, 2, 4


@lru_cache(maxsize=1)
def load_logic():
    header = COMPONENT / "inputs_logic.h"
    if not header.is_file():
        raise AssertionError("missing production inputs_logic.h")
    build = Path(tempfile.mkdtemp(prefix="micro_box_inputs_"))
    wrapper = build / "inputs_host.c"
    wrapper.write_text(
        '#include "' + header.as_posix() + '"\n' + r'''
#ifdef _WIN32
#define API __declspec(dllexport)
#else
#define API
#endif
static mb3_input_state_t states[3];
API void host_init(unsigned index, uint32_t now) {
    mb3_input_init(&states[index], now);
}
API unsigned host_step(unsigned index, unsigned pressed, unsigned valid,
                       uint32_t now, uint32_t debounce, uint32_t long_ms) {
    return mb3_input_step(&states[index], pressed != 0, valid != 0,
                          now, debounce, long_ms);
}
API unsigned host_pressed(unsigned index) { return states[index].pressed; }
static mb3_touch_calibration_t calibration;
API unsigned host_touch(uint32_t baseline, uint32_t raw, unsigned pressed,
                        unsigned press_percent, unsigned release_percent) {
    return mb3_touch_candidate(baseline, raw, pressed != 0,
                               press_percent, release_percent);
}
API unsigned host_raw_valid(uint32_t raw) { return mb3_touch_raw_valid(raw); }
API void host_cal_init(uint32_t now) { mb3_touch_calibration_init(&calibration, now); }
API uint32_t host_cal_step(uint32_t raw, unsigned valid, uint32_t now) {
    return mb3_touch_calibration_step(&calibration, raw, valid != 0, now);
}
''', encoding="utf-8")
    lib = compile_library(build, [wrapper], "micro_box_inputs")
    lib.host_init.argtypes = [ctypes.c_uint, ctypes.c_uint32]
    lib.host_init.restype = None
    lib.host_step.argtypes = [ctypes.c_uint] * 3 + [ctypes.c_uint32] * 3
    lib.host_step.restype = ctypes.c_uint
    lib.host_pressed.argtypes = [ctypes.c_uint]
    lib.host_pressed.restype = ctypes.c_uint
    lib.host_touch.argtypes = [ctypes.c_uint32, ctypes.c_uint32] + [ctypes.c_uint] * 3
    lib.host_touch.restype = ctypes.c_uint
    lib.host_raw_valid.argtypes = [ctypes.c_uint32]
    lib.host_raw_valid.restype = ctypes.c_uint
    lib.host_cal_init.argtypes = [ctypes.c_uint32]
    lib.host_cal_init.restype = None
    lib.host_cal_step.argtypes = [ctypes.c_uint32, ctypes.c_uint, ctypes.c_uint32]
    lib.host_cal_step.restype = ctypes.c_uint32
    return lib


class InputLogicTests(unittest.TestCase):
    def setUp(self):
        self.lib = load_logic()
        for index in range(3):
            self.lib.host_init(index, 0)

    def step(self, pressed, now, *, index=1, valid=True, debounce=25, long_ms=2000):
        return self.lib.host_step(index, pressed, valid, now, debounce, long_ms)

    def test_button_requires_full_25ms_press_and_release(self):
        self.assertEqual(self.step(True, 10), 0)
        self.assertEqual(self.step(True, 34), 0)
        self.assertEqual(self.step(True, 35), PRESS)
        self.assertEqual(self.lib.host_pressed(1), 1)
        self.assertEqual(self.step(False, 40), 0)
        self.assertEqual(self.step(False, 64), 0)
        self.assertEqual(self.step(False, 65), RELEASE)
        self.assertEqual(self.lib.host_pressed(1), 0)

    def test_long_press_is_independent_once_per_hold(self):
        for index in range(3):
            self.assertEqual(self.step(True, index * 100, index=index), 0)
            self.assertEqual(self.step(True, index * 100 + 25, index=index), PRESS)
        for index in range(3):
            self.assertEqual(self.step(True, index * 100 + 2024, index=index), 0)
            self.assertEqual(self.step(True, index * 100 + 2025, index=index), LONG_PRESS)
            self.assertEqual(self.step(True, 9000, index=index), 0)
        self.step(False, 9100)
        self.assertEqual(self.step(False, 9125), RELEASE)
        self.step(True, 9200)
        self.assertEqual(self.step(True, 9225), PRESS)
        self.assertEqual(self.step(True, 11225), LONG_PRESS)

    def test_zero_long_press_disables_long_event(self):
        self.step(True, 0, long_ms=0)
        self.assertEqual(self.step(True, 25, long_ms=0), PRESS)
        self.assertEqual(self.step(True, 100000, long_ms=0), 0)

    def test_bounce_restarts_both_edges(self):
        for pressed, now in [(True, 0), (False, 15), (True, 20), (False, 30)]:
            self.assertEqual(self.step(pressed, now), 0)
        self.step(True, 40)
        self.assertEqual(self.step(True, 64), 0)
        self.assertEqual(self.step(True, 65), PRESS)
        for pressed, now in [(False, 70), (True, 80), (False, 90)]:
            self.assertEqual(self.step(pressed, now), 0)
        self.assertEqual(self.step(False, 115), RELEASE)

    def test_invalid_sample_discards_pending_press_and_release(self):
        self.step(True, 0)
        self.assertEqual(self.step(True, 20, valid=False), 0)
        self.assertEqual(self.step(True, 100), 0)
        self.assertEqual(self.step(True, 124), 0)
        self.assertEqual(self.step(True, 125), PRESS)
        self.step(False, 130)
        self.step(False, 150, valid=False)
        self.assertEqual(self.step(False, 500), 0)
        self.assertEqual(self.step(False, 525), RELEASE)

    def test_invalid_sample_does_not_emit_or_accumulate_long_press(self):
        self.step(True, 0)
        self.assertEqual(self.step(True, 25), PRESS)
        self.assertEqual(self.step(True, 5000, valid=False), 0)
        self.assertEqual(self.lib.host_pressed(1), 1)
        self.assertEqual(self.step(True, 6000), 0)
        self.assertEqual(self.step(True, 7999), 0)
        self.assertEqual(self.step(True, 8000), LONG_PRESS)

    def test_timers_survive_uint32_wraparound(self):
        self.lib.host_init(1, 0xFFFFFFE0)
        self.assertEqual(self.step(True, 0xFFFFFFF0), 0)
        self.assertEqual(self.step(True, 8), 0)
        self.assertEqual(self.step(True, 9), PRESS)
        self.assertEqual(self.step(True, 2008), 0)
        self.assertEqual(self.step(True, 2009), LONG_PRESS)

    def test_invalid_gap_after_long_does_not_repeat_event(self):
        self.step(True, 0)
        self.step(True, 25)
        self.assertEqual(self.step(True, 2025), LONG_PRESS)
        self.assertEqual(self.step(True, 2030, valid=False), 0)
        self.assertEqual(self.step(True, 3000), 0)
        self.assertEqual(self.step(True, 6000), 0)

    def test_release_candidate_does_not_emit_spurious_long_press(self):
        self.step(True, 0)
        self.step(True, 25)
        self.assertEqual(self.step(False, 2020), 0)
        self.assertEqual(self.step(False, 2025), 0)
        self.assertEqual(self.step(False, 2045), RELEASE)


class TouchLogicTests(unittest.TestCase):
    def setUp(self):
        self.lib = load_logic()
        self.lib.host_init(0, 0)
        self.lib.host_cal_init(0)

    def touch(self, raw, pressed=False, baseline=1000, press=10, release=5):
        return self.lib.host_touch(baseline, raw, pressed, press, release)

    def test_s3_positive_delta_and_hysteresis_boundaries(self):
        self.assertEqual(self.touch(1099), 0)
        self.assertEqual(self.touch(1100), 1)
        self.assertEqual(self.touch(1070, True), 1)
        self.assertEqual(self.touch(1050, True), 1)
        self.assertEqual(self.touch(1049, True), 0)
        self.assertEqual(self.touch(900), 0)

    def test_touch_debounce_requires_35ms(self):
        step = self.lib.host_step
        self.assertEqual(step(0, self.touch(1100), True, 0, 35, 2000), 0)
        self.assertEqual(step(0, self.touch(1100), True, 34, 35, 2000), 0)
        self.assertEqual(step(0, self.touch(1100), True, 35, 35, 2000), PRESS)
        self.assertEqual(step(0, self.touch(1070, True), True, 40, 35, 2000), 0)
        self.assertEqual(step(0, self.touch(1049, True), True, 50, 35, 2000), 0)
        self.assertEqual(step(0, self.touch(1049, True), True, 85, 35, 2000), RELEASE)

    def test_configurable_thresholds_and_rounding(self):
        self.assertEqual(self.touch(1199, press=20, release=8), 0)
        self.assertEqual(self.touch(1200, press=20, release=8), 1)
        self.assertEqual(self.touch(1080, True, press=20, release=8), 1)
        self.assertEqual(self.touch(1079, True, press=20, release=8), 0)
        self.assertEqual(self.touch(111, baseline=101), 0)
        self.assertEqual(self.touch(112, baseline=101), 1)

    def test_invalid_raw_and_baseline_are_not_touch_candidates(self):
        for raw in (0, 0x1FFFFF, 0x3FFFFF, 0xFFFFFFFF):
            self.assertEqual(self.lib.host_raw_valid(raw), 0)
            self.assertEqual(self.touch(raw), 0)
        self.assertEqual(self.lib.host_raw_valid(1), 1)
        self.assertEqual(self.lib.host_raw_valid(0x1FFFFE), 1)
        self.assertEqual(self.touch(1100, baseline=0), 0)
        self.assertEqual(self.touch(1100, baseline=0xFFFFFFFF), 0)

    def test_baseline_zero_invalidates_pending_touch_timer(self):
        step = self.lib.host_step
        step(0, self.touch(1100), True, 0, 35, 2000)
        self.assertEqual(step(0, self.touch(1100, baseline=0), False, 30, 35, 2000), 0)
        self.assertEqual(step(0, self.touch(1100), True, 100, 35, 2000), 0)
        self.assertEqual(step(0, self.touch(1100), True, 134, 35, 2000), 0)
        self.assertEqual(step(0, self.touch(1100), True, 135, 35, 2000), PRESS)

    def test_calibration_ignores_first_second_and_waits_three_seconds(self):
        cal = self.lib.host_cal_step
        for now in range(0, 1000, 20):
            self.assertEqual(cal(900000, True, now), 0)
        for now in range(1000, 3000, 20):
            self.assertEqual(cal(1000, True, now), 0)
        self.assertEqual(cal(1000, True, 3000), 1000)
        self.assertEqual(cal(2000, True, 9000), 1000)

    def test_calibration_requires_50_valid_samples_and_recovers(self):
        cal = self.lib.host_cal_step
        for now in range(1000, 4000, 20):
            self.assertEqual(cal(1000, False, now), 0)
        for raw in (0, 0x1FFFFF, 0x3FFFFF, 0xFFFFFFFF):
            self.assertEqual(cal(raw, True, 4000), 0)
        for index in range(49):
            self.assertEqual(cal(1200, True, 5000 + index * 20), 0)
        self.assertEqual(cal(1200, True, 5980), 1200)

    def test_calibration_average_uses_wide_sum_and_wrap_safe_elapsed(self):
        self.lib.host_cal_init(0xFFFFFC18)
        cal = self.lib.host_cal_step
        for index in range(50):
            self.assertEqual(cal(2000000 + index * 2, True, index * 20), 0)
        self.assertEqual(cal(2000000, False, 2000), 2000049)

    def test_calibration_sum_exceeds_uint32_without_wrapping(self):
        cal = self.lib.host_cal_step
        for _ in range(3000):
            self.assertEqual(cal(2000000, True, 1000), 0)
        self.assertEqual(cal(0, False, 3000), 2000000)


@lru_cache(maxsize=1)
def load_driver():
    """Compile real public API and driver bodies; fake only GPIO/RTOS services.

    The deterministic scheduler runs the real worker on join or on request.
    It is deliberately not a claim to test FreeRTOS multicore scheduling.
    """
    source = COMPONENT / "inputs.c"
    header = COMPONENT / "include/micro_box_s3_inputs.h"
    if not source.is_file() or not header.is_file():
        raise AssertionError("missing production inputs driver/public API")
    build = Path(tempfile.mkdtemp(prefix="micro_box_inputs_driver_"))
    wrapper = build / "driver_host.c"
    prefix = r'''
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <string.h>
#ifdef _WIN32
#define API __declspec(dllexport)
#else
#define API
#endif
typedef int esp_err_t;
#define ESP_OK 0
#define ESP_FAIL -1
#define ESP_ERR_NO_MEM 0x101
#define ESP_ERR_INVALID_ARG 0x102
#define ESP_ERR_INVALID_STATE 0x103
#define MICRO_BOX_S3_TOUCH_GPIO 11
#define MICRO_BOX_S3_BUTTON_A_GPIO 12
#define MICRO_BOX_S3_BUTTON_B_GPIO 13
#define TOUCH_PAD_NUM11 11
#define TOUCH_PAD_THRESHOLD_MAX 0x1fffffU
#define TOUCH_FSM_MODE_TIMER 1
#define GPIO_MODE_INPUT 1
#define GPIO_PULLUP_ENABLE 1
#define GPIO_PULLDOWN_DISABLE 0
#define GPIO_INTR_DISABLE 0
#define ESP_LOGI(...) ((void)0)
#define ESP_LOGW(...) ((void)0)
#define ESP_LOGE(...) ((void)0)
typedef int gpio_num_t;
typedef struct { uint64_t pin_bit_mask; int mode, pull_up_en, pull_down_en, intr_type; } gpio_config_t;
typedef int portMUX_TYPE;
#define portMUX_INITIALIZER_UNLOCKED 0
static int host_locks;
#define portENTER_CRITICAL(lock) ((void)(lock), ++host_locks)
#define portEXIT_CRITICAL(lock) ((void)(lock), --host_locks)
typedef uint32_t TickType_t;
typedef int BaseType_t;
typedef void *TaskHandle_t;
typedef struct { unsigned used, given; } host_sem_t;
typedef host_sem_t *SemaphoreHandle_t;
#define pdMS_TO_TICKS(ms) ((ms) / 10U)
#define portMAX_DELAY UINT32_MAX
#define pdPASS 1
#define pdTRUE 1
static union { uint64_t align; unsigned char bytes[4096]; } allocation;
static host_sem_t semaphores[2];
static unsigned live_allocation, sem_calls, fail_sem, fail_allocation, fail_task;
static unsigned fail_hw, hw_calls, touch_live, gpio_live, touch_mask, gpio_calls;
static unsigned callback_count, callback_locks, self_delete_result;
static unsigned host_events[3][3], budget, worker_runs, forced_deletes, delay_ticks;
static unsigned callback_delete, callback_snapshot_result;
static uint32_t host_time, press_at, release_at, touch_press_at, touch_release_at;
static int64_t host_clock;
static TaskHandle_t current_task;
static void (*worker_fn)(void *);
static void *worker_arg;
static int task_tag;
static unsigned sem_live(void) { return semaphores[0].used + semaphores[1].used; }
static void *host_calloc(size_t count, size_t size) {
    if (fail_allocation || count * size > sizeof(allocation.bytes) || live_allocation) return NULL;
    memset(&allocation, 0, sizeof(allocation)); live_allocation = 1; return allocation.bytes;
}
static void host_free(void *p) { if (p == allocation.bytes) live_allocation = 0; }
#define calloc host_calloc
#define free host_free
static SemaphoreHandle_t xSemaphoreCreateBinary(void) {
    unsigned i; ++sem_calls;
    if (sem_calls == fail_sem) return NULL;
    for (i = 0; i < 2; ++i) if (!semaphores[i].used) {
        semaphores[i].used = 1; semaphores[i].given = 0; return &semaphores[i];
    }
    return NULL;
}
static BaseType_t xSemaphoreGive(SemaphoreHandle_t sem) { sem->given = 1; return pdTRUE; }
static BaseType_t xSemaphoreTake(SemaphoreHandle_t sem, TickType_t wait) {
    (void)wait;
    if (!sem->given && worker_fn) {
        current_task = &task_tag; ++worker_runs; worker_fn(worker_arg); current_task = NULL;
    }
    if (!sem->given) return 0;
    sem->given = 0; return pdTRUE;
}
static void vSemaphoreDelete(SemaphoreHandle_t sem) { sem->used = 0; }
static BaseType_t xTaskCreate(void (*fn)(void *), const char *name, uint32_t stack,
                             void *arg, unsigned priority, TaskHandle_t *out) {
    (void)name; (void)stack; (void)priority;
    if (fail_task) return 0;
    worker_fn = fn; worker_arg = arg; *out = &task_tag; return pdPASS;
}
static TaskHandle_t xTaskGetCurrentTaskHandle(void) { return current_task; }
static void vTaskDelete(TaskHandle_t task) { if (task) ++forced_deletes; }
static void vTaskDelay(TickType_t ticks);
static int64_t esp_timer_get_time(void) { return host_clock; }
static esp_err_t hardware_result(void) { return ++hw_calls == fail_hw ? ESP_FAIL : ESP_OK; }
static esp_err_t touch_pad_init(void) {
    esp_err_t result = hardware_result(); if (result == ESP_OK) touch_live = 1; return result;
}
static esp_err_t touch_pad_config(int channel) {
    touch_mask |= 1U << channel; return hardware_result();
}
static esp_err_t touch_pad_set_fsm_mode(int mode) { (void)mode; return hardware_result(); }
static esp_err_t touch_pad_fsm_start(void) { return hardware_result(); }
static esp_err_t touch_pad_fsm_stop(void) { return ESP_OK; }
static esp_err_t touch_pad_deinit(void) { touch_live = 0; return ESP_OK; }
static esp_err_t touch_pad_read_raw_data(int channel, uint32_t *raw) {
    touch_mask |= 1U << channel;
    *raw = host_time >= touch_press_at && host_time < touch_release_at ? 1200U : 1000U;
    return ESP_OK;
}
static esp_err_t gpio_config(const gpio_config_t *config) {
    ++gpio_calls; gpio_live |= (unsigned)config->pin_bit_mask;
    if (config->mode != GPIO_MODE_INPUT || config->pull_up_en != GPIO_PULLUP_ENABLE)
        return ESP_FAIL;
    return hardware_result();
}
static esp_err_t gpio_reset_pin(gpio_num_t pin) { gpio_live &= ~(1U << pin); return ESP_OK; }
static int gpio_get_level(gpio_num_t pin) {
    (void)pin; return !(host_time >= press_at && host_time < release_at);
}
'''
    suffix = r'''
static void vTaskDelay(TickType_t ticks) {
    delay_ticks = ticks; host_time += ticks * 10U; host_clock = (int64_t)host_time * 1000;
    if (budget && --budget == 0) s_instance->stop = true;
}
static void host_callback(micro_box_s3_input_t input,
                          micro_box_s3_input_event_t event, void *arg) {
    micro_box_s3_inputs_snapshot_t snapshot;
    (void)arg; ++callback_count; callback_locks += (unsigned)host_locks;
    ++host_events[input][event];
    callback_snapshot_result = (unsigned)micro_box_s3_inputs_get_snapshot(s_instance, &snapshot);
    if (callback_delete) self_delete_result = (unsigned)micro_box_s3_inputs_delete(s_instance);
}
API void host_reset_driver(void) {
    s_instance = NULL; s_busy = false; host_locks = 0;
    live_allocation = 0; sem_calls = 0; fail_sem = 0; fail_allocation = 0; fail_task = 0;
    fail_hw = 0; hw_calls = 0; touch_live = 0; gpio_live = 0; touch_mask = 0; gpio_calls = 0;
    callback_count = 0; callback_locks = 0; self_delete_result = 0;
    budget = 0; worker_runs = 0; forced_deletes = 0; delay_ticks = 0;
    callback_delete = 0; callback_snapshot_result = 0;
    host_time = 0; host_clock = 0; current_task = NULL; worker_fn = NULL; worker_arg = NULL;
    press_at = UINT32_MAX; release_at = UINT32_MAX;
    touch_press_at = UINT32_MAX; touch_release_at = UINT32_MAX;
    memset(semaphores, 0, sizeof(semaphores)); memset(host_events, 0, sizeof(host_events));
}
API void host_fail(unsigned kind, unsigned value) {
    if (kind == 0) fail_allocation = value;
    if (kind == 1) fail_sem = value;
    if (kind == 2) fail_task = value;
    if (kind == 3) fail_hw = value;
}
API int host_create(unsigned touch, unsigned buttons, unsigned press_percent,
                    unsigned release_percent) {
    micro_box_s3_inputs_config_t config = MICRO_BOX_S3_INPUTS_DEFAULT_CONFIG();
    micro_box_s3_inputs_handle_t handle = (micro_box_s3_inputs_handle_t)&task_tag;
    config.enable_touch = touch != 0; config.enable_buttons = buttons != 0;
    config.touch_press_percent = press_percent; config.touch_release_percent = release_percent;
    config.callback = host_callback;
    esp_err_t result = micro_box_s3_inputs_create(&config, &handle);
    if ((result != ESP_OK && handle != NULL) || (result == ESP_OK && handle != s_instance))
        return 0xBAD;
    return result;
}
API int host_contract(unsigned which) {
    micro_box_s3_inputs_config_t config = MICRO_BOX_S3_INPUTS_DEFAULT_CONFIG();
    micro_box_s3_inputs_snapshot_t snapshot;
    micro_box_s3_inputs_handle_t out = NULL;
    micro_box_s3_inputs_handle_t invalid = (micro_box_s3_inputs_handle_t)&task_tag;
    switch (which) {
    case 0: return micro_box_s3_inputs_create(NULL, &out);
    case 1: return micro_box_s3_inputs_create(&config, NULL);
    case 2: return micro_box_s3_inputs_delete(NULL);
    case 3: return micro_box_s3_inputs_get_snapshot(NULL, &snapshot);
    case 4: return micro_box_s3_inputs_get_snapshot(s_instance, NULL);
    case 5: return micro_box_s3_inputs_get_snapshot(invalid, &snapshot);
    case 6: return micro_box_s3_inputs_delete(invalid);
    case 7: return config.enable_touch && config.enable_buttons &&
                   config.long_press_ms == 2000U && config.callback == NULL &&
                   config.user_data == NULL && config.touch_press_percent == 10U &&
                   config.touch_release_percent == 5U;
    default: return ESP_FAIL;
    }
}
API int host_delete(void) { return micro_box_s3_inputs_delete(s_instance); }
API unsigned host_resources(void) { return live_allocation + sem_live() + touch_live + gpio_live; }
API unsigned host_stat(unsigned index) {
    switch (index) {
    case 0: return touch_mask; case 1: return gpio_calls;
    case 2: return worker_runs; case 3: return forced_deletes;
    case 4: return delay_ticks; case 5: return callback_count;
    case 6: return callback_locks; case 7: return self_delete_result;
    case 8: return callback_snapshot_result; case 9: return touch_live;
    default: return hw_calls;
    }
}
API void host_run(unsigned polls, unsigned self_delete) {
    budget = polls; callback_delete = self_delete; current_task = &task_tag;
    ++worker_runs; worker_fn(worker_arg); current_task = NULL;
}
API void host_schedule(uint32_t button_start, uint32_t button_end,
                       uint32_t touch_start, uint32_t touch_end) {
    press_at = button_start; release_at = button_end;
    touch_press_at = touch_start; touch_release_at = touch_end;
}
API unsigned host_event(unsigned input, unsigned event) { return host_events[input][event]; }
API int host_snapshot(unsigned field) {
    micro_box_s3_inputs_snapshot_t snapshot;
    esp_err_t result = micro_box_s3_inputs_get_snapshot(s_instance, &snapshot);
    if (result != ESP_OK) return result;
    switch (field) {
    case 0: return snapshot.calibrated;
    case 1: return (int)snapshot.touch_baseline;
    case 2: return snapshot.button_a_pressed;
    case 3: return snapshot.button_b_pressed;
    case 4: return snapshot.touch_pressed;
    default: return 0;
    }
}
'''
    strip_includes = lambda text: re.sub(r'^\s*#\s*include[^\n]*\n', '', text, flags=re.MULTILINE)
    api = strip_includes(header.read_text(encoding="utf-8")).replace("#pragma once", "")
    body = strip_includes(source.read_text(encoding="utf-8"))
    logic_include = '#include "' + (COMPONENT / "inputs_logic.h").as_posix() + '"\n'
    wrapper.write_text(prefix + logic_include + api + "\n" + body + suffix, encoding="utf-8")
    lib = compile_library(build, [wrapper], "micro_box_inputs_driver")
    for name, args, result in (
        ("host_reset_driver", [], None), ("host_fail", [ctypes.c_uint] * 2, None),
        ("host_create", [ctypes.c_uint] * 4, ctypes.c_int), ("host_delete", [], ctypes.c_int),
        ("host_resources", [], ctypes.c_uint), ("host_stat", [ctypes.c_uint], ctypes.c_uint),
        ("host_run", [ctypes.c_uint] * 2, None), ("host_schedule", [ctypes.c_uint32] * 4, None),
        ("host_event", [ctypes.c_uint] * 2, ctypes.c_uint), ("host_snapshot", [ctypes.c_uint], ctypes.c_int),
        ("host_contract", [ctypes.c_uint], ctypes.c_int),
    ):
        fn = getattr(lib, name); fn.argtypes = args; fn.restype = result
    return lib


class DriverHostTests(unittest.TestCase):
    def setUp(self):
        self.lib = load_driver()
        self.lib.host_reset_driver()

    def test_create_is_async_and_singleton_delete_joins_worker(self):
        self.assertEqual(self.lib.host_create(1, 1, 10, 5), 0)
        self.assertEqual(self.lib.host_stat(2), 0)
        self.assertEqual(self.lib.host_snapshot(0), 0)
        self.assertEqual(self.lib.host_create(1, 1, 10, 5), 0x103)
        self.assertEqual(self.lib.host_delete(), 0)
        self.assertEqual(self.lib.host_stat(2), 1)
        self.assertEqual(self.lib.host_stat(3), 0)
        self.assertEqual(self.lib.host_resources(), 0)
        self.assertEqual(self.lib.host_create(0, 1, 10, 5), 0)
        self.assertEqual(self.lib.host_delete(), 0)

    def test_defaults_and_null_or_nonlive_handles(self):
        self.assertEqual(self.lib.host_contract(7), 1)
        for which in range(5):
            self.assertEqual(self.lib.host_contract(which), 0x102)
        self.assertEqual(self.lib.host_contract(5), 0x103)
        self.assertEqual(self.lib.host_contract(6), 0x103)
        self.assertEqual(self.lib.host_resources(), 0)

    def test_zero_optional_thresholds_use_defaults(self):
        self.assertEqual(self.lib.host_create(1, 0, 0, 0), 0)
        self.lib.host_schedule(0xFFFFFFFF, 0xFFFFFFFF, 3100, 3200)
        self.lib.host_run(330, 0)
        self.assertEqual(self.lib.host_event(0, 0), 1)
        self.assertEqual(self.lib.host_event(0, 1), 1)
        self.assertEqual(self.lib.host_event(0, 2), 0)
        self.assertEqual(self.lib.host_delete(), 0)

    def test_disabled_subsystems_are_never_initialized(self):
        self.assertEqual(self.lib.host_create(0, 1, 10, 5), 0)
        self.assertEqual(self.lib.host_stat(0), 0)
        self.assertEqual(self.lib.host_stat(9), 0)
        self.assertEqual(self.lib.host_snapshot(0), 1)
        self.assertEqual(self.lib.host_delete(), 0)
        self.lib.host_reset_driver()
        self.assertEqual(self.lib.host_create(1, 0, 10, 5), 0)
        self.assertEqual(self.lib.host_stat(1), 0)
        self.assertEqual(self.lib.host_stat(0), 1 << 11)
        self.assertEqual(self.lib.host_delete(), 0)

    def test_rejects_empty_and_invalid_threshold_configuration(self):
        for touch, buttons, press, release in ((0, 0, 10, 5), (1, 1, 5, 10),
                                               (1, 1, 5, 5), (1, 0, 1001, 5)):
            self.assertEqual(self.lib.host_create(touch, buttons, press, release), 0x102)
            self.assertEqual(self.lib.host_resources(), 0)

    def test_allocation_semaphore_and_task_failures_release_resources(self):
        for kind, value in ((0, 1), (1, 1), (1, 2), (2, 1)):
            with self.subTest(kind=kind, value=value):
                self.lib.host_reset_driver(); self.lib.host_fail(kind, value)
                self.assertEqual(self.lib.host_create(1, 1, 10, 5), 0x101)
                self.assertEqual(self.lib.host_resources(), 0)
                self.lib.host_fail(kind, 0)
                self.assertEqual(self.lib.host_create(1, 1, 10, 5), 0)
                self.assertEqual(self.lib.host_delete(), 0)

    def test_each_hardware_failure_unwinds_and_releases_singleton(self):
        # GPIO config plus touch init/config/FSM mode/FSM start.
        for fail_at in range(1, 6):
            with self.subTest(fail_at=fail_at):
                self.lib.host_reset_driver(); self.lib.host_fail(3, fail_at)
                self.assertEqual(self.lib.host_create(1, 1, 10, 5), -1)
                self.assertEqual(self.lib.host_resources(), 0)
                self.lib.host_fail(3, 0)
                self.assertEqual(self.lib.host_create(1, 1, 10, 5), 0)
                self.assertEqual(self.lib.host_delete(), 0)

    def test_real_worker_callbacks_are_unlocked_and_self_delete_rejected(self):
        self.assertEqual(self.lib.host_create(0, 1, 10, 5), 0)
        self.lib.host_schedule(0, 2100, 0xFFFFFFFF, 0xFFFFFFFF)
        self.lib.host_run(220, 1)
        for input_index in (1, 2):
            for event in (0, 1, 2):
                self.assertEqual(self.lib.host_event(input_index, event), 1)
        self.assertEqual(self.lib.host_stat(5), 6)
        self.assertEqual(self.lib.host_stat(6), 0)
        self.assertEqual(self.lib.host_stat(7), 0x103)
        self.assertEqual(self.lib.host_stat(8), 0)
        self.assertGreaterEqual(self.lib.host_stat(4), 1)
        self.assertEqual(self.lib.host_delete(), 0)
        self.assertEqual(self.lib.host_resources(), 0)

    def test_buttons_work_during_calibration_and_only_touch_11_scanned(self):
        self.assertEqual(self.lib.host_create(1, 1, 10, 5), 0)
        self.lib.host_schedule(0, 100, 3100, 5200)
        self.lib.host_run(530, 0)
        self.assertEqual(self.lib.host_event(1, 0), 1)
        self.assertEqual(self.lib.host_event(1, 1), 1)
        for event in (0, 1, 2):
            self.assertEqual(self.lib.host_event(0, event), 1)
        self.assertEqual(self.lib.host_snapshot(0), 1)
        self.assertEqual(self.lib.host_snapshot(1), 1000)
        self.assertEqual(self.lib.host_snapshot(4), 0)
        self.assertEqual(self.lib.host_stat(0), 1 << 11)
        self.assertEqual(self.lib.host_delete(), 0)


if __name__ == "__main__":
    unittest.main()