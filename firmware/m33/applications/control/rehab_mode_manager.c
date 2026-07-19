#include "rehab_mode_manager.h"

#include "control_layer_cfg.h"
#include "rehab_app_lease.h"
#include "rehab_can_lease.h"

typedef struct
{
    struct rt_mutex command_lock;
    struct rt_mutex lock;
    rehab_app_lease_t app_lease;
    rehab_can_lease_t lease;
    rt_tick_t explicit_stop_last_attempt_tick;
    rt_uint32_t explicit_stop_retry_count;
    rt_uint8_t last_sequence;
    rt_uint8_t last_reject_sequence;
    rt_uint8_t last_reject_detail;
    rt_bool_t explicit_stop_latched;
    rt_bool_t explicit_stop_has_attempt;
    rt_bool_t initialized;
} rehab_mode_adapter_runtime_t;

static rehab_mode_adapter_runtime_t s_rehab_adapter;

enum
{
    REHAB_MODE_ADAPTER_CMD_MARKER = CONTROL_REHAB_MODE_CMD_MARKER,
    REHAB_MODE_STOP_RETRY_MS = 100U,
    REHAB_APP_MODE_MIN_TTL_MS = 200U,
    REHAB_APP_MODE_MAX_TTL_MS = 2000U
};

static rt_bool_t rehab_mode_adapter_heartbeat_ok(rt_tick_t now)
{
    if (!s_rehab_adapter.lease.has_heartbeat)
    {
        return RT_FALSE;
    }
    return ((now - s_rehab_adapter.lease.last_heartbeat_tick) <=
            rt_tick_from_millisecond(CONTROL_ROS_HEARTBEAT_TIMEOUT_MS))
               ? RT_TRUE
               : RT_FALSE;
}

static rt_bool_t rehab_mode_adapter_joint_mask_supported(rt_uint8_t joint_mask)
{
    const rt_uint8_t supported_mask = CONTROL_REHAB_ASSIST_DEFAULT_JOINT_MASK;

    if (joint_mask == 0U)
    {
        return RT_TRUE;
    }
    return ((joint_mask & (rt_uint8_t)~supported_mask) == 0U) ? RT_TRUE : RT_FALSE;
}

static rt_bool_t rehab_mode_adapter_lease_supervised(rehab_demo_mode_t mode)
{
    return ((mode == REHAB_DEMO_MODE_ACTIVE_FOLLOW) ||
            (mode == REHAB_DEMO_MODE_ASSIST) ||
            (mode == REHAB_DEMO_MODE_RESIST))
               ? RT_TRUE
               : RT_FALSE;
}

static rt_bool_t rehab_mode_adapter_source_supported(rehab_cmd_source_t source)
{
    return ((source == REHAB_CMD_SOURCE_CAN) ||
            (source == REHAB_CMD_SOURCE_VOICE))
               ? RT_TRUE
               : RT_FALSE;
}

static rehab_demo_mode_t rehab_mode_adapter_to_service_mode(rehab_mode_t mode,
                                                            rehab_mode_submode_t submode)
{
    if ((mode == REHAB_MODE_ACTIVE) && (submode == REHAB_MODE_SUBMODE_IDLE))
    {
        return REHAB_DEMO_MODE_ACTIVE_FOLLOW;
    }
    if ((mode == REHAB_MODE_ASSIST) && (submode == REHAB_MODE_SUBMODE_IDLE))
    {
        return REHAB_DEMO_MODE_ASSIST;
    }
    if ((mode == REHAB_MODE_RESIST) && (submode == REHAB_MODE_SUBMODE_IDLE))
    {
        return REHAB_DEMO_MODE_RESIST;
    }
    if ((mode == REHAB_MODE_CURL) && (submode == REHAB_MODE_SUBMODE_IDLE))
    {
        return REHAB_DEMO_MODE_CURL;
    }
    if ((mode == REHAB_MODE_FIXED_ACTION) && (submode == REHAB_MODE_SUBMODE_IDLE))
    {
        return REHAB_DEMO_MODE_FIXED_ACTION;
    }
    if ((mode == REHAB_MODE_MEMORY) && (submode == REHAB_MODE_SUBMODE_RECORD))
    {
        return REHAB_DEMO_MODE_MEMORY_RECORD;
    }
    if ((mode == REHAB_MODE_MEMORY) && (submode == REHAB_MODE_SUBMODE_PLAYBACK))
    {
        return REHAB_DEMO_MODE_MEMORY_PLAYBACK;
    }
    return REHAB_DEMO_MODE_PASSIVE;
}

