#include "smif0_guard_client.h"

#include "cy_ipc_drv.h"

#define SMIF0_GUARD_CHANNEL_TIMEOUT_MS         (50U)
#define SMIF0_GUARD_ACK_TIMEOUT_MS             (500U)
#define SMIF0_GUARD_DONE_TIMEOUT_MS            (500U)
#define SMIF0_GUARD_MUTEX_TIMEOUT_MS           (50U)
#define SMIF0_GUARD_NOTIFY_MASK                (1UL << SMIF0_GUARD_IPC_INTERRUPT_LOCAL)

#define SMIF0_GUARD_MAILBOX                    \
    ((volatile smif0_guard_mailbox_t *)(uintptr_t)SMIF0_GUARD_SHARED_ADDRESS)
#define SMIF0_GUARD_IPC_STRUCT                 \
    (&IPC1->STRUCT[SMIF0_GUARD_IPC_CHANNEL_LOCAL])

static struct rt_mutex g_smif0_guard_mutex;
static rt_bool_t g_smif0_guard_initialized;
static uint32_t g_smif0_guard_next_seq;
static uint32_t g_smif0_guard_active_seq;
static uint32_t g_smif0_guard_active_epoch;

static rt_bool_t smif0_guard_timeout_elapsed(rt_tick_t start, uint32_t timeout_ms)
{
    const rt_tick_t timeout_ticks = rt_tick_from_millisecond(timeout_ms);

    return ((rt_tick_t)(rt_tick_get() - start) >= timeout_ticks) ? RT_TRUE : RT_FALSE;
}

static rt_err_t smif0_guard_validate_online(uint32_t *epoch_out)
{
    uint32_t magic;
    uint32_t version;
    uint32_t size;
    uint32_t epoch;
    uint32_t state;

    __DMB();
    magic = SMIF0_GUARD_MAILBOX->magic;
    version = SMIF0_GUARD_MAILBOX->version;
    size = SMIF0_GUARD_MAILBOX->size;
    epoch = SMIF0_GUARD_MAILBOX->epoch;
    state = SMIF0_GUARD_MAILBOX->state;
    __DMB();

    if ((magic != SMIF0_GUARD_MAGIC) ||
        (version != SMIF0_GUARD_VERSION) ||
        (size != sizeof(smif0_guard_mailbox_t)) ||
        (epoch == 0U))
    {
        return -RT_EINVAL;
    }

    if (state == SMIF0_GUARD_STATE_FATAL)
    {
        return -RT_ERROR;
    }

    if (state != SMIF0_GUARD_STATE_ONLINE)
    {
        return -RT_EBUSY;
    }

    *epoch_out = epoch;
    return RT_EOK;
}

static rt_err_t smif0_guard_lock_channel(void)
{
    const rt_tick_t start = rt_tick_get();

    do
    {
        if (Cy_IPC_Drv_LockAcquire(SMIF0_GUARD_IPC_STRUCT) == CY_IPC_DRV_SUCCESS)
        {
            return RT_EOK;
        }
        rt_thread_mdelay(1U);
    } while (!smif0_guard_timeout_elapsed(start, SMIF0_GUARD_CHANNEL_TIMEOUT_MS));

    return -RT_ETIMEOUT;
}

static void smif0_guard_cancel_request(uint32_t request_seq, uint32_t request_epoch)
{
    __DMB();
    SMIF0_GUARD_MAILBOX->release_seq = request_seq;
    __DSB();
    g_smif0_guard_active_seq = request_seq;
    g_smif0_guard_active_epoch = request_epoch;
    (void)Cy_IPC_Drv_LockRelease(SMIF0_GUARD_IPC_STRUCT, CY_IPC_NO_NOTIFICATION);
}

