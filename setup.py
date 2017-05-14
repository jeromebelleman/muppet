#!/usr/bin/env python
# coding=utf-8

import os
from distutils.core import setup

setup(
    name='muppet',
    version='1.0',
    author='Jérôme Belleman',
    author_email='Jerome.Belleman@gmail.com',
    url='http://cern.ch/jbl',
    description='"Configuration management tool"',
    long_description='"Manage Debian-based system configurations from manifests written in Python."',
    scripts=['scripts/muppet'],
    packages=['muppet'],
    data_files=[('share/man/man1', ['muppet.1'])],
)