static rehab_mode_t rehab_mode_adapter_from_service_mode(rehab_demo_mode_t mode,
                                                         rehab_mode_submode_t *submode)
{
    if (submode == RT_NULL)
    {
        return REHAB_MODE_PASSIVE;
    }

    *submode = REHAB_MODE_SUBMODE_IDLE;
    switch (mode)
    {
    case REHAB_DEMO_MODE_ACTIVE_FOLLOW:
        return REHAB_MODE_ACTIVE;
    case REHAB_DEMO_MODE_ASSIST:
        return REHAB_MODE_ASSIST;
    case REHAB_DEMO_MODE_RESIST:
        return REHAB_MODE_RESIST;
    case REHAB_DEMO_MODE_CURL:
        return REHAB_MODE_CURL;
    case REHAB_DEMO_MODE_FIXED_ACTION:
        return REHAB_MODE_FIXED_ACTION;
    case REHAB_DEMO_MODE_MEMORY_RECORD:
        *submode = REHAB_MODE_SUBMODE_RECORD;
        return REHAB_MODE_MEMORY;
    case REHAB_DEMO_MODE_MEMORY_PLAYBACK:
        *submode = REHAB_MODE_SUBMODE_PLAYBACK;
        return REHAB_MODE_MEMORY;
    case REHAB_DEMO_MODE_PASSIVE:
    default:
        return REHAB_MODE_PASSIVE;
    }
}

static void rehab_mode_adapter_store_reject(rt_uint8_t sequence, rt_uint8_t detail)
{
    rt_mutex_take(&s_rehab_adapter.lock, RT_WAITING_FOREVER);
    s_rehab_adapter.last_reject_sequence = sequence;
    s_rehab_adapter.last_reject_detail = detail;
    rt_mutex_release(&s_rehab_adapter.lock);
}

rt_err_t rehab_mode_manager_init(void)
{
    rt_err_t ret;

    if (s_rehab_adapter.initialized)
    {
        return RT_EOK;
    }

    rt_memset(&s_rehab_adapter, 0, sizeof(s_rehab_adapter));
    ret = rt_mutex_init(&s_rehab_adapter.lock, "rehaba", RT_IPC_FLAG_PRIO);
    if (ret != RT_EOK)
    {
        return ret;
    }
    ret = rt_mutex_init(&s_rehab_adapter.command_lock, "rehabcmd", RT_IPC_FLAG_PRIO);
    if (ret != RT_EOK)
    {
        rt_mutex_detach(&s_rehab_adapter.lock);
        return ret;
    }

    ret = rehab_service_init();
    if (ret != RT_EOK)
    {
        rt_mutex_detach(&s_rehab_adapter.command_lock);
        rt_mutex_detach(&s_rehab_adapter.lock);
        return ret;
    }

    s_rehab_adapter.initialized = RT_TRUE;
    return RT_EOK;
}