static rt_err_t smif0_guard_reap_completed_request(void)
{
    const uint32_t request_seq = g_smif0_guard_active_seq;
    uint32_t done_seq;
    uint32_t result;
    uint32_t state;
    uint32_t epoch;

    if (request_seq == 0U)
    {
        return RT_EOK;
    }

    __DMB();
    epoch = SMIF0_GUARD_MAILBOX->epoch;
    __DMB();
    if (epoch != g_smif0_guard_active_epoch)
    {
        /* CM33 restarted; the old ticket belongs to the previous boot epoch. */
        g_smif0_guard_active_seq = 0U;
        g_smif0_guard_active_epoch = 0U;
        return RT_EOK;
    }

    done_seq = SMIF0_GUARD_MAILBOX->done_seq;
    if (done_seq != request_seq)
    {
        return -RT_EBUSY;
    }

    __DMB();
    result = SMIF0_GUARD_MAILBOX->result;
    state = SMIF0_GUARD_MAILBOX->state;
    epoch = SMIF0_GUARD_MAILBOX->epoch;
    if (epoch != g_smif0_guard_active_epoch)
    {
        g_smif0_guard_active_seq = 0U;
        g_smif0_guard_active_epoch = 0U;
        return RT_EOK;
    }

    if (state != SMIF0_GUARD_STATE_ONLINE)
    {
        return -RT_ERROR;
    }

    g_smif0_guard_active_seq = 0U;
    g_smif0_guard_active_epoch = 0U;
    if (result == SMIF0_GUARD_RESULT_DONE)
    {
        return RT_EOK;
    }
    if (result == SMIF0_GUARD_RESULT_BUSY)
    {
        return -RT_EBUSY;
    }
    if (result == SMIF0_GUARD_RESULT_INVALID)
    {
        return -RT_EINVAL;
    }
    return -RT_ERROR;
}

static uint32_t smif0_guard_allocate_sequence(void)
{
    uint32_t request_seq;
    uint32_t ack_seq;
    uint32_t done_seq;
    uint32_t candidate = g_smif0_guard_next_seq;
    uint32_t attempt;

    __DMB();
    request_seq = SMIF0_GUARD_MAILBOX->request_seq;
    ack_seq = SMIF0_GUARD_MAILBOX->ack_seq;
    done_seq = SMIF0_GUARD_MAILBOX->done_seq;
    __DMB();

    /* Four non-zero candidates are sufficient to avoid three stale tickets. */
    for (attempt = 0U; attempt < 4U; ++attempt)
    {
        ++candidate;
        if (candidate == 0U)
        {
            ++candidate;
        }

        if ((candidate != request_seq) &&
            (candidate != ack_seq) &&
            (candidate != done_seq))
        {
            g_smif0_guard_next_seq = candidate;
            return candidate;
        }
    }

    return 0U;
}

rt_err_t smif0_guard_client_init(void)
{
    uint32_t epoch;
    rt_err_t status;

    rt_enter_critical();
    if (g_smif0_guard_initialized)
    {
        rt_exit_critical();
        return RT_EOK;
    }

    if (rt_mutex_init(&g_smif0_guard_mutex, "smif0", RT_IPC_FLAG_PRIO) != RT_EOK)
    {
        rt_exit_critical();
        return -RT_ERROR;
    }

    status = smif0_guard_validate_online(&epoch);
    if (status != RT_EOK)
    {
        (void)rt_mutex_detach(&g_smif0_guard_mutex);
        rt_exit_critical();
        return status;
    }

    __DMB();
    g_smif0_guard_next_seq = SMIF0_GUARD_MAILBOX->request_seq;
    __DMB();
    if (SMIF0_GUARD_MAILBOX->epoch != epoch)
    {
        (void)rt_mutex_detach(&g_smif0_guard_mutex);
        rt_exit_critical();
        return -RT_EBUSY;
    }
    g_smif0_guard_active_seq = 0U;
    g_smif0_guard_active_epoch = 0U;
    g_smif0_guard_initialized = RT_TRUE;
    rt_exit_critical();
    return RT_EOK;
}

rt_err_t smif0_guard_client_lock(void)
{
    if (!g_smif0_guard_initialized)
    {
        return -RT_ERROR;
    }

    return rt_mutex_take(&g_smif0_guard_mutex,
                         rt_tick_from_millisecond(SMIF0_GUARD_MUTEX_TIMEOUT_MS));
}

void smif0_guard_client_unlock(void)
{
    if (g_smif0_guard_initialized)
    {
        (void)rt_mutex_release(&g_smif0_guard_mutex);
    }
}

