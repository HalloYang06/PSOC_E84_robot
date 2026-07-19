#include "voice_rehab_ipc_bridge.h"

#include <finsh.h>

#include "voice_mode_request_guard.h"
#include "../control/rehab_mode_manager.h"
#include "../control/voice_active_precheck.h"

#define VOICE_REHAB_IPC_THREAD_STACK_SIZE 2048U
#define VOICE_REHAB_IPC_THREAD_PRIORITY 20U
#define VOICE_REHAB_IPC_THREAD_TICK 10U

typedef struct
{
    rehab_mode_request_msg_t request;
    rt_tick_t received_tick;
} voice_rehab_ipc_queue_item_t;

static struct rt_messagequeue s_voice_rehab_mq;
static rt_uint8_t s_voice_rehab_mq_pool[
    RT_MQ_BUF_SIZE(sizeof(voice_rehab_ipc_queue_item_t),
                   VOICE_REHAB_IPC_QUEUE_DEPTH)];
static voice_rehab_ipc_bridge_diag_t s_voice_rehab_diag;
static rt_bool_t s_voice_rehab_initialized;
static rt_thread_t s_voice_rehab_thread;
static voice_mode_guard_t s_voice_rehab_guard;

static rt_uint32_t voice_rehab_protocol_mode(rehab_demo_mode_t mode)
{
    if (mode == REHAB_DEMO_MODE_ASSIST)
    {
        return REHAB_MODE_REQUEST_MODE_ASSIST;
    }
    if (mode == REHAB_DEMO_MODE_RESIST)
    {
        return REHAB_MODE_REQUEST_MODE_RESIST;
    }
    return REHAB_MODE_REQUEST_MODE_PASSIVE;
}

static voice_mode_current_t voice_rehab_current_mode(rehab_demo_mode_t mode)
{
    if (mode == REHAB_DEMO_MODE_PASSIVE)
    {
        return VOICE_MODE_CURRENT_PASSIVE;
    }
    if (mode == REHAB_DEMO_MODE_ASSIST)
    {
        return VOICE_MODE_CURRENT_ASSIST;
    }
    if (mode == REHAB_DEMO_MODE_RESIST)
    {
        return VOICE_MODE_CURRENT_RESIST;
    }
    return VOICE_MODE_CURRENT_OTHER_ACTIVE;
}

static rt_uint32_t voice_rehab_result_for_decision(voice_mode_decision_t decision)
{
    switch (decision)
    {
    case VOICE_MODE_DECISION_REJECT_INVALID:
        return REHAB_MODE_RESULT_INVALID;
    case VOICE_MODE_DECISION_REJECT_EXPIRED:
    case VOICE_MODE_DECISION_REJECT_STALE:
        return REHAB_MODE_RESULT_STALE;
    case VOICE_MODE_DECISION_REJECT_DUPLICATE:
        return REHAB_MODE_RESULT_DUPLICATE;
    case VOICE_MODE_DECISION_REJECT_PRECONDITION:
        return REHAB_MODE_RESULT_PRECONDITION;
    case VOICE_MODE_DECISION_NEEDS_PASSIVE:
    case VOICE_MODE_DECISION_NEEDS_REARM:
    case VOICE_MODE_DECISION_REJECT_EPOCH:
        return REHAB_MODE_RESULT_BUSY;
    default:
        return REHAB_MODE_RESULT_NONE;
    }
}

static void voice_rehab_record_result(rt_uint32_t status, rt_uint32_t detail)
{
    rt_base_t level = rt_hw_interrupt_disable();

    s_voice_rehab_diag.processed++;
    if (status == REHAB_MODE_RESULT_APPLIED)
    {
        s_voice_rehab_diag.applied++;
    }
    else
    {
        s_voice_rehab_diag.rejected++;
    }
    s_voice_rehab_diag.last_result = status;
    s_voice_rehab_diag.last_detail = detail;
    rt_hw_interrupt_enable(level);
}

