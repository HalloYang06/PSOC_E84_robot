from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
SERVICE_C = (ROOT / "applications" / "control" / "rehab_service.c").read_text(encoding="utf-8")
SERVICE_H = (ROOT / "applications" / "control" / "rehab_service.h").read_text(encoding="utf-8")
SHELL_C = (ROOT / "applications" / "control" / "rehab_shell.c").read_text(encoding="utf-8")


class RehabServiceActuationStaticTest(unittest.TestCase):
    def test_active_feedback_guard_rejects_stale_and_faulted_feedback(self):
        start = SERVICE_C.index("static rt_err_t rehab_feedback_active_check")
        end = SERVICE_C.index("static rt_err_t rehab_service_prepare_feedback", start)
        body = SERVICE_C[start:end]
        self.assertIn("rehab_feedback_is_fresh(fb, now)", body)
        self.assertIn("fb->fault_summary != 0U", body)
        self.assertIn("return -RT_ETIMEOUT;", body)
        self.assertIn("return -RT_ERROR;", body)

    def test_feedback_prepare_rejects_fault_before_mode_transition(self):
        start = SERVICE_C.index("static rt_err_t rehab_service_prepare_feedback(")
        end = SERVICE_C.index("static float rehab_service_positive_or_default", start)
        body = SERVICE_C[start:end]
        snapshot = body.index("control_get_motor_feedback(m33_joint_id, &fb)")
        guard = body.index("rehab_feedback_active_check(&fb, rt_tick_get())", snapshot)
        self.assertLess(snapshot, guard)

    def test_mask_feedback_prepare_rejects_fault_before_mode_transition(self):
        start = SERVICE_C.index("static rt_err_t rehab_service_prepare_feedback_mask")
        end = SERVICE_C.index("static void rehab_service_reset_all_strategy_states_locked", start)
        body = SERVICE_C[start:end]
        self.assertNotIn("rehab_feedback_active_check(&fb, now)", body)
        self.assertIn("rehab_feedback_active_check(&fb, rt_tick_get())", body)
        self.assertIn("if (feedback_ret == -RT_ERROR)", body)

    def test_worker_checks_fault_before_running_strategy(self):
        start = SERVICE_C.index("static void rehab_service_worker")
        end = SERVICE_C.index("rt_err_t rehab_service_init", start)
        body = SERVICE_C[start:end]
        guard = body.index("rehab_feedback_active_check(&fb, feedback_check_tick)")
        strategy = body.index("rehab_assist_strategy_step")
        self.assertLess(guard, strategy)

    def test_worker_reads_feedback_tick_after_snapshot(self):
        start = SERVICE_C.index("static void rehab_service_worker")
        end = SERVICE_C.index("rt_err_t rehab_service_init", start)
        body = SERVICE_C[start:end]
        snapshot = body.index("control_get_motor_feedback(joint, &fb)")
        tick = body.index("feedback_check_tick = rt_tick_get();", snapshot)
        guard = body.index("rehab_feedback_active_check(&fb, feedback_check_tick)", tick)
        self.assertLess(snapshot, tick)
        self.assertLess(tick, guard)
        self.assertNotIn("rehab_feedback_active_check(&fb, now)", body)

    def test_current_write_rechecks_feedback_under_actuation_lock(self):
        start = SERVICE_C.index("static rt_err_t rehab_service_apply_strategy_output")
        end = SERVICE_C.index("static void rehab_service_worker", start)
        body = SERVICE_C[start:end]
        lock = body.index("rt_mutex_take(&s_rehab.actuation_lock")
        read = body.index("control_get_motor_feedback(m33_joint, &latest_fb)")
        guard = body.index("rehab_feedback_active_check(&latest_fb, rt_tick_get())")
        current = body.index("control_motor_current_setpoint(m33_joint, out->current_a)")
        self.assertLess(lock, read)
        self.assertLess(read, guard)
        self.assertLess(guard, current)
        self.assertIn("control_motor_stop(m33_joint, RT_FALSE)", body[guard:current])

    def test_periodic_path_never_rearms_current_mode(self):
        self.assertNotIn("control_motor_current_control(", SERVICE_C)
        start = SERVICE_C.index("static rt_err_t rehab_service_apply_strategy_output")
        end = SERVICE_C.index("static void rehab_service_worker", start)
        body = SERVICE_C[start:end]
        self.assertIn("control_motor_current_setpoint(m33_joint, 0.0f)", body)
        self.assertNotIn("control_motor_current_prepare", body)

    def test_current_mode_is_prepared_once_before_status_transition(self):
        start = SERVICE_C.index("static rt_err_t rehab_service_set_mode_mask_internal")
        end = SERVICE_C.index("rt_err_t rehab_service_set_mode_mask(", start)
        body = SERVICE_C[start:end]
        prepare = body.index("rehab_service_prepare_current_mask(active_joint_mask)")
        transition = body.index("rehab_service_apply_status_locked(")
        self.assertLess(prepare, transition)

        helper_start = SERVICE_C.index("static rt_err_t rehab_service_prepare_current_mask")
        helper_end = SERVICE_C.index("static void rehab_service_default_params", helper_start)
        helper = SERVICE_C[helper_start:helper_end]
        self.assertIn("control_motor_current_prepare(joint)", helper)
        self.assertIn("fb.mode_state != 2U", helper)
        self.assertIn("CONTROL_REHAB_FEEDBACK_PREPARE_TIMEOUT_MS", helper)
        self.assertIn("rehab_service_stop_joint_mask(active_joint_mask, RT_FALSE)", helper)

    def test_fault_stop_is_generation_guarded_and_serialized(self):
        start = SERVICE_C.index("static void rehab_service_note_fault_mask")
        end = SERVICE_C.index("static void rehab_service_note_fault(", start)
        body = SERVICE_C[start:end]
        self.assertIn("expected_generation", body)
        self.assertIn("s_rehab.status.mode_generation != expected_generation", body)
        self.assertIn("rt_mutex_take(&s_rehab.actuation_lock", body)

    def test_fault_status_preserves_joint_and_feedback_age(self):
        self.assertIn("last_fault_joint", SERVICE_H)
        self.assertIn("last_fault_stage", SERVICE_H)
        self.assertIn("last_fault_feedback_age_ms", SERVICE_H)
        start = SERVICE_C.index("static void rehab_service_note_fault_mask")
        end = SERVICE_C.index("static void rehab_service_note_fault(", start)
        body = SERVICE_C[start:end]
        self.assertIn("s_rehab.status.last_fault_joint = m33_joint", body)
        self.assertIn("s_rehab.status.last_fault_stage = fault_stage", body)
        self.assertIn("s_rehab.status.last_fault_feedback_age_ms", body)
        self.assertIn("fault_joint=%u", SHELL_C)
        self.assertIn("fault_stage=%u", SHELL_C)
        self.assertIn("fault_age_ms=%u", SHELL_C)

    def test_failed_stop_latch_blocks_normal_mode_entry(self):
        self.assertGreaterEqual(SERVICE_C.count("s_rehab.stop_pending"), 4)
        self.assertGreaterEqual(SERVICE_C.count("return -RT_EBUSY;"), 4)

    def test_active_mode_prepares_fresh_feedback_before_state_transition(self):
        start = SERVICE_C.index("static rt_err_t rehab_service_enter_mode_on_m33")
        end = SERVICE_C.index("static rt_err_t rehab_service_enter_mode(", start)
        body = SERVICE_C[start:end]
        self.assertIn("rehab_service_prepare_feedback(m33_joint_id)", body)
        prepare = body.index("rehab_service_prepare_feedback(m33_joint_id)")
        transition = body.index("rehab_service_apply_status_locked(")
        self.assertLess(prepare, transition)

    def test_feedback_prepare_requests_reporting_with_bounded_wait(self):
        self.assertIn("control_motor_set_active_report(m33_joint_id, RT_TRUE)", SERVICE_C)
        self.assertIn("CONTROL_REHAB_FEEDBACK_PREPARE_TIMEOUT_MS", SERVICE_C)
        self.assertIn("return -RT_ETIMEOUT;", SERVICE_C)

    def test_mask_mode_prepares_all_feedback_before_state_transition(self):
        start = SERVICE_C.index("rt_err_t rehab_service_set_mode_mask")
        end = SERVICE_C.index("rt_err_t rehab_service_set_mode_on_m33", start)
        body = SERVICE_C[start:end]
        self.assertIn("rehab_service_prepare_feedback_mask(active_joint_mask)", body)
        prepare = body.index("rehab_service_prepare_feedback_mask(active_joint_mask)")
        transition = body.index("rehab_service_apply_status_locked(")
        self.assertLess(prepare, transition)

    def test_mask_feedback_prepare_has_one_shared_timeout_window(self):
        self.assertIn("static rt_err_t rehab_service_prepare_feedback_mask", SERVICE_C)
        start = SERVICE_C.index("static rt_err_t rehab_service_prepare_feedback_mask")
        end = SERVICE_C.index("static void rehab_service_reset_all_strategy_states_locked", start)
        body = SERVICE_C[start:end]
        self.assertIn("control_motor_set_active_report(joint, RT_TRUE)", body)
        self.assertEqual(body.count("start = rt_tick_get();"), 1)
        self.assertIn("return -RT_ETIMEOUT;", body)


if __name__ == "__main__":
    unittest.main()
