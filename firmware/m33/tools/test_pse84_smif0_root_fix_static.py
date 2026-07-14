from pathlib import Path
import re
import unittest


M33_ROOT = Path(__file__).resolve().parents[1]
WORKSPACE = M33_ROOT.parent
if (WORKSPACE / "m55").is_dir():
    # PSOC_E84_robot monorepo layout: firmware/m33 + firmware/m55.
    M55_ROOT = WORKSPACE / "m55"
    SECURE_ROOT = M33_ROOT
else:
    # RT-Thread Studio workspace layout with three sibling projects.
    M55_ROOT = WORKSPACE / "Edgi_Talk_M55_Blink_LED"
    SECURE_ROOT = WORKSPACE / "secureCore"


def read(path: Path) -> str:
    if not path.is_file():
        return ""
    return path.read_text(encoding="utf-8", errors="ignore")


def function_body(text: str, signature: str) -> str:
    match = re.search(re.escape(signature) + r"[^;{]*\{", text)
    if match is None:
        raise AssertionError(f"function not found: {signature}")
    start = match.start()
    brace = text.index("{", start)
    depth = 0
    for index in range(brace, len(text)):
        if text[index] == "{":
            depth += 1
        elif text[index] == "}":
            depth -= 1
            if depth == 0:
                return text[start:index + 1]
    raise AssertionError(f"unterminated function: {signature}")