static void voice_rehab_publish_result(const rehab_mode_request_msg_t *request,
                                       rt_uint32_t status,
                                       rt_uint32_t detail,
                                       rt_uint32_t applied_mode,
                                       rt_uint32_t mode_generation)
{
    m33_m55_message_t message;
    rt_err_t ret;
    rt_base_t level;

    if (request == RT_NULL)
    {
        return;
    }

    rt_memset(&message, 0, sizeof(message));
    message.type = MSG_TYPE_REHAB_MODE_RESULT;
    message.payload.rehab_mode_result.version = REHAB_MODE_PROTOCOL_VERSION;
    message.payload.rehab_mode_result.boot_epoch = request->boot_epoch;
    message.payload.rehab_mode_result.request_id = request->request_id;
    message.payload.rehab_mode_result.status = status;
    message.payload.rehab_mode_result.detail = detail;
    message.payload.rehab_mode_result.requested_mode = request->mode;
    message.payload.rehab_mode_result.applied_mode = applied_mode;
    message.payload.rehab_mode_result.joint_mask = request->joint_mask;
    message.payload.rehab_mode_result.mode_generation = mode_generation;
    ret = m33_m55_comm_try_publish(&message);
    if (ret != RT_EOK)
    {
        level = rt_hw_interrupt_disable();
        s_voice_rehab_diag.result_publish_fail++;
        rt_hw_interrupt_enable(level);
    }
}

static rt_err_t voice_rehab_apply_mode(const rehab_mode_request_msg_t *request)
{
    rehab_mode_command_t command;

    rt_memset(&command, 0, sizeof(command));
    command.mode = (rehab_mode_t)request->mode;
    command.submode = REHAB_MODE_SUBMODE_IDLE;
    command.source = REHAB_CMD_SOURCE_VOICE;
    command.joint_mask = (rt_uint8_t)request->joint_mask;
    command.sequence = (rt_uint8_t)request->request_id;
    return rehab_mode_manager_apply_command(&command);
}

static void voice_rehab_process_item(const voice_rehab_ipc_queue_item_t *item)
{
    const rehab_mode_request_msg_t *request = &item->request;
    rehab_service_status_t status;
    control_voice_precheck_result_t precheck;
    voice_mode_request_t guarded_request;
    voice_mode_current_t current_mode;
    voice_mode_decision_t decision;
    rt_uint32_t owner_active;
    rt_uint32_t preconditions_met = 1U;
    rt_uint32_t result_status;
    rt_uint32_t result_detail = 0U;
    rt_uint8_t applied_level = 0U;
    rt_err_t ret = RT_EOK;

    rehab_service_get_status(&status);
    current_mode = voice_rehab_current_mode(status.mode);
    owner_active = (status.mode == REHAB_DEMO_MODE_PASSIVE) ? 0U : 1U;

    if ((s_voice_rehab_guard.trusted_epoch != request->boot_epoch) &&
        !voice_mode_guard_accept_epoch(&s_voice_rehab_guard,
                                       request->boot_epoch,
                                       current_mode,
                                       owner_active))
    {
        /* The guard below reports whether passive re-arming is required. */
    }

    if ((request->action == REHAB_MODE_ACTION_SET_MODE) &&
        (request->mode != REHAB_MODE_REQUEST_MODE_PASSIVE) &&
        (current_mode == VOICE_MODE_CURRENT_PASSIVE))
    {
        ret = control_voice_precheck_assess(&precheck);
        preconditions_met = ((ret == RT_EOK) && precheck.passed) ? 1U : 0U;
        if (!preconditions_met)
        {
            result_detail = (ret == RT_EOK) ? precheck.reason_mask : 0U;
        }
    }

    guarded_request.source = request->source;
    guarded_request.boot_epoch = request->boot_epoch;
    guarded_request.request_id = request->request_id;
    guarded_request.joint_mask = request->joint_mask;
    guarded_request.target_mode = request->mode;
    guarded_request.received_tick = item->received_tick;
    guarded_request.ttl_ms = request->ttl_ms;
    decision = voice_mode_guard_decide(&s_voice_rehab_guard,
                                       &guarded_request,
                                       rt_tick_get(),
                                       RT_TICK_PER_SECOND,
                                       current_mode,
                                       owner_active,
                                       preconditions_met);
    result_status = voice_rehab_result_for_decision(decision);

    if (request->action == REHAB_MODE_ACTION_SET_MODE)
    {
        if ((decision == VOICE_MODE_DECISION_APPLY_PASSIVE) ||
            (decision == VOICE_MODE_DECISION_APPLY_ACTIVE))
        {
            ret = voice_rehab_apply_mode(request);
        }
        else if (decision != VOICE_MODE_DECISION_ALREADY_ACTIVE)
        {
            ret = -RT_EBUSY;
        }
    }
    else if ((decision == VOICE_MODE_DECISION_ALREADY_ACTIVE) &&
             (status.source == REHAB_CMD_SOURCE_VOICE) &&
             (current_mode == request->mode))
    {
        rt_int8_t delta = (request->action == REHAB_MODE_ACTION_LEVEL_UP) ? 1 : -1;

        ret = rehab_service_adjust_intensity_level(status.mode,
                                                   delta,
                                                   REHAB_CMD_SOURCE_VOICE,
                                                   &applied_level);
        result_detail = applied_level;
    }
    else
    {
        if (status.source != REHAB_CMD_SOURCE_VOICE)
        {
            result_detail = (rt_uint32_t)status.source;
        }
        if (result_status == REHAB_MODE_RESULT_NONE)
        {
            result_status = REHAB_MODE_RESULT_BUSY;
        }
        ret = -RT_EBUSY;
    }

    if (ret == RT_EOK)
    {
        if (!voice_mode_guard_commit(&s_voice_rehab_guard,
                                     &guarded_request,
                                     decision))
        {
            result_status = REHAB_MODE_RESULT_STALE;
        }
        else
        {
            result_status = REHAB_MODE_RESULT_APPLIED;
        }
    }
    else if (result_status == REHAB_MODE_RESULT_NONE)
    {
        result_status = (request->mode == REHAB_MODE_REQUEST_MODE_PASSIVE) ?
                        REHAB_MODE_RESULT_STOP_FAILED :
                        REHAB_MODE_RESULT_PRECONDITION;
    }

    rehab_service_get_status(&status);
    voice_rehab_record_result(result_status, result_detail);
    voice_rehab_publish_result(request,
                               result_status,
                               result_detail,
                               voice_rehab_protocol_mode(status.mode),
                               status.mode_generation);
}

