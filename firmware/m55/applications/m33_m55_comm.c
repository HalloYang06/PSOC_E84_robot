#include "m33_m55_comm.h"

#include <board.h>

#include "cy_sysint.h"
#include "mtb_ipc.h"

#include <stddef.h>
#include <stdint.h>

#define M33_M55_IPC_INTERNAL_CHANNEL     MTB_IPC_CHAN_1
#define M33_M55_IPC_QUEUE_CHANNEL        MTB_IPC_CHAN_0
#define M33_M55_IPC_INSTANCE_SEMA        (5UL)
#define M33_M55_QUEUE_M33_TO_M55         (0UL)
#define M33_M55_QUEUE_M55_TO_M33         (1UL)
#define M33_M55_IPC_TIMEOUT_MS           (5000UL)
#define M33_M55_TTS_PUBLISH_TIMEOUT_MS   (1000UL)

#define M33_M55_IPC_IRQ_SEMA             (MTB_IPC_IRQ_USER + 4)
#define M33_M55_IPC_IRQ_QUEUE            (MTB_IPC_IRQ_USER + 5)

#define M33_M55_SHARED_START             (0x261C0000UL)
#define M33_M55_SHARED_END               (0x26200000UL)
#define M33_M55_SHARED_ALIAS_START       (0x061C0000UL)
#define M33_M55_SHARED_ALIAS_END         (0x06200000UL)
#define M33_M55_CM33_SRAM_START          (0x24000000UL)
#define M33_M55_CM33_SRAM_END            (0x24100000UL)
#define M33_M55_IPC_PREFLIGHT_TIMEOUT_MS (50UL)

typedef struct
{
    rt_bool_t runtime_ready;
    rt_bool_t initialized;
    rt_bool_t attaching;
    rt_bool_t deferred_attach;
    rt_thread_t retry_thread;
    rt_uint32_t seq;
    struct rt_mutex lock;
} m33_m55_comm_runtime_t;

static m33_m55_comm_runtime_t g_comm_runtime;
static mtb_ipc_t g_ipc_handle _MTB_IPC_DATA_ALIGN;
static mtb_ipc_queue_t g_tx_queue_handle _MTB_IPC_DATA_ALIGN;
static mtb_ipc_queue_t g_rx_queue_handle _MTB_IPC_DATA_ALIGN;
__attribute__((section(".ipc_stream_shared"), aligned(32)))
volatile m33_m55_pcm_shared_t g_m33_m55_pcm_shared;

static void m33_m55_shared_pcm_dsb(void)
{
    __DSB();
}

void m33_m55_shared_pcm_invalidate_header(volatile m33_m55_pcm_shared_t *shared)
{
    if (shared == RT_NULL)
    {
        return;
    }

    SCB_InvalidateDCache_by_Addr((void *)(uintptr_t)shared,
                                (int32_t)offsetof(m33_m55_pcm_shared_t, data));
    m33_m55_shared_pcm_dsb();
}

void m33_m55_shared_pcm_invalidate_payload(volatile m33_m55_pcm_shared_t *shared,
                                           rt_uint32_t payload_len)
{
    if ((shared == RT_NULL) || (payload_len == 0U))
    {
        return;
    }
    if (payload_len > M33_M55_PCM_SHARED_CAPACITY)
    {
        payload_len = M33_M55_PCM_SHARED_CAPACITY;
    }

    SCB_InvalidateDCache_by_Addr((void *)(uintptr_t)&shared->data[0],
                                (int32_t)payload_len);
    m33_m55_shared_pcm_dsb();
}

static const mtb_ipc_config_t g_ipc_config = {
    .internal_channel_index = M33_M55_IPC_INTERNAL_CHANNEL,
    .semaphore_irq = M33_M55_IPC_IRQ_SEMA,
    .queue_irq = M33_M55_IPC_IRQ_QUEUE,
    .semaphore_num = M33_M55_IPC_INSTANCE_SEMA
};

static void m33_m55_ipc_semaphore_irq_handler(void)
{
    mtb_ipc_semaphore_process_interrupt(&g_ipc_handle);
}

static void m33_m55_ipc_queue_irq_handler(void)
{
    mtb_ipc_queue_process_interrupt(&g_ipc_handle);
}

static void m33_m55_ipc_enable_irqs(void)
{
    cy_stc_sysint_t intr_cfg_sema = {
        .intrSrc = (IRQn_Type)CY_IPC_INTR_MUX(M33_M55_IPC_IRQ_SEMA),
        .intrPriority = 7u
    };
    cy_stc_sysint_t intr_cfg_queue = {
        .intrSrc = (IRQn_Type)CY_IPC_INTR_MUX(M33_M55_IPC_IRQ_QUEUE),
        .intrPriority = 7u
    };

    Cy_SysInt_Init(&intr_cfg_sema, m33_m55_ipc_semaphore_irq_handler);
    Cy_SysInt_Init(&intr_cfg_queue, m33_m55_ipc_queue_irq_handler);
    NVIC_EnableIRQ((IRQn_Type)CY_IPC_INTR_MUX(M33_M55_IPC_IRQ_SEMA));
    NVIC_EnableIRQ((IRQn_Type)CY_IPC_INTR_MUX(M33_M55_IPC_IRQ_QUEUE));
}

