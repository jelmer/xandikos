# Xandikos
# Copyright (C) 2026 Jelmer Vernooĳ <jelmer@jelmer.uk>, et al.
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

"""Cfait properties.

Cfait (https://github.com/trougnouf/cfait) stores its settings as custom
properties on the default calendar collection. Before using them it probes
for support by setting, reading back and removing a "probe" property.
"""

from xandikos import caldav, webdav

NAMESPACE = "http://trougnouf.com/ns/cfait/"


class SettingsProperty(webdav.Property):
    """JSON settings payload."""

    name = "{%s}settings" % NAMESPACE
    resource_type = caldav.CALENDAR_RESOURCE_TYPE
    live = False

    async def get_value(self, href, resource, el, environ):
        el.text = resource.get_cfait_settings()

    async def set_value(self, href, resource, el):
        resource.set_cfait_settings(None if el is None else (el.text or ""))


class SettingsRevProperty(webdav.Property):
    """Revision of the settings payload, as unix seconds.

    This is derived from the time the settings were last stored.
    """

    name = "{%s}settings-rev" % NAMESPACE
    resource_type = caldav.CALENDAR_RESOURCE_TYPE
    live = False

    async def get_value(self, href, resource, el, environ):
        el.text = str(resource.get_cfait_settings_mtime())

    async def set_value(self, href, resource, el):
        # Cfait always sets this together with the settings, which update
        # the revision. Rejecting it would make Cfait treat custom
        # properties as unsupported.
        pass


class ProbeProperty(webdav.Property):
    """Property used to probe for custom property support."""

    name = "{%s}probe" % NAMESPACE
    resource_type = caldav.CALENDAR_RESOURCE_TYPE
    live = False

    async def get_value(self, href, resource, el, environ):
        el.text = resource.get_cfait_probe()

    async def set_value(self, href, resource, el):
        resource.set_cfait_probe(None if el is None else (el.text or ""))