class Pse84Smif0RootFixStaticTest(unittest.TestCase):
    def test_secure_reset_reenables_icache_after_invalidate(self):
        source = read(
            SECURE_ROOT
            / "libs/TARGET_APP_KIT_PSE84_EVAL_EPC2/COMPONENT_CM33"
            / "COMPONENT_SECURE_DEVICE/s_start_pse84.c"
        )
        reset = function_body(source, "void S_Reset_Handler(void)")

        disable = reset.index("~ICACHE_CTL_CA_EN_Msk")
        invalidate = reset.index("ICACHE_CMD_INV_Msk | ICACHE_CMD_BUFF_INV_Msk")
        enable_matches = list(
            re.finditer(r"ICACHE0->CTL\s*=.*\|\s*ICACHE_CTL_CA_EN_Msk", reset)
        )

        self.assertTrue(enable_matches, "Secure reset must re-enable M33 I-cache")
        enable = enable_matches[-1].start()
        self.assertLess(disable, invalidate)
        self.assertLess(invalidate, enable)
        self.assertIn("__DSB();", reset[enable:])
        self.assertIn("__ISB();", reset[enable:])
        self.assertNotIn("Keep the instruction cache disabled", reset)
        self.assertIn("#define SECURE_FAULT_RAMFUNC", source)
        for handler in (
            "SysLib_FaultHandler",
            "S_NMIException_Handler",
            "S_HardFault_Handler",
            "S_MemManage_Handler",
            "S_BusFault_Handler",
            "S_UsageFault_Handler",
            "S_SecureFault_Handler",
        ):
            self.assertRegex(
                source,
                rf"SECURE_FAULT_RAMFUNC\s+void\s+{handler}\s*\(",
            )

        partition = read(
            SECURE_ROOT
            / "libs/TARGET_APP_KIT_PSE84_EVAL_EPC2/COMPONENT_CM33"
            / "COMPONENT_SECURE_DEVICE/partition_ARMCM33.h"
        )
        self.assertRegex(partition, r"SCB_AIRCR_BFHFNMINS_VAL\s+0")

    def test_m33_start_checks_icache_command_is_idle(self):
        flow = read(M33_ROOT / "tools/openocd/pse84_m33_verified_flash.tcl")
        start = flow.index("proc m33_start_ns {} {")
        end = flow.index("proc m33_compare_alias", start)
        start_ns = flow[start:end]

        self.assertIn(
            "set cmd [ifx::read32 cat1d.sys33 0x42223008]",
            start_ns,
        )
        self.assertIn("if {($cmd & 0x3) != 0}", start_ns)

    def test_flash_script_compares_secure_sources_independent_of_line_endings(self):
        script = read(M33_ROOT / "tools/flash_m33_verified.ps1")

        self.assertIn("[string]$EdgeProtectToolsPath", script)
        self.assertIn("function Read-NormalizedText", script)
        self.assertIn('.Replace("`r`n", "`n").Replace("`r", "`n")', script)
        self.assertIn("[System.StringComparison]::Ordinal", script)
        self.assertNotIn("$trackedSecureStartupHash", script)

    def test_m33_guard_is_installed_before_deferred_cm55_boot(self):
        board = read(M33_ROOT / "board/board.c")
        guard_source = read(M33_ROOT / "board/smif0_guard.c")
        init = function_body(board, "void cy_bsp_all_init(void)")

        cybsp = init.index("cybsp_init()")
        guard = init.index("smif0_guard_early_init()")

        self.assertLess(cybsp, guard)
        self.assertNotIn("Cy_SysEnableCM55", init)
        start = function_body(guard_source, "static int smif0_guard_start_cm55(")
        self.assertLess(start.index("smif0_guard_mark_online"), start.index("Cy_SysEnableCM55"))
        self.assertIn("INIT_PREV_EXPORT(smif0_guard_start_cm55)", guard_source)

    def test_m33_guard_critical_path_is_internal_ram_and_bounded(self):
        protocol = read(M33_ROOT / "board/smif0_guard_protocol.h")
        source = read(M33_ROOT / "board/smif0_guard.c")
        linker = read(M33_ROOT / "board/linker_scripts/link.ld")
        irq = function_body(source, "static SMIF0_GUARD_RAMFUNC void smif0_guard_irq_handler(")

        self.assertIn("0x261FFF00", protocol)
        self.assertIn("CY_IPC_CHAN_USER + 2", protocol)
        self.assertIn("CY_IPC_INTR_USER + 6", protocol)
        self.assertIn(".cy_ramfunc", source)
        self.assertIn("DWT->CYCCNT", source)
        self.assertIn("NVIC_SystemReset", source)
        self.assertIn(
            "ICACHE0->CMD = ICACHE_CMD_INV_Msk | ICACHE_CMD_BUFF_INV_Msk",
            source,
        )
        self.assertIn(
            "ICACHE0->CMD & (ICACHE_CMD_INV_Msk | ICACHE_CMD_BUFF_INV_Msk)",
            source,
        )
        self.assertIn("SMIF0 guard mailbox overlaps shared data", linker)
        self.assertIn("smif0_guard_quiesce_icache", source)
        self.assertIn("smif0_guard_resume_icache", source)
        quiesce = irq.index("smif0_guard_quiesce_icache")
        parked = irq.index("g_smif0_guard_mailbox.state = SMIF0_GUARD_STATE_PARKED")
        release_wait = irq.index("smif0_guard_wait_for_release")
        resume = irq.index("smif0_guard_resume_icache")
        done = irq.index("g_smif0_guard_mailbox.result = SMIF0_GUARD_RESULT_DONE")
        self.assertLess(quiesce, parked)
        self.assertLess(release_wait, resume)
        self.assertLess(resume, done)

    def test_m33_guard_publishes_payload_before_sequence(self):
        source = read(M33_ROOT / "board/smif0_guard.c")
        fatal = function_body(source, "static SMIF0_GUARD_RAMFUNC void smif0_guard_fatal(")
        irq = function_body(source, "static SMIF0_GUARD_RAMFUNC void smif0_guard_irq_handler(")

        publication_patterns = (
            (fatal, r"timeout_count\+\+;\s*__DMB\(\);\s*"
                    r"g_smif0_guard_mailbox\.ack_seq = request_seq;\s*"
                    r"g_smif0_guard_mailbox\.done_seq = request_seq;\s*__DSB\(\);"),
            (irq, r"result = SMIF0_GUARD_RESULT_INVALID;[\s\S]*?"
                  r"__DMB\(\);\s*g_smif0_guard_mailbox\.ack_seq = request_seq;\s*"
                  r"g_smif0_guard_mailbox\.done_seq = request_seq;\s*__DSB\(\);\s*"
                  r"SMIF0_GUARD_IPC_STRUCT->RELEASE"),
            (irq, r"result = SMIF0_GUARD_RESULT_BUSY;[\s\S]*?denied_count\+\+;\s*"
                  r"__DMB\(\);\s*g_smif0_guard_mailbox\.ack_seq = request_seq;\s*"
                  r"g_smif0_guard_mailbox\.done_seq = request_seq;\s*__DSB\(\);\s*"
                  r"SMIF0_GUARD_IPC_STRUCT->RELEASE"),
            (irq, r"state = SMIF0_GUARD_STATE_PARKED;[\s\S]*?grant_count\+\+;\s*"
                  r"__DMB\(\);\s*g_smif0_guard_mailbox\.ack_seq = request_seq;\s*__DSB\(\);"),
            (irq, r"result = SMIF0_GUARD_RESULT_DONE;[\s\S]*?"
                  r"state = SMIF0_GUARD_STATE_ONLINE;\s*__DMB\(\);\s*"
                  r"g_smif0_guard_mailbox\.done_seq = request_seq;\s*__DSB\(\);\s*"
                  r"SMIF0_GUARD_IPC_STRUCT->RELEASE"),
        )

        for body, pattern in publication_patterns:
            self.assertRegex(body, pattern)

    def test_m55_fal_read_uses_xip_and_real_erase_geometry(self):
        fal = read(
            M55_ROOT / "libraries/Common/board/ports/fal/fal_flash_port.c"
        )
        read_body = function_body(fal, "static int read(")

        self.assertIn("FLASH_SECTOR_SIZE      (64U * 1024U)", fal)
        self.assertIn("FLASH_PAGE_SIZE        (256U)", fal)
        self.assertRegex(fal, r"\.timeout\s*=\s*[1-9]")
        self.assertRegex(fal, r"\.memReadyPollDelay\s*=\s*[1-9]")
        self.assertNotIn("Cy_SMIF_MemRead(", read_body)
        self.assertNotIn("Cy_SMIF_Init(", fal)
        self.assertIn("FLASH_START_ADDRESS", read_body)
        self.assertIn("SCB_InvalidateDCache_by_Addr", read_body)
        self.assertIn("memcpy", read_body)
        self.assertRegex(read_body, r"offset\s*<\s*0")
        self.assertIn("FLASH_SIZE - size", read_body)

    def test_m55_fal_partition_table_matches_migrated_layout(self):
        config = read(
            M55_ROOT / "libraries/Common/board/ports/fal/fal_cfg.h"
        )

        self.assertRegex(
            config,
            r'"filesystem"\s*,\s*NOR_FLASH_DEV_NAME,\s*0x100000,\s*512\*1024',
        )
        self.assertRegex(
            config,
            r'"wifi_cfg"\s*,\s*NOR_FLASH_DEV_NAME,\s*0x180000,\s*256\*1024',
        )
        self.assertRegex(
            config,
            r'"xiaozhi_cfg"\s*,\s*NOR_FLASH_DEV_NAME,\s*0x1C0000,\s*256\*1024',
        )

    def test_m55_fal_geometry_matches_generated_smif_device(self):
        fal = read(
            M55_ROOT / "libraries/Common/board/ports/fal/fal_flash_port.c"
        )
        rtconfig = read(M55_ROOT / "rtconfig.py")
        linker = read(M55_ROOT / "board/linker_scripts/link.ld")
        protection = read(
            M55_ROOT
            / "libs/TARGET_APP_KIT_PSE84_EVAL_EPC2/config/GeneratedSource"
            / "cycfg_system.c"
        )
        generated = read(
            M55_ROOT
            / "libs/TARGET_APP_KIT_PSE84_EVAL_EPC2/config/GeneratedSource"
            / "cycfg_qspi_memslot.c"
        )

        region2 = re.search(
            r"S25FS128S_SMIF0_SlaveSlot_1_region2\s*=\s*\{([\s\S]*?)\};",
            generated,
        )
        device = re.search(
            r"deviceCfg_S25FS128S_SMIF0_SlaveSlot_1\s*=\s*\{([\s\S]*?)\};",
            generated,
        )

        self.assertIsNotNone(region2)
        self.assertIsNotNone(device)
        self.assertIn("-T board/linker_scripts/link.ld", rtconfig)
        self.assertIn("FLASH_START_ADDRESS    (0x60DC0000UL)", fal)
        self.assertIn("SMIF_BASE_ADDRESS      (0x60000000UL)", fal)
        self.assertRegex(region2.group(1), r"\.regionAddress\s*=\s*0x10000U")
        self.assertRegex(region2.group(1), r"\.eraseSize\s*=\s*0x10000U")
        self.assertRegex(region2.group(1), r"\.eraseTime\s*=\s*725U")
        self.assertRegex(device.group(1), r"\.eraseSize\s*=\s*0x0*10000U")
        self.assertRegex(device.group(1), r"\.programSize\s*=\s*0x0*100U")
        self.assertRegex(device.group(1), r"\.programTime\s*=\s*2000U")

        trailer = re.search(
            r"m55_trailer\s*:\s*ORIGIN\s*=\s*(0x[0-9A-Fa-f]+),\s*"
            r"LENGTH\s*=\s*(0x[0-9A-Fa-f]+)",
            linker,
        )
        m55_mpc = re.search(
            r"\.start\s*=\s*\(void \*\)\s*0x60580000\s*,\s*"
            r"\.length\s*=\s*(0x[0-9A-Fa-f]+)U,\s*"
            r"\.is_secure\s*=\s*false",
            protection,
        )
        self.assertIsNotNone(trailer)
        self.assertIsNotNone(m55_mpc)

        fal_start = 0x60DC0000
        fal_end = fal_start + 0x200000
        trailer_end = int(trailer.group(1), 16) + int(trailer.group(2), 16)
        mpc_end = 0x60580000 + int(m55_mpc.group(1), 16)
        self.assertEqual(fal_start, trailer_end)
        self.assertLessEqual(fal_end, mpc_end)

    def test_dormant_m33_fal_driver_cannot_restore_old_mpc_unsafe_base(self):
        fal = read(
            M33_ROOT / "libraries/Common/board/ports/fal/fal_flash_port.c"
        )

        self.assertNotIn("0x60E00000", fal)
        self.assertIn("FLASH_START_ADDRESS    0x60DC0000", fal)

    def test_m55_guard_mailbox_is_in_non_cacheable_mpu_region(self):
        system = read(
            M55_ROOT
            / "libs/TARGET_APP_KIT_PSE84_EVAL_EPC2/config/GeneratedSource"
            / "cycfg_system.c"
        )
        protection = read(
            M55_ROOT
            / "libs/TARGET_APP_KIT_PSE84_EVAL_EPC2/config/GeneratedSource"
            / "cycfg_protection.c"
        )
        cmsis_mpu = read(
            M55_ROOT
            / "libraries/components/Infineon_cmsis-latest/Core/Include"
            / "m-profile/armv8m_mpu.h"
        )

        shared_region = re.search(
            r"\.base_addr\s*=\s*0x261C0000,[\s\S]*?"
            r"\.end_addr\s*=\s*0x261FFFFF,[\s\S]*?"
            r"\.cacheable\s*=\s*(\d+)",
            system,
        )

        self.assertIsNotNone(shared_region)
        self.assertEqual(shared_region.group(1), "4")
        self.assertRegex(cmsis_mpu, r"ARM_MPU_ATTR_NON_CACHEABLE\s+\(\s*4U\s*\)")
        self.assertIn("Cy_MPU_Init(cycfg_mpu_cm55_ns_0_config", protection)

    def test_guard_ipc_resources_do_not_reuse_existing_numbers(self):
        protocol = read(M33_ROOT / "board/smif0_guard_protocol.h")
        comm = read(M55_ROOT / "applications/m33_m55_comm.c")
        mtb_config = read(
            M55_ROOT / "libs/TARGET_APP_KIT_PSE84_EVAL_EPC2/mtb_ipc_config.h"
        )

        self.assertIn("SMIF0_GUARD_IPC_CHANNEL == 19U", protocol)
        self.assertIn("SMIF0_GUARD_IPC_INTERRUPT == 15U", protocol)
        self.assertIn("M33_M55_IPC_INTERNAL_CHANNEL     MTB_IPC_CHAN_1", comm)
        self.assertIn("M33_M55_IPC_IRQ_SEMA             (MTB_IPC_IRQ_USER + 4)", comm)
        self.assertIn("M33_M55_IPC_IRQ_QUEUE            (MTB_IPC_IRQ_USER + 5)", comm)
        self.assertIn("MTB_IPC_IRQ_QUEUE_SRF_CLIENT", mtb_config)
        self.assertNotIn("MTB_IPC_IRQ_USER + 6", comm)

    def test_m55_mount_failure_never_auto_formats_littlefs(self):
        mount = read(
            M55_ROOT / "libraries/Common/board/ports/filesystem/mnt.c"
        )

        self.assertNotIn('dfs_mkfs("lfs", "filesystem")', mount)
        self.assertIn("Mount filesystem failed", mount)
        self.assertIn('rt_thread_create("fal_mount"', mount)
        self.assertRegex(
            mount,
            r'rt_thread_create\("fal_mount",[\s\S]*?4096,[\s\S]*?16,[\s\S]*?20\)',
        )
        init = function_body(mount, "int mnt_init(")
        self.assertLess(init.index("fal_init()"), init.index('rt_thread_create("fal_mount"'))
        self.assertNotIn("_fal_mount();", init)

    def test_m55_write_and_erase_are_guarded_and_bounded(self):
        fal = read(
            M55_ROOT / "libraries/Common/board/ports/fal/fal_flash_port.c"
        )
        client_protocol = read(
            M55_ROOT
            / "libraries/Common/board/ports/fal/smif0_guard_protocol.h"
        )
        client = read(
            M55_ROOT
            / "libraries/Common/board/ports/fal/smif0_guard_client.c"
        )
        scons = read(M55_ROOT / "libraries/Common/board/SConscript")

        m33_protocol = read(M33_ROOT / "board/smif0_guard_protocol.h")
        self.assertEqual(m33_protocol, client_protocol)
        self.assertIn("0x261FFF00", client_protocol)
        self.assertIn("CY_IPC_CHAN_USER + 2", client_protocol)
        self.assertIn("CY_IPC_INTR_USER + 6", client_protocol)
        self.assertIn("SMIF0_GUARD_OP_WRITE", fal)
        self.assertIn("SMIF0_GUARD_OP_ERASE", fal)
        self.assertIn("smif0_guard_client_acquire", fal)
        self.assertIn("smif0_guard_client_release", fal)
        self.assertIn("rt_mutex", client)
        self.assertIn("CY_IPC_DRV_SUCCESS", client)
        self.assertIn("SMIF0_GUARD_ACK_TIMEOUT", client)
        self.assertIn(".cy_ramfunc", fal)
        self.assertIn("Glob('ports/fal/*.c')", scons)

        write_body = function_body(fal, "static int write(")
        erase_body = function_body(fal, "static int erase(")
        leaf = function_body(fal, "static FAL_SMIF_RAMFUNC void smif0_guard_execute_command(")

        self.assertIn("FLASH_PAGE_SIZE", write_body)
        self.assertIn("page_remaining", write_body)
        self.assertIn("while (remaining > 0U)", write_body)
        self.assertIn("memcpy", write_body)
        self.assertIn("smif0_guard_client_lock", write_body)
        self.assertIn("smif0_guard_client_unlock", write_body)
        self.assertIn("FLASH_SECTOR_SIZE", erase_body)
        self.assertIn("offset % FLASH_SECTOR_SIZE", erase_body)
        self.assertIn("size % FLASH_SECTOR_SIZE", erase_body)
        self.assertIn("while (remaining > 0U)", erase_body)

        normal = leaf.index("Cy_SMIF_SetMode(SMIF0_CORE, CY_SMIF_NORMAL)")
        command = min(
            leaf.index("Cy_SMIF_MemWrite("),
            leaf.index("Cy_SMIF_MemEraseSector("),
        )
        memory = leaf.index("Cy_SMIF_SetMode(SMIF0_CORE, CY_SMIF_MEMORY)")
        self.assertLess(normal, command)
        self.assertLess(command, memory)
        self.assertIn("__disable_irq", leaf)
        self.assertIn("Cy_SMIF_CacheInvalidate", leaf)
        self.assertIn("SCB_InvalidateDCache_by_Addr", leaf)
        self.assertIn("NVIC_SystemReset", fal)

    def test_m55_guard_timeout_cannot_leave_cm33_parked(self):
        fal = read(
            M55_ROOT / "libraries/Common/board/ports/fal/fal_flash_port.c"
        )
        client = read(
            M55_ROOT
            / "libraries/Common/board/ports/fal/smif0_guard_client.c"
        )

        self.assertIn("SMIF0_GUARD_ACK_TIMEOUT_MS             (500U)", client)
        for body in (
            function_body(fal, "static int write("),
            function_body(fal, "static int erase("),
        ):
            self.assertRegex(
                body,
                r"status = smif0_guard_client_acquire\([\s\S]*?"
                r"if \(status != RT_EOK\)\s*\{\s*"
                r"if \(status == -RT_ETIMEOUT\)\s*\{\s*"
                r"smif0_guard_command_fatal_reset\(\);\s*\}\s*break;",
            )
            self.assertRegex(
                body,
                r"status = smif0_guard_client_release\(request_seq\);\s*"
                r"if \(status != RT_EOK\)\s*\{\s*"
                r"smif0_guard_command_fatal_reset\(\);\s*\}",
            )

    def test_m55_guard_mailbox_publication_is_release_acquire_ordered(self):
        client = read(
            M55_ROOT
            / "libraries/Common/board/ports/fal/smif0_guard_client.c"
        )
        reap = function_body(client, "static rt_err_t smif0_guard_reap_completed_request(")
        acquire = function_body(client, "rt_err_t smif0_guard_client_acquire(")
        release = function_body(client, "rt_err_t smif0_guard_client_release(")

        channel = acquire.index("smif0_guard_lock_channel()")
        online = acquire.index("smif0_guard_validate_online(&request_epoch)")
        payload = acquire.index("SMIF0_GUARD_MAILBOX->operation = operation")
        self.assertLess(channel, online)
        self.assertLess(online, payload)
        self.assertIn("Cy_IPC_Drv_AcquireNotify", acquire)
        self.assertIn("1UL << SMIF0_GUARD_IPC_INTERRUPT_LOCAL", client)
        self.assertNotIn("Cy_IPC_Drv_SetInterrupt", acquire)
        self.assertRegex(
            acquire,
            r"operation = operation;[\s\S]*?address = address;[\s\S]*?"
            r"length = length;[\s\S]*?release_seq = 0U;\s*__DMB\(\);\s*"
            r"SMIF0_GUARD_MAILBOX->request_seq = request_seq;\s*__DSB\(\);",
        )
        self.assertRegex(
            acquire,
            r"ack_seq;\s*if \(ack_seq == request_seq\)[\s\S]*?"
            r"__DMB\(\);[\s\S]*?result =",
        )
        self.assertRegex(
            acquire,
            r"release_seq = request_seq;\s*__DSB\(\);[\s\S]*?"
            r"Cy_IPC_Drv_LockRelease",
        )
        self.assertNotIn("SMIF0_GUARD_MAILBOX->release_seq = request_seq", release)
        self.assertRegex(
            release,
            r"done_seq;\s*if \(done_seq == request_seq\)[\s\S]*?"
            r"__DMB\(\);[\s\S]*?result =",
        )
        release_timeout = release[release.rfind("SMIF0_GUARD_DONE_TIMEOUT_MS"):]
        self.assertNotIn("g_smif0_guard_active_seq = 0U", release_timeout)
        self.assertNotIn("g_smif0_guard_active_epoch = 0U", release_timeout)
        epoch_read = reap.index("epoch = SMIF0_GUARD_MAILBOX->epoch")
        done_check = reap.index("if (done_seq != request_seq)")
        self.assertLess(epoch_read, done_check)
        self.assertRegex(
            reap,
            r"if\s*\(epoch\s*!=\s*g_smif0_guard_active_epoch\)\s*\{\s*"
            r"g_smif0_guard_active_seq\s*=\s*0U;\s*"
            r"g_smif0_guard_active_epoch\s*=\s*0U;\s*"
            r"return\s+RT_EOK;\s*\}",
        )
        self.assertLess(
            reap.index("g_smif0_guard_active_seq = 0U", reap.index("state !=")),
            reap.index("SMIF0_GUARD_RESULT_BUSY", reap.index("state !=")),
        )
        self.assertIn("return -RT_EBUSY", reap)
        self.assertIn("return -RT_EINVAL", reap)

        init = function_body(client, "rt_err_t smif0_guard_client_init(")
        allocate = function_body(client, "static uint32_t smif0_guard_allocate_sequence(")
        self.assertIn("smif0_guard_validate_online", init)
        self.assertIn("SMIF0_GUARD_MAILBOX->request_seq", init)
        self.assertLess(init.index("rt_enter_critical()"), init.index("g_smif0_guard_initialized"))
        self.assertIn("rt_exit_critical()", init)
        self.assertIn("SMIF0_GUARD_MAILBOX->ack_seq", allocate)
        self.assertIn("SMIF0_GUARD_MAILBOX->done_seq", allocate)
        self.assertIn("SMIF0_GUARD_MAILBOX->request_seq", allocate)
        self.assertIn("smif0_guard_allocate_sequence()", acquire)

    def test_m55_ram_leaf_releases_cm33_before_restoring_interrupts(self):
        fal = read(
            M55_ROOT / "libraries/Common/board/ports/fal/fal_flash_port.c"
        )
        leaf = function_body(
            fal, "static FAL_SMIF_RAMFUNC void smif0_guard_execute_command("
        )
        write_body = function_body(fal, "static int write(")
        erase_body = function_body(fal, "static int erase(")

        self.assertRegex(leaf, r"uint32_t\s+request_seq")
        self.assertRegex(
            leaf,
            r"SCB_InvalidateDCache_by_Addr[\s\S]*?__DMB\(\);\s*"
            r"SMIF0_GUARD_MAILBOX->release_seq = request_seq;\s*"
            r"__DSB\(\);[\s\S]*?__set_PRIMASK\(saved_primask\);",
        )
        release = leaf.index("SMIF0_GUARD_MAILBOX->release_seq = request_seq")
        restore_irq = leaf.index("__set_PRIMASK(saved_primask)")
        self.assertLess(release, restore_irq)
        self.assertRegex(
            leaf,
            r"__ns_vector_table_rw\[2U\]\s*=\s*"
            r"smif0_guard_command_fatal_reset;[\s\S]*?"
            r"__ns_vector_table_rw\[3U\]\s*=\s*"
            r"smif0_guard_command_fatal_reset;",
        )
        vector_guard = leaf.index("__ns_vector_table_rw[2U] =")
        disable_icache = leaf.index("SCB_DisableICache()")
        normal_mode = leaf.index("Cy_SMIF_SetMode(SMIF0_CORE, CY_SMIF_NORMAL)")
        wait_cache = leaf.index("smif0_guard_wait_cache_invalidate()")
        enable_icache = leaf.index("SCB_EnableICache()")
        vector_restore = leaf.index("__ns_vector_table_rw[2U] = saved_nmi_vector")
        self.assertLess(vector_guard, normal_mode)
        self.assertLess(vector_guard, disable_icache)
        self.assertLess(disable_icache, normal_mode)
        self.assertLess(normal_mode, wait_cache)
        self.assertLess(wait_cache, enable_icache)
        self.assertLess(vector_restore, release)
        self.assertLess(vector_restore, restore_irq)
        wait_idle = function_body(
            fal, "static FAL_SMIF_RAMFUNC bool smif0_guard_wait_smif_idle("
        )
        wait_invalidate = function_body(
            fal, "static FAL_SMIF_RAMFUNC bool smif0_guard_wait_cache_invalidate("
        )
        self.assertIn("SMIF_STATUS_BUSY_Msk", wait_idle)
        self.assertIn("SMIF_SLOW_CA_CMD_INV_Msk", wait_invalidate)
        self.assertIn("SMIF_FAST_CA_CMD_INV_Msk", wait_invalidate)
        self.assertIn("budget--", wait_idle)
        self.assertIn("budget--", wait_invalidate)
        self.assertRegex(
            write_body,
            r"smif0_guard_execute_command\([\s\S]*?request_seq\s*\);",
        )
        self.assertRegex(
            erase_body,
            r"smif0_guard_execute_command\([\s\S]*?request_seq\s*\);",
        )

    def test_m55_gpu_is_idle_and_locked_around_smif_commands(self):
        fal = read(
            M55_ROOT / "libraries/Common/board/ports/fal/fal_flash_port.c"
        )
        display = read(
            M55_ROOT / "libraries/Common/board/ports/lvgl/lv_port_disp.c"
        )
        driver = read(M55_ROOT / "libraries/HAL_Drivers/drv_lcd.c")
        vg_utils = read(
            M55_ROOT / "libraries/Common/board/ports/lvgl/lv_vg_lite_utils.c"
        )
        lv_thread = read(
            M55_ROOT
            / "libraries/components/lvgl_9.2.0/env_support/rt-thread/lv_rt_thread_port.c"
        )
        vg_hal = read(
            M55_ROOT
            / "libraries/components/mtb-device-support-pse8xxgp/pdl/drivers"
            / "third_party/COMPONENT_GFXSS/vsi/gcnano/vg_lite_hal.c"
        )
        vg_core = read(
            M55_ROOT
            / "libraries/components/mtb-device-support-pse8xxgp/pdl/drivers"
            / "third_party/COMPONENT_GFXSS/vsi/gcnano/vg_lite.c"
        )
        write_body = function_body(fal, "static int write(")
        erase_body = function_body(fal, "static int erase(")
        quiesce = function_body(display, "rt_err_t lv_port_disp_smif0_quiesce(")
        resume = function_body(display, "void lv_port_disp_smif0_resume(")
        hw_init_begin = function_body(display, "rt_err_t lv_port_disp_smif0_hw_init_begin(")
        hw_init_end = function_body(display, "void lv_port_disp_smif0_hw_init_end(")
        init_begin = function_body(display, "rt_err_t lv_port_disp_smif0_init_begin(")
        init_end = function_body(display, "void lv_port_disp_smif0_init_end(")
        render_begin = function_body(display, "rt_err_t lv_port_disp_smif0_render_begin(")
        render_end = function_body(display, "void lv_port_disp_smif0_render_end(")
        thread_entry = function_body(lv_thread, "static void lvgl_thread_entry(")
        baremetal_wait = function_body(vg_hal, "int32_t vg_lite_hal_wait_interrupt(")
        stall = function_body(vg_core, "static vg_lite_error_t stall(")
        finish_timeout = function_body(vg_core, "vg_lite_error_t vg_lite_finish_timeout(")
        driver_init = function_body(driver, "int drv_lcd_hw_init(")
        vg_flush = function_body(vg_utils, "void lv_vg_lite_flush(")
        vg_finish = function_body(vg_utils, "void lv_vg_lite_finish(")

        self.assertIn("INIT_PREV_EXPORT(lv_port_disp_smif0_gate_init)", display)
        self.assertIn("SMIF0_GPU_STATE_HW_INITING", hw_init_begin)
        self.assertIn("SMIF0_GPU_STATE_HW_READY", hw_init_end)
        self.assertLess(
            driver_init.index("lv_port_disp_smif0_hw_init_begin()"),
            driver_init.index("vg_lite_init_mem("),
        )
        self.assertLess(
            driver_init.index("vg_lite_init("),
            driver_init.index("lv_port_disp_smif0_hw_init_end("),
        )
        self.assertIn("rt_mutex_take(&g_smif0_gpu_gate", init_begin)
        self.assertIn("SMIF0_GPU_STATE_HW_READY", init_begin)
        self.assertIn("SMIF0_GPU_STATE_UI_INITING", init_begin)
        self.assertIn("SMIF0_GPU_STATE_READY", init_end)
        self.assertIn("SMIF0_GPU_STATE_FAILED", init_end)
        self.assertIn("rt_mutex_take(&g_smif0_gpu_gate", render_begin)
        self.assertIn("rt_mutex_release(&g_smif0_gpu_gate)", render_end)
        self.assertLess(
            thread_entry.index("lv_port_disp_smif0_init_begin()"),
            thread_entry.index("lv_init()"),
        )
        self.assertLess(
            thread_entry.index("lv_port_disp_smif0_render_begin()"),
            thread_entry.index("lv_timer_handler()"),
        )
        self.assertLess(
            thread_entry.index("lv_timer_handler()"),
            thread_entry.index("lv_port_disp_smif0_render_end()"),
        )
        self.assertRegex(
            thread_entry,
            r"while \(\(status = lv_port_disp_smif0_init_begin\(\)\) != RT_EOK\)",
        )
        self.assertNotIn("lvgl_thread_started = RT_FALSE", thread_entry)
        thread_init = function_body(lv_thread, "int lvgl_thread_init(")
        self.assertLess(
            thread_init.index("lvgl_thread_started = RT_TRUE"),
            thread_init.index("rt_thread_init(&lvgl_thread"),
        )
        self.assertIn("rt_enter_critical()", thread_init)
        self.assertIn("rt_thread_detach(&lvgl_thread)", thread_init)

        self.assertIn("rt_tick_from_millisecond(SMIF0_GPU_GATE_TIMEOUT_MS)", quiesce)
        self.assertIn("g_smif0_gpu_transaction_held = RT_TRUE", quiesce)
        self.assertIn("SMIF0_GPU_STATE_COLD", quiesce)
        self.assertLess(
            quiesce.index("vg_lite_finish_timeout(SMIF0_GPU_FINISH_TIMEOUT_MS)"),
            quiesce.index("gpu_idle == 0U"),
        )
        self.assertIn("gpu_idle == 0U", quiesce)
        self.assertIn("rt_mutex_release(&g_smif0_gpu_gate)", resume)
        self.assertNotIn("lv_lock()", quiesce)

        self.assertIn("timeout_us", baremetal_wait)
        self.assertIn("return 0", baremetal_wait)
        self.assertIn("int_status & mask", baremetal_wait)
        self.assertIn("g_wait_timeout_override_ms", baremetal_wait)
        self.assertIn("VG_LITE_INFINITE", stall)
        self.assertNotIn("VG_LITE_DEFAULT_WAIT_TIMEOUT_MS", vg_core)
        self.assertLess(
            finish_timeout.index("vg_lite_hal_set_wait_timeout_override"),
            finish_timeout.index("vg_lite_finish()"),
        )
        self.assertLess(
            finish_timeout.index("vg_lite_finish()"),
            finish_timeout.index("vg_lite_hal_clear_wait_timeout_override"),
        )
        for body in (vg_flush, vg_finish):
            self.assertIn("lv_port_disp_smif0_gpu_fault()", body)
            self.assertLess(
                body.index("lv_port_disp_smif0_gpu_fault()"),
                body.index("return;", body.index("lv_port_disp_smif0_gpu_fault()")),
            )
        self.assertNotIn("LV_VG_LITE_CHECK_ERROR(vg_lite_flush())", vg_flush)
        self.assertNotIn("LV_VG_LITE_CHECK_ERROR(vg_lite_finish())", vg_finish)

        for body in (write_body, erase_body):
            stop_gpu = body.index("lv_port_disp_smif0_quiesce()")
            lock = body.index("smif0_guard_client_lock()")
            acquire = body.index("smif0_guard_client_acquire(")
            command = body.index("smif0_guard_execute_command(")
            release = body.index("smif0_guard_client_release(")
            resume_gpu = body.rindex("lv_port_disp_smif0_resume()")
            unlock = body.index("smif0_guard_client_unlock()")
            self.assertLess(stop_gpu, lock)
            self.assertLess(lock, acquire)
            self.assertLess(acquire, command)
            self.assertLess(command, release)
            self.assertLess(release, unlock)
            self.assertLess(unlock, resume_gpu)
            self.assertRegex(
                body,
                r"status = smif0_guard_client_lock\(\);\s*"
                r"if \(status != RT_EOK\)\s*\{\s*"
                r"lv_port_disp_smif0_resume\(\);\s*return status;",
            )

    def test_motion_state_controls_long_erase_window(self):
        control = read(M33_ROOT / "applications/m33/control_manager.c")
        set_mode = function_body(control, "rt_err_t control_set_mode(")

        self.assertIn("smif0_guard_set_safe_to_block", control)
        self.assertRegex(
            set_mode,
            r"if\s*\(mode\s*!=\s*CONTROL_MODE_PASSIVE\)[\s\S]*?"
            r"smif0_guard_set_safe_to_block\(false\);[\s\S]*?"
            r"g_control_status\.mode\s*=\s*mode;[\s\S]*?"
            r"if\s*\(mode\s*==\s*CONTROL_MODE_PASSIVE\)[\s\S]*?"
            r"smif0_guard_set_safe_to_block\(true\);",
        )

    def test_wifi_forget_erases_a_physical_sector(self):
        wifi = read(M55_ROOT / "applications/wifi_config_service.c")

        self.assertNotIn("fal_partition_erase(part, 0, 4096)", wifi)
        self.assertIn("WIFI_CONFIG_FAL_ERASE_SIZE", wifi)

    def test_wifi_forget_always_removes_dfs_fallback(self):
        wifi = read(M55_ROOT / "applications/wifi_config_service.c")
        forget = function_body(wifi, "rt_err_t wifi_config_forget(")

        self.assertIn("#include <errno.h>", wifi)
        self.assertLess(
            forget.index("fal_partition_erase("),
            forget.index("remove(WIFI_CONFIG_FILE_PATH)"),
        )
        self.assertNotRegex(
            forget,
            r"if\s*\(\s*ret\s*!=\s*RT_EOK[\s\S]{0,80}"
            r"remove\(WIFI_CONFIG_FILE_PATH\)",
        )
        self.assertRegex(
            forget,
            r"remove\(WIFI_CONFIG_FILE_PATH\)\s*!=\s*0[\s\S]*?"
            r"remove_errno\s*!=\s*ENOENT[\s\S]*?"
            r"remove_errno\s*!=\s*-ENOENT[\s\S]*?"
            r"ret\s*=\s*-RT_ERROR",
        )


if __name__ == "__main__":
    unittest.main()
