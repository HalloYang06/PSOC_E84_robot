from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
DRV_CAN = ROOT / "libraries" / "HAL_Drivers" / "drv_can.c"
CAN_CONFIG = ROOT / "libraries" / "HAL_Drivers" / "CAN_config.h"


def direct_recv_body():
    text = DRV_CAN.read_text(encoding="utf-8")
    start = text.index("rt_ssize_t ifx_can_direct_recv")
    end = text.index("rt_err_t ifx_can_direct_get_diag", start)
    return text[start:end]


class M33CanDirectRecvStaticTest(unittest.TestCase):
    def test_direct_recv_uses_pdl_extractor_not_rxftop_raw_reads(self):
        body = direct_recv_body()

        self.assertIn("Cy_CANFD_ExtractMsgFromRXBuffer", body)
        self.assertIn("can->rx_buffer.r0_f = &can->rx_r0", body)
        self.assertIn("can->rx_buffer.r1_f = &can->rx_r1", body)
        self.assertIn("can->rx_buffer.data_area_f = can->rx_data", body)
        self.assertNotIn("CANFD_RXFTOP_CTL", body)
        self.assertNotIn("CANFD_RXFTOP0_DATA", body)

    def test_direct_recv_clamps_copy_to_rt_can_msg_storage(self):
        body = direct_recv_body()

        self.assertIn("if (len > sizeof(msg->data))", body)
        self.assertIn("len = (rt_uint8_t)sizeof(msg->data);", body)
        self.assertIn("rt_memcpy(msg->data, can->rx_data, len);", body)

    def test_fifo0_top_pointer_logic_is_enabled_in_canfd_config(self):
        text = CAN_CONFIG.read_text(encoding="utf-8")
        start = text.index("static const cy_en_canfd_fifo_config_t ifx_canfd0_rx_fifo0_cfg")
        end = text.index("static const cy_en_canfd_fifo_config_t ifx_canfd0_rx_fifo1_cfg", start)
        fifo0_cfg = text[start:end]

        self.assertIn(".topPointerLogicEnabled = true", fifo0_cfg)


if __name__ == "__main__":
    unittest.main()
