#include "board.h"

#include "cy_sysint.h"

#include "smif0_guard.h"
#include "smif0_guard_protocol.h"

#define SMIF0_GUARD_PARK_TIMEOUT_SECONDS       (3UL)
#define SMIF0_GUARD_CACHE_TIMEOUT_DIVISOR      (10UL)
#define SMIF0_GUARD_MAX_WRAP_SAFE_CYCLES       (0x7FFFFFFFUL)
#define SMIF0_GUARD_CHANNEL_MASK               (1UL << SMIF0_GUARD_IPC_CHANNEL_LOCAL)
#define SMIF0_GUARD_NOTIFY_STATUS_MASK         (SMIF0_GUARD_CHANNEL_MASK << IPC_INTR_STRUCT_INTR_NOTIFY_Pos)
#define SMIF0_GUARD_RELEASE_STATUS_MASK        (SMIF0_GUARD_CHANNEL_MASK << IPC_INTR_STRUCT_INTR_RELEASE_Pos)

#define SMIF0_GUARD_IPC_STRUCT                 (&IPC1->STRUCT[SMIF0_GUARD_IPC_CHANNEL_LOCAL])
#define SMIF0_GUARD_INTR_STRUCT                (&IPC1->INTR_STRUCT[SMIF0_GUARD_IPC_INTERRUPT_LOCAL])

#define SMIF0_GUARD_RAMFUNC __attribute__((section(".cy_ramfunc"), noinline))

__attribute__((section(".smif0_guard_shared"), aligned(SMIF0_GUARD_CACHE_LINE_SIZE), used))
volatile smif0_guard_mailbox_t g_smif0_guard_mailbox;

static bool g_smif0_guard_ready;
static uint32_t g_smif0_guard_cache_budget_cycles;

static SMIF0_GUARD_RAMFUNC bool smif0_guard_request_is_valid(uint32_t operation,
                                                             uint32_t address,
                                                             uint32_t length)
{
    if ((address < SMIF0_GUARD_FLASH_OFFSET_START) ||
        (address >= SMIF0_GUARD_FLASH_OFFSET_END) ||
        (length > (SMIF0_GUARD_FLASH_OFFSET_END - address)))
    {
        return false;
    }

    if (operation == SMIF0_GUARD_OP_WRITE)
    {
        return (length != 0U) &&
               (length <= SMIF0_GUARD_WRITE_PAGE_SIZE) &&
               (((address & (SMIF0_GUARD_WRITE_PAGE_SIZE - 1U)) + length) <=
                SMIF0_GUARD_WRITE_PAGE_SIZE);
    }

    if (operation == SMIF0_GUARD_OP_ERASE)
    {
        return (length == SMIF0_GUARD_ERASE_SECTOR_SIZE) &&
               ((address & (SMIF0_GUARD_ERASE_SECTOR_SIZE - 1U)) == 0U);
    }

    return false;
}

static SMIF0_GUARD_RAMFUNC bool smif0_guard_wait_for_release(uint32_t request_seq,
                                                             uint32_t budget_cycles)
{
    const uint32_t start_cycles = DWT->CYCCNT;

    while (g_smif0_guard_mailbox.release_seq != request_seq)
    {
        if ((uint32_t)(DWT->CYCCNT - start_cycles) >= budget_cycles)
        {
            return false;
        }
    }

    __DMB();
    return true;
}

static SMIF0_GUARD_RAMFUNC bool smif0_guard_invalidate_icache(uint32_t budget_cycles)
{
    const uint32_t start_cycles = DWT->CYCCNT;

    ICACHE0->CMD = ICACHE_CMD_INV_Msk | ICACHE_CMD_BUFF_INV_Msk;
    __DSB();

    while ((ICACHE0->CMD & (ICACHE_CMD_INV_Msk | ICACHE_CMD_BUFF_INV_Msk)) != 0U)
    {
        if ((uint32_t)(DWT->CYCCNT - start_cycles) >= budget_cycles)
        {
            return false;
        }
    }

    __DSB();
    __ISB();
    return true;
}

