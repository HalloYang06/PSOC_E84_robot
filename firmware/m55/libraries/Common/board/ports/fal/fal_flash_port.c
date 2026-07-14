/*
 * Copyright (c) 2006-2018, RT-Thread Development Team
 *
 * SPDX-License-Identifier: Apache-2.0
 */

#include <fal.h>
#include <stdint.h>
#include <string.h>

#include "cy_smif.h"
#include "cycfg_qspi_memslot.h"
#include "smif0_guard_client.h"

#if defined(BSP_USING_LVGL)
#include "lv_port_disp.h"
#else
static rt_err_t lv_port_disp_smif0_quiesce(void)
{
    return RT_EOK;
}

static void lv_port_disp_smif0_resume(void)
{
}
#endif

#define LOG_TAG                "drv.fal_flash"
#include <drv_log.h>

#define smifMemConfigs         smif0MemConfigs
#define MEM_SLOT_NUM           (0U)

#ifndef FAL_USING_NOR_FLASH_DEV_NAME
#define FAL_USING_NOR_FLASH_DEV_NAME    "norflash0"
#endif

#define SMIF_BASE_ADDRESS      (0x60000000UL)
#define FLASH_START_ADDRESS    (0x60DC0000UL)
#define FLASH_SIZE             (2U * 1024U * 1024U)
#define FLASH_SECTOR_SIZE      (64U * 1024U)
#define FLASH_PAGE_SIZE        (256U)
#define FLASH_END_ADDRESS      (FLASH_START_ADDRESS + FLASH_SIZE)
#define SMIF_DEVICE_OFFSET     (FLASH_START_ADDRESS - SMIF_BASE_ADDRESS)
#define SMIF0_GUARD_MAILBOX    \
    ((volatile smif0_guard_mailbox_t *)(uintptr_t)SMIF0_GUARD_SHARED_ADDRESS)

#define FAL_SMIF_RAMFUNC       __attribute__((section(".cy_ramfunc"), noinline))
#define SMIF0_GUARD_CACHE_WAIT_BUDGET (1000000UL)

/*
 * A nonzero poll delay keeps Cy_SMIF_MemIsReady() on the ITCM-resident
 * Cy_SysLib_Rtos_DelayUs() path while command mode has XIP disabled.
 */
static cy_stc_smif_context_t smif_context =
{
    .timeout = 1000000U,
    .memReadyPollDelay = 100U
};

/* The command leaf must never dereference a caller buffer that might be in XIP. */
static uint8_t g_smif0_page_buffer[FLASH_PAGE_SIZE];

static int init(void);
static int read(long offset, uint8_t *buf, size_t size);
static int write(long offset, const uint8_t *buf, size_t size);
static int erase(long offset, size_t size);

struct rt_device *flash_dev;
struct fal_flash_dev nor_flash0 =
{
    .name       = FAL_USING_NOR_FLASH_DEV_NAME,
    .addr       = FLASH_START_ADDRESS,
    .len        = FLASH_SIZE,
    .blk_size   = FLASH_SECTOR_SIZE,
    .ops        = {init, read, write, erase},
    .write_gran = 1
};

__attribute__((noreturn))
static FAL_SMIF_RAMFUNC void smif0_guard_command_fatal_reset(void)
{
    /* Never release CM33 or return to XIP while flash readiness is uncertain. */
    __DSB();
    NVIC_SystemReset();
    for (;;)
    {
        __NOP();
    }
}

static FAL_SMIF_RAMFUNC bool smif0_guard_wait_smif_idle(void)
{
    uint32_t budget = SMIF0_GUARD_CACHE_WAIT_BUDGET;

    while ((SMIF_STATUS(SMIF0_CORE) & SMIF_STATUS_BUSY_Msk) != 0U)
    {
        if (budget == 0U)
        {
            return false;
        }
        budget--;
    }

    __DSB();
    return true;
}

static FAL_SMIF_RAMFUNC bool smif0_guard_wait_cache_invalidate(void)
{
    uint32_t budget = SMIF0_GUARD_CACHE_WAIT_BUDGET;

    while (((SMIF_SLOW_CA_CMD(SMIF0_CORE) & SMIF_SLOW_CA_CMD_INV_Msk) != 0U) ||
           ((SMIF_FAST_CA_CMD(SMIF0_CORE) & SMIF_FAST_CA_CMD_INV_Msk) != 0U))
    {
        if (budget == 0U)
        {
            return false;
        }
        budget--;
    }

    __DSB();
    return true;
}

