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

"""Currently called author to not make a huge delta, but already going more in
the direction of processing anything from the environment into information that
goes into the commit"""

from typing import Optional

class Author:
    @classmethod
    def from_request(cls, request):
        s = cls()
        s._request = request
        return s

    def as_git_trailers(self) -> str:
        trailers = {k: v for (k, v) in self._request.headers.items() if k.lower() in ('user-agent', )}
        return "\n".join("%s: %s" % (k, v) for (k, v) in trailers.items())

    def as_git_author(self) -> Optional[str]:
        return None
