#include "voice_rehab_ipc_sender.h"

#include <finsh.h>
#include <rtdevice.h>
#include <stdint.h>

#include "voice_mode_intent.h"

#define VOICE_REHAB_EVENT_ID_SIZE 65U
#define VOICE_REHAB_CANONICAL_PAYLOAD_SIZE 64U
#define VOICE_REHAB_REQUEST_TTL_MS 500U
#define VOICE_REHAB_RESULT_TIMEOUT_MS 1500U
#define VOICE_REHAB_PUBLISH_BUSY_ATTEMPTS 2U

typedef struct
{
    rt_bool_t used;
    char event_id[VOICE_REHAB_EVENT_ID_SIZE];
    char payload[VOICE_REHAB_CANONICAL_PAYLOAD_SIZE];
} voice_rehab_event_entry_t;

typedef struct
{
    rt_bool_t used;
    rt_uint32_t request_id;
    rt_uint32_t mode;
    rt_uint32_t joint_mask;
    rt_tick_t publish_tick;
} voice_rehab_pending_entry_t;

typedef struct
{
    struct rt_mutex lock;
    rt_bool_t initialized;
    rt_uint32_t boot_epoch;
    rt_uint32_t next_request_id;
    rt_uint32_t event_write_index;
    voice_rehab_event_entry_t events[VOICE_REHAB_EVENT_HISTORY_DEPTH];
    voice_rehab_pending_entry_t pending[VOICE_REHAB_PENDING_DEPTH];
    voice_rehab_ipc_sender_diag_t diag;
} voice_rehab_ipc_sender_state_t;

static voice_rehab_ipc_sender_state_t s_sender;

static rt_uint32_t voice_rehab_make_boot_epoch(void)
{
    struct rt_device *random_dev = rt_device_find("urandom");
    rt_uint32_t epoch = 0U;

    if (random_dev != RT_NULL)
    {
        rt_ssize_t got = rt_device_read(random_dev, 0, &epoch, sizeof(epoch));

        if ((got == (rt_ssize_t)sizeof(epoch)) && (epoch != 0U))
        {
            return epoch;
        }
    }

    epoch = (rt_uint32_t)rt_tick_get();
    epoch ^= (rt_uint32_t)(uintptr_t)rt_thread_self();
    epoch ^= (rt_uint32_t)(uintptr_t)&s_sender;
    epoch ^= UINT32_C(0x56524548);
    return (epoch != 0U) ? epoch : UINT32_C(0x56524549);
}

static rt_uint32_t voice_rehab_elapsed_ms(rt_tick_t now, rt_tick_t then)
{
    return (rt_uint32_t)(((rt_uint64_t)(now - then) * 1000ULL) /
                         RT_TICK_PER_SECOND);
}

static voice_rehab_pending_entry_t *voice_rehab_find_free_pending(void)
{
    rt_uint32_t index;

    for (index = 0U; index < VOICE_REHAB_PENDING_DEPTH; index++)
    {
        if (!s_sender.pending[index].used)
        {
            return &s_sender.pending[index];
        }
    }
    return RT_NULL;
}

static voice_rehab_pending_entry_t *voice_rehab_find_pending(rt_uint32_t request_id)
{
    rt_uint32_t index;

    for (index = 0U; index < VOICE_REHAB_PENDING_DEPTH; index++)
    {
        voice_rehab_pending_entry_t *pending = &s_sender.pending[index];

        if (pending->used && (pending->request_id == request_id))
        {
            return pending;
        }
    }
    return RT_NULL;
}

static void voice_rehab_expire_pending_locked(rt_tick_t now)
{
    rt_uint32_t index;

    for (index = 0U; index < VOICE_REHAB_PENDING_DEPTH; index++)
    {
        voice_rehab_pending_entry_t *pending = &s_sender.pending[index];

        if (pending->used &&
            (voice_rehab_elapsed_ms(now, pending->publish_tick) >
             VOICE_REHAB_RESULT_TIMEOUT_MS))
        {
            pending->used = RT_FALSE;
            s_sender.diag.result_timeout++;
        }
    }
}

static rt_err_t voice_rehab_check_event_locked(const char *event_id,
                                               const char *payload)
{
    rt_uint32_t index;

    for (index = 0U; index < VOICE_REHAB_EVENT_HISTORY_DEPTH; index++)
    {
        const voice_rehab_event_entry_t *entry = &s_sender.events[index];

        if (!entry->used || (rt_strcmp(entry->event_id, event_id) != 0))
        {
            continue;
        }
        if (rt_strcmp(entry->payload, payload) == 0)
        {
            s_sender.diag.duplicate_event++;
        }
        else
        {
            s_sender.diag.conflicting_event++;
        }
        return -RT_EBUSY;
    }
    return RT_EOK;
}

