#!/usr/bin/env python3
# encoding: utf-8
#
# Xandikos
# Copyright (C) 2016 Jelmer Vernooĳ <jelmer@jelmer.uk>
#
# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; version 2
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

from distutils.core import setup

version = "0.0.1"

setup(name="xandikos",
      description="CalDAV/CardDAV server",
      version=version,
      author="Jelmer Vernooij",
      author_email="jelmer@jelmer.uk",
      license="Apache v2 or later",
      url="https://www.jelmer.uk/projects/xandikos",
      requires=['icalendar', 'dulwich', 'defusedxml'],
      packages=['xandikos'])
