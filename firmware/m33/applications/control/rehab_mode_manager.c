#include "rehab_mode_manager.h"

#include "control_layer_cfg.h"

typedef struct
{
    struct rt_mutex lock;
    rt_tick_t last_heartbeat_tick;
    rt_bool_t has_heartbeat;
    rt_uint8_t last_sequence;
    rt_uint8_t last_reject_sequence;
    rt_uint8_t last_reject_detail;
    rt_bool_t initialized;
} rehab_mode_adapter_runtime_t;

static rehab_mode_adapter_runtime_t s_rehab_adapter;

enum
{
    REHAB_MODE_ADAPTER_CMD_MARKER = CONTROL_REHAB_MODE_CMD_MARKER
};

static rt_bool_t rehab_mode_adapter_heartbeat_ok(rt_tick_t now)
{
    if (!s_rehab_adapter.has_heartbeat)
    {
        return RT_FALSE;
    }
    return ((now - s_rehab_adapter.last_heartbeat_tick) <=
            rt_tick_from_millisecond(CONTROL_ROS_HEARTBEAT_TIMEOUT_MS))
               ? RT_TRUE
               : RT_FALSE;
}

static rt_bool_t rehab_mode_adapter_joint_mask_supported(rt_uint8_t joint_mask)
{
    const rt_uint8_t elbow_mask = 0x02U;

    if (joint_mask == 0U)
    {
        return RT_TRUE;
    }
    return ((joint_mask & (rt_uint8_t)~elbow_mask) == 0U) ? RT_TRUE : RT_FALSE;
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

    s_rehab_adapter.initialized = RT_TRUE;
    return rehab_service_init();
}

rt_err_t rehab_mode_manager_apply_command(const rehab_mode_command_t *cmd)
{
    rehab_demo_mode_t service_mode;
    rt_err_t ret;
    rt_tick_t now;

    if (cmd == RT_NULL)
    {
        return -RT_EINVAL;
    }
    ret = rehab_mode_manager_init();
    if (ret != RT_EOK)
    {
        return ret;
    }

    now = rt_tick_get();
    rt_mutex_take(&s_rehab_adapter.lock, RT_WAITING_FOREVER);
    if ((cmd->mode != REHAB_MODE_PASSIVE) && !rehab_mode_adapter_heartbeat_ok(now))
    {
        s_rehab_adapter.last_reject_sequence = cmd->sequence;
        s_rehab_adapter.last_reject_detail = CONTROL_STATUS_DETAIL_HEARTBEAT_TIMEOUT;
        rt_mutex_release(&s_rehab_adapter.lock);
        return -RT_ETIMEOUT;
    }
    rt_mutex_release(&s_rehab_adapter.lock);

    if (!rehab_mode_adapter_joint_mask_supported(cmd->joint_mask))
    {
        rehab_mode_adapter_store_reject(cmd->sequence, CONTROL_STATUS_DETAIL_UNKNOWN_JOINT);
        return -RT_EINVAL;
    }

    service_mode = rehab_mode_adapter_to_service_mode(cmd->mode, cmd->submode);
    if ((service_mode == REHAB_DEMO_MODE_PASSIVE) && (cmd->mode != REHAB_MODE_PASSIVE))
    {
        rehab_mode_adapter_store_reject(cmd->sequence, CONTROL_STATUS_DETAIL_UNSUPPORTED_COMMAND);
        return -RT_EINVAL;
    }

    if (service_mode == REHAB_DEMO_MODE_PASSIVE)
    {
        ret = rehab_service_stop(REHAB_CMD_SOURCE_CAN);
    }
    else if (service_mode == REHAB_DEMO_MODE_MEMORY_RECORD)
    {
        ret = rehab_service_record_start(0U, REHAB_JOINT_ELBOW, REHAB_CMD_SOURCE_CAN);
    }
    else if (service_mode == REHAB_DEMO_MODE_MEMORY_PLAYBACK)
    {
        ret = rehab_service_play_start(0U, REHAB_JOINT_ELBOW, REHAB_CMD_SOURCE_CAN);
    }
    else
    {
        ret = rehab_service_set_mode(service_mode, REHAB_JOINT_ELBOW, REHAB_CMD_SOURCE_CAN);
    }

    rt_mutex_take(&s_rehab_adapter.lock, RT_WAITING_FOREVER);
    s_rehab_adapter.last_sequence = cmd->sequence;
    if (ret == RT_EOK)
    {
        s_rehab_adapter.last_reject_detail = CONTROL_STATUS_DETAIL_NONE;
    }
    else
    {
        s_rehab_adapter.last_reject_sequence = cmd->sequence;
        s_rehab_adapter.last_reject_detail = CONTROL_STATUS_DETAIL_MOTOR_FAULT;
    }
    rt_mutex_release(&s_rehab_adapter.lock);

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
    s_rehab_adapter.last_heartbeat_tick = rt_tick_get();
    s_rehab_adapter.has_heartbeat = RT_TRUE;
    rt_mutex_release(&s_rehab_adapter.lock);
}

void rehab_mode_manager_tick(void)
{
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
    rt_mutex_release(&s_rehab_adapter.lock);

    out->mode = rehab_mode_adapter_from_service_mode(service_status.mode, &submode);
    out->submode = submode;
    out->active_joint_mask = 0x02U;
    out->flags = flags;
    out->detail = (service_status.detail != CONTROL_STATUS_DETAIL_NONE) ?
                  service_status.detail :
                  adapter_detail;
    out->assist_engaged_mask = service_status.assist_engaged ? 0x02U : 0U;
    out->sequence = sequence;
    out->timestamp = service_status.timestamp;
}