rt_err_t smif0_guard_client_acquire(smif0_guard_operation_t operation,
                                    uint32_t address,
                                    uint32_t length,
                                    uint32_t *request_seq_out)
{
    rt_tick_t start;
    uint32_t request_seq;
    uint32_t request_epoch;
    rt_err_t status;

    if ((request_seq_out == RT_NULL) ||
        ((operation != SMIF0_GUARD_OP_WRITE) && (operation != SMIF0_GUARD_OP_ERASE)))
    {
        return -RT_EINVAL;
    }

    status = smif0_guard_reap_completed_request();
    if (status != RT_EOK)
    {
        return status;
    }

    status = smif0_guard_lock_channel();
    if (status != RT_EOK)
    {
        return status;
    }

    status = smif0_guard_validate_online(&request_epoch);
    if (status != RT_EOK)
    {
        (void)Cy_IPC_Drv_LockRelease(SMIF0_GUARD_IPC_STRUCT, CY_IPC_NO_NOTIFICATION);
        return status;
    }

    request_seq = smif0_guard_allocate_sequence();
    if (request_seq == 0U)
    {
        (void)Cy_IPC_Drv_LockRelease(SMIF0_GUARD_IPC_STRUCT, CY_IPC_NO_NOTIFICATION);
        return -RT_ERROR;
    }

    SMIF0_GUARD_MAILBOX->operation = operation;
    SMIF0_GUARD_MAILBOX->address = address;
    SMIF0_GUARD_MAILBOX->length = length;
    SMIF0_GUARD_MAILBOX->release_seq = 0U;
    __DMB();
    SMIF0_GUARD_MAILBOX->request_seq = request_seq;
    __DSB();

    Cy_IPC_Drv_WriteDataValue(SMIF0_GUARD_IPC_STRUCT, request_seq);
    __DSB();
    Cy_IPC_Drv_AcquireNotify(SMIF0_GUARD_IPC_STRUCT, SMIF0_GUARD_NOTIFY_MASK);

    start = rt_tick_get();
    do
    {
        const uint32_t ack_seq = SMIF0_GUARD_MAILBOX->ack_seq;

        if (ack_seq == request_seq)
        {
            uint32_t result;
            uint32_t state;
            uint32_t epoch;

            __DMB();
            result = SMIF0_GUARD_MAILBOX->result;
            state = SMIF0_GUARD_MAILBOX->state;
            epoch = SMIF0_GUARD_MAILBOX->epoch;

            if (epoch != request_epoch)
            {
                smif0_guard_cancel_request(request_seq, request_epoch);
                return -RT_ERROR;
            }

            if ((result == SMIF0_GUARD_RESULT_GRANTED) &&
                (state == SMIF0_GUARD_STATE_PARKED))
            {
                g_smif0_guard_active_seq = request_seq;
                g_smif0_guard_active_epoch = request_epoch;
                *request_seq_out = request_seq;
                return RT_EOK;
            }

            if (result == SMIF0_GUARD_RESULT_BUSY)
            {
                return -RT_EBUSY;
            }

            if (result == SMIF0_GUARD_RESULT_INVALID)
            {
                return -RT_EINVAL;
            }

            smif0_guard_cancel_request(request_seq, request_epoch);
            return -RT_ERROR;
        }

        rt_thread_mdelay(1U);
    } while (!smif0_guard_timeout_elapsed(start, SMIF0_GUARD_ACK_TIMEOUT_MS));

    /* A late CM33 ISR observes this release and cannot remain parked forever. */
    __DMB();
    SMIF0_GUARD_MAILBOX->release_seq = request_seq;
    __DSB();
    g_smif0_guard_active_seq = request_seq;
    g_smif0_guard_active_epoch = request_epoch;
    (void)Cy_IPC_Drv_LockRelease(SMIF0_GUARD_IPC_STRUCT, CY_IPC_NO_NOTIFICATION);
    return -RT_ETIMEOUT;
}

rt_err_t smif0_guard_client_release(uint32_t request_seq)
{
    const rt_tick_t start = rt_tick_get();
    const uint32_t request_epoch = g_smif0_guard_active_epoch;

    if ((request_seq == 0U) || (request_seq != g_smif0_guard_active_seq))
    {
        return -RT_EINVAL;
    }

    do
    {
        const uint32_t done_seq = SMIF0_GUARD_MAILBOX->done_seq;

        if (done_seq == request_seq)
        {
            uint32_t result;
            uint32_t state;
            uint32_t epoch;

            __DMB();
            result = SMIF0_GUARD_MAILBOX->result;
            state = SMIF0_GUARD_MAILBOX->state;
            epoch = SMIF0_GUARD_MAILBOX->epoch;
            if ((result == SMIF0_GUARD_RESULT_DONE) &&
                (state == SMIF0_GUARD_STATE_ONLINE) &&
                (epoch == request_epoch))
            {
                g_smif0_guard_active_seq = 0U;
                g_smif0_guard_active_epoch = 0U;
                return RT_EOK;
            }

            return -RT_ERROR;
        }

        rt_thread_mdelay(1U);
    } while (!smif0_guard_timeout_elapsed(start, SMIF0_GUARD_DONE_TIMEOUT_MS));

    return -RT_ETIMEOUT;
}
