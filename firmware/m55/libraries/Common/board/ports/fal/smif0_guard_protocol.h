/*
 * Shared CM33/CM55 protocol for exclusive SMIF0 command-mode access.
 *
 * Keep this file byte-for-byte identical in both core projects.  Each writable
 * cache line has exactly one owner; the mailbox itself lives in non-cacheable
 * shared SRAM on the current PSE84 memory map.
 */
#ifndef __SMIF0_GUARD_PROTOCOL_H__
#define __SMIF0_GUARD_PROTOCOL_H__

#include <stddef.h>
#include <stdint.h>

#include "cy_device.h"

#ifdef __cplusplus
extern "C" {
#endif

#define SMIF0_GUARD_SHARED_ADDRESS          (0x261FFF00UL)
#define SMIF0_GUARD_SHARED_SLOT_SIZE        (0x100UL)
#define SMIF0_GUARD_CACHE_LINE_SIZE         (32UL)

#define SMIF0_GUARD_IPC_CHANNEL             (CY_IPC_CHAN_USER + 2U)
#define SMIF0_GUARD_IPC_INTERRUPT           (CY_IPC_INTR_USER + 6U)
#define SMIF0_GUARD_IPC_CHANNEL_LOCAL       (SMIF0_GUARD_IPC_CHANNEL % CY_IPC_CHANNELS_PER_INSTANCE)
#define SMIF0_GUARD_IPC_INTERRUPT_LOCAL     (SMIF0_GUARD_IPC_INTERRUPT % CY_IPC_INTERRUPTS_PER_INSTANCE)

#define SMIF0_GUARD_MAGIC                   (0x30474D53UL) /* "SMG0" */
#define SMIF0_GUARD_VERSION                 (1UL)
#define SMIF0_GUARD_MAILBOX_SIZE            (128UL)
#define SMIF0_GUARD_FLASH_OFFSET_START      (0x00DC0000UL)
#define SMIF0_GUARD_FLASH_SIZE              (2UL * 1024UL * 1024UL)
#define SMIF0_GUARD_FLASH_OFFSET_END        (SMIF0_GUARD_FLASH_OFFSET_START + SMIF0_GUARD_FLASH_SIZE)
#define SMIF0_GUARD_WRITE_PAGE_SIZE         (256UL)
#define SMIF0_GUARD_ERASE_SECTOR_SIZE       (64UL * 1024UL)

typedef enum
{
    SMIF0_GUARD_STATE_OFFLINE = 0U,
    SMIF0_GUARD_STATE_ONLINE  = 1U,
    SMIF0_GUARD_STATE_PARKED  = 2U,
    SMIF0_GUARD_STATE_FATAL   = 3U
} smif0_guard_state_t;

typedef enum
{
    SMIF0_GUARD_OP_NONE  = 0U,
    SMIF0_GUARD_OP_WRITE = 1U,
    SMIF0_GUARD_OP_ERASE = 2U
} smif0_guard_operation_t;

typedef enum
{
    SMIF0_GUARD_RESULT_NONE    = 0U,
    SMIF0_GUARD_RESULT_GRANTED = 1U,
    SMIF0_GUARD_RESULT_DONE    = 2U,
    SMIF0_GUARD_RESULT_BUSY    = 3U,
    SMIF0_GUARD_RESULT_INVALID = 4U,
    SMIF0_GUARD_RESULT_TIMEOUT = 5U,
    SMIF0_GUARD_RESULT_FATAL   = 6U
} smif0_guard_result_t;

typedef enum
{
    SMIF0_GUARD_ERROR_NONE          = 0U,
    SMIF0_GUARD_ERROR_BAD_REQUEST   = 1U,
    SMIF0_GUARD_ERROR_PARK_TIMEOUT  = 2U,
    SMIF0_GUARD_ERROR_CACHE_TIMEOUT = 3U,
    SMIF0_GUARD_ERROR_NO_CYCCNT     = 4U,
    SMIF0_GUARD_ERROR_IRQ_INIT      = 5U
} smif0_guard_error_t;

typedef struct
{
    /* Cache line 0: CM33-owned control. */
    uint32_t magic;
    uint32_t version;
    uint32_t size;
    uint32_t epoch;
    uint32_t state;
    uint32_t safe_to_block;
    uint32_t park_budget_cycles;
    uint32_t flags;

    /* Cache line 1: CM55-owned request. */
    uint32_t request_seq;
    uint32_t release_seq;
    uint32_t operation;
    uint32_t address;
    uint32_t length;
    uint32_t request_reserved[3];

    /* Cache line 2: CM33-owned response and counters. */
    uint32_t ack_seq;
    uint32_t done_seq;
    uint32_t result;
    uint32_t error_code;
    uint32_t denied_count;
    uint32_t timeout_count;
    uint32_t grant_count;
    uint32_t complete_count;

    /* Cache line 3: reserved for protocol-compatible diagnostics. */
    uint32_t reserved[8];
} smif0_guard_mailbox_t;

#if defined(__cplusplus)
#define SMIF0_GUARD_STATIC_ASSERT(condition, message) static_assert((condition), message)
#else
#define SMIF0_GUARD_STATIC_ASSERT(condition, message) _Static_assert((condition), message)
#endif

SMIF0_GUARD_STATIC_ASSERT(SMIF0_GUARD_IPC_CHANNEL == 19U, "SMIF0 guard must use IPC1 channel 19");
SMIF0_GUARD_STATIC_ASSERT(SMIF0_GUARD_IPC_INTERRUPT == 15U, "SMIF0 guard must use IPC1 interrupt 15");
SMIF0_GUARD_STATIC_ASSERT(sizeof(smif0_guard_mailbox_t) == SMIF0_GUARD_MAILBOX_SIZE,
                          "SMIF0 guard mailbox layout changed");
SMIF0_GUARD_STATIC_ASSERT(sizeof(smif0_guard_mailbox_t) <= 128U,
                          "SMIF0 guard mailbox exceeds four cache lines");
SMIF0_GUARD_STATIC_ASSERT(offsetof(smif0_guard_mailbox_t, request_seq) == 32U,
                          "CM55 request line must start at offset 32");
SMIF0_GUARD_STATIC_ASSERT(offsetof(smif0_guard_mailbox_t, ack_seq) == 64U,
                          "CM33 response line must start at offset 64");
SMIF0_GUARD_STATIC_ASSERT(offsetof(smif0_guard_mailbox_t, reserved) == 96U,
                          "reserved line must start at offset 96");

#undef SMIF0_GUARD_STATIC_ASSERT

#ifdef __cplusplus
}
#endif

#endif /* __SMIF0_GUARD_PROTOCOL_H__ */