rt_err_t rehab_mode_manager_apply_command(const rehab_mode_command_t *cmd)
{
    rehab_demo_mode_t service_mode;
    rt_uint8_t joint_mask;
    rt_err_t ret;
    rt_tick_t now;
    rehab_service_status_t service_status;

    if (cmd == RT_NULL)
    {
        return -RT_EINVAL;
    }
    if (!rehab_mode_adapter_source_supported(cmd->source))
    {
        return -RT_EINVAL;
    }
    ret = rehab_mode_manager_init();
    if (ret != RT_EOK)
    {
        return ret;
    }

    rt_mutex_take(&s_rehab_adapter.command_lock, RT_WAITING_FOREVER);
    rehab_service_get_status(&service_status);
    if ((cmd->mode != REHAB_MODE_PASSIVE) &&
        (service_status.mode != REHAB_DEMO_MODE_PASSIVE) &&
        (service_status.source == REHAB_CMD_SOURCE_APP_BLE))
    {
        rt_mutex_release(&s_rehab_adapter.command_lock);
        return -RT_EBUSY;
    }
    now = rt_tick_get();
    rt_mutex_take(&s_rehab_adapter.lock, RT_WAITING_FOREVER);
    if ((cmd->mode != REHAB_MODE_PASSIVE) &&
        (!rehab_mode_adapter_heartbeat_ok(now) ||
         !rehab_can_lease_can_enter_active_mode(&s_rehab_adapter.lease)))
    {
        s_rehab_adapter.last_reject_sequence = cmd->sequence;
        s_rehab_adapter.last_reject_detail = CONTROL_STATUS_DETAIL_HEARTBEAT_TIMEOUT;
        rt_mutex_release(&s_rehab_adapter.lock);
        rt_mutex_release(&s_rehab_adapter.command_lock);
        return -RT_ETIMEOUT;
    }
    rt_mutex_release(&s_rehab_adapter.lock);

    joint_mask = (cmd->joint_mask == 0U) ?
                 CONTROL_REHAB_ASSIST_DEFAULT_JOINT_MASK :
                 cmd->joint_mask;

    if (!rehab_mode_adapter_joint_mask_supported(joint_mask))
    {
        rehab_mode_adapter_store_reject(cmd->sequence, CONTROL_STATUS_DETAIL_UNKNOWN_JOINT);
        rt_mutex_release(&s_rehab_adapter.command_lock);
        return -RT_EINVAL;
    }

    service_mode = rehab_mode_adapter_to_service_mode(cmd->mode, cmd->submode);
    if ((service_mode == REHAB_DEMO_MODE_PASSIVE) && (cmd->mode != REHAB_MODE_PASSIVE))
    {
        rehab_mode_adapter_store_reject(cmd->sequence, CONTROL_STATUS_DETAIL_UNSUPPORTED_COMMAND);
        rt_mutex_release(&s_rehab_adapter.command_lock);
        return -RT_EINVAL;
    }

    if (service_mode == REHAB_DEMO_MODE_PASSIVE)
    {
        ret = rehab_service_stop(cmd->source);
    }
    else if (service_mode == REHAB_DEMO_MODE_MEMORY_RECORD)
    {
        ret = rehab_service_record_start(0U, REHAB_JOINT_ELBOW, cmd->source);
    }
    else if (service_mode == REHAB_DEMO_MODE_MEMORY_PLAYBACK)
    {
        ret = rehab_service_play_start(0U, REHAB_JOINT_ELBOW, cmd->source);
    }
    else
    {
        ret = rehab_service_set_mode_mask(service_mode, joint_mask, cmd->source);
    }

    if (ret == RT_EOK)
    {
        rehab_service_get_status(&service_status);
    }

    rt_mutex_take(&s_rehab_adapter.lock, RT_WAITING_FOREVER);
    s_rehab_adapter.last_sequence = cmd->sequence;
    if (ret == RT_EOK)
    {
        rehab_app_lease_revoke(&s_rehab_adapter.app_lease);
        rehab_can_lease_note_mode(&s_rehab_adapter.lease,
                                  (rehab_mode_adapter_source_supported(service_status.source) &&
                                   rehab_mode_adapter_lease_supervised(service_status.mode))
                                      ? RT_TRUE
                                      : RT_FALSE,
                                  (rt_uint8_t)service_status.source,
                                  service_status.mode_generation);
        s_rehab_adapter.last_reject_detail = CONTROL_STATUS_DETAIL_NONE;
    }
    else
    {
        s_rehab_adapter.last_reject_sequence = cmd->sequence;
        s_rehab_adapter.last_reject_detail = CONTROL_STATUS_DETAIL_MOTOR_FAULT;
    }
    rt_mutex_release(&s_rehab_adapter.lock);
    rt_mutex_release(&s_rehab_adapter.command_lock);

    return ret;
}