static FAL_SMIF_RAMFUNC void smif0_guard_execute_command(smif0_guard_operation_t operation,
                                                         uint32_t address,
                                                         const uint8_t *buffer,
                                                         uint32_t length,
                                                         uint32_t request_seq)
{
    const uint32_t saved_primask = __get_PRIMASK();
    const ExecFuncPtrRw saved_nmi_vector = __ns_vector_table_rw[2U];
    const ExecFuncPtrRw saved_hardfault_vector = __ns_vector_table_rw[3U];
    const bool icache_was_enabled = (SCB->CCR & SCB_CCR_IC_Msk) != 0U;
    cy_en_smif_status_t result;

    __disable_irq();

    /* PRIMASK cannot mask NMI/HardFault; route both to the ITCM reset path. */
    __ns_vector_table_rw[2U] = smif0_guard_command_fatal_reset;
    __ns_vector_table_rw[3U] = smif0_guard_command_fatal_reset;
    SCB_DisableICache();
    __DSB();
    __ISB();

    Cy_SMIF_SetMode(SMIF0_CORE, CY_SMIF_NORMAL);
    __DSB();
    __ISB();

    if (operation == SMIF0_GUARD_OP_WRITE)
    {
        result = Cy_SMIF_MemWrite(SMIF0_CORE,
                                  smifMemConfigs[MEM_SLOT_NUM],
                                  address,
                                  buffer,
                                  length,
                                  &smif_context);
    }
    else if (operation == SMIF0_GUARD_OP_ERASE)
    {
        result = Cy_SMIF_MemEraseSector(SMIF0_CORE,
                                        smifMemConfigs[MEM_SLOT_NUM],
                                        address,
                                        length,
                                        &smif_context);
    }
    else
    {
        result = CY_SMIF_BAD_PARAM;
    }

    if (result != CY_SMIF_SUCCESS)
    {
        smif0_guard_command_fatal_reset();
    }

    Cy_SMIF_SetMode(SMIF0_CORE, CY_SMIF_MEMORY);
    if (!smif0_guard_wait_smif_idle())
    {
        smif0_guard_command_fatal_reset();
    }
    if (Cy_SMIF_CacheInvalidate(SMIF0_CORE, CY_SMIF_CACHE_BOTH) != CY_SMIF_SUCCESS)
    {
        smif0_guard_command_fatal_reset();
    }
    __DSB();
    if (!smif0_guard_wait_cache_invalidate())
    {
        smif0_guard_command_fatal_reset();
    }

    SCB_InvalidateDCache_by_Addr((void *)(uintptr_t)(SMIF_BASE_ADDRESS + address),
                                (int32_t)length);
    __DSB();
    __ISB();

    if (icache_was_enabled)
    {
        SCB_EnableICache();
    }
    else
    {
        SCB_InvalidateICache();
    }

    __ns_vector_table_rw[2U] = saved_nmi_vector;
    __ns_vector_table_rw[3U] = saved_hardfault_vector;
    __DSB();
    __ISB();

    __DMB();
    SMIF0_GUARD_MAILBOX->release_seq = request_seq;
    __DSB();
    __set_PRIMASK(saved_primask);
}

static int init(void)
{
    if (smif0_guard_client_init() != RT_EOK)
    {
        LOG_E("SMIF0 guard client init failed");
        return -RT_ERROR;
    }

    LOG_D("FAL XIP flash ready: page=%u sector=%u",
          (unsigned int)FLASH_PAGE_SIZE,
          (unsigned int)FLASH_SECTOR_SIZE);
    return 0;
}

static int read(long offset, uint8_t *buf, size_t size)
{
    rt_err_t status;

    if ((buf == RT_NULL) || (offset < 0) ||
        (size > FLASH_SIZE) || ((size_t)offset > (FLASH_SIZE - size)))
    {
        return -RT_EINVAL;
    }
    if (size == 0U)
    {
        return 0;
    }

    status = smif0_guard_client_lock();
    if (status != RT_EOK)
    {
        return status;
    }

    SCB_InvalidateDCache_by_Addr((void *)(uintptr_t)(FLASH_START_ADDRESS + (uint32_t)offset),
                                (int32_t)size);
    memcpy(buf, (const void *)(uintptr_t)(FLASH_START_ADDRESS + (uint32_t)offset), size);

    smif0_guard_client_unlock();
    return (int)size;
}

