from setuptools import setup
import os
from glob import glob

package_name = 'http_bridge'

setup(
    name=package_name,
    version='0.1.0',
    packages=[package_name],
    data_files=[
        ('share/ament_index/resource_index/packages',
            ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
        (os.path.join('share', package_name, 'launch'), glob('launch/*.py')),
    ],
    install_requires=['setuptools', 'flask', 'flask-cors'],
    zip_safe=True,
    maintainer='HalloYang06',
    maintainer_email='2735283977@qq.com',
    description='HTTP Bridge server for OpenClaw Android APP communication',
    license='MIT',
    tests_require=['pytest'],
    entry_points={
        'console_scripts': [
            'http_bridge_server = http_bridge.http_bridge_server:main',
        ],
    },
)
