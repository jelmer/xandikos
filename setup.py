#!/usr/bin/env python3
# encoding: utf-8
#
# Xandikos
# Copyright (C) 2016-2017 Jelmer Vernooij <jelmer@jelmer.uk>, et al.
#
# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; version 3
# of the License or (at your option) any later version of
# the License.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston,
# MA  02110-1301, USA.

from setuptools import find_packages, setup
import sys

version = "0.1.0"

with open('README.rst', encoding='utf-8') as f:
    long_description = f.read()

if sys.platform == 'win32':
    # Strip out non-mbcs characters
    long_description = long_description.encode('ascii', 'replace').decode()

setup(name="xandikos",
      description="Lightweight CalDAV/CardDAV server",
      long_description=long_description,
      version=version,
      author="Jelmer Vernooij",
      author_email="jelmer@jelmer.uk",
      license="GNU GPLv3 or later",
      url="https://www.xandikos.org/",
      install_requires=[
          'icalendar',
          'dulwich>=0.19.1',
          'defusedxml',
          'jinja2',
      ],
      packages=find_packages(),
      package_data={'xandikos': ['templates/*.html']},
      scripts=['bin/xandikos'],
      test_suite='xandikos.tests.test_suite',
      classifiers=[
          'Development Status :: 4 - Beta',
          'License :: OSI Approved :: GNU General Public License v3 or later (GPLv3+)',  # noqa
          'Programming Language :: Python :: 3.4',
          'Programming Language :: Python :: 3.5',
          'Programming Language :: Python :: 3.6',
          'Programming Language :: Python :: 3.7',
          'Programming Language :: Python :: Implementation :: CPython',
          'Programming Language :: Python :: Implementation :: PyPy',
          'Operating System :: POSIX',
      ])
