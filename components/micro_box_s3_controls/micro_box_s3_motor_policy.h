// SPDX-License-Identifier: MIT
#pragma once
#include <stdbool.h>
#include <stdint.h>

// Internal, SDK-independent policy. Caller serializes all calls and callbacks.
#define MICRO_BOX_S3_MOTOR_POLICY_MAX_MS 400u
#define MICRO_BOX_S3_MOTOR_POLICY_MAX_BOOST_MS 40u
#define MICRO_BOX_S3_MOTOR_POLICY_COOLDOWN_US UINT64_C(3000000)

typedef struct {
    bool active;
    bool faulted;
    bool cooling;
    bool boost_pending;
    unsigned duty_percent;
    unsigned duration_ms;
    uint32_t pulses_started;
    uint64_t cooldown_until_us;
    uint64_t off_deadline_us;
    uint64_t boost_deadline_us;
} micro_box_s3_motor_policy_t;

typedef enum {
    MICRO_BOX_S3_MOTOR_POLICY_OK = 0,
    MICRO_BOX_S3_MOTOR_POLICY_INVALID_ARG = 1,
    MICRO_BOX_S3_MOTOR_POLICY_INVALID_STATE = 2,
    MICRO_BOX_S3_MOTOR_POLICY_IO_ERROR = 3
} micro_box_s3_motor_policy_result_t;

// Operations must not call back inline. false means failure (possibly after
// changing hardware). cancel_timers must try BOTH timers even if one fails.
typedef struct {
    bool (*arm_off)(void *context, uint64_t delay_us);
    bool (*arm_boost)(void *context, uint64_t delay_us);
    bool (*cancel_timers)(void *context);
    bool (*output)(void *context, unsigned duty_percent);
    void *context;
    // Optional monotonic clock sampled AFTER output-low finishes, so preemption
    // or slow I/O cannot consume the cooldown before the pin has been stopped.
    // If NULL, deterministic callers use the supplied now_us timestamp.
    uint64_t (*now_us)(void *context);
} micro_box_s3_motor_policy_ops_t;

void micro_box_s3_motor_policy_init(micro_box_s3_motor_policy_t *policy);
int micro_box_s3_motor_policy_pulse(micro_box_s3_motor_policy_t *policy,
    const micro_box_s3_motor_policy_ops_t *ops, uint64_t now_us,
    unsigned duration_ms, unsigned duty_percent, unsigned boost_ms);
int micro_box_s3_motor_policy_stop(micro_box_s3_motor_policy_t *policy,
    const micro_box_s3_motor_policy_ops_t *ops, uint64_t now_us);
int micro_box_s3_motor_policy_off(micro_box_s3_motor_policy_t *policy,
    const micro_box_s3_motor_policy_ops_t *ops, uint64_t now_us);
int micro_box_s3_motor_policy_boost(micro_box_s3_motor_policy_t *policy,
    const micro_box_s3_motor_policy_ops_t *ops, uint64_t now_us);