rt_err_t rehab_mode_manager_apply_app_command(const rehab_app_mode_command_t *cmd)
{
    rehab_demo_mode_t service_mode;
    rehab_service_status_t service_status;
    const rehab_fixed_action_profile_t *fixed_profile;
    rt_tick_t now;
    rt_err_t ret;
    rt_err_t rollback_ret;
    rt_bool_t lease_started;

    fixed_profile = (cmd != RT_NULL)
        ? rehab_fixed_action_profile(cmd->fixed_action)
        : RT_NULL;
    if ((cmd == RT_NULL) || (cmd->request_id == 0U) ||
        (cmd->session_generation == 0U) ||
        (cmd->ttl_ms < REHAB_APP_MODE_MIN_TTL_MS) ||
        (cmd->ttl_ms > REHAB_APP_MODE_MAX_TTL_MS) ||
        ((cmd->mode != REHAB_MODE_ACTIVE) &&
         (cmd->mode != REHAB_MODE_ASSIST) &&
         (cmd->mode != REHAB_MODE_RESIST) &&
         (cmd->mode != REHAB_MODE_CURL) &&
         (cmd->mode != REHAB_MODE_FIXED_ACTION)) ||
        (((cmd->mode == REHAB_MODE_CURL) &&
          ((cmd->joint_mask != CONTROL_REHAB_CURL_JOINT_MASK) ||
           (cmd->fixed_action != REHAB_FIXED_ACTION_NONE))) ||
         ((cmd->mode == REHAB_MODE_FIXED_ACTION) &&
          ((fixed_profile == RT_NULL) ||
           !fixed_profile->enabled ||
           (cmd->joint_mask != fixed_profile->joint_mask))) ||
         (((cmd->mode != REHAB_MODE_CURL) &&
           (cmd->mode != REHAB_MODE_FIXED_ACTION)) &&
          (cmd->joint_mask != CONTROL_REHAB_ASSIST_DEFAULT_JOINT_MASK))))
    {
        return -RT_EINVAL;
    }

    ret = rehab_mode_manager_init();
    if (ret != RT_EOK)
    {
        return ret;
    }

    rt_mutex_take(&s_rehab_adapter.command_lock, RT_WAITING_FOREVER);
    rt_mutex_take(&s_rehab_adapter.lock, RT_WAITING_FOREVER);
    if (!rehab_app_lease_can_begin(&s_rehab_adapter.app_lease,
                                   (rt_uint8_t)REHAB_CMD_SOURCE_APP_BLE,
                                   cmd->session_generation))
    {
        rt_mutex_release(&s_rehab_adapter.lock);
        rt_mutex_release(&s_rehab_adapter.command_lock);
        return -RT_EBUSY;
    }
    rt_mutex_release(&s_rehab_adapter.lock);

    rehab_service_get_status(&service_status);
    if ((service_status.mode != REHAB_DEMO_MODE_PASSIVE) &&
        (service_status.source != REHAB_CMD_SOURCE_APP_BLE))
    {
        rt_mutex_release(&s_rehab_adapter.command_lock);
        return -RT_EBUSY;
    }

    service_mode = rehab_mode_adapter_to_service_mode(cmd->mode,
                                                      REHAB_MODE_SUBMODE_IDLE);
    if (service_mode == REHAB_DEMO_MODE_CURL)
    {
        ret = rehab_service_curl_start_if_unchanged(
            REHAB_CMD_SOURCE_APP_BLE,
            service_status.source,
            service_status.mode_generation);
    }
    else if (service_mode == REHAB_DEMO_MODE_FIXED_ACTION)
    {
        ret = rehab_service_fixed_action_start_if_unchanged(
            cmd->fixed_action,
            REHAB_CMD_SOURCE_APP_BLE,
            service_status.source,
            service_status.mode_generation);
    }
    else
    {
        ret = rehab_service_set_mode_mask_if_unchanged(
            service_mode,
            cmd->joint_mask,
            REHAB_CMD_SOURCE_APP_BLE,
            service_status.source,
            service_status.mode_generation);
    }
    if (ret == RT_EOK)
    {
        rehab_service_get_status(&service_status);
        if ((service_status.source != REHAB_CMD_SOURCE_APP_BLE) ||
            (service_status.mode != service_mode) ||
            (service_status.active_joint_mask != cmd->joint_mask))
        {
            ret = -RT_EBUSY;
        }
    }

    if (ret == RT_EOK)
    {
        now = rt_tick_get();
        rt_mutex_take(&s_rehab_adapter.lock, RT_WAITING_FOREVER);
        lease_started = rehab_app_lease_begin(
            &s_rehab_adapter.app_lease,
            (rt_uint8_t)REHAB_CMD_SOURCE_APP_BLE,
            service_status.mode_generation,
            cmd->session_generation,
            now,
            rt_tick_from_millisecond(cmd->ttl_ms));
        if (lease_started)
        {
            rehab_can_lease_note_mode(&s_rehab_adapter.lease,
                                      RT_FALSE,
                                      (rt_uint8_t)REHAB_CMD_SOURCE_APP_BLE,
                                      service_status.mode_generation);
            s_rehab_adapter.last_sequence = (rt_uint8_t)cmd->request_id;
            s_rehab_adapter.last_reject_detail = CONTROL_STATUS_DETAIL_NONE;
        }
        rt_mutex_release(&s_rehab_adapter.lock);

        if (!lease_started)
        {
            rollback_ret = rehab_service_stop_if_owned(
                REHAB_CMD_SOURCE_APP_BLE,
                service_status.mode_generation,
                CONTROL_STATUS_DETAIL_HEARTBEAT_TIMEOUT);
            rt_mutex_take(&s_rehab_adapter.lock, RT_WAITING_FOREVER);
            if ((rollback_ret == RT_EOK) || (rollback_ret == -RT_EBUSY))
            {
                rehab_app_lease_revoke(&s_rehab_adapter.app_lease);
            }
            else
            {
                s_rehab_adapter.last_reject_sequence = (rt_uint8_t)cmd->request_id;
                s_rehab_adapter.last_reject_detail = CONTROL_STATUS_DETAIL_MOTOR_FAULT;
            }
            rt_mutex_release(&s_rehab_adapter.lock);
            ret = ((rollback_ret == RT_EOK) || (rollback_ret == -RT_EBUSY))
                      ? -RT_EBUSY
                      : rollback_ret;
        }
    }

    rt_mutex_release(&s_rehab_adapter.command_lock);
    return ret;
}

