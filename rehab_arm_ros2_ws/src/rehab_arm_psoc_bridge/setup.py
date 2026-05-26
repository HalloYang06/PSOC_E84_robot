from setuptools import setup

package_name = 'rehab_arm_psoc_bridge'

setup(
    name=package_name,
    version='0.1.0',
    packages=[package_name],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='HalloYang06',
    maintainer_email='2735283977@qq.com',
    description='NanoPi bridge from ROS JointTrajectory to PSoC CAN command frames',
    license='MIT',
    entry_points={
        'console_scripts': [
            'psoc_can_bridge_node = rehab_arm_psoc_bridge.psoc_can_bridge_node:main',
            'data_recorder_node = rehab_arm_psoc_bridge.data_recorder_node:main',
            'camera_keyframe_node = rehab_arm_psoc_bridge.camera_keyframe_node:main',
            'joint_state_motor_state_node = rehab_arm_psoc_bridge.joint_state_motor_state_node:main',
            'check_recording = rehab_arm_psoc_bridge.check_recording:main',
            'summarize_recording = rehab_arm_psoc_bridge.summarize_recording:main',
            'validate_recording_quality = rehab_arm_psoc_bridge.validate_recording_quality:main',
            'export_recording_csv = rehab_arm_psoc_bridge.export_recording_csv:main',
            'build_manifest = rehab_arm_psoc_bridge.build_manifest:main',
            'sync_dry_run = rehab_arm_psoc_bridge.sync_dry_run:main',
            'sync_upload = rehab_arm_psoc_bridge.sync_upload:main',
            'check_server_quality_gate = rehab_arm_psoc_bridge.check_server_quality_gate:main',
            'sync_test_server = rehab_arm_psoc_bridge.sync_test_server:main',
            'candump_motor_telemetry = rehab_arm_psoc_bridge.candump_motor_telemetry:main',
        ],
    },
)