static SMIF0_GUARD_RAMFUNC bool smif0_guard_quiesce_icache(uint32_t budget_cycles)
{
    ICACHE0->CTL &= ~ICACHE_CTL_CA_EN_Msk;
    __DSB();
    __ISB();

    if (!smif0_guard_invalidate_icache(budget_cycles))
    {
        return false;
    }

    return (ICACHE0->CTL & ICACHE_CTL_CA_EN_Msk) == 0U;
}

static SMIF0_GUARD_RAMFUNC bool smif0_guard_resume_icache(uint32_t budget_cycles)
{
    if (!smif0_guard_invalidate_icache(budget_cycles))
    {
        return false;
    }

    ICACHE0->CTL |= ICACHE_CTL_CA_EN_Msk;
    __DSB();
    __ISB();

    return (ICACHE0->CTL & ICACHE_CTL_CA_EN_Msk) != 0U;
}

__attribute__((noreturn))
static SMIF0_GUARD_RAMFUNC void smif0_guard_fatal(uint32_t request_seq, uint32_t error_code)
{
    g_smif0_guard_mailbox.state = SMIF0_GUARD_STATE_FATAL;
    g_smif0_guard_mailbox.result = SMIF0_GUARD_RESULT_FATAL;
    g_smif0_guard_mailbox.error_code = error_code;
    g_smif0_guard_mailbox.timeout_count++;
    __DMB();
    g_smif0_guard_mailbox.ack_seq = request_seq;
    g_smif0_guard_mailbox.done_seq = request_seq;
    __DSB();

    /* Keep the IPC channel locked: returning to XIP after this point is unsafe. */
    NVIC_SystemReset();
    for (;;)
    {
        __NOP();
    }
}

static SMIF0_GUARD_RAMFUNC void smif0_guard_irq_handler(void)
{
    const uint32_t interrupt_status = SMIF0_GUARD_INTR_STRUCT->INTR_MASKED;
    uint32_t request_seq;
    uint32_t operation;
    uint32_t address;
    uint32_t length;

    if ((interrupt_status & SMIF0_GUARD_NOTIFY_STATUS_MASK) == 0U)
    {
        return;
    }

    SMIF0_GUARD_INTR_STRUCT->INTR = SMIF0_GUARD_NOTIFY_STATUS_MASK;
    (void)SMIF0_GUARD_INTR_STRUCT->INTR;
    __DMB();

    request_seq = g_smif0_guard_mailbox.request_seq;
    operation = g_smif0_guard_mailbox.operation;
    address = g_smif0_guard_mailbox.address;
    length = g_smif0_guard_mailbox.length;

    if ((g_smif0_guard_mailbox.magic != SMIF0_GUARD_MAGIC) ||
        (g_smif0_guard_mailbox.version != SMIF0_GUARD_VERSION) ||
        (g_smif0_guard_mailbox.size != sizeof(smif0_guard_mailbox_t)) ||
        (g_smif0_guard_mailbox.state != SMIF0_GUARD_STATE_ONLINE) ||
        (request_seq == 0U) ||
        (request_seq == g_smif0_guard_mailbox.ack_seq) ||
        !smif0_guard_request_is_valid(operation, address, length))
    {
        g_smif0_guard_mailbox.result = SMIF0_GUARD_RESULT_INVALID;
        g_smif0_guard_mailbox.error_code = SMIF0_GUARD_ERROR_BAD_REQUEST;
        __DMB();
        g_smif0_guard_mailbox.ack_seq = request_seq;
        g_smif0_guard_mailbox.done_seq = request_seq;
        __DSB();
        SMIF0_GUARD_IPC_STRUCT->RELEASE = 0U;
        return;
    }

    if ((operation == SMIF0_GUARD_OP_ERASE) &&
        (g_smif0_guard_mailbox.safe_to_block == 0U))
    {
        g_smif0_guard_mailbox.result = SMIF0_GUARD_RESULT_BUSY;
        g_smif0_guard_mailbox.error_code = SMIF0_GUARD_ERROR_NONE;
        g_smif0_guard_mailbox.denied_count++;
        __DMB();
        g_smif0_guard_mailbox.ack_seq = request_seq;
        g_smif0_guard_mailbox.done_seq = request_seq;
        __DSB();
        SMIF0_GUARD_IPC_STRUCT->RELEASE = 0U;
        return;
    }

    if (!smif0_guard_quiesce_icache(g_smif0_guard_cache_budget_cycles))
    {
        smif0_guard_fatal(request_seq, SMIF0_GUARD_ERROR_CACHE_TIMEOUT);
    }

    g_smif0_guard_mailbox.state = SMIF0_GUARD_STATE_PARKED;
    g_smif0_guard_mailbox.result = SMIF0_GUARD_RESULT_GRANTED;
    g_smif0_guard_mailbox.error_code = SMIF0_GUARD_ERROR_NONE;
    g_smif0_guard_mailbox.grant_count++;
    __DMB();
    g_smif0_guard_mailbox.ack_seq = request_seq;
    __DSB();

    if (!smif0_guard_wait_for_release(request_seq,
                                      g_smif0_guard_mailbox.park_budget_cycles))
    {
        smif0_guard_fatal(request_seq, SMIF0_GUARD_ERROR_PARK_TIMEOUT);
    }

    if (!smif0_guard_resume_icache(g_smif0_guard_cache_budget_cycles))
    {
        smif0_guard_fatal(request_seq, SMIF0_GUARD_ERROR_CACHE_TIMEOUT);
    }

    g_smif0_guard_mailbox.result = SMIF0_GUARD_RESULT_DONE;
    g_smif0_guard_mailbox.error_code = SMIF0_GUARD_ERROR_NONE;
    g_smif0_guard_mailbox.complete_count++;
    g_smif0_guard_mailbox.state = SMIF0_GUARD_STATE_ONLINE;
    __DMB();
    g_smif0_guard_mailbox.done_seq = request_seq;
    __DSB();
    SMIF0_GUARD_IPC_STRUCT->RELEASE = 0U;
}

