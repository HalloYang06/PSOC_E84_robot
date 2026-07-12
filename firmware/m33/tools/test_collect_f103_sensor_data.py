import csv
import io
import queue
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import collect_f103_sensor_data as collect


class FakePort:
    def __init__(self, device, description, manufacturer, hwid):
        self.device = device
        self.description = description
        self.manufacturer = manufacturer
        self.hwid = hwid


class CollectF103SensorDataTests(unittest.TestCase):
    def test_detect_infineon_serial_port_prefers_kitprog3_uart(self):
        ports = [
            FakePort("COM6", "USB Serial Device", "Microsoft", "USB VID:PID=1234:5678"),
            FakePort("COM20", "KitProg3 USB-UART", "Cypress", "USB VID:PID=04B4:F155"),
        ]

        self.assertEqual(collect.detect_infineon_serial_port(ports), "COM20")

    def test_resolve_serial_port_keeps_explicit_port(self):
        ports = [FakePort("COM20", "KitProg3 USB-UART", "Cypress", "USB VID:PID=04B4:F155")]

        self.assertEqual(collect.resolve_serial_port("COM7", ports), "COM7")

    def test_resolve_serial_port_auto_detects_infineon_port(self):
        ports = [FakePort("COM20", "KitProg3 USB-UART", "Cypress", "USB VID:PID=04B4:F155")]

        self.assertEqual(collect.resolve_serial_port("auto", ports), "COM20")

    def test_parse_candump_log_line(self):
        frame = collect.parse_candump_line(
            "(1719440000.123456) can0 7C2#3412FEFFCDAB4803"
        )

        self.assertEqual(frame.timestamp, 1719440000.123456)
        self.assertEqual(frame.channel, "can0")
        self.assertEqual(frame.arbitration_id, 0x7C2)
        self.assertEqual(frame.data, bytes.fromhex("34 12 FE FF CD AB 48 03"))

    def test_parse_candump_log_line_with_utf8_bom(self):
        frame = collect.parse_candump_line(
            "\ufeff(1719440000.123456) can0 7C2#3412FEFFCDAB4803"
        )

        self.assertIsNotNone(frame)
        self.assertEqual(frame.arbitration_id, 0x7C2)

    def test_parse_candump_log_line_with_powershell_bom_mojibake(self):
        frame = collect.parse_candump_line(
            "\u9518\udcbf(1719440000.123456) can0 7C2#3412FEFFCDAB4803"
        )

        self.assertIsNotNone(frame)
        self.assertEqual(frame.arbitration_id, 0x7C2)

    def test_decode_f103_sensor_frame(self):
        frame = collect.CanFrame(
            timestamp=1719440000.123456,
            channel="can0",
            arbitration_id=0x7C2,
            data=bytes.fromhex("34 12 FE FF CD AB 48 03"),
        )

        row = collect.decode_frame(frame, first_timestamp=1719440000.0)

        self.assertEqual(row["kind"], "sensor")
        self.assertEqual(row["emg_raw"], 0x1234)
        self.assertEqual(row["emg_filt"], -2)
        self.assertEqual(row["hr_raw"], 0xABCD)
        self.assertEqual(row["hr_bpm"], 72)
        self.assertEqual(row["flags"], 0x03)
        self.assertEqual(row["adc0"], 0x1234)
        self.assertEqual(row["adc1"], 0xFFFE)
        self.assertEqual(row["adc2"], 0xABCD)
        self.assertEqual(row["adc3"], 0x0348)
        self.assertEqual(row["rel_ms"], 123)

    def test_decode_emg3_sensor_frame(self):
        frame = collect.CanFrame(
            timestamp=1719440000.120,
            channel="can0",
            arbitration_id=0x7C2,
            data=bytes.fromhex("E8 03 D0 07 B8 0B A0 0F"),
        )

        row = collect.decode_frame(frame, first_timestamp=1719440000.0, protocol="emg3-motor")

        self.assertEqual(row["kind"], "sensor")
        self.assertEqual(row["adc0"], 1000)
        self.assertEqual(row["adc1"], 2000)
        self.assertEqual(row["adc2"], 3000)
        self.assertEqual(row["adc3"], 4000)
        self.assertEqual(row["emg_biceps"], 1000)
        self.assertEqual(row["emg_triceps"], 2000)
        self.assertEqual(row["emg_ant_deltoid"], 3000)
        self.assertEqual(row["emg_flags"], 0)
        self.assertEqual(row["emg_seq"], "")
        self.assertEqual(row["rel_ms"], 120)

    def test_decode_m33_compatible_motor_status_frame(self):
        frame = collect.CanFrame(
            timestamp=1719440000.020,
            channel="can0",
            arbitration_id=0x331,
            data=bytes.fromhex("B3 2A 04 12 38 FF FE 24"),
        )

        row = collect.decode_frame(frame, first_timestamp=1719440000.0, protocol="emg3-motor")

        self.assertEqual(row["kind"], "motor_status")
        self.assertEqual(row["motor_slot"], 1)
        self.assertEqual(row["motor_id"], 4)
        self.assertEqual(row["motor_flags"], 0x12)
        self.assertFalse(row["motor_fresh"])
        self.assertTrue(row["motor_fault"])
        self.assertEqual(row["motor_pos_mrad"], -200)
        self.assertEqual(row["motor_vel_mrad_s"], -200)
        self.assertEqual(row["motor_temp_c"], 36)

    def test_decode_m33_training_kinematics_frame(self):
        frame = collect.CanFrame(
            timestamp=1719440000.040,
            channel="can0",
            arbitration_id=0x342,
            data=bytes.fromhex("D0 11 01 03 D4 FE FA 00"),
        )

        row = collect.decode_frame(frame, first_timestamp=1719440000.0, protocol="emg3-motor")

        self.assertEqual(row["kind"], "motor_training_kin")
        self.assertEqual(row["motor_slot"], 1)
        self.assertEqual(row["ros_slot"], 1)
        self.assertEqual(row["motor_flags"], 0x03)
        self.assertEqual(row["motor_pos_mrad"], -300)
        self.assertEqual(row["motor_vel_mrad_s"], 250)

    def test_decode_m33_training_effort_frame_uses_command_current_name(self):
        frame = collect.CanFrame(
            timestamp=1719440000.060,
            channel="can0",
            arbitration_id=0x343,
            data=bytes.fromhex("D1 12 01 09 A6 FF E7 32"),
        )

        row = collect.decode_frame(frame, first_timestamp=1719440000.0, protocol="emg3-motor")

        self.assertEqual(row["kind"], "motor_training_effort")
        self.assertEqual(row["motor_slot"], 1)
        self.assertEqual(row["ros_slot"], 1)
        self.assertEqual(row["motor_flags"], 0x09)
        self.assertEqual(row["motor_torque_mNm"], -90)
        self.assertAlmostEqual(row["output_current_cmd_a"], -0.5)
        self.assertAlmostEqual(row["limit_current_a"], 1.0)
        self.assertTrue(row["motor_saturated"])
        self.assertNotIn("measured_current_a", row)

    def test_parse_emg3_motor_serial_line(self):
        row = collect.parse_emg3_motor_serial_line(
            "EMG3MOTOR,1234,100,200,300,5,9,"
            "10,20,30,36,0.4,1.0,1,"
            "110,220,330,37,-0.5,1.2,9"
        )

        self.assertIsNotNone(row)
        assert row is not None
        self.assertEqual(row["kind"], "sensor")
        self.assertEqual(row["source"], "serial")
        self.assertEqual(row["m33_ms"], 1234)
        self.assertEqual(row["adc0"], 100)
        self.assertEqual(row["adc1"], 200)
        self.assertEqual(row["adc2"], 300)
        self.assertEqual(row["adc3"], "")
        self.assertEqual(row["emg_biceps"], 100)
        self.assertEqual(row["emg_triceps"], 200)
        self.assertEqual(row["emg_ant_deltoid"], 300)
        self.assertEqual(row["emg_flags"], 5)
        self.assertEqual(row["emg_seq"], 9)
        self.assertEqual(row["shoulder_pos_mrad"], 10)
        self.assertEqual(row["shoulder_vel_mrad_s"], 20)
        self.assertEqual(row["shoulder_torque_mNm"], 30)
        self.assertAlmostEqual(row["shoulder_output_current_cmd_a"], 0.4)
        self.assertFalse(row["shoulder_stale"])
        self.assertEqual(row["elbow_pos_mrad"], 110)
        self.assertEqual(row["elbow_vel_mrad_s"], 220)
        self.assertEqual(row["elbow_torque_mNm"], 330)
        self.assertAlmostEqual(row["elbow_output_current_cmd_a"], -0.5)
        self.assertTrue(row["elbow_saturated"])
        self.assertEqual(row["target_elbow_pos_mrad"], 110)
        self.assertEqual(row["target_elbow_vel_mrad_s"], 220)
        self.assertAlmostEqual(row["target_elbow_output_current_cmd_a"], -0.5)
        self.assertNotIn("measured_current_a", row)

    def test_parse_emg3_motor_serial_line_with_adc3(self):
        row = collect.parse_emg3_motor_serial_line(
            "EMG3MOTOR,1234,100,200,300,400,5,9,"
            "10,20,30,36,0.4,1.0,1,"
            "110,220,330,37,-0.5,1.2,9"
        )

        self.assertIsNotNone(row)
        assert row is not None
        self.assertEqual(row["adc0"], 100)
        self.assertEqual(row["adc1"], 200)
        self.assertEqual(row["adc2"], 300)
        self.assertEqual(row["adc3"], 400)
        self.assertEqual(row["emg_biceps"], 100)
        self.assertEqual(row["emg_triceps"], 200)
        self.assertEqual(row["emg_ant_deltoid"], 300)
        self.assertEqual(row["emg_flags"], 5)
        self.assertEqual(row["emg_seq"], 9)
        self.assertEqual(row["shoulder_pos_mrad"], 10)
        self.assertEqual(row["elbow_pos_mrad"], 110)

    def test_serial_parser_ignores_non_telemetry_lines(self):
        self.assertIsNone(collect.parse_emg3_motor_serial_line("msh /> sensor_show"))
        self.assertIsNone(collect.parse_emg3_motor_serial_line("[control] init ok"))

    def test_serial_diagnostic_error_detects_missing_firmware_command(self):
        error = collect._serial_diagnostic_error("emg_motor_stream: command not found.")

        self.assertIsInstance(error, RuntimeError)
        self.assertIn("emg_motor_stream", str(error))
        self.assertIn("firmware", str(error))

    def test_serial_command_bytes_splits_multiple_shell_commands(self):
        payload = collect._serial_command_bytes(
            "cmd_control_init; cmd_sensor_rate 2 50; emg_motor_stream 1 20"
        )

        self.assertEqual(
            payload,
            b"cmd_control_init\r\ncmd_sensor_rate 2 50\r\nemg_motor_stream 1 20\r\n",
        )

    def test_serial_command_bytes_splits_newline_commands(self):
        payload = collect._serial_command_bytes("cmd_control_init\ncmd_sensor_rate 2 50\n")

        self.assertEqual(payload, b"cmd_control_init\r\ncmd_sensor_rate 2 50\r\n")

    def test_window_aggregator_emits_overlapping_features(self):
        aggregator = collect.WindowAggregator(window_ms=40, step_ms=20)
        rows = []
        for rel_ms, emg_filt, hr_bpm in (
            (0, -3, 70),
            (20, 4, 72),
            (40, 5, 74),
            (60, -6, 76),
        ):
            rows.extend(
                aggregator.add_sensor_row(
                    {
                        "rel_ms": rel_ms,
                        "emg_raw": 100,
                        "emg_filt": emg_filt,
                        "hr_raw": 200,
                        "hr_bpm": hr_bpm,
                        "flags": 0x01,
                    }
                )
            )

        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["window_start_ms"], 0)
        self.assertEqual(rows[0]["window_end_ms"], 40)
        self.assertEqual(rows[0]["sample_count"], 2)
        self.assertAlmostEqual(rows[0]["emg_abs_mean"], 3.5)
        self.assertAlmostEqual(rows[0]["emg_rms"], (25 / 2) ** 0.5)
        self.assertAlmostEqual(rows[0]["hr_bpm_mean"], 71.0)
        self.assertEqual(rows[1]["window_start_ms"], 20)
        self.assertEqual(rows[1]["window_end_ms"], 60)

    def test_emg3_motor_aligner_marks_fresh_then_stale_motor_state(self):
        aligner = collect.Emg3MotorAligner(stale_after_ms=250)
        aligner.observe(
            {
                "kind": "motor_training_kin",
                "rel_ms": 0,
                "ros_slot": 1,
                "motor_pos_mrad": 120,
                "motor_vel_mrad_s": 30,
            }
        )
        aligner.observe(
            {
                "kind": "motor_training_effort",
                "rel_ms": 10,
                "ros_slot": 1,
                "motor_torque_mNm": 45,
                "output_current_cmd_a": 0.2,
                "limit_current_a": 1.0,
                "motor_saturated": False,
                "motor_fresh": True,
                "motor_fault": False,
            }
        )

        fresh = aligner.align_sensor_row({"kind": "sensor", "rel_ms": 100})
        stale = aligner.align_sensor_row({"kind": "sensor", "rel_ms": 300})

        self.assertEqual(fresh["elbow_pos_mrad"], 120)
        self.assertEqual(fresh["elbow_vel_mrad_s"], 30)
        self.assertEqual(fresh["elbow_torque_mNm"], 45)
        self.assertAlmostEqual(fresh["elbow_output_current_cmd_a"], 0.2)
        self.assertFalse(fresh["elbow_stale"])
        self.assertTrue(fresh["elbow_fresh"])
        self.assertEqual(stale["elbow_pos_mrad"], 120)
        self.assertTrue(stale["elbow_stale"])
        self.assertFalse(stale["elbow_fresh"])

    def test_emg3_window_aggregator_emits_emg_and_motor_features(self):
        aggregator = collect.Emg3MotorWindowAggregator(window_ms=40, step_ms=20)
        rows = []
        samples = (
            (0, 10, 20, 30, 100, 5, False),
            (20, 14, 24, 34, 120, 7, False),
            (40, 16, 28, 36, 130, 9, True),
        )
        for rel_ms, biceps, triceps, deltoid, pos, current, stale in samples:
            rows.extend(
                aggregator.add_sensor_row(
                    {
                        "session_id": "s1",
                        "label": "elbow_flex",
                        "rel_ms": rel_ms,
                        "emg_biceps": biceps,
                        "emg_triceps": triceps,
                        "emg_ant_deltoid": deltoid,
                        "emg_flags": 0x01,
                        "elbow_pos_mrad": pos,
                        "elbow_vel_mrad_s": 10,
                        "elbow_torque_mNm": 50,
                        "elbow_output_current_cmd_a": current / 10.0,
                        "elbow_limit_current_a": 1.0,
                        "elbow_stale": stale,
                    }
                )
            )

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["window_start_ms"], 0)
        self.assertEqual(rows[0]["sample_count"], 2)
        self.assertAlmostEqual(rows[0]["emg_biceps_mean"], 12.0)
        self.assertAlmostEqual(rows[0]["emg_biceps_rms"], ((10 * 10 + 14 * 14) / 2) ** 0.5)
        self.assertAlmostEqual(rows[0]["emg_ant_deltoid_mean"], 32.0)
        self.assertAlmostEqual(rows[0]["elbow_pos_mrad_mean"], 110.0)
        self.assertAlmostEqual(rows[0]["elbow_output_current_cmd_a_mean"], 0.6)
        self.assertEqual(rows[0]["stale_count"], 0)

    def test_csv_columns_include_labels_serial_metadata_and_training_targets(self):
        for column in (
            "label",
            "source",
            "m33_ms",
            "target_elbow_output_current_cmd_a",
            "target_elbow_vel_mrad_s",
            "target_elbow_pos_mrad",
            "target_shoulder_output_current_cmd_a",
            "target_shoulder_vel_mrad_s",
            "target_shoulder_pos_mrad",
        ):
            self.assertIn(column, collect.RAW_COLUMNS)

        for column in (
            "target_elbow_output_current_cmd_a_mean",
            "target_elbow_vel_mrad_s_mean",
            "target_elbow_pos_mrad_mean",
            "target_shoulder_output_current_cmd_a_mean",
            "target_shoulder_vel_mrad_s_mean",
            "target_shoulder_pos_mrad_mean",
        ):
            self.assertIn(column, collect.WINDOW_COLUMNS)

    def test_guided_trial_plan_has_fixed_labels_and_expected_samples(self):
        plan = collect.build_guided_trial_plan(trials_per_label=2, record_s=8.0, sample_hz=50)

        self.assertEqual(
            [trial.label for trial in plan.trials],
            [
                "rest",
                "rest",
                "elbow_flex",
                "elbow_flex",
                "elbow_extend",
                "elbow_extend",
                "shoulder_flex",
                "shoulder_flex",
            ],
        )
        self.assertEqual(plan.expected_raw_samples, 4 * 2 * 8 * 50)
        self.assertEqual(plan.window_ms, 300)
        self.assertEqual(plan.step_ms, 100)
        self.assertEqual(plan.labels, collect.DEFAULT_EMG3_LABELS)

    def test_manual_trial_state_numbers_labels_independently(self):
        state = collect.ManualTrialState()

        first_elbow = state.start_trial(" elbow_flex ")
        first_shoulder = state.start_trial("shoulder_flex")
        second_elbow = state.start_trial("elbow_flex")

        self.assertEqual(first_elbow.trial_index, 1)
        self.assertEqual(first_elbow.label, "elbow_flex")
        self.assertEqual(first_elbow.label_trial_index, 1)
        self.assertEqual(first_elbow.trial_id, "001_elbow_flex_01")
        self.assertEqual(first_shoulder.trial_index, 2)
        self.assertEqual(first_shoulder.label_trial_index, 1)
        self.assertEqual(first_shoulder.trial_id, "002_shoulder_flex_01")
        self.assertEqual(second_elbow.trial_index, 3)
        self.assertEqual(second_elbow.label_trial_index, 2)
        self.assertEqual(second_elbow.trial_id, "003_elbow_flex_02")

    def test_manual_trial_state_accepts_numeric_label_shortcuts(self):
        state = collect.ManualTrialState()

        rest = state.start_trial("1")
        elbow_up = state.start_trial("2")
        elbow_down = state.start_trial("3")
        shoulder_up = state.start_trial("4")

        self.assertEqual(rest.label, "rest")
        self.assertEqual(elbow_up.label, "elbow_flex")
        self.assertEqual(elbow_down.label, "elbow_extend")
        self.assertEqual(shoulder_up.label, "shoulder_flex")
        self.assertEqual(elbow_up.trial_id, "002_elbow_flex_01")

    def test_manual_trial_state_counts_shortcut_and_full_label_together(self):
        state = collect.ManualTrialState()

        first_elbow = state.start_trial("2")
        second_elbow = state.start_trial("elbow_flex")

        self.assertEqual(first_elbow.label, "elbow_flex")
        self.assertEqual(first_elbow.label_trial_index, 1)
        self.assertEqual(second_elbow.label, "elbow_flex")
        self.assertEqual(second_elbow.label_trial_index, 2)

    def test_manual_trial_state_rejects_empty_label(self):
        state = collect.ManualTrialState()

        with self.assertRaises(ValueError):
            state.start_trial("  ")

    def test_drain_queue_or_raise_surfaces_background_errors(self):
        row_queue = queue.Queue()
        row_queue.put(RuntimeError("serial busy"))

        with self.assertRaisesRegex(RuntimeError, "serial busy"):
            collect._drain_queue_or_raise(row_queue)

    def test_csv_writer_uses_stable_columns(self):
        output = io.StringIO()
        writer = collect.CsvRowWriter(output, collect.RAW_COLUMNS)
        writer.write(
            {
                "timestamp": 1719440000.0,
                "channel": "can0",
                "can_id": "0x7C2",
                "kind": "sensor",
                "emg_raw": 1,
                "unexpected_future_field": "ignored",
            }
        )

        output.seek(0)
        rows = list(csv.DictReader(output))
        self.assertEqual(rows[0]["can_id"], "0x7C2")
        self.assertEqual(rows[0]["emg_raw"], "1")
        self.assertNotIn("unexpected_future_field", rows[0])


if __name__ == "__main__":
    unittest.main()
