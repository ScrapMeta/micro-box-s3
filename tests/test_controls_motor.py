"""Real host C policy tests plus adapter tests with deterministic SDK fakes.

The fakes model dispatch ordering and failure-after-side-effect, not real RTOS
parallel execution, electrical output, thermal safety, or ESP32 timing jitter.
"""
import ctypes
from functools import lru_cache
import re
from pathlib import Path
import tempfile
import unittest

from test_vb6824_parser import compile_library

ROOT = Path(__file__).resolve().parents[1]
COMPONENT = ROOT / "components" / "micro_box_s3_controls"


@lru_cache(maxsize=1)
def load_motor():
    source = COMPONENT / "micro_box_s3_motor_policy.c"
    if not source.is_file():
        raise AssertionError("missing bounded motor policy implementation")
    scratch = ROOT / ".build" / "host"
    scratch.mkdir(parents=True, exist_ok=True)
    build = Path(tempfile.mkdtemp(prefix="motor_policy_", dir=scratch))
    wrapper = build / "motor_host.c"
    wrapper.write_text(r'''
#include "''' + (COMPONENT / "micro_box_s3_motor_policy.h").as_posix() + r'''"
#ifdef _MSC_VER
#define API __declspec(dllexport)
#else
#define API __attribute__((visibility("default")))
#endif
static micro_box_s3_motor_policy_t policy;
static unsigned fail_mask, output, events[128], used;
static uint64_t off_delay, boost_delay;
static uint64_t io_clock, stop_latency;
static void record(unsigned event) { if (used < 128u) events[used++] = event; }
static bool arm_off(void *ctx, uint64_t us)
{ (void)ctx; record(1u); off_delay = us; return !(fail_mask & 1u); }
static bool arm_boost(void *ctx, uint64_t us)
{ (void)ctx; record(2u); boost_delay = us; return !(fail_mask & 2u); }
static bool cancel(void *ctx)
{ (void)ctx; record(3u); return !(fail_mask & 16u); }
static bool set_output(void *ctx, unsigned duty)
{
    (void)ctx; record(1000u + duty);
    /* Model a driver failing AFTER changing the pin, not just before. */
    output = duty;
    if (!duty) io_clock += stop_latency;
    return !(fail_mask & (duty ? 4u : 8u));
}
static uint64_t now_us(void *ctx) { (void)ctx; return io_clock; }
static const micro_box_s3_motor_policy_ops_t ops = {
    arm_off, arm_boost, cancel, set_output, 0, now_us
};
API void host_reset(void)
{
    micro_box_s3_motor_policy_init(&policy);
    fail_mask = output = used = 0; off_delay = boost_delay = 0;
    io_clock = stop_latency = 0;
}
API unsigned host_active(void) { return policy.active ? 1u : 0u; }
API unsigned host_count(void) { return policy.pulses_started; }
API unsigned host_output(void) { return output; }
API unsigned host_faulted(void) { return policy.faulted ? 1u : 0u; }
API unsigned host_events(void) { return used; }
API unsigned host_event(unsigned index) { return events[index]; }
API uint64_t host_off_delay(void) { return off_delay; }
API uint64_t host_boost_delay(void) { return boost_delay; }
API void host_fail(unsigned mask) { fail_mask = mask; }
API void host_stop_latency(uint64_t latency) { stop_latency = latency; }
API int host_pulse(uint64_t now, unsigned ms, unsigned duty, unsigned boost)
{ io_clock = now; return micro_box_s3_motor_policy_pulse(&policy, &ops, now, ms, duty, boost); }
API int host_stop(uint64_t now)
{ io_clock = now; return micro_box_s3_motor_policy_stop(&policy, &ops, now); }
API int host_off(uint64_t now)
{ io_clock = now; return micro_box_s3_motor_policy_off(&policy, &ops, now); }
API int host_boost(uint64_t now)
{ io_clock = now; return micro_box_s3_motor_policy_boost(&policy, &ops, now); }
''', encoding="utf-8")
    library = compile_library(build, [source, wrapper], "motor_policy")
    library.host_reset.argtypes = []
    library.host_reset.restype = None
    for name in ("active", "count", "output", "faulted", "events"):
        function = getattr(library, "host_" + name)
        function.argtypes = []
        function.restype = ctypes.c_uint
    library.host_event.argtypes = [ctypes.c_uint]
    library.host_event.restype = ctypes.c_uint
    library.host_fail.argtypes = [ctypes.c_uint]
    library.host_fail.restype = None
    library.host_pulse.argtypes = [ctypes.c_uint64] + [ctypes.c_uint] * 3
    library.host_stop_latency.argtypes = [ctypes.c_uint64]
    library.host_stop_latency.restype = None
    library.host_pulse.restype = ctypes.c_int
    for name in ("stop", "off", "boost"):
        function = getattr(library, "host_" + name)
        function.argtypes = [ctypes.c_uint64]
        function.restype = ctypes.c_int
    for name in ("off_delay", "boost_delay"):
        function = getattr(library, "host_" + name)
        function.argtypes = []
        function.restype = ctypes.c_uint64
    return library


