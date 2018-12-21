# Xandikos
# Copyright (C) 2017 Jelmer Vernooĳ <jelmer@jelmer.uk>, et al.
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

"""VCard file handling.

"""

from .store import File, InvalidFileContents


class VCardFile(File):
    content_type = 'text/vcard'

    def validate(self):
        c = b''.join(self.content).strip()
        # TODO(jelmer): Do more extensive checking of VCards
        if not c.startswith((b'BEGIN:VCARD\r\n', b'BEGIN:VCARD\n')) or \
           not c.endswith(b'\nEND:VCARD'):
            raise InvalidFileContents(
                self.content_type, self.content,
                "Missing header and trailer lines")
