from setuptools import find_packages, setup

package_name = 'test_node_python'

setup(
    name=package_name,
    version='0.0.0',
    packages=find_packages(exclude=['test']),
    data_files=[
        ('share/ament_index/resource_index/packages',
            ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='Luca40mx',
    maintainer_email='145957795+Luca40mx@users.noreply.github.com',
    description='Minimal Python test node that logs a message once per second',
    license='Apache-2.0',
    extras_require={
        'test': [
            'pytest',
        ],
    },
    entry_points={
        'console_scripts': [
            'test_node_python = test_node_python.test_node_python:main',
        ],
    },
)