static rt_err_t m33_m55_result_to_rt(cy_rslt_t result)
{
    if (result == CY_RSLT_SUCCESS)
    {
        return RT_EOK;
    }
    if (result == MTB_IPC_RSLT_ERR_QUEUE_EMPTY)
    {
        return -RT_EEMPTY;
    }
    if (result == MTB_IPC_RSLT_ERR_QUEUE_FULL)
    {
        return -RT_EFULL;
    }
    if (result == MTB_IPC_RSLT_ERR_TIMEOUT)
    {
        return -RT_ETIMEOUT;
    }
    if (result == MTB_IPC_RSLT_ERR_QUEUE_NOT_FOUND)
    {
        return -RT_ENOSYS;
    }
    return -RT_ERROR;
}

static rt_bool_t m33_m55_shared_ptr_is_valid(uint32_t shared_ptr)
{
    if ((shared_ptr >= M33_M55_SHARED_START) && (shared_ptr < M33_M55_SHARED_END))
    {
        return RT_TRUE;
    }

    if ((shared_ptr >= M33_M55_SHARED_ALIAS_START) && (shared_ptr < M33_M55_SHARED_ALIAS_END))
    {
        return RT_TRUE;
    }

    if ((shared_ptr >= M33_M55_CM33_SRAM_START) && (shared_ptr < M33_M55_CM33_SRAM_END))
    {
        return RT_TRUE;
    }

    return RT_FALSE;
}

static rt_err_t m33_m55_wait_for_valid_shared_ptr(void)
{
    IPC_STRUCT_Type *ipc_base;
    uint32_t shared_ptr = 0UL;
    uint32_t timeout = M33_M55_IPC_PREFLIGHT_TIMEOUT_MS;

    ipc_base = Cy_IPC_Drv_GetIpcBaseAddress((uint32_t)M33_M55_IPC_INTERNAL_CHANNEL);
    while (timeout > 0UL)
    {
        if ((cy_en_ipcdrv_status_t)CY_IPC_DRV_SUCCESS == Cy_IPC_Drv_LockAcquire(ipc_base))
        {
            shared_ptr = Cy_IPC_Drv_ReadDataValue(ipc_base);
            (void)Cy_IPC_Drv_LockRelease(ipc_base, CY_IPC_NO_NOTIFICATION);

            if (m33_m55_shared_ptr_is_valid(shared_ptr))
            {
                return RT_EOK;
            }

            if (shared_ptr != 0UL)
            {
                rt_kprintf("[m33_m55_comm] ignore stale shared ptr on CM55: 0x%08lx\n",
                           (unsigned long)shared_ptr);
                return -RT_ETIMEOUT;
            }
        }

        rt_thread_mdelay(1);
        timeout--;
    }

    return -RT_ETIMEOUT;
}

static void m33_m55_runtime_prepare(void)
{
    if (g_comm_runtime.runtime_ready)
    {
        return;
    }

    rt_memset(&g_comm_runtime, 0, sizeof(g_comm_runtime));
    rt_memset(&g_ipc_handle, 0, sizeof(g_ipc_handle));
    rt_memset(&g_tx_queue_handle, 0, sizeof(g_tx_queue_handle));
    rt_memset(&g_rx_queue_handle, 0, sizeof(g_rx_queue_handle));
    rt_mutex_init(&g_comm_runtime.lock, "m33m55", RT_IPC_FLAG_PRIO);
    m33_m55_ipc_enable_irqs();
    g_comm_runtime.runtime_ready = RT_TRUE;
}

static rt_err_t m33_m55_try_attach(void)
{
    cy_rslt_t result;

    m33_m55_runtime_prepare();

    if (g_comm_runtime.initialized || g_comm_runtime.attaching)
    {
        return g_comm_runtime.initialized ? RT_EOK : -RT_EBUSY;
    }

    g_comm_runtime.attaching = RT_TRUE;

    if (m33_m55_wait_for_valid_shared_ptr() != RT_EOK)
    {
        g_comm_runtime.attaching = RT_FALSE;
        return -RT_ETIMEOUT;
    }

    result = mtb_ipc_get_handle(&g_ipc_handle, &g_ipc_config, M33_M55_IPC_TIMEOUT_MS);
    if (result == CY_RSLT_SUCCESS)
    {
        result = mtb_ipc_queue_get_handle(&g_ipc_handle, &g_rx_queue_handle,
                                          M33_M55_IPC_QUEUE_CHANNEL, M33_M55_QUEUE_M33_TO_M55);
        if (result == CY_RSLT_SUCCESS)
        {
            result = mtb_ipc_queue_get_handle(&g_ipc_handle, &g_tx_queue_handle,
                                              M33_M55_IPC_QUEUE_CHANNEL, M33_M55_QUEUE_M55_TO_M33);
        }
    }

    if (result == CY_RSLT_SUCCESS)
    {
        g_comm_runtime.initialized = RT_TRUE;
        g_comm_runtime.deferred_attach = RT_FALSE;
        rt_kprintf("[m33_m55_comm] attached queues on CM55\n");
    }

    g_comm_runtime.attaching = RT_FALSE;
    return m33_m55_result_to_rt(result);
}

