#include "m33_m55_comm.h"

#include <board.h>

#include "cy_sysint.h"
#include "mtb_ipc.h"

#define M33_M55_IPC_INTERNAL_CHANNEL     MTB_IPC_CHAN_1
#define M33_M55_IPC_QUEUE_CHANNEL        MTB_IPC_CHAN_0
#define M33_M55_IPC_INSTANCE_SEMA        (5UL)
#define M33_M55_QUEUE_M33_TO_M55         (0UL)
#define M33_M55_QUEUE_M55_TO_M33         (1UL)
#define M33_M55_QUEUE_SEMA_M33_TO_M55    (6UL)
#define M33_M55_QUEUE_SEMA_M55_TO_M33    (7UL)
#define M33_M55_QUEUE_DEPTH              (5UL)

#define M33_M55_IPC_IRQ_SEMA             (MTB_IPC_IRQ_USER + 4)
#define M33_M55_IPC_IRQ_QUEUE            (MTB_IPC_IRQ_USER + 5)

typedef struct
{
    rt_bool_t initialized;
    rt_uint32_t seq;
    struct rt_mutex lock;
    mtb_ipc_t ipc;
    mtb_ipc_queue_t tx_queue;
    mtb_ipc_queue_t rx_queue;
} m33_m55_comm_runtime_t;

static m33_m55_comm_runtime_t g_comm_runtime;
__attribute__((section(".cy_shared_socmem"), aligned(32)))
volatile m33_m55_pcm_shared_t g_m33_m55_pcm_shared;

CY_SECTION_SHAREDMEM static mtb_ipc_shared_t g_m33_m55_shared_data _MTB_IPC_DATA_ALIGN;
CY_SECTION_SHAREDMEM static mtb_ipc_queue_data_t g_m33_to_m55_queue_data _MTB_IPC_DATA_ALIGN;
CY_SECTION_SHAREDMEM static mtb_ipc_queue_data_t g_m55_to_m33_queue_data _MTB_IPC_DATA_ALIGN;
CY_SECTION_SHAREDMEM static uint8_t g_m33_to_m55_queue_pool[M33_M55_QUEUE_DEPTH * sizeof(m33_m55_message_t)] _MTB_IPC_DATA_ALIGN;
CY_SECTION_SHAREDMEM static uint8_t g_m55_to_m33_queue_pool[M33_M55_QUEUE_DEPTH * sizeof(m33_m55_message_t)] _MTB_IPC_DATA_ALIGN;

static const mtb_ipc_config_t g_ipc_config = {
    .internal_channel_index = M33_M55_IPC_INTERNAL_CHANNEL,
    .semaphore_irq = M33_M55_IPC_IRQ_SEMA,
    .queue_irq = M33_M55_IPC_IRQ_QUEUE,
    .semaphore_num = M33_M55_IPC_INSTANCE_SEMA
};

static const mtb_ipc_queue_config_t g_queue_cfg_m33_to_m55 = {
    .channel_num = M33_M55_IPC_QUEUE_CHANNEL,
    .queue_num = M33_M55_QUEUE_M33_TO_M55,
    .max_num_items = M33_M55_QUEUE_DEPTH,
    .item_size = sizeof(m33_m55_message_t),
    .queue_pool = g_m33_to_m55_queue_pool,
    .semaphore_num = M33_M55_QUEUE_SEMA_M33_TO_M55
};

static const mtb_ipc_queue_config_t g_queue_cfg_m55_to_m33 = {
    .channel_num = M33_M55_IPC_QUEUE_CHANNEL,
    .queue_num = M33_M55_QUEUE_M55_TO_M33,
    .max_num_items = M33_M55_QUEUE_DEPTH,
    .item_size = sizeof(m33_m55_message_t),
    .queue_pool = g_m55_to_m33_queue_pool,
    .semaphore_num = M33_M55_QUEUE_SEMA_M55_TO_M33
};

static void m33_m55_ipc_semaphore_irq_handler(void)
{
    mtb_ipc_semaphore_process_interrupt(&g_comm_runtime.ipc);
}

static void m33_m55_ipc_queue_irq_handler(void)
{
    mtb_ipc_queue_process_interrupt(&g_comm_runtime.ipc);
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
    return -RT_ERROR;
}

