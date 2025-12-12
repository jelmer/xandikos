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

import shutil
import tempfile
import unittest

from xandikos.web import XandikosApp, XandikosBackend


class WebTests(unittest.TestCase):
    # When changing this API, please update notes/api-stability.rst and inform
    # vdirsyncer, who rely on this API.

    def test_backend(self):
        path = tempfile.mkdtemp()
        try:
            backend = XandikosBackend(path)
            backend.create_principal("foo", create_defaults=True)
            XandikosApp(backend, "foo")
        finally:
            shutil.rmtree(path)
