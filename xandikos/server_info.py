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

"""Server info.

See https://www.ietf.org/archive/id/draft-douglass-server-info-03.txt
"""

import hashlib


from xandikos import version_string, webdav

ET = webdav.ET

# Feature to advertise server-info support.
FEATURE = "server-info"
SERVER_INFO_MIME_TYPE = "application/server-info+xml"


class ServerInfo:
    """Server info."""

    def __init__(self) -> None:
        self._token = None
        self._features: list[str] = []
        self._applications: list[str] = []

    def add_feature(self, feature):
        self._features.append(feature)
        self._token = None

    @property
    def token(self):
        if self._token is None:
            h = hashlib.sha1()
            h.update(version_string.encode("utf-8"))
            for z in self._features + self._applications:
                h.update(z.encode("utf-8"))
            self._token = h.hexdigest()
        return self._token

    async def get_body(self):
        el = ET.Element("{DAV:}server-info")
        el.set("token", self.token)
        server_el = ET.SubElement(el, "server-instance-info")
        ET.SubElement(server_el, "name").text = "Xandikos"
        ET.SubElement(server_el, "version").text = version_string
        features_el = ET.SubElement(el, "features")
        for feature in self._features:
            features_el.append(feature)
        applications_el = ET.SubElement(el, "applications")
        for application in self.applications:
            applications_el.append(application)
        return el