rt_err_t rehab_mode_manager_note_app_heartbeat(rt_uint32_t session_generation)
{
    rehab_service_status_t service_status;
    rt_bool_t accepted;
    rt_err_t ret;

    if (session_generation == 0U)
    {
        return -RT_EINVAL;
    }
    ret = rehab_mode_manager_init();
    if (ret != RT_EOK)
    {
        return ret;
    }

    rehab_service_get_status(&service_status);
    rt_mutex_take(&s_rehab_adapter.lock, RT_WAITING_FOREVER);
    accepted = rehab_app_lease_note_heartbeat(
        &s_rehab_adapter.app_lease,
        (rt_uint8_t)service_status.source,
        service_status.mode_generation,
        session_generation,
        rt_tick_get());
    rt_mutex_release(&s_rehab_adapter.lock);
    return accepted ? RT_EOK : -RT_EBUSY;
}

rt_err_t rehab_mode_manager_note_app_disconnect(rt_uint32_t session_generation)
{
    rt_uint32_t expected_generation;
    rt_uint32_t claimed_session_generation;
    rt_uint8_t expected_source_value;
    rehab_cmd_source_t expected_source;
    rt_err_t ret;
    rt_bool_t should_stop;

    if (session_generation == 0U)
    {
        return -RT_EINVAL;
    }
    ret = rehab_mode_manager_init();
    if (ret != RT_EOK)
    {
        return ret;
    }

    rt_mutex_take(&s_rehab_adapter.command_lock, RT_WAITING_FOREVER);
    rt_mutex_take(&s_rehab_adapter.lock, RT_WAITING_FOREVER);
    if (s_rehab_adapter.explicit_stop_latched)
    {
        rt_mutex_release(&s_rehab_adapter.lock);
        rt_mutex_release(&s_rehab_adapter.command_lock);
        return -RT_EBUSY;
    }
    should_stop = rehab_app_lease_claim_disconnect_stop(
        &s_rehab_adapter.app_lease,
        session_generation,
        rt_tick_get(),
        rt_tick_from_millisecond(REHAB_MODE_STOP_RETRY_MS),
        &expected_source_value,
        &expected_generation,
        &claimed_session_generation);
    rt_mutex_release(&s_rehab_adapter.lock);

    if (!should_stop)
    {
        rt_mutex_release(&s_rehab_adapter.command_lock);
        return -RT_EBUSY;
    }

    expected_source = (rehab_cmd_source_t)expected_source_value;
    ret = rehab_service_stop_if_owned(expected_source,
                                      expected_generation,
                                      CONTROL_STATUS_DETAIL_HEARTBEAT_TIMEOUT);
    rt_mutex_take(&s_rehab_adapter.lock, RT_WAITING_FOREVER);
    rehab_app_lease_note_stop_result(&s_rehab_adapter.app_lease,
                                     (ret == RT_EOK) ? RT_TRUE : RT_FALSE,
                                     (ret == -RT_EBUSY) ? RT_TRUE : RT_FALSE);
    if ((ret != RT_EOK) && (ret != -RT_EBUSY))
    {
        s_rehab_adapter.last_reject_detail = CONTROL_STATUS_DETAIL_MOTOR_FAULT;
    }
    rt_mutex_release(&s_rehab_adapter.lock);
    rt_mutex_release(&s_rehab_adapter.command_lock);
    (void)claimed_session_generation;
    return ret;
}

