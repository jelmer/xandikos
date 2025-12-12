# Xandikos
# Copyright (C) 2016-2017 Jelmer Vernooĳ <jelmer@jelmer.uk>, et al.
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

import unittest


def test_suite():
    names = [
        "apache",
        "api",
        "caldav",
        "carddav",
        "config",
        "davcommon",
        "icalendar",
        "insufficient_index_handling",
        "main",
        "rrule_index_usage",
        "store",
        "store_regression",
        "sync",
        "vcard",
        "webdav",
        "web",
        "wsgi",
        "wsgi_helpers",
    ]
    module_names = ["tests.test_" + name for name in names]
    loader = unittest.TestLoader()
    return loader.loadTestsFromNames(module_names)
