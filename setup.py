#!/usr/bin/env python3
# encoding: utf-8
#
# Xandikos
# Copyright (C) 2016-2017 Jelmer Vernooĳ <jelmer@jelmer.uk>
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

from setuptools import setup

version = "0.0.4"

setup(name="xandikos",
      description="CalDAV/CardDAV server",
      version=version,
      author="Jelmer Vernooij",
      author_email="jelmer@jelmer.uk",
      license="GNU GPLv3 or later",
      url="https://www.jelmer.uk/projects/xandikos",
      install_requires=['icalendar', 'dulwich', 'defusedxml', 'jinja2'],
      packages=['xandikos', 'xandikos.tests'],
      package_data={'xandikos': ['templates/*.html']},
      scripts=['bin/xandikos'],
      classifiers=[
          'Development Status :: 4 - Beta',
          'License :: OSI Approved :: GNU General Public License v3 or later (GPLv3+)',  # noqa
          'Programming Language :: Python :: 3.3',
          'Programming Language :: Python :: 3.4',
          'Programming Language :: Python :: 3.5',
          'Programming Language :: Python :: 3.6',
          'Programming Language :: Python :: Implementation :: CPython',
          'Programming Language :: Python :: Implementation :: PyPy',
          'Operating System :: POSIX',
      ])
