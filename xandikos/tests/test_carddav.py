# Xandikos
# Copyright (C) 2022 Jelmer Vernooĳ <jelmer@jelmer.uk>, et al.
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

import asyncio
import unittest

from ..carddav import NAMESPACE, apply_filter
from ..vcard import VCardFile
from ..webdav import ET
from .test_vcard import EXAMPLE_VCARD1


class TestApplyFilter(unittest.TestCase):

    async def get_file(self):
        return VCardFile([EXAMPLE_VCARD1], "text/vcard")

    def get_content_type(self):
        return "text/vcard"

    def test_apply_filter(self):
        el = ET.Element("{%s}filter" % NAMESPACE)
        el.set("test", "anyof")
        pf = ET.SubElement(el, "{%s}prop-filter" % NAMESPACE)
        pf.set("name", "FN")
        tm = ET.SubElement(pf, "{%s}text-match" % NAMESPACE)
        tm.set("collation", "i;unicode-casemap")
        tm.set("match-type", "contains")
        tm.text = "Jeffrey"
        loop = asyncio.get_event_loop()
        self.assertTrue(loop.run_until_complete(apply_filter(el, self)))