class MotorPolicyTests(unittest.TestCase):
    def setUp(self):
        self.motor = load_motor()
        self.motor.host_reset()

    def test_created_policy_is_idle_and_has_no_pulses(self):
        self.assertEqual(self.motor.host_active(), 0)
        self.assertEqual(self.motor.host_count(), 0)
    def test_full_power_pulse_arms_cutoff_before_output_and_stops(self):
        self.assertEqual(self.motor.host_pulse(0, 400, 100, 0), 0)
        self.assertEqual(self.motor.host_active(), 1)
        self.assertEqual(self.motor.host_output(), 100)
        self.assertEqual(self.motor.host_count(), 1)
        self.assertEqual(self.motor.host_off_delay(), 400000)
        self.assertEqual([self.motor.host_event(i) for i in range(2)], [1, 1100])
        self.assertEqual(self.motor.host_off(400000), 0)
        self.assertEqual(self.motor.host_active(), 0)
        self.assertEqual(self.motor.host_output(), 0)
    def test_admission_rejects_invalid_busy_and_cooldown_without_mutation(self):
        for ms, duty, boost in ((0, 100, 0), (401, 100, 0), (100, 0, 0),
                                (100, 101, 0), (20, 30, 21), (400, 30, 41),
                                (0xFFFFFFFF, 30, 0), (400, 0xFFFFFFFF, 0)):
            with self.subTest(ms=ms, duty=duty, boost=boost):
                self.assertEqual(self.motor.host_pulse(0, ms, duty, boost), 1)
                self.assertEqual(self.motor.host_events(), 0)
                self.assertEqual(self.motor.host_count(), 0)
        self.assertEqual(self.motor.host_stop(0), 0)  # idle stop must not cool
        self.assertEqual(self.motor.host_pulse(0, 100, 100, 0), 0)
        events = self.motor.host_events()
        self.assertEqual(self.motor.host_pulse(50000, 400, 100, 0), 2)
        self.assertEqual(self.motor.host_pulse(50000, 401, 100, 0), 1)
        self.assertEqual(self.motor.host_events(), events)
        self.assertEqual(self.motor.host_output(), 100)
        self.assertEqual(self.motor.host_stop(60000), 0)
        self.assertEqual(self.motor.host_stop(90000), 0)
        self.assertEqual(self.motor.host_pulse(3059999, 1, 1, 0), 2)
        self.assertEqual(self.motor.host_pulse(3060000, 1, 1, 0), 0)
        self.assertEqual(self.motor.host_count(), 2)
    def test_boost_transition_and_late_callbacks_never_revive_stopped_output(self):
        self.assertEqual(self.motor.host_pulse(0, 400, 30, 40), 0)
        self.assertEqual(self.motor.host_output(), 100)
        self.assertEqual(self.motor.host_boost_delay(), 40000)
        self.assertEqual(self.motor.host_boost(39999), 0)
        self.assertEqual(self.motor.host_output(), 100)
        self.assertEqual(self.motor.host_boost(40000), 0)
        self.assertEqual(self.motor.host_output(), 30)
        self.assertEqual(self.motor.host_boost(50000), 0)
        self.assertEqual(self.motor.host_stop(60000), 0)
        self.assertEqual(self.motor.host_boost(70000), 0)
        self.assertEqual(self.motor.host_output(), 0)
        self.assertEqual(self.motor.host_pulse(3060000, 400, 60, 40), 0)
        self.assertEqual(self.motor.host_off(3060000), 0)  # stale old cutoff
        self.assertEqual(self.motor.host_boost(3060000), 0)  # stale old boost
        self.assertEqual(self.motor.host_output(), 100)
        self.assertEqual(self.motor.host_boost(3460000), 0)  # very late boost
        self.assertEqual(self.motor.host_output(), 0)  # cutoff wins
        self.assertEqual(self.motor.host_active(), 0)
    def test_io_failures_roll_back_timers_and_output_and_fault_latch(self):
        for mask in (1, 2, 4, 1 | 8, 2 | 16):
            with self.subTest(mask=mask):
                self.motor.host_reset()
                self.motor.host_fail(mask)
                self.assertEqual(self.motor.host_pulse(0, 400, 30, 40), 3)
                self.assertEqual(self.motor.host_active(), 0)
                self.assertEqual(self.motor.host_output(), 0)
                self.assertEqual(self.motor.host_count(), 0)
                events = [self.motor.host_event(i)
                          for i in range(self.motor.host_events())]
                self.assertEqual(events[-2:], [3, 1000])
                if mask & 3:
                    self.assertNotIn(1100, events)
                self.motor.host_fail(0)
                if mask & (8 | 16):
                    self.assertEqual(self.motor.host_faulted(), 1)
                    self.assertEqual(self.motor.host_pulse(4000000, 100, 100, 0), 2)
                self.assertEqual(self.motor.host_stop(500000), 0)
                self.assertEqual(self.motor.host_faulted(), 0)
                end = 3500000 if mask & (8 | 16) else 3000000
                self.assertEqual(self.motor.host_pulse(end - 1, 100, 100, 0), 2)
                self.assertEqual(self.motor.host_pulse(end, 100, 100, 0), 0)
        self.motor.host_reset()
        self.assertEqual(self.motor.host_pulse(0, 400, 30, 40), 0)
        self.motor.host_fail(4)
        self.assertEqual(self.motor.host_boost(40000), 3)
        self.assertEqual(self.motor.host_output(), 0)
        self.assertEqual(self.motor.host_active(), 0)
        self.motor.host_fail(8)
        self.assertEqual(self.motor.host_stop(50000), 3)
        self.assertEqual(self.motor.host_faulted(), 1)
    def test_cooldown_begins_after_slow_stop_not_before_io(self):
        self.assertEqual(self.motor.host_pulse(0, 400, 100, 0), 0)
        self.motor.host_stop_latency(500000)
        self.assertEqual(self.motor.host_stop(100000), 0)
        self.assertEqual(self.motor.host_pulse(3599999, 100, 100, 0), 2)
        self.assertEqual(self.motor.host_pulse(3600000, 100, 100, 0), 0)

    def test_fault_recovery_restarts_cooldown_from_confirmed_stop(self):
        self.assertEqual(self.motor.host_pulse(0, 400, 100, 0), 0)
        self.motor.host_fail(8)
        self.assertEqual(self.motor.host_stop(100000), 3)
        self.motor.host_fail(0)
        self.assertEqual(self.motor.host_stop(2000000), 0)
        self.assertEqual(self.motor.host_pulse(4999999, 100, 100, 0), 2)
        self.assertEqual(self.motor.host_pulse(5000000, 100, 100, 0), 0)


