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

"""Tests for xandikos.vcard."""

from datetime import datetime

import pytz
import unittest

from xandikos import (
    collation as _mod_collation,
)
from xandikos.vcard import (
    VCardFile,
)
from xandikos.store import InvalidFileContents

EXAMPLE_VCARD1 = b"""\
BEGIN:VCARD
VERSION:3.0
EMAIL;TYPE=INTERNET:jeffrey@osafoundation.org
EMAIL;TYPE=INTERNET:jeffery@example.org
ORG:Open Source Applications Foundation
FN:Jeffrey Harris
N:Harris;Jeffrey;;;
END:VCARD
"""


class ParseVcardTests(unittest.TestCase):

    def test_validate(self):
        fi = VCardFile([EXAMPLE_VCARD1], "text/calendar")
        fi.validate()
