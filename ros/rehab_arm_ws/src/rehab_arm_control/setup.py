from setuptools import setup

package_name = 'rehab_arm_control'

setup(
    name=package_name,
    version='0.1.0',
    packages=[package_name],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='HalloYang06',
    maintainer_email='2735283977@qq.com',
    description='Trajectory generation and VLA task placeholder',
    license='MIT',
    entry_points={
        'console_scripts': [
            'demo_trajectory_node = rehab_arm_control.demo_trajectory_node:main',
            'vla_task_planner_node = rehab_arm_control.vla_task_planner_node:main',
        ],
    },
)