static void m33_m55_attach_retry_entry(void *parameter)
{
    RT_UNUSED(parameter);

    while (!g_comm_runtime.initialized)
    {
        if (g_comm_runtime.deferred_attach)
        {
            rt_err_t ret = m33_m55_try_attach();
            if ((ret != RT_EOK) && (ret != -RT_EBUSY) && (ret != -RT_ENOSYS))
            {
                rt_kprintf("[m33_m55_comm] retry attach pending on CM55 (%d)\n", ret);
            }
        }
        rt_thread_mdelay(500);
    }

    g_comm_runtime.retry_thread = RT_NULL;
}

rt_err_t m33_m55_comm_init(void)
{
    cy_rslt_t result;

    if (g_comm_runtime.initialized)
    {
        return RT_EOK;
    }

    m33_m55_runtime_prepare();

    if (m33_m55_wait_for_valid_shared_ptr() != RT_EOK)
    {
        rt_kprintf("[m33_m55_comm] initial attach waiting for CM33 shared IPC\n");
        g_comm_runtime.deferred_attach = RT_TRUE;
        if (g_comm_runtime.retry_thread == RT_NULL)
        {
            g_comm_runtime.retry_thread = rt_thread_create("ipc_att",
                                                           m33_m55_attach_retry_entry,
                                                           RT_NULL,
                                                           2048,
                                                           20,
                                                           20);
            if (g_comm_runtime.retry_thread)
            {
                rt_thread_startup(g_comm_runtime.retry_thread);
            }
        }
        return RT_EOK;
    }

    result = mtb_ipc_get_handle(&g_ipc_handle, &g_ipc_config, M33_M55_IPC_TIMEOUT_MS);
    if (result == CY_RSLT_SUCCESS)
    {
        result = mtb_ipc_queue_get_handle(&g_ipc_handle, &g_rx_queue_handle,
                                          M33_M55_IPC_QUEUE_CHANNEL, M33_M55_QUEUE_M33_TO_M55);
        if (result == CY_RSLT_SUCCESS)
        {
            result = mtb_ipc_queue_get_handle(&g_ipc_handle, &g_tx_queue_handle,
                                              M33_M55_IPC_QUEUE_CHANNEL, M33_M55_QUEUE_M55_TO_M33);
        }
    }

    if (result == CY_RSLT_SUCCESS)
    {
        g_comm_runtime.initialized = RT_TRUE;
        rt_kprintf("[m33_m55_comm] ready on CM55\n");
        return RT_EOK;
    }

    rt_kprintf("[m33_m55_comm] initial attach pending on CM55: 0x%08lx\n", (unsigned long)result);
    g_comm_runtime.deferred_attach = RT_TRUE;
    if (g_comm_runtime.retry_thread == RT_NULL)
    {
        g_comm_runtime.retry_thread = rt_thread_create("ipc_att",
                                                       m33_m55_attach_retry_entry,
                                                       RT_NULL,
                                                       2048,
                                                       20,
                                                       20);
        if (g_comm_runtime.retry_thread)
        {
            rt_thread_startup(g_comm_runtime.retry_thread);
        }
    }
    return RT_EOK;
}

rt_err_t m33_m55_comm_publish(const m33_m55_message_t *msg)
{
    m33_m55_message_t local;
    cy_rslt_t result;

    if (msg == RT_NULL)
    {
        return -RT_ERROR;
    }

    m33_m55_runtime_prepare();

    if (!g_comm_runtime.initialized)
    {
        rt_err_t ret = m33_m55_try_attach();
        if (ret != RT_EOK)
        {
            return ret;
        }
    }

    local = *msg;
    rt_mutex_take(&g_comm_runtime.lock, RT_WAITING_FOREVER);
    local.seq = ++g_comm_runtime.seq;
    rt_mutex_release(&g_comm_runtime.lock);

    result = mtb_ipc_queue_put(&g_tx_queue_handle, &local,
                               (local.type == MSG_TYPE_TTS_AUDIO) ?
                               M33_M55_TTS_PUBLISH_TIMEOUT_MS : 0);
    return m33_m55_result_to_rt(result);
}

rt_err_t m33_m55_comm_consume(m33_m55_message_t *msg)
{
    cy_rslt_t result;

    if (msg == RT_NULL)
    {
        return -RT_ERROR;
    }

    m33_m55_runtime_prepare();

    if (!g_comm_runtime.initialized)
    {
        rt_err_t ret = m33_m55_try_attach();
        if (ret != RT_EOK)
        {
            return ret;
        }
    }

    result = mtb_ipc_queue_get(&g_rx_queue_handle, msg, 0);
    return m33_m55_result_to_rt(result);
}
