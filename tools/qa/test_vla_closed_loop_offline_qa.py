from __future__ import annotations

import importlib.util
from pathlib import Path


def test_offline_qa_reaches_linux_candidate_without_motion_authority():
    path = Path(__file__).with_name("vla_closed_loop_offline_qa.py")
    spec = importlib.util.spec_from_file_location("vla_closed_loop_offline_qa", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)

    report = module.run_offline_qa()

    assert report["ok"] is True
    assert report["transform_state"] == "calibrated"
    assert report["ik_status"] in {"candidate_ready", "candidate_approximate"}
    assert report["visual_joint_count"] == 6
    assert report["hardware_joint_count"] == 3
    assert report["active_motor_ids"] == [4, 5, 6]
    assert report["first_publish_scope"] == "/sim/medical_arm/joint_trajectory"
    assert report["control_boundary"] == "offline_qa_only_not_motion_permission"