static void voice_rehab_ipc_worker(void *parameter)
{
    voice_rehab_ipc_queue_item_t item;
    rt_ssize_t recv_size;
    rt_base_t level;

    RT_UNUSED(parameter);
    while (1)
    {
        recv_size = rt_mq_recv(&s_voice_rehab_mq,
                               &item,
                               sizeof(item),
                               RT_WAITING_FOREVER);
        if (recv_size != (rt_ssize_t)sizeof(item))
        {
            level = rt_hw_interrupt_disable();
            s_voice_rehab_diag.recv_fail++;
            rt_hw_interrupt_enable(level);
            continue;
        }
        voice_rehab_process_item(&item);
    }
}

static rt_bool_t voice_rehab_mode_supported(rt_uint32_t mode)
{
    return ((mode == REHAB_MODE_REQUEST_MODE_ASSIST) ||
            (mode == REHAB_MODE_REQUEST_MODE_RESIST))
               ? RT_TRUE
               : RT_FALSE;
}

static rt_bool_t voice_rehab_action_supported(rt_uint32_t action,
                                              rt_uint32_t mode)
{
    if (action == REHAB_MODE_ACTION_SET_MODE)
    {
        return RT_TRUE;
    }
    if ((action == REHAB_MODE_ACTION_LEVEL_UP) ||
        (action == REHAB_MODE_ACTION_LEVEL_DOWN))
    {
        return ((mode == REHAB_MODE_REQUEST_MODE_ASSIST) ||
                (mode == REHAB_MODE_REQUEST_MODE_RESIST))
                   ? RT_TRUE
                   : RT_FALSE;
    }
    return RT_FALSE;
}

static rt_bool_t voice_rehab_request_valid(const rehab_mode_request_msg_t *request)
{
    return ((request != RT_NULL) &&
            (request->version == REHAB_MODE_PROTOCOL_VERSION) &&
            (request->boot_epoch != 0U) &&
            (request->request_id != 0U) &&
            (request->source == REHAB_MODE_SOURCE_VOICE) &&
            voice_rehab_mode_supported(request->mode) &&
            (request->joint_mask == REHAB_MODE_JOINT_MASK) &&
            (request->ttl_ms != 0U) &&
            (request->ttl_ms <= REHAB_MODE_MAX_TTL_MS) &&
            voice_rehab_action_supported(request->action, request->mode))
               ? RT_TRUE
               : RT_FALSE;
}