rt_err_t rehab_mode_manager_stop_app(rt_uint32_t session_generation)
{
    rt_err_t ret;

    if (session_generation == 0U)
    {
        return -RT_EINVAL;
    }
    ret = rehab_mode_manager_init();
    if (ret != RT_EOK)
    {
        return ret;
    }

    rt_mutex_take(&s_rehab_adapter.command_lock, RT_WAITING_FOREVER);
    rt_mutex_take(&s_rehab_adapter.lock, RT_WAITING_FOREVER);
    if (s_rehab_adapter.explicit_stop_latched)
    {
        rt_mutex_release(&s_rehab_adapter.lock);
        rt_mutex_release(&s_rehab_adapter.command_lock);
        return -RT_EBUSY;
    }
    if (s_rehab_adapter.app_lease.active &&
        (s_rehab_adapter.app_lease.session_generation != session_generation))
    {
        rt_mutex_release(&s_rehab_adapter.lock);
        rt_mutex_release(&s_rehab_adapter.command_lock);
        return -RT_EBUSY;
    }
    s_rehab_adapter.explicit_stop_latched = RT_TRUE;
    s_rehab_adapter.explicit_stop_has_attempt = RT_TRUE;
    s_rehab_adapter.explicit_stop_last_attempt_tick = rt_tick_get();
    rt_mutex_release(&s_rehab_adapter.lock);

    ret = rehab_service_stop(REHAB_CMD_SOURCE_APP_BLE);
    rt_mutex_take(&s_rehab_adapter.lock, RT_WAITING_FOREVER);
    if (ret == RT_EOK)
    {
        s_rehab_adapter.explicit_stop_latched = RT_FALSE;
        s_rehab_adapter.explicit_stop_has_attempt = RT_FALSE;
        rehab_app_lease_revoke(&s_rehab_adapter.app_lease);
        rehab_can_lease_note_mode(&s_rehab_adapter.lease,
                                  RT_FALSE,
                                  (rt_uint8_t)REHAB_CMD_SOURCE_APP_BLE,
                                  0U);
        s_rehab_adapter.last_reject_detail = CONTROL_STATUS_DETAIL_NONE;
    }
    else
    {
        s_rehab_adapter.explicit_stop_retry_count++;
        s_rehab_adapter.last_reject_detail = CONTROL_STATUS_DETAIL_MOTOR_FAULT;
    }
    rt_mutex_release(&s_rehab_adapter.lock);
    rt_mutex_release(&s_rehab_adapter.command_lock);
    return ret;
}

void rehab_mode_manager_record_reject(rt_uint8_t sequence, rt_uint8_t detail)
{
    if (rehab_mode_manager_init() != RT_EOK)
    {
        return;
    }
    rehab_mode_adapter_store_reject(sequence, detail);
}

void rehab_mode_manager_note_heartbeat(void)
{
    if (rehab_mode_manager_init() != RT_EOK)
    {
        return;
    }

    rt_mutex_take(&s_rehab_adapter.lock, RT_WAITING_FOREVER);
    rehab_can_lease_note_heartbeat(&s_rehab_adapter.lease, rt_tick_get());
    rt_mutex_release(&s_rehab_adapter.lock);
}