static int write(long offset, const uint8_t *buf, size_t size)
{
    size_t remaining = size;
    size_t completed = 0U;
    uint32_t current_address;
    rt_err_t status;

    if ((buf == RT_NULL) || (offset < 0) ||
        (size > FLASH_SIZE) || ((size_t)offset > (FLASH_SIZE - size)))
    {
        return -RT_EINVAL;
    }
    if (size == 0U)
    {
        return 0;
    }

    status = lv_port_disp_smif0_quiesce();
    if (status != RT_EOK)
    {
        return status;
    }

    status = smif0_guard_client_lock();
    if (status != RT_EOK)
    {
        lv_port_disp_smif0_resume();
        return status;
    }

    current_address = SMIF_DEVICE_OFFSET + (uint32_t)offset;
    while (remaining > 0U)
    {
        const size_t page_remaining =
            FLASH_PAGE_SIZE - (current_address & (FLASH_PAGE_SIZE - 1U));
        const size_t chunk = (remaining < page_remaining) ? remaining : page_remaining;
        uint32_t request_seq;

        memcpy(g_smif0_page_buffer, buf + completed, chunk);
        __DMB();

        status = smif0_guard_client_acquire(SMIF0_GUARD_OP_WRITE,
                                            current_address,
                                            (uint32_t)chunk,
                                            &request_seq);
        if (status != RT_EOK)
        {
            if (status == -RT_ETIMEOUT)
            {
                smif0_guard_command_fatal_reset();
            }
            break;
        }

        smif0_guard_execute_command(SMIF0_GUARD_OP_WRITE,
                                    current_address,
                                    g_smif0_page_buffer,
                                    (uint32_t)chunk,
                                    request_seq);

        status = smif0_guard_client_release(request_seq);
        if (status != RT_EOK)
        {
            smif0_guard_command_fatal_reset();
        }

        current_address += (uint32_t)chunk;
        completed += chunk;
        remaining -= chunk;
    }

    smif0_guard_client_unlock();
    lv_port_disp_smif0_resume();
    return (status == RT_EOK) ? (int)size : status;
}

static int erase(long offset, size_t size)
{
    size_t remaining = size;
    uint32_t current_address;
    rt_err_t status;

    if ((offset < 0) || (size > FLASH_SIZE) ||
        ((size_t)offset > (FLASH_SIZE - size)) ||
        (((size_t)offset % FLASH_SECTOR_SIZE) != 0U) ||
        ((size % FLASH_SECTOR_SIZE) != 0U))
    {
        return -RT_EINVAL;
    }
    if (size == 0U)
    {
        return 0;
    }

    status = lv_port_disp_smif0_quiesce();
    if (status != RT_EOK)
    {
        return status;
    }

    status = smif0_guard_client_lock();
    if (status != RT_EOK)
    {
        lv_port_disp_smif0_resume();
        return status;
    }

    current_address = SMIF_DEVICE_OFFSET + (uint32_t)offset;
    while (remaining > 0U)
    {
        uint32_t request_seq;

        status = smif0_guard_client_acquire(SMIF0_GUARD_OP_ERASE,
                                            current_address,
                                            FLASH_SECTOR_SIZE,
                                            &request_seq);
        if (status != RT_EOK)
        {
            if (status == -RT_ETIMEOUT)
            {
                smif0_guard_command_fatal_reset();
            }
            break;
        }

        smif0_guard_execute_command(SMIF0_GUARD_OP_ERASE,
                                    current_address,
                                    RT_NULL,
                                    FLASH_SECTOR_SIZE,
                                    request_seq);

        status = smif0_guard_client_release(request_seq);
        if (status != RT_EOK)
        {
            smif0_guard_command_fatal_reset();
        }

        current_address += FLASH_SECTOR_SIZE;
        remaining -= FLASH_SECTOR_SIZE;
    }

    smif0_guard_client_unlock();
    lv_port_disp_smif0_resume();
    return (status == RT_EOK) ? (int)size : status;
}
