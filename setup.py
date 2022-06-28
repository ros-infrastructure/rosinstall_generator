#!/usr/bin/env python

import os
import sys
from setuptools import setup, find_packages

exec(open(os.path.join(os.path.dirname(__file__), 'src', 'rosinstall_generator', '__init__.py')).read())

setup(
    name='rosinstall_generator',
    version=__version__,
    install_requires=[
        'catkin_pkg >= 0.1.28',
        'PyYAML',
        'rosdistro >= 0.7.3',
        'rospkg',
    ],
    extras_require={
        'test': [
            "mock; python_version < '3.3'",
            'pytest',
        ],
    },
    packages=find_packages('src'),
    package_dir={'': 'src'},
    entry_points = {
        'console_scripts': [
            'rosinstall_generator=rosinstall_generator.cli:main',
        ],
    },
    author='Dirk Thomas',
    author_email='dthomas@osrfoundation.org',
    maintainer='ROS Infrastructure Team',
    project_urls={
        'Source code':
        'https://github.com/ros-infrastructure/rosinstall_generator',
        'Issue tracker':
        'https://github.com/ros-infrastructure/rosinstall_generator/issues',
    },
    url='http://wiki.ros.org/rosinstall_generator',
    keywords=['ROS'],
    classifiers=['Programming Language :: Python',
                 'License :: OSI Approved :: BSD License',
                 'License :: OSI Approved :: MIT License'],
    description="A tool for generating rosinstall files",
    long_description="""A tool for generating rosinstall files""",
    license='BSD'
)