void rehab_mode_manager_tick(void)
{
    rt_uint32_t expected_generation;
    rt_uint32_t expected_session_generation = 0U;
    rt_uint8_t expected_source_value;
    rehab_cmd_source_t expected_source;
    rt_err_t ret;
    rt_tick_t now;
    rt_bool_t should_stop_explicit;
    rt_bool_t should_stop_legacy;
    rt_bool_t should_stop_app;

    if (rehab_mode_manager_init() != RT_EOK)
    {
        return;
    }

    rt_mutex_take(&s_rehab_adapter.command_lock, RT_WAITING_FOREVER);
    rt_mutex_take(&s_rehab_adapter.lock, RT_WAITING_FOREVER);
    now = rt_tick_get();
    should_stop_explicit = s_rehab_adapter.explicit_stop_latched &&
                           (!s_rehab_adapter.explicit_stop_has_attempt ||
                            ((now - s_rehab_adapter.explicit_stop_last_attempt_tick) >=
                             rt_tick_from_millisecond(REHAB_MODE_STOP_RETRY_MS)));
    if (should_stop_explicit)
    {
        s_rehab_adapter.explicit_stop_last_attempt_tick = now;
        s_rehab_adapter.explicit_stop_has_attempt = RT_TRUE;
    }
    should_stop_legacy = RT_FALSE;
    should_stop_app = RT_FALSE;
    if (!s_rehab_adapter.explicit_stop_latched)
    {
        should_stop_legacy = rehab_can_lease_claim_stop(
            &s_rehab_adapter.lease,
            now,
            rt_tick_from_millisecond(CONTROL_ROS_HEARTBEAT_TIMEOUT_MS),
            rt_tick_from_millisecond(REHAB_MODE_STOP_RETRY_MS),
            &expected_source_value,
            &expected_generation);
        if (!should_stop_legacy)
        {
            should_stop_app = rehab_app_lease_claim_timeout_stop(
                &s_rehab_adapter.app_lease,
                now,
                rt_tick_from_millisecond(REHAB_MODE_STOP_RETRY_MS),
                &expected_source_value,
                &expected_generation,
                &expected_session_generation);
        }
    }
    rt_mutex_release(&s_rehab_adapter.lock);

    if (!should_stop_explicit && !should_stop_legacy && !should_stop_app)
    {
        rt_mutex_release(&s_rehab_adapter.command_lock);
        return;
    }

    if (should_stop_explicit)
    {
        ret = rehab_service_stop(REHAB_CMD_SOURCE_APP_BLE);
    }
    else
    {
        expected_source = (rehab_cmd_source_t)expected_source_value;
        ret = rehab_service_stop_if_owned(expected_source,
                                          expected_generation,
                                          CONTROL_STATUS_DETAIL_HEARTBEAT_TIMEOUT);
    }

    rt_mutex_take(&s_rehab_adapter.lock, RT_WAITING_FOREVER);
    if (should_stop_explicit)
    {
        if (ret == RT_EOK)
        {
            s_rehab_adapter.explicit_stop_latched = RT_FALSE;
            s_rehab_adapter.explicit_stop_has_attempt = RT_FALSE;
            rehab_app_lease_revoke(&s_rehab_adapter.app_lease);
            rehab_can_lease_note_mode(&s_rehab_adapter.lease,
                                      RT_FALSE,
                                      (rt_uint8_t)REHAB_CMD_SOURCE_APP_BLE,
                                      0U);
        }
        else
        {
            s_rehab_adapter.explicit_stop_retry_count++;
        }
    }
    else if (should_stop_legacy)
    {
        rehab_can_lease_note_stop_result(&s_rehab_adapter.lease,
                                         (ret == RT_EOK) ? RT_TRUE : RT_FALSE,
                                         (ret == -RT_EBUSY) ? RT_TRUE : RT_FALSE);
    }
    else
    {
        rehab_app_lease_note_stop_result(&s_rehab_adapter.app_lease,
                                         (ret == RT_EOK) ? RT_TRUE : RT_FALSE,
                                         (ret == -RT_EBUSY) ? RT_TRUE : RT_FALSE);
    }
    if (ret == RT_EOK)
    {
        s_rehab_adapter.last_reject_detail = should_stop_explicit
                                                 ? CONTROL_STATUS_DETAIL_NONE
                                                 : CONTROL_STATUS_DETAIL_HEARTBEAT_TIMEOUT;
        if (!should_stop_explicit)
        {
            s_rehab_adapter.last_reject_sequence = s_rehab_adapter.last_sequence;
        }
    }
    else if (ret != -RT_EBUSY)
    {
        s_rehab_adapter.last_reject_detail = CONTROL_STATUS_DETAIL_MOTOR_FAULT;
        s_rehab_adapter.last_reject_sequence = s_rehab_adapter.last_sequence;
    }
    rt_mutex_release(&s_rehab_adapter.lock);
    rt_mutex_release(&s_rehab_adapter.command_lock);
    (void)expected_session_generation;
}