@lru_cache(maxsize=1)
def load_driver():
    """Real adapter C with deterministic SDK service fakes (not hardware tests)."""
    source = COMPONENT / "micro_box_s3_motor.c"
    header = COMPONENT / "include" / "micro_box_s3_motor.h"
    if not source.is_file() or not header.is_file():
        raise AssertionError("missing reusable motor driver implementation")
    build_root = ROOT / ".build" / "host"
    build_root.mkdir(parents=True, exist_ok=True)
    build = Path(tempfile.mkdtemp(prefix="motor_driver_", dir=build_root))
    prefix = r'''
#include <stdbool.h>
#include <stdint.h>
#include <stddef.h>
#ifdef _MSC_VER
#define API __declspec(dllexport)
#pragma warning(disable: 4505)
#else
#define API __attribute__((visibility("default")))
#pragma GCC diagnostic ignored "-Wunused-function"
#endif
typedef int esp_err_t;
#define ESP_OK 0
#define ESP_FAIL -1
#define ESP_ERR_INVALID_ARG 0x102
#define ESP_ERR_INVALID_STATE 0x103
#define ESP_ERR_NO_MEM 0x101
#define pdTRUE 1
#define pdFALSE 0
#define portMAX_DELAY 0xffffffffu
#define portMUX_INITIALIZER_UNLOCKED 0
#define portENTER_CRITICAL(x) ((void)(x))
#define portEXIT_CRITICAL(x) ((void)(x))
typedef int portMUX_TYPE;
typedef int BaseType_t;
static unsigned fail_stage, pwm, sem_errors, timer_creates, live_sems;
static uint64_t clock_us;
static unsigned config_hz, config_timer, config_channel, config_bits, config_pin;
struct fake_sem { bool used; unsigned token; };
typedef struct fake_sem *SemaphoreHandle_t;
static struct fake_sem sems[8];
static void dispatch_wait(void);
static SemaphoreHandle_t make_sem(unsigned token, unsigned stage)
{
    unsigned i;
    if (fail_stage == stage) return NULL;
    for (i = 0; i < 8; ++i) if (!sems[i].used) {
        sems[i].used = true; sems[i].token = token; ++live_sems; return &sems[i];
    }
    return NULL;
}
static SemaphoreHandle_t xSemaphoreCreateMutex(void) { return make_sem(1, 1); }
static SemaphoreHandle_t xSemaphoreCreateBinary(void) { return make_sem(0, 2); }
static BaseType_t xSemaphoreTake(SemaphoreHandle_t sem, unsigned wait)
{
    if (!sem || !sem->used) { ++sem_errors; return pdFALSE; }
    if (!sem->token && wait) dispatch_wait();
    if (!sem->token) return pdFALSE;
    --sem->token; return pdTRUE;
}
static BaseType_t xSemaphoreGive(SemaphoreHandle_t sem)
{
    if (!sem || !sem->used) { ++sem_errors; return pdFALSE; }
    sem->token = 1; return pdTRUE;
}
static void vSemaphoreDelete(SemaphoreHandle_t sem)
{ if (sem && sem->used) { sem->used = false; --live_sems; } else ++sem_errors; }
typedef void (*esp_timer_cb_t)(void *);
typedef struct {
    esp_timer_cb_t callback; void *arg; int dispatch_method; const char *name;
    bool skip_unhandled_events;
} esp_timer_create_args_t;
#define ESP_TIMER_TASK 0
struct fake_timer {
    bool used, armed; esp_timer_cb_t callback; void *arg; uint64_t deadline;
    char kind;
};
typedef struct fake_timer *esp_timer_handle_t;
static struct fake_timer timers[12];
static esp_timer_cb_t deferred_callback;
static void *deferred_arg;
static unsigned deferred_ran;
static esp_err_t esp_timer_create(const esp_timer_create_args_t *args,
                                  esp_timer_handle_t *out)
{
    unsigned i, stage;
    char kind = args->name[6];
    ++timer_creates;
    stage = kind == 'o' ? 5u : (kind == 'b' ? 6u : 7u);
    if (fail_stage == stage) return ESP_FAIL;
    for (i = 0; i < 12; ++i) if (!timers[i].used) {
        timers[i] = (struct fake_timer){0};
        timers[i].used = true; timers[i].callback = args->callback;
        timers[i].arg = args->arg; timers[i].kind = kind; *out = &timers[i];
        return ESP_OK;
    }
    return ESP_ERR_NO_MEM;
}
static esp_err_t esp_timer_start_once(esp_timer_handle_t timer, uint64_t delay)
{
    unsigned stage = timer->kind == 'o' ? 8u : (timer->kind == 'b' ? 9u : 12u);
    if (fail_stage == stage) return ESP_FAIL;
    if (timer->armed) return ESP_ERR_INVALID_STATE;
    timer->armed = true; timer->deadline = clock_us + delay; return ESP_OK;
}
static esp_err_t esp_timer_stop(esp_timer_handle_t timer)
{
    if (!timer->armed) return ESP_ERR_INVALID_STATE;
    timer->armed = false; return ESP_OK;
}
static esp_err_t esp_timer_delete(esp_timer_handle_t timer)
{
    if (fail_stage == 13) return ESP_FAIL;
    if (timer->armed) return ESP_ERR_INVALID_STATE;
    /* Intentionally does NOT drain a callback already selected for dispatch. */
    timer->used = false; return ESP_OK;
}
static int64_t esp_timer_get_time(void) { return (int64_t)clock_us; }
static void dispatch_wait(void)
{
    unsigned i; struct fake_timer *first = NULL;
    if (deferred_callback) {
        esp_timer_cb_t callback = deferred_callback;
        deferred_callback = NULL; callback(deferred_arg); ++deferred_ran;
    }
    for (i = 0; i < 12; ++i) if (timers[i].used && timers[i].armed &&
        (!first || timers[i].deadline < first->deadline)) first = &timers[i];
    if (first) {
        clock_us = first->deadline; first->armed = false; first->callback(first->arg);
    }
}
#define LEDC_LOW_SPEED_MODE 0
#define LEDC_TIMER_10_BIT 10
#define LEDC_AUTO_CLK 0
#define LEDC_INTR_DISABLE 0
#define GPIO_MODE_OUTPUT 1
#define GPIO_PULLUP_DISABLE 0
#define GPIO_PULLDOWN_DISABLE 0
#define GPIO_INTR_DISABLE 0
typedef int gpio_num_t;
typedef struct { uint64_t pin_bit_mask; int mode, pull_up_en, pull_down_en, intr_type; } gpio_config_t;
typedef struct { int speed_mode, duty_resolution, timer_num; unsigned freq_hz; int clk_cfg; bool deconfigure; } ledc_timer_config_t;
typedef struct { int gpio_num, speed_mode, channel, intr_type, timer_sel; unsigned duty, hpoint; struct { unsigned output_invert; } flags; } ledc_channel_config_t;
static esp_err_t gpio_set_level(int gpio, unsigned level)
{ (void)gpio; if (!level) pwm = 0; return ESP_OK; }
static esp_err_t gpio_config(const gpio_config_t *config)
{ (void)config; pwm = 0; return ESP_OK; }
static esp_err_t gpio_set_direction(int gpio, int mode)
{ (void)gpio; (void)mode; pwm = 0; return ESP_OK; }
static esp_err_t ledc_timer_config(const ledc_timer_config_t *config)
{
    if (config->deconfigure) return ESP_OK;
    config_hz = config->freq_hz; config_timer = (unsigned)config->timer_num;
    config_bits = (unsigned)config->duty_resolution;
    return fail_stage == 3 ? ESP_FAIL : ESP_OK;
}
static esp_err_t ledc_channel_config(const ledc_channel_config_t *config)
{
    config_channel = (unsigned)config->channel; config_pin = (unsigned)config->gpio_num;
    pwm = config->duty; return fail_stage == 4 ? ESP_FAIL : ESP_OK;
}
static esp_err_t ledc_stop(int mode, int channel, unsigned idle)
{ (void)mode; (void)channel; pwm = idle; return fail_stage == 11 ? ESP_FAIL : ESP_OK; }
static esp_err_t ledc_set_duty(int mode, int channel, unsigned duty)
{ (void)mode; (void)channel; pwm = duty; return fail_stage == 10 ? ESP_FAIL : ESP_OK; }
static esp_err_t ledc_update_duty(int mode, int channel)
{ (void)mode; (void)channel; return fail_stage == 14 ? ESP_FAIL : ESP_OK; }
static esp_err_t ledc_timer_pause(int mode, int timer)
{ (void)mode; (void)timer; return ESP_OK; }
'''
    # Only SDK includes are replaced. The entire adapter body is compiled.
    public = re.sub(r'^#(?:include|pragma).*$', '', header.read_text(encoding="utf-8"),
                    flags=re.MULTILINE)
    driver = re.sub(r'^#include.*$', '', source.read_text(encoding="utf-8"),
                    flags=re.MULTILINE)
    includes = '\n#include "' + (COMPONENT / "micro_box_s3_motor_policy.h").as_posix() + '"\n'
    includes += '#include "' + (ROOT / "components/micro_box_s3/include/micro_box_s3_pins.h").as_posix() + '"\n'
    suffix = r'''
API void host_fail(unsigned stage) { fail_stage = stage; }
API unsigned host_pwm(void) { return pwm; }
API unsigned host_sems(void) { return live_sems; }
API unsigned host_sem_errors(void) { return sem_errors; }
API unsigned host_deferred_ran(void) { return deferred_ran; }
API unsigned host_live_timers(void)
{ unsigned i, n = 0; for (i = 0; i < 12; ++i) if (timers[i].used) ++n; return n; }
API unsigned host_config(unsigned field)
{
    const unsigned values[] = {config_hz, config_timer, config_channel, config_bits, config_pin};
    return values[field];
}
API void host_time(uint64_t now) { clock_us = now; }
API void host_dispatch_due(uint64_t now)
{
    unsigned i; struct fake_timer *first;
    clock_us = now;
    do {
        first = NULL;
        for (i = 0; i < 12; ++i) if (timers[i].used && timers[i].armed &&
            timers[i].deadline <= now &&
            (!first || timers[i].deadline < first->deadline)) first = &timers[i];
        if (first) { first->armed = false; first->callback(first->arg); }
    } while (first);
}
API void host_queue_boost(void)
{
    unsigned i;
    for (i = 0; i < 12; ++i) if (timers[i].used && timers[i].kind == 'b') {
        deferred_callback = timers[i].callback; deferred_arg = timers[i].arg;
        timers[i].armed = false; return;
    }
}
API int host_create(micro_box_s3_motor_handle_t *out) { return micro_box_s3_motor_create(out); }
API int host_delete(micro_box_s3_motor_handle_t handle) { return micro_box_s3_motor_delete(handle); }
API int host_stop(micro_box_s3_motor_handle_t handle) { return micro_box_s3_motor_stop(handle); }
API int host_pulse(micro_box_s3_motor_handle_t handle, unsigned ms, unsigned duty, unsigned boost)
{ return micro_box_s3_motor_pulse(handle, ms, duty, boost); }
API int host_state(micro_box_s3_motor_handle_t handle, micro_box_s3_motor_state_t *out)
{ return micro_box_s3_motor_get_state(handle, out); }
'''
    wrapper = build / "motor_driver_host.c"
    wrapper.write_text(prefix + includes + public + driver + suffix, encoding="utf-8")
    library = compile_library(build, [COMPONENT / "micro_box_s3_motor_policy.c", wrapper],
                              "motor_driver")
    library.host_create.argtypes = [ctypes.POINTER(ctypes.c_void_p)]
    library.host_create.restype = ctypes.c_int
    for name in ("delete", "stop"):
        getattr(library, "host_" + name).argtypes = [ctypes.c_void_p]
        getattr(library, "host_" + name).restype = ctypes.c_int
    library.host_pulse.argtypes = [ctypes.c_void_p] + [ctypes.c_uint] * 3
    library.host_pulse.restype = ctypes.c_int
    library.host_state.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
    library.host_state.restype = ctypes.c_int
    for name in ("pwm", "sems", "sem_errors", "live_timers", "deferred_ran"):
        getattr(library, "host_" + name).argtypes = []
        getattr(library, "host_" + name).restype = ctypes.c_uint
    library.host_config.argtypes = [ctypes.c_uint]
    library.host_config.restype = ctypes.c_uint
    library.host_fail.argtypes = [ctypes.c_uint]
    library.host_fail.restype = None
    library.host_time.argtypes = [ctypes.c_uint64]
    library.host_time.restype = None
    library.host_dispatch_due.argtypes = [ctypes.c_uint64]
    library.host_dispatch_due.restype = None
    library.host_queue_boost.argtypes = []
    library.host_queue_boost.restype = None
    return library


