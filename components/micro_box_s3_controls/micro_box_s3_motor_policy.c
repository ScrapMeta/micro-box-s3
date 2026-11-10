// SPDX-License-Identifier: MIT
#include "micro_box_s3_motor_policy.h"

void micro_box_s3_motor_policy_init(micro_box_s3_motor_policy_t *policy)
{
    *policy = (micro_box_s3_motor_policy_t){0};
}

static int rollback(micro_box_s3_motor_policy_t *policy,
    const micro_box_s3_motor_policy_ops_t *ops, uint64_t now_us)
{
    // An I/O operation may fail after affecting hardware. Cool conservatively.
    policy->active = true;
    (void)micro_box_s3_motor_policy_stop(policy, ops, now_us);
    return MICRO_BOX_S3_MOTOR_POLICY_IO_ERROR;
}

int micro_box_s3_motor_policy_pulse(micro_box_s3_motor_policy_t *policy,
    const micro_box_s3_motor_policy_ops_t *ops, uint64_t now_us,
    unsigned duration_ms, unsigned duty_percent, unsigned boost_ms)
{
    if (duration_ms == 0 || duration_ms > MICRO_BOX_S3_MOTOR_POLICY_MAX_MS ||
        duty_percent == 0 || duty_percent > 100 || boost_ms > duration_ms ||
        boost_ms > MICRO_BOX_S3_MOTOR_POLICY_MAX_BOOST_MS) {
        return MICRO_BOX_S3_MOTOR_POLICY_INVALID_ARG;
    }
    if (policy->active || policy->faulted ||
        (policy->cooling && now_us < policy->cooldown_until_us)) {
        return MICRO_BOX_S3_MOTOR_POLICY_INVALID_STATE;
    }
    policy->off_deadline_us = now_us + (uint64_t)duration_ms * 1000u;
    policy->boost_pending = boost_ms > 0 && duty_percent < 100;
    policy->boost_deadline_us = now_us + (uint64_t)boost_ms * 1000u;
    if (!ops->arm_off(ops->context, (uint64_t)duration_ms * 1000u)) {
        return rollback(policy, ops, now_us);
    }
    if (policy->boost_pending && boost_ms < duration_ms &&
        !ops->arm_boost(ops->context, (uint64_t)boost_ms * 1000u)) {
        return rollback(policy, ops, now_us);
    }
    if (!ops->output(ops->context, policy->boost_pending ? 100 : duty_percent)) {
        return rollback(policy, ops, now_us);
    }
    policy->active = true;
    policy->duty_percent = duty_percent;
    policy->duration_ms = duration_ms;
    policy->pulses_started++;
    return MICRO_BOX_S3_MOTOR_POLICY_OK;
}

int micro_box_s3_motor_policy_stop(micro_box_s3_motor_policy_t *policy,
    const micro_box_s3_motor_policy_ops_t *ops, uint64_t now_us)
{
    bool was_faulted = policy->faulted;
    bool canceled = ops->cancel_timers(ops->context);
    bool low = ops->output(ops->context, 0);
    policy->faulted = !canceled || !low;
    if (policy->active || was_faulted) {
        policy->cooling = true;
        uint64_t stopped_at = ops->now_us ? ops->now_us(ops->context) : now_us;
        policy->cooldown_until_us = stopped_at + MICRO_BOX_S3_MOTOR_POLICY_COOLDOWN_US;
    }
    policy->active = false;
    policy->boost_pending = false;
    policy->duty_percent = 0;
    policy->duration_ms = 0;
    return policy->faulted ? MICRO_BOX_S3_MOTOR_POLICY_IO_ERROR :
                            MICRO_BOX_S3_MOTOR_POLICY_OK;
}

int micro_box_s3_motor_policy_off(micro_box_s3_motor_policy_t *policy,
    const micro_box_s3_motor_policy_ops_t *ops, uint64_t now_us)
{
    if (!policy->active || now_us < policy->off_deadline_us) {
        return MICRO_BOX_S3_MOTOR_POLICY_OK;
    }
    return micro_box_s3_motor_policy_stop(policy, ops, now_us);
}

int micro_box_s3_motor_policy_boost(micro_box_s3_motor_policy_t *policy,
    const micro_box_s3_motor_policy_ops_t *ops, uint64_t now_us)
{
    if (!policy->active) {
        return MICRO_BOX_S3_MOTOR_POLICY_OK;
    }
    if (now_us >= policy->off_deadline_us) {
        return micro_box_s3_motor_policy_stop(policy, ops, now_us);
    }
    if (policy->boost_pending && now_us >= policy->boost_deadline_us) {
        policy->boost_pending = false;
        if (!ops->output(ops->context, policy->duty_percent)) {
            return rollback(policy, ops, now_us);
        }
    }
    return MICRO_BOX_S3_MOTOR_POLICY_OK;
}