rt_bool_t rehab_mode_manager_accepts_ros_target(void)
{
    return rehab_service_accepts_ros_target();
}

rt_bool_t rehab_mode_manager_accepts_ros_stop(void)
{
    return RT_TRUE;
}

void rehab_mode_manager_get_status(rehab_mode_status_t *out)
{
    rehab_service_status_t service_status;
    rehab_mode_submode_t submode;
    rt_uint8_t flags = 0U;
    rt_uint8_t adapter_detail;
    rt_uint8_t sequence;
    rt_tick_t now;
    rt_uint32_t lease_timeout_count;
    rt_uint32_t lease_stop_retry_count;
    rt_bool_t lease_stop_latched;

    if (out == RT_NULL)
    {
        return;
    }
    if (rehab_mode_manager_init() != RT_EOK)
    {
        rt_memset(out, 0, sizeof(*out));
        return;
    }

    now = rt_tick_get();
    rehab_service_get_status(&service_status);

    if (service_status.assist_engaged)
    {
        flags |= REHAB_MODE_STATUS_FLAG_ASSIST_ENGAGED;
    }
    if (!service_status.feedback_fresh &&
        (service_status.mode != REHAB_DEMO_MODE_PASSIVE))
    {
        flags |= REHAB_MODE_STATUS_FLAG_STALE_FEEDBACK;
    }
    if (service_status.mode == REHAB_DEMO_MODE_MEMORY_RECORD)
    {
        flags |= REHAB_MODE_STATUS_FLAG_RECORD;
    }
    if (service_status.mode == REHAB_DEMO_MODE_MEMORY_PLAYBACK)
    {
        flags |= REHAB_MODE_STATUS_FLAG_PLAYBACK;
    }

    rt_mutex_take(&s_rehab_adapter.lock, RT_WAITING_FOREVER);
    if (rehab_mode_adapter_heartbeat_ok(now))
    {
        flags |= REHAB_MODE_STATUS_FLAG_HEARTBEAT_OK;
    }
    if (s_rehab_adapter.last_reject_detail != CONTROL_STATUS_DETAIL_NONE)
    {
        flags |= REHAB_MODE_STATUS_FLAG_REJECTED;
    }
    adapter_detail = s_rehab_adapter.last_reject_detail;
    sequence = (adapter_detail != CONTROL_STATUS_DETAIL_NONE) ?
               s_rehab_adapter.last_reject_sequence :
               s_rehab_adapter.last_sequence;
    lease_timeout_count = s_rehab_adapter.lease.timeout_count;
    lease_stop_retry_count = s_rehab_adapter.lease.stop_retry_count;
    lease_stop_latched = s_rehab_adapter.lease.stop_latched;
    rt_mutex_release(&s_rehab_adapter.lock);

    out->mode = rehab_mode_adapter_from_service_mode(service_status.mode, &submode);
    out->submode = submode;
    out->active_joint_mask = service_status.active_joint_mask;
    out->flags = flags;
    out->detail = (service_status.detail != CONTROL_STATUS_DETAIL_NONE) ?
                  service_status.detail :
                  adapter_detail;
    out->assist_engaged_mask = service_status.assist_engaged_mask;
    out->sequence = sequence;
    out->timestamp = service_status.timestamp;
    out->mode_generation = service_status.mode_generation;
    out->lease_timeout_count = lease_timeout_count;
    out->lease_stop_retry_count = lease_stop_retry_count;
    out->lease_stop_latched = lease_stop_latched;
}
