import ast
from pathlib import Path
import xml.etree.ElementTree as ET


ROOT = Path(__file__).resolve().parents[5]
ROS_SRC_ROOT = ROOT / "ros/rehab_arm_ws/src"
BRINGUP_ROOT = ROS_SRC_ROOT / "rehab_arm_bringup"
SIM_DATA_COLLECTION_LAUNCH = BRINGUP_ROOT / "launch/sim_data_collection.launch.py"
DEMO_ONLY_LAUNCHES = {
    "rehab_arm_bringup/launch/sim_data_collection.launch.py",
    "rehab_arm_control/launch/control.launch.py",
}
LEGACY_PUBLISHERS = {"demo_trajectory_node", "vla_task_planner_node"}


def test_formal_launches_do_not_enable_legacy_motion_publishers() -> None:
    offenders: list[str] = []
    for path in ROS_SRC_ROOT.glob("*/launch/**/*.launch.py"):
        relative_path = path.relative_to(ROS_SRC_ROOT).as_posix()
        if relative_path in DEMO_ONLY_LAUNCHES:
            continue
        text = path.read_text(encoding="utf-8")
        if any(publisher in text for publisher in LEGACY_PUBLISHERS):
            offenders.append(relative_path)
    assert offenders == []


def test_sim_data_collection_keeps_demo_disabled_by_default() -> None:
    tree = ast.parse(SIM_DATA_COLLECTION_LAUNCH.read_text(encoding="utf-8"))
    declarations = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "DeclareLaunchArgument"
        and node.args
        and isinstance(node.args[0], ast.Constant)
        and node.args[0].value == "enable_demo_trajectory"
    ]
    assert len(declarations) == 1
    default_value = next(
        (keyword.value for keyword in declarations[0].keywords if keyword.arg == "default_value"),
        None,
    )
    assert isinstance(default_value, ast.Constant)
    assert default_value.value == "false"


def test_sim_data_collection_demo_node_uses_enable_condition() -> None:
    tree = ast.parse(SIM_DATA_COLLECTION_LAUNCH.read_text(encoding="utf-8"))
    launch_configurations = [
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Assign)
        and any(
            isinstance(target, ast.Name) and target.id == "enable_demo_trajectory"
            for target in node.targets
        )
    ]
    assert len(launch_configurations) == 1
    launch_configuration = launch_configurations[0]
    assert isinstance(launch_configuration, ast.Call)
    assert isinstance(launch_configuration.func, ast.Name)
    assert launch_configuration.func.id == "LaunchConfiguration"
    assert len(launch_configuration.args) == 1
    assert isinstance(launch_configuration.args[0], ast.Constant)
    assert launch_configuration.args[0].value == "enable_demo_trajectory"

    demo_nodes = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if not isinstance(node.func, ast.Name) or node.func.id != "Node":
            continue
        executable = next(
            (keyword.value for keyword in node.keywords if keyword.arg == "executable"),
            None,
        )
        if isinstance(executable, ast.Constant) and executable.value == "demo_trajectory_node.py":
            demo_nodes.append(node)

    assert len(demo_nodes) == 1
    condition = next(
        (keyword.value for keyword in demo_nodes[0].keywords if keyword.arg == "condition"),
        None,
    )
    assert isinstance(condition, ast.Call)
    assert isinstance(condition.func, ast.Name)
    assert condition.func.id == "IfCondition"
    assert len(condition.args) == 1
    assert isinstance(condition.args[0], ast.Name)
    assert condition.args[0].id == "enable_demo_trajectory"


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