static bool smif0_guard_enable_cycle_counter(void)
{
    if ((DWT->CTRL & (1UL << DWT_CTRL_NOCYCCNT_Pos)) != 0U)
    {
        return false;
    }

    CoreDebug->DEMCR |= (1UL << CoreDebug_DEMCR_TRCENA_Pos);
    DWT->CYCCNT = 0U;
    DWT->CTRL |= (1UL << DWT_CTRL_CYCCNTENA_Pos);
    __DSB();
    __ISB();

    return (DWT->CTRL & (1UL << DWT_CTRL_CYCCNTENA_Pos)) != 0U;
}

static void smif0_guard_reset_mailbox(void)
{
    volatile uint32_t *word = (volatile uint32_t *)&g_smif0_guard_mailbox;
    uint32_t old_epoch = 0U;
    uint32_t index;
    uint64_t park_budget;

    if ((g_smif0_guard_mailbox.magic == SMIF0_GUARD_MAGIC) &&
        (g_smif0_guard_mailbox.version == SMIF0_GUARD_VERSION))
    {
        old_epoch = g_smif0_guard_mailbox.epoch;
    }

    for (index = 0U; index < (sizeof(g_smif0_guard_mailbox) / sizeof(uint32_t)); index++)
    {
        word[index] = 0U;
    }

    old_epoch++;
    if (old_epoch == 0U)
    {
        old_epoch = 1U;
    }

    park_budget = (uint64_t)SystemCoreClock * SMIF0_GUARD_PARK_TIMEOUT_SECONDS;
    if (park_budget > SMIF0_GUARD_MAX_WRAP_SAFE_CYCLES)
    {
        park_budget = SMIF0_GUARD_MAX_WRAP_SAFE_CYCLES;
    }
    if (park_budget == 0U)
    {
        park_budget = 1U;
    }

    g_smif0_guard_cache_budget_cycles = SystemCoreClock / SMIF0_GUARD_CACHE_TIMEOUT_DIVISOR;
    if (g_smif0_guard_cache_budget_cycles == 0U)
    {
        g_smif0_guard_cache_budget_cycles = 1U;
    }

    g_smif0_guard_mailbox.magic = SMIF0_GUARD_MAGIC;
    g_smif0_guard_mailbox.version = SMIF0_GUARD_VERSION;
    g_smif0_guard_mailbox.size = sizeof(smif0_guard_mailbox_t);
    g_smif0_guard_mailbox.epoch = old_epoch;
    g_smif0_guard_mailbox.state = SMIF0_GUARD_STATE_OFFLINE;
    g_smif0_guard_mailbox.safe_to_block = 1U;
    g_smif0_guard_mailbox.park_budget_cycles = (uint32_t)park_budget;
    __DSB();
}