rt_err_t m33_m55_comm_init(void)
{
    cy_rslt_t result;

    if (g_comm_runtime.initialized)
    {
        return RT_EOK;
    }

    rt_memset(&g_comm_runtime, 0, sizeof(g_comm_runtime));
    rt_mutex_init(&g_comm_runtime.lock, "m33m55", RT_IPC_FLAG_PRIO);
    m33_m55_ipc_enable_irqs();

    rt_memset(&g_m33_m55_shared_data, 0, sizeof(g_m33_m55_shared_data));
    rt_memset(&g_m33_to_m55_queue_data, 0, sizeof(g_m33_to_m55_queue_data));
    rt_memset(&g_m55_to_m33_queue_data, 0, sizeof(g_m55_to_m33_queue_data));
    rt_memset(g_m33_to_m55_queue_pool, 0, sizeof(g_m33_to_m55_queue_pool));
    rt_memset(g_m55_to_m33_queue_pool, 0, sizeof(g_m55_to_m33_queue_pool));

    result = mtb_ipc_init(&g_comm_runtime.ipc, &g_m33_m55_shared_data, &g_ipc_config);
    if (result != CY_RSLT_SUCCESS)
    {
        rt_kprintf("[m33_m55_comm] mtb_ipc_init failed on CM33: 0x%08lx\n", (unsigned long)result);
        return m33_m55_result_to_rt(result);
    }

    result = mtb_ipc_queue_init(&g_comm_runtime.ipc, &g_comm_runtime.tx_queue,
                                &g_m33_to_m55_queue_data, &g_queue_cfg_m33_to_m55);
    if (result != CY_RSLT_SUCCESS)
    {
        rt_kprintf("[m33_m55_comm] queue_init tx failed on CM33: 0x%08lx\n", (unsigned long)result);
        return m33_m55_result_to_rt(result);
    }

    result = mtb_ipc_queue_init(&g_comm_runtime.ipc, &g_comm_runtime.rx_queue,
                                &g_m55_to_m33_queue_data, &g_queue_cfg_m55_to_m33);
    if (result != CY_RSLT_SUCCESS)
    {
        rt_kprintf("[m33_m55_comm] queue_init rx failed on CM33: 0x%08lx\n", (unsigned long)result);
        return m33_m55_result_to_rt(result);
    }

    g_comm_runtime.initialized = RT_TRUE;
    rt_kprintf("[m33_m55_comm] ready on CM33\n");
    return RT_EOK;
}

rt_err_t m33_m55_comm_publish(const m33_m55_message_t *msg)
{
    m33_m55_message_t local;
    cy_rslt_t result;
    uint32_t timeout_ms = 0;

    if ((msg == RT_NULL) || !g_comm_runtime.initialized)
    {
        return -RT_ERROR;
    }

    local = *msg;
    rt_mutex_take(&g_comm_runtime.lock, RT_WAITING_FOREVER);
    local.seq = ++g_comm_runtime.seq;
    rt_mutex_release(&g_comm_runtime.lock);

    if ((local.type == MSG_TYPE_AUDIO_DATA) ||
        ((local.type == MSG_TYPE_SENSOR_STREAM) &&
         (local.payload.sensor_stream.source == MODEL_INPUT_SRC_AUDIO_PCM)) ||
        (local.type == MSG_TYPE_ASR_TEXT) ||
        (local.type == MSG_TYPE_TTS_REQUEST))
    {
        timeout_ms = 5000;
    }

    result = mtb_ipc_queue_put(&g_comm_runtime.tx_queue, &local, timeout_ms);
    return m33_m55_result_to_rt(result);
}

rt_err_t m33_m55_comm_consume(m33_m55_message_t *msg)
{
    cy_rslt_t result;

    if ((msg == RT_NULL) || !g_comm_runtime.initialized)
    {
        return -RT_ERROR;
    }

    result = mtb_ipc_queue_get(&g_comm_runtime.rx_queue, msg, 0);
    return m33_m55_result_to_rt(result);
}

rt_bool_t m33_m55_comm_is_ready(void)
{
    return g_comm_runtime.initialized;
}

rt_uint32_t m33_m55_comm_rx_count(void)
{
    return g_comm_runtime.initialized ? mtb_ipc_queue_count(&g_comm_runtime.rx_queue) : 0U;
}

rt_uint32_t m33_m55_comm_tx_count(void)
{
    return g_comm_runtime.initialized ? mtb_ipc_queue_count(&g_comm_runtime.tx_queue) : 0U;
}
