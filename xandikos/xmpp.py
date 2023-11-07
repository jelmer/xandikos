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


"""XMPP support.

https://github.com/evert/calendarserver-extensions/blob/master/caldav-pubsubdiscovery.txt
"""

from . import webdav
from .caldav import CALENDAR_RESOURCE_TYPE

ET = webdav.ET


class XmppUriProperty(webdav.Property):
    """xmpp-uri property."""

    name = "{http://calendarserver.org/ns/}xmpp-uri"
    resource_type = CALENDAR_RESOURCE_TYPE
    in_allprops = True
    live = False

    async def get_value(self, base_href, resource, el, environ):
        el.text = resource.get_xmpp_uri()

    async def set_value(self, href, resource, el):
        raise NotImplementedError(self.set_value)


class XmppHeartbeatProperty(webdav.Property):
    """xmpp-heartbeat property."""

    name = "{http://calendarserver.org/ns/}xmpp-heartbeat"
    resource_type = CALENDAR_RESOURCE_TYPE
    in_allprops = True
    live = False

    async def get_value(self, base_href, resource, el, environ):
        (uri, minutes) = resource.get_xmpp_heartbeat()
        uri_el = ET.SubElement(el, "{http://calendarserver.org/ns/}xmpp-heartbeat-uri")
        uri_el.text = uri
        minutes_el = ET.SubElement(
            el, "{http://calendarserver.org/ns/}xmpp-heartbeat-minutes"
        )
        minutes_el.text = str(minutes)

    async def set_value(self, href, resource, el):
        raise NotImplementedError(self.set_value)


class XmppServerProperty(webdav.Property):
    """xmpp-server property."""

    name = "{http://calendarserver.org/ns/}xmpp-server"
    resource_type = CALENDAR_RESOURCE_TYPE
    in_allprops = True
    live = False

    async def get_value(self, base_href, resource, el, environ):
        server = resource.get_xmpp_server()
        el.text = server

    async def set_value(self, href, resource, el):
        raise NotImplementedError(self.set_value)
