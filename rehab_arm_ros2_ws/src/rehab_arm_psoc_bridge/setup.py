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
        ],
    },
)
