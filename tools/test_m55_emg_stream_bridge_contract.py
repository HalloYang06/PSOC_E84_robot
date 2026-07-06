from pathlib import Path
import unittest


M33_ROOT = Path(__file__).resolve().parents[1]
APP_M33 = M33_ROOT / "applications" / "m33"


class M55EmgStreamBridgeContractTest(unittest.TestCase):
    def test_m33_bridge_publishes_emg_window_via_shared_memory_and_ipc(self):
        source_path = APP_M33 / "m55_emg_stream_bridge.c"
        self.assertTrue(source_path.exists(), f"missing M33 EMG stream bridge: {source_path}")
        text = source_path.read_text(encoding="utf-8")

        required = [
            "control_get_sensor_node_sample",
            "node->adc_raw[0]",
            "node->adc_raw[1]",
            "node->adc_raw[2]",
            "node->adc_raw[3]",
            "node->emg3_raw[0]",
            "node->emg3_raw[1]",
            "node->emg3_raw[2]",
            "g_m33_m55_pcm_shared.data",
            "RT_HW_CACHE_FLUSH",
            "MSG_TYPE_SENSOR_STREAM",
            "MODEL_INPUT_SRC_EMG",
            "MODEL_INPUT_FMT_UINT16",
            "m33_m55_comm_publish",
            "control_sensor_report_enable",
        ]
        for fragment in required:
            with self.subTest(fragment=fragment):
                self.assertIn(fragment, text)

        self.assertNotIn("MODEL_INPUT_SRC_IMU", text)
        self.assertNotIn("gyro", text.lower())
        self.assertNotIn("accel", text.lower())

    def test_m33_bridge_uses_expected_emg_window_shape(self):
        text = (APP_M33 / "m55_emg_stream_bridge.c").read_text(encoding="utf-8")

        self.assertIn("#define M55_EMG_PHYSICAL_CHANNELS 4U", text)
        self.assertIn("#define M55_EMG_MODEL_CHANNELS 3U", text)
        self.assertIn("#define M55_EMG_WINDOW_SAMPLES 15U", text)
        self.assertIn("#define M55_EMG_DEFAULT_PERIOD_MS 20U", text)
        self.assertIn("#define M55_EMG_SAMPLE_RATE_HZ 50U", text)
        self.assertIn("msg.payload.sensor_stream.channels = M55_EMG_PHYSICAL_CHANNELS", text)
        self.assertIn("msg.payload.sensor_stream.reserved0 = M55_EMG_MODEL_CHANNELS", text)
        self.assertIn("msg.payload.sensor_stream.reserved1 = stale_count", text)

    def test_m33_bridge_exposes_shell_controls(self):
        text = (APP_M33 / "m55_emg_stream_bridge.c").read_text(encoding="utf-8")

        self.assertIn("MSH_CMD_EXPORT(cmd_m55_emg_stream", text)
        self.assertIn("MSH_CMD_EXPORT(cmd_m55_emg_once", text)
        self.assertIn("MSH_CMD_EXPORT(cmd_m55_emg_status", text)

    def test_m33_boot_autostarts_emg_inference_stream_after_ipc_ready(self):
        main_text = (M33_ROOT / "applications" / "main.c").read_text(encoding="utf-8")

        self.assertIn("#include \"m33/m55_emg_stream_bridge.h\"", main_text)
        self.assertIn("#define M33_AUTO_START_EMG_M55_INFERENCE 1", main_text)
        self.assertIn("#define M33_AUTO_EMG_SAMPLE_PERIOD_MS 20U", main_text)
        self.assertIn("#define M33_AUTO_EMG_MANAGE_F103 1", main_text)
        self.assertIn("m33_start_ipc_pump();", main_text)
        self.assertIn("m55_emg_stream_bridge_start((rt_uint16_t)M33_AUTO_EMG_SAMPLE_PERIOD_MS", main_text)
        self.assertIn("[m33] auto EMG->M55 stream ret=", main_text)


if __name__ == "__main__":
    unittest.main()