rt_err_t voice_rehab_ipc_bridge_init(void)
{
    rt_err_t ret;

    if (s_voice_rehab_initialized)
    {
        return RT_EOK;
    }

    rt_memset(&s_voice_rehab_diag, 0, sizeof(s_voice_rehab_diag));
    ret = rt_mq_init(&s_voice_rehab_mq,
                     "vrehab",
                     s_voice_rehab_mq_pool,
                     sizeof(voice_rehab_ipc_queue_item_t),
                     sizeof(s_voice_rehab_mq_pool),
                     RT_IPC_FLAG_FIFO);
    if (ret == RT_EOK)
    {
        voice_mode_guard_init(&s_voice_rehab_guard);
        s_voice_rehab_thread = rt_thread_create("vrehab",
                                                voice_rehab_ipc_worker,
                                                RT_NULL,
                                                VOICE_REHAB_IPC_THREAD_STACK_SIZE,
                                                VOICE_REHAB_IPC_THREAD_PRIORITY,
                                                VOICE_REHAB_IPC_THREAD_TICK);
        if (s_voice_rehab_thread == RT_NULL)
        {
            rt_mq_detach(&s_voice_rehab_mq);
            return -RT_ENOMEM;
        }
        s_voice_rehab_initialized = RT_TRUE;
        ret = rt_thread_startup(s_voice_rehab_thread);
        if (ret != RT_EOK)
        {
            s_voice_rehab_initialized = RT_FALSE;
            rt_thread_delete(s_voice_rehab_thread);
            s_voice_rehab_thread = RT_NULL;
            rt_mq_detach(&s_voice_rehab_mq);
        }
    }
    return ret;
}

rt_err_t voice_rehab_ipc_bridge_submit(const rehab_mode_request_msg_t *request)
{
    voice_rehab_ipc_queue_item_t item;
    rt_err_t ret;
    rt_base_t level;

    level = rt_hw_interrupt_disable();
    s_voice_rehab_diag.total++;
    rt_hw_interrupt_enable(level);

    if (!s_voice_rehab_initialized || !voice_rehab_request_valid(request))
    {
        level = rt_hw_interrupt_disable();
        s_voice_rehab_diag.invalid++;
        rt_hw_interrupt_enable(level);
        if (request != RT_NULL)
        {
            voice_rehab_publish_result(request,
                                       REHAB_MODE_RESULT_INVALID,
                                       0U,
                                       REHAB_MODE_REQUEST_MODE_PASSIVE,
                                       0U);
        }
        return -RT_EINVAL;
    }

    item.request = *request;
    item.received_tick = rt_tick_get();
    ret = rt_mq_send(&s_voice_rehab_mq, &item, sizeof(item));

    level = rt_hw_interrupt_disable();
    s_voice_rehab_diag.last_request_id = request->request_id;
    s_voice_rehab_diag.last_receive_tick = item.received_tick;
    if (ret == RT_EOK)
    {
        s_voice_rehab_diag.accepted++;
    }
    else
    {
        s_voice_rehab_diag.queue_full++;
    }
    rt_hw_interrupt_enable(level);
    if (ret != RT_EOK)
    {
        voice_rehab_publish_result(request,
                                   REHAB_MODE_RESULT_QUEUE_FULL,
                                   0U,
                                   REHAB_MODE_REQUEST_MODE_PASSIVE,
                                   0U);
    }
    return ret;
}

void voice_rehab_ipc_bridge_diag_snapshot(voice_rehab_ipc_bridge_diag_t *out)
{
    rt_base_t level;

    if (out == RT_NULL)
    {
        return;
    }

    level = rt_hw_interrupt_disable();
    *out = s_voice_rehab_diag;
    rt_hw_interrupt_enable(level);
}

static int cmd_voice_rehab_ipc_debug(int argc, char **argv)
{
    voice_rehab_ipc_bridge_diag_t diag;

    RT_UNUSED(argc);
    RT_UNUSED(argv);
    voice_rehab_ipc_bridge_diag_snapshot(&diag);
    rt_kprintf("VOICE_REHAB_IPC: total=%lu enq=%lu invalid=%lu qfull=%lu processed=%lu applied=%lu rejected=%lu recv_fail=%lu tx_fail=%lu\n",
               (unsigned long)diag.total,
               (unsigned long)diag.accepted,
               (unsigned long)diag.invalid,
               (unsigned long)diag.queue_full,
               (unsigned long)diag.processed,
               (unsigned long)diag.applied,
               (unsigned long)diag.rejected,
               (unsigned long)diag.recv_fail,
               (unsigned long)diag.result_publish_fail);
    rt_kprintf("VOICE_REHAB_LAST: request=%lu result=%lu detail=%lu rx_tick=%lu\n",
               (unsigned long)diag.last_request_id,
               (unsigned long)diag.last_result,
               (unsigned long)diag.last_detail,
               (unsigned long)diag.last_receive_tick);
    return 0;
}
MSH_CMD_EXPORT(cmd_voice_rehab_ipc_debug, show voice rehab IPC queue diagnostics);