static void voice_rehab_store_event_locked(const char *event_id,
                                           const char *payload)
{
    voice_rehab_event_entry_t *entry =
        &s_sender.events[s_sender.event_write_index];

    rt_memset(entry, 0, sizeof(*entry));
    entry->used = RT_TRUE;
    rt_strncpy(entry->event_id, event_id, sizeof(entry->event_id) - 1U);
    rt_strncpy(entry->payload, payload, sizeof(entry->payload) - 1U);
    s_sender.event_write_index =
        (s_sender.event_write_index + 1U) % VOICE_REHAB_EVENT_HISTORY_DEPTH;
}

rt_err_t voice_rehab_ipc_sender_init(void)
{
    rt_uint32_t epoch;
    rt_err_t ret;

    if (s_sender.initialized)
    {
        return RT_EOK;
    }

    epoch = voice_rehab_make_boot_epoch();

    rt_memset(&s_sender, 0, sizeof(s_sender));
    ret = rt_mutex_init(&s_sender.lock, "vrehabtx", RT_IPC_FLAG_PRIO);
    if (ret != RT_EOK)
    {
        return ret;
    }
    s_sender.boot_epoch = epoch;
    s_sender.diag.boot_epoch = epoch;
    s_sender.initialized = RT_TRUE;
    return RT_EOK;
}

rt_err_t voice_rehab_ipc_sender_submit_vla(const char *event_id,
                                           const char *payload,
                                           rt_uint32_t *request_id)
{
    voice_mode_request_t intent;
    voice_rehab_pending_entry_t *pending;
    m33_m55_message_t message;
    rt_uint32_t allocated_id;
    rt_uint32_t publish_attempt;
    rt_err_t ret;

    if (request_id != RT_NULL)
    {
        *request_id = 0U;
    }
    if (!s_sender.initialized)
    {
        return -RT_EBUSY;
    }
    if (!voice_mode_intent_classify(VOICE_MODE_EVENT_XIAOZHI_VLA_CONTROL,
                                    event_id,
                                    payload,
                                    &intent))
    {
        rt_mutex_take(&s_sender.lock, RT_WAITING_FOREVER);
        s_sender.diag.invalid_intent++;
        rt_mutex_release(&s_sender.lock);
        return -RT_EINVAL;
    }

    rt_mutex_take(&s_sender.lock, RT_WAITING_FOREVER);
    voice_rehab_expire_pending_locked(rt_tick_get());
    ret = voice_rehab_check_event_locked(event_id, payload);
    if (ret != RT_EOK)
    {
        rt_mutex_release(&s_sender.lock);
        return ret;
    }
    if (s_sender.next_request_id == UINT32_MAX)
    {
        rt_mutex_release(&s_sender.lock);
        return -RT_EFULL;
    }
    pending = voice_rehab_find_free_pending();
    if (pending == RT_NULL)
    {
        s_sender.diag.pending_full++;
        rt_mutex_release(&s_sender.lock);
        return -RT_EFULL;
    }

    allocated_id = ++s_sender.next_request_id;
    voice_rehab_store_event_locked(event_id, payload);
    pending->used = RT_TRUE;
    pending->request_id = allocated_id;
    pending->mode = intent.mode;
    pending->joint_mask = intent.joint_mask;
    pending->publish_tick = rt_tick_get();
    s_sender.diag.last_request_id = allocated_id;
    rt_mutex_release(&s_sender.lock);

    rt_memset(&message, 0, sizeof(message));
    message.type = MSG_TYPE_REHAB_MODE_REQUEST;
    message.payload.rehab_mode_request.version = REHAB_MODE_PROTOCOL_VERSION;
    message.payload.rehab_mode_request.boot_epoch = s_sender.boot_epoch;
    message.payload.rehab_mode_request.request_id = allocated_id;
    message.payload.rehab_mode_request.source = REHAB_MODE_SOURCE_VOICE;
    message.payload.rehab_mode_request.mode = intent.mode;
    message.payload.rehab_mode_request.joint_mask = intent.joint_mask;
    message.payload.rehab_mode_request.ttl_ms = VOICE_REHAB_REQUEST_TTL_MS;
    message.payload.rehab_mode_request.action = intent.action;
    for (publish_attempt = 0U;
         publish_attempt < VOICE_REHAB_PUBLISH_BUSY_ATTEMPTS;
        publish_attempt++)
    {
        ret = m33_m55_comm_try_publish(&message);
        if (ret == -RT_EBUSY)
        {
            if ((publish_attempt + 1U) < VOICE_REHAB_PUBLISH_BUSY_ATTEMPTS)
            {
                rt_thread_yield();
            }
            continue;
        }
        break;
    }

    rt_mutex_take(&s_sender.lock, RT_WAITING_FOREVER);
    if (ret == RT_EOK)
    {
        s_sender.diag.published++;
    }
    else
    {
        pending = voice_rehab_find_pending(allocated_id);
        if (pending != RT_NULL)
        {
            pending->used = RT_FALSE;
        }
        s_sender.diag.publish_failed++;
    }
    rt_mutex_release(&s_sender.lock);

    if (request_id != RT_NULL)
    {
        *request_id = allocated_id;
    }
    return ret;
}

