import ast
from pathlib import Path
import xml.etree.ElementTree as ET


ROOT = Path(__file__).resolve().parents[5]
ROS_SRC_ROOT = ROOT / "ros/rehab_arm_ws/src"
BRINGUP_ROOT = ROS_SRC_ROOT / "rehab_arm_bringup"
CONTROL_ROOT = ROS_SRC_ROOT / "rehab_arm_control"
SIM_DATA_COLLECTION_LAUNCH = BRINGUP_ROOT / "launch/sim_data_collection.launch.py"
LEGACY_ROOT = ROOT / "tools/bench-debug/legacy-5dof"
LEGACY_PUBLISHERS = {"demo_trajectory_node", "vla_task_planner_node"}


def test_formal_launches_do_not_reference_legacy_motion_publishers() -> None:
    offenders: list[str] = []
    for path in ROS_SRC_ROOT.glob("*/launch/**/*.launch.py"):
        text = path.read_text(encoding="utf-8")
        if any(publisher in text for publisher in LEGACY_PUBLISHERS):
            offenders.append(path.relative_to(ROS_SRC_ROOT).as_posix())
    assert offenders == []


def test_sim_data_collection_has_no_legacy_demo_switch_or_node() -> None:
    text = SIM_DATA_COLLECTION_LAUNCH.read_text(encoding="utf-8")
    assert "enable_demo_trajectory" not in text
    assert "demo_trajectory_node" not in text
    assert "IfCondition" not in text


def test_control_package_does_not_install_legacy_entry_points() -> None:
    setup_text = (CONTROL_ROOT / "setup.py").read_text(encoding="utf-8")
    cmake_text = (CONTROL_ROOT / "CMakeLists.txt").read_text(encoding="utf-8")
    for publisher in LEGACY_PUBLISHERS:
        assert publisher not in setup_text
        assert publisher not in cmake_text


def test_control_package_contains_no_legacy_demo_modules() -> None:
    package_root = CONTROL_ROOT / "rehab_arm_control"
    assert not (package_root / "demo_trajectory_node.py").exists()
    assert not (package_root / "vla_task_planner_node.py").exists()


def test_legacy_demo_sources_are_archived_outside_the_ros_workspace() -> None:
    expected_files = {
        "README.md",
        "control.launch.py",
        "demo_trajectory_node.py",
        "trajectory_utils.py",
        "vla_task_planner_node.py",
    }
    assert expected_files <= {path.name for path in LEGACY_ROOT.iterdir() if path.is_file()}

    readme = (LEGACY_ROOT / "README.md").read_text(encoding="utf-8")
    assert "not a colcon package" in readme
    assert "must not be referenced by formal launch files" in readme
    assert "historical reference only" in readme


def test_archived_python_sources_parse() -> None:
    for path in LEGACY_ROOT.glob("*.py"):
        ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def test_mainline_boundary_test_is_registered_with_ament() -> None:
    cmake = (BRINGUP_ROOT / "CMakeLists.txt").read_text(encoding="utf-8")
    assert "find_package(ament_cmake_pytest REQUIRED)" in cmake
    assert (
        "ament_add_pytest_test(test_mainline_boundaries "
        "test/test_mainline_boundaries.py)" in cmake
    )

    package = ET.parse(BRINGUP_ROOT / "package.xml").getroot()
    test_dependencies = {element.text for element in package.findall("test_depend")}
    assert "ament_cmake_pytest" in test_dependencies