class MotorState(ctypes.Structure):
    _fields_ = [("active", ctypes.c_bool), ("duty_percent", ctypes.c_uint),
                ("duration_ms", ctypes.c_uint), ("pulses_started", ctypes.c_uint32),
                ("faulted", ctypes.c_bool)]


class MotorDriverTests(unittest.TestCase):
    def test_create_is_low_singleton_null_checked_and_deletes_cleanly(self):
        motor = load_driver()
        handle = ctypes.c_void_p()
        motor.host_fail(0)
        self.assertEqual(motor.host_create(None), 0x102)
        self.assertEqual(motor.host_create(ctypes.byref(handle)), 0)
        self.assertEqual(motor.host_pwm(), 0)
        self.assertEqual([motor.host_config(i) for i in range(5)], [200, 1, 1, 10, 14])
        other = ctypes.c_void_p()
        self.assertEqual(motor.host_create(ctypes.byref(other)), 0x103)
        self.assertIsNone(other.value)
        self.assertEqual(motor.host_stop(None), 0x102)
        self.assertEqual(motor.host_delete(None), 0x102)
        self.assertEqual(motor.host_pulse(None, 100, 100, 0), 0x102)
        self.assertEqual(motor.host_state(handle, None), 0x102)
        self.assertEqual(motor.host_delete(handle), 0)
        self.assertEqual(motor.host_live_timers(), 0)
        self.assertEqual(motor.host_sems(), 0)
        self.assertEqual(motor.host_sem_errors(), 0)
    def test_create_failure_at_each_resource_stage_rolls_back(self):
        motor = load_driver()
        for stage in (1, 2, 3, 4, 5, 6, 7, 11):
            with self.subTest(stage=stage):
                handle = ctypes.c_void_p()
                motor.host_fail(stage)
                self.assertNotEqual(motor.host_create(ctypes.byref(handle)), 0)
                self.assertIsNone(handle.value)
                self.assertEqual(motor.host_pwm(), 0)
                self.assertEqual(motor.host_live_timers(), 0)
                self.assertEqual(motor.host_sems(), 0)
                motor.host_fail(0)
                self.assertEqual(motor.host_create(ctypes.byref(handle)), 0)
                self.assertEqual(motor.host_delete(handle), 0)
        self.assertEqual(motor.host_sem_errors(), 0)

    def test_pulse_driver_failures_leave_pin_low_and_cooldown_enforced(self):
        motor = load_driver()
        for stage in (8, 9, 10, 14):
            with self.subTest(stage=stage):
                handle = ctypes.c_void_p()
                motor.host_fail(0)
                motor.host_time(0)
                self.assertEqual(motor.host_create(ctypes.byref(handle)), 0)
                motor.host_fail(stage)
                self.assertNotEqual(motor.host_pulse(handle, 400, 30, 40), 0)
                self.assertEqual(motor.host_pwm(), 0)
                motor.host_fail(0)
                motor.host_time(2999999)
                self.assertEqual(motor.host_pulse(handle, 400, 30, 40), 0x103)
                motor.host_time(3000000)
                self.assertEqual(motor.host_pulse(handle, 400, 30, 40), 0)
                self.assertEqual(motor.host_pwm(), 1024)
                self.assertEqual(motor.host_delete(handle), 0)
        self.assertEqual(motor.host_live_timers(), 0)
        self.assertEqual(motor.host_sems(), 0)

    def test_delete_drains_callback_selected_before_stop_and_can_recreate(self):
        motor = load_driver()
        handle = ctypes.c_void_p()
        motor.host_fail(0)
        motor.host_time(0)
        self.assertEqual(motor.host_create(ctypes.byref(handle)), 0)
        self.assertEqual(motor.host_pulse(handle, 400, 30, 40), 0)
        motor.host_queue_boost()  # selected, but callback has not entered yet
        before = motor.host_deferred_ran()
        self.assertEqual(motor.host_delete(handle), 0)
        self.assertEqual(motor.host_deferred_ran(), before + 1)
        self.assertEqual(motor.host_pwm(), 0)
        self.assertEqual(motor.host_live_timers(), 0)
        self.assertEqual(motor.host_sems(), 0)
        self.assertEqual(motor.host_sem_errors(), 0)
        self.assertEqual(motor.host_create(ctypes.byref(handle)), 0)
        self.assertEqual(motor.host_pulse(handle, 100, 100, 0), 0)
        self.assertEqual(motor.host_delete(handle), 0)

    def test_failed_delete_preserves_context_and_is_retryable(self):
        motor = load_driver()
        for stage in (11, 12, 13):
            with self.subTest(stage=stage):
                handle = ctypes.c_void_p()
                motor.host_fail(0)
                motor.host_time(0)
                self.assertEqual(motor.host_create(ctypes.byref(handle)), 0)
                self.assertEqual(motor.host_pulse(handle, 400, 30, 40), 0)
                motor.host_queue_boost()
                motor.host_fail(stage)
                self.assertNotEqual(motor.host_delete(handle), 0)
                self.assertEqual(motor.host_pwm(), 0)
                self.assertEqual(motor.host_pulse(handle, 100, 100, 0), 0x103)
                self.assertGreater(motor.host_sems(), 0)
                motor.host_fail(0)
                self.assertEqual(motor.host_delete(handle), 0)
                self.assertEqual(motor.host_live_timers(), 0)
                self.assertEqual(motor.host_sems(), 0)
        self.assertEqual(motor.host_sem_errors(), 0)
    def test_state_boost_duty_cutoff_and_delayed_dispatch(self):
        motor = load_driver()
        handle = ctypes.c_void_p()
        state = MotorState()
        motor.host_fail(0)
        motor.host_time(0)
        self.assertEqual(motor.host_create(ctypes.byref(handle)), 0)
        self.assertEqual(motor.host_state(None, ctypes.byref(state)), 0x102)
        self.assertEqual(motor.host_pulse(handle, 400, 30, 40), 0)
        self.assertEqual(motor.host_state(handle, ctypes.byref(state)), 0)
        self.assertTrue(state.active)
        self.assertEqual((state.duty_percent, state.duration_ms, state.pulses_started),
                         (30, 400, 1))
        motor.host_dispatch_due(40000)
        self.assertEqual(motor.host_pwm(), (1024 * 30 + 50) // 100)
        self.assertEqual(motor.host_pulse(handle, 400, 60, 40), 0x103)
        self.assertEqual(motor.host_pulse(handle, 401, 60, 40), 0x102)
        motor.host_dispatch_due(400000)
        self.assertEqual(motor.host_pwm(), 0)
        self.assertEqual(motor.host_state(handle, ctypes.byref(state)), 0)
        self.assertFalse(state.active)
        self.assertFalse(state.faulted)
        self.assertEqual((state.duty_percent, state.duration_ms), (0, 0))
        motor.host_time(3400000)
        self.assertEqual(motor.host_pulse(handle, 400, 60, 40), 0)
        motor.host_dispatch_due(3900000)  # boost callback blocked past cutoff
        self.assertEqual(motor.host_pwm(), 0)
        self.assertEqual(motor.host_state(handle, ctypes.byref(state)), 0)
        self.assertEqual(state.pulses_started, 2)
        self.assertFalse(state.active)
        self.assertEqual(motor.host_delete(handle), 0)


if __name__ == "__main__":
    unittest.main()