void voice_rehab_ipc_sender_handle_result(const rehab_mode_result_msg_t *result)
{
    voice_rehab_pending_entry_t *pending;
    rt_tick_t now;

    if ((result == RT_NULL) || !s_sender.initialized)
    {
        return;
    }

    rt_mutex_take(&s_sender.lock, RT_WAITING_FOREVER);
    if ((result->version != REHAB_MODE_PROTOCOL_VERSION) ||
        (result->boot_epoch != s_sender.boot_epoch))
    {
        s_sender.diag.result_foreign++;
        rt_mutex_release(&s_sender.lock);
        return;
    }

    voice_rehab_expire_pending_locked(rt_tick_get());
    pending = voice_rehab_find_pending(result->request_id);
    if (pending == RT_NULL)
    {
        if (result->request_id == s_sender.diag.last_request_id)
        {
            s_sender.diag.result_duplicate++;
        }
        else
        {
            s_sender.diag.result_unknown++;
        }
        rt_mutex_release(&s_sender.lock);
        return;
    }
    if ((pending->mode != result->requested_mode) ||
        (pending->joint_mask != result->joint_mask))
    {
        s_sender.diag.result_foreign++;
        rt_mutex_release(&s_sender.lock);
        return;
    }

    now = rt_tick_get();
    s_sender.diag.result_received++;
    s_sender.diag.last_request_id = result->request_id;
    s_sender.diag.last_result_status = result->status;
    s_sender.diag.last_result_detail = result->detail;
    s_sender.diag.last_applied_mode = result->applied_mode;
    s_sender.diag.last_mode_generation = result->mode_generation;
    s_sender.diag.last_result_rtt_ms =
        voice_rehab_elapsed_ms(now, pending->publish_tick);
    pending->used = RT_FALSE;
    rt_mutex_release(&s_sender.lock);
}

void voice_rehab_ipc_sender_diag_snapshot(voice_rehab_ipc_sender_diag_t *out)
{
    if (out == RT_NULL)
    {
        return;
    }
    rt_memset(out, 0, sizeof(*out));
    if (!s_sender.initialized)
    {
        return;
    }

    rt_mutex_take(&s_sender.lock, RT_WAITING_FOREVER);
    voice_rehab_expire_pending_locked(rt_tick_get());
    *out = s_sender.diag;
    rt_mutex_release(&s_sender.lock);
}

static int cmd_voice_rehab_ipc_debug(int argc, char **argv)
{
    voice_rehab_ipc_sender_diag_t diag;

    RT_UNUSED(argc);
    RT_UNUSED(argv);
    voice_rehab_ipc_sender_diag_snapshot(&diag);
    rt_kprintf("VOICE_REHAB_TX: epoch=%lu published=%lu tx_fail=%lu duplicate=%lu conflict=%lu invalid=%lu pending_full=%lu\n",
               (unsigned long)diag.boot_epoch,
               (unsigned long)diag.published,
               (unsigned long)diag.publish_failed,
               (unsigned long)diag.duplicate_event,
               (unsigned long)diag.conflicting_event,
               (unsigned long)diag.invalid_intent,
               (unsigned long)diag.pending_full);
    rt_kprintf("VOICE_REHAB_RX: received=%lu foreign=%lu unknown=%lu duplicate=%lu timeout=%lu\n",
               (unsigned long)diag.result_received,
               (unsigned long)diag.result_foreign,
               (unsigned long)diag.result_unknown,
               (unsigned long)diag.result_duplicate,
               (unsigned long)diag.result_timeout);
    rt_kprintf("VOICE_REHAB_LAST: request=%lu status=%lu detail=%lu mode=%lu generation=%lu rtt_ms=%lu\n",
               (unsigned long)diag.last_request_id,
               (unsigned long)diag.last_result_status,
               (unsigned long)diag.last_result_detail,
               (unsigned long)diag.last_applied_mode,
               (unsigned long)diag.last_mode_generation,
               (unsigned long)diag.last_result_rtt_ms);
    return 0;
}
MSH_CMD_EXPORT(cmd_voice_rehab_ipc_debug, show voice rehab IPC sender diagnostics);
