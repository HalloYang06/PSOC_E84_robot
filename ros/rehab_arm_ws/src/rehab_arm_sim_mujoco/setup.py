from setuptools import setup

package_name = 'rehab_arm_sim_mujoco'

setup(
    name=package_name,
    version='0.1.0',
    packages=[package_name],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='HalloYang06',
    maintainer_email='2735283977@qq.com',
    description='MuJoCo-ready simulation node for the rehabilitation arm',
    license='MIT',
    entry_points={
        'console_scripts': [
            'mujoco_sim_node = rehab_arm_sim_mujoco.mujoco_sim_node:main',
            'check_sim_env = rehab_arm_sim_mujoco.check_sim_env:main',
            'upload_sim_readiness = rehab_arm_sim_mujoco.upload_sim_readiness:main',
            'medical_arm_visualizer = rehab_arm_sim_mujoco.medical_arm_visualizer_node:main',
        ],
    },
)
