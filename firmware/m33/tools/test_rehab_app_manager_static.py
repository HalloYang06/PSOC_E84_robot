from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
MANAGER_C = (ROOT / "applications" / "control" / "rehab_mode_manager.c").read_text(encoding="utf-8")
MANAGER_H = (ROOT / "applications" / "control" / "rehab_mode_manager.h").read_text(encoding="utf-8")


def body(text, start_marker, end_marker):
    start = text.index(start_marker)
    return text[start:text.index(end_marker, start)]


class RehabAppManagerStaticTest(unittest.TestCase):
    def test_app_command_contract_is_source_bound(self):
        command = body(
            MANAGER_H,
            "typedef struct\n{\n    rehab_mode_t mode;",
            "} rehab_app_mode_command_t;",
        )
        for field in (
            "rt_uint8_t joint_mask;",
            "rt_uint32_t request_id;",
            "rt_uint32_t session_generation;",
            "rt_uint32_t ttl_ms;",
        ):
            self.assertIn(field, command)
        self.assertIn("rehab_mode_manager_apply_app_command", MANAGER_H)
        self.assertIn("rehab_mode_manager_note_app_heartbeat", MANAGER_H)
        self.assertIn("rehab_mode_manager_note_app_disconnect", MANAGER_H)
        self.assertIn("rehab_mode_manager_stop_app", MANAGER_H)

    def test_app_mode_uses_independent_lease_and_generation_guard(self):
        self.assertIn('#include "rehab_app_lease.h"', MANAGER_C)
        self.assertIn("rehab_app_lease_t app_lease;", MANAGER_C)
        apply_app = body(
            MANAGER_C,
            "rt_err_t rehab_mode_manager_apply_app_command",
            "rt_err_t rehab_mode_manager_note_app_heartbeat",
        )
        self.assertIn("REHAB_CMD_SOURCE_APP_BLE", apply_app)
        self.assertIn("CONTROL_REHAB_ASSIST_DEFAULT_JOINT_MASK", apply_app)
        self.assertIn("REHAB_APP_MODE_MIN_TTL_MS", apply_app)
        self.assertIn("REHAB_APP_MODE_MAX_TTL_MS", apply_app)
        self.assertLess(
            apply_app.index("rehab_app_lease_can_begin"),
            apply_app.index("rehab_service_set_mode_mask_if_unchanged"),
        )
        self.assertIn("service_status.source != REHAB_CMD_SOURCE_APP_BLE", apply_app)
        self.assertIn("service_status.mode_generation", apply_app)
        self.assertIn("cmd->session_generation", apply_app)
        self.assertIn("rt_tick_from_millisecond(cmd->ttl_ms)", apply_app)
        self.assertIn("rollback_ret = rehab_service_stop_if_owned", apply_app)
        self.assertIn("rollback_ret == RT_EOK", apply_app)
        self.assertIn("rollback_ret == -RT_EBUSY", apply_app)
        self.assertIn(": rollback_ret", apply_app)
        self.assertIn("cmd->ttl_ms < REHAB_APP_MODE_MIN_TTL_MS", apply_app)
        self.assertIn("cmd->ttl_ms > REHAB_APP_MODE_MAX_TTL_MS", apply_app)

    def test_app_heartbeat_cannot_be_renewed_by_can_heartbeat(self):
        app_heartbeat = body(
            MANAGER_C,
            "rt_err_t rehab_mode_manager_note_app_heartbeat",
            "void rehab_mode_manager_record_reject",
        )
        can_heartbeat = body(
            MANAGER_C,
            "void rehab_mode_manager_note_heartbeat",
            "void rehab_mode_manager_tick",
        )
        self.assertIn("rehab_service_get_status", app_heartbeat)
        self.assertIn("rehab_app_lease_note_heartbeat", app_heartbeat)
        self.assertIn("service_status.mode_generation", app_heartbeat)
        self.assertIn("session_generation", app_heartbeat)
        self.assertNotIn("rehab_app_lease", can_heartbeat)
        self.assertIn("rehab_can_lease_note_heartbeat", can_heartbeat)

    def test_legacy_non_stop_cannot_steal_app_owner(self):
        apply_legacy = body(
            MANAGER_C,
            "rt_err_t rehab_mode_manager_apply_command",
            "rt_err_t rehab_mode_manager_apply_app_command",
        )
        self.assertIn("service_status.source == REHAB_CMD_SOURCE_APP_BLE", apply_legacy)
        self.assertIn("cmd->mode != REHAB_MODE_PASSIVE", apply_legacy)
        self.assertIn("return -RT_EBUSY", apply_legacy)
        self.assertIn("rehab_app_lease_revoke", apply_legacy)

    def test_timeout_and_disconnect_use_generation_conditioned_stop(self):
        tick = body(
            MANAGER_C,
            "void rehab_mode_manager_tick",
            "rt_bool_t rehab_mode_manager_accepts_ros_target",
        )
        disconnect = body(
            MANAGER_C,
            "rt_err_t rehab_mode_manager_note_app_disconnect",
            "rt_err_t rehab_mode_manager_stop_app",
        )
        self.assertIn("rehab_app_lease_claim_timeout_stop", tick)
        self.assertIn("rehab_service_stop_if_owned", tick)
        self.assertIn("rehab_app_lease_note_stop_result", tick)
        self.assertIn("explicit_stop_latched", tick)
        self.assertIn("rehab_service_stop(REHAB_CMD_SOURCE_APP_BLE)", tick)
        self.assertLess(
            tick.index("explicit_stop_latched"),
            tick.index("rehab_app_lease_claim_timeout_stop"),
        )
        self.assertIn("rehab_app_lease_claim_disconnect_stop", disconnect)
        self.assertIn("rehab_service_stop_if_owned", disconnect)
        self.assertIn("rehab_app_lease_note_stop_result", disconnect)
        self.assertIn("s_rehab_adapter.command_lock", disconnect)

    def test_explicit_app_stop_allows_stop_but_rejects_old_session_owner(self):
        stop = body(
            MANAGER_C,
            "rt_err_t rehab_mode_manager_stop_app",
            "void rehab_mode_manager_record_reject",
        )
        self.assertIn("s_rehab_adapter.app_lease.active", stop)
        self.assertIn("s_rehab_adapter.app_lease.session_generation != session_generation", stop)
        self.assertIn("rehab_service_stop(REHAB_CMD_SOURCE_APP_BLE)", stop)
        self.assertIn("rehab_app_lease_revoke", stop)
        self.assertLess(
            stop.index("if (s_rehab_adapter.explicit_stop_latched)"),
            stop.index("s_rehab_adapter.explicit_stop_latched = RT_TRUE"),
        )
        self.assertLess(
            stop.index("s_rehab_adapter.explicit_stop_latched = RT_TRUE"),
            stop.index("rehab_service_stop(REHAB_CMD_SOURCE_APP_BLE)"),
        )
        self.assertIn("s_rehab_adapter.explicit_stop_retry_count++", stop)


if __name__ == "__main__":
    unittest.main()