void smif0_guard_early_init(void)
{
    const cy_stc_sysint_t interrupt_config =
    {
        .intrSrc = (IRQn_Type)CY_IPC_INTR_MUX(SMIF0_GUARD_IPC_INTERRUPT),
        .intrPriority = 0U
    };

    g_smif0_guard_ready = false;
    smif0_guard_reset_mailbox();

    if (!smif0_guard_enable_cycle_counter())
    {
        g_smif0_guard_mailbox.state = SMIF0_GUARD_STATE_FATAL;
        g_smif0_guard_mailbox.result = SMIF0_GUARD_RESULT_FATAL;
        g_smif0_guard_mailbox.error_code = SMIF0_GUARD_ERROR_NO_CYCCNT;
        __DSB();
        return;
    }

    SMIF0_GUARD_INTR_STRUCT->INTR_MASK = 0U;
    SMIF0_GUARD_INTR_STRUCT->INTR = SMIF0_GUARD_NOTIFY_STATUS_MASK |
                                     SMIF0_GUARD_RELEASE_STATUS_MASK;
    (void)SMIF0_GUARD_INTR_STRUCT->INTR;

    if (Cy_SysInt_Init(&interrupt_config, smif0_guard_irq_handler) != CY_SYSINT_SUCCESS)
    {
        g_smif0_guard_mailbox.state = SMIF0_GUARD_STATE_FATAL;
        g_smif0_guard_mailbox.result = SMIF0_GUARD_RESULT_FATAL;
        g_smif0_guard_mailbox.error_code = SMIF0_GUARD_ERROR_IRQ_INIT;
        __DSB();
        return;
    }

    SMIF0_GUARD_INTR_STRUCT->INTR_MASK = SMIF0_GUARD_NOTIFY_STATUS_MASK;
    NVIC_ClearPendingIRQ((IRQn_Type)CY_IPC_INTR_MUX(SMIF0_GUARD_IPC_INTERRUPT));
    NVIC_EnableIRQ((IRQn_Type)CY_IPC_INTR_MUX(SMIF0_GUARD_IPC_INTERRUPT));
    g_smif0_guard_ready = true;
}

void smif0_guard_set_safe_to_block(bool safe_to_block)
{
    g_smif0_guard_mailbox.safe_to_block = safe_to_block ? 1U : 0U;
    __DMB();
}

static void smif0_guard_mark_online(void)
{
    g_smif0_guard_mailbox.result = SMIF0_GUARD_RESULT_NONE;
    g_smif0_guard_mailbox.error_code = SMIF0_GUARD_ERROR_NONE;
    g_smif0_guard_mailbox.state = SMIF0_GUARD_STATE_ONLINE;
    __DSB();
}

static int smif0_guard_start_cm55(void)
{
    if (!g_smif0_guard_ready)
    {
        return -RT_ERROR;
    }

    smif0_guard_mark_online();
#ifdef SOC_Enable_CM55
    Cy_SysEnableCM55(MXCM55, CY_CM55_APP_BOOT_ADDR, 10);
#ifdef SOC_Enable_CM33_DeepSleep
    for (;;)
    {
        Cy_SysPm_CpuEnterDeepSleep(CY_SYSPM_WAIT_FOR_INTERRUPT);
    }
#endif
#endif
    return RT_EOK;
}
INIT_PREV_EXPORT(smif0_guard_start_cm55);
