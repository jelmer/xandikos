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

"""Scheduling.

See https://tools.ietf.org/html/rfc6638
"""

from xandikos import caldav, webdav


SCHEDULE_INBOX_RESOURCE_TYPE = '{%s}schedule-inbox' % caldav.NAMESPACE

# Feature to advertise to indicate scheduling support.
FEATURE = 'calendar-auto-schedule'

CALENDAR_USER_TYPE_INDIVIDUAL = "INDIVIDUAL"  # An individual
CALENDAR_USER_TYPE_GROUP = "GROUP"  # A group of individuals
CALENDAR_USER_TYPE_RESOURCE = "RESOURCE"  # A physical resource
CALENDAR_USER_TYPE_ROOM = "ROOM"  # A room resource
CALENDAR_USER_TYPE_UNKNOWN = "UNKNOWN"  # Otherwise not known

CALENDAR_USER_TYPES = (
    CALENDAR_USER_TYPE_INDIVIDUAL,
    CALENDAR_USER_TYPE_GROUP,
    CALENDAR_USER_TYPE_RESOURCE,
    CALENDAR_USER_TYPE_ROOM,
    CALENDAR_USER_TYPE_UNKNOWN)


class ScheduleInbox(caldav.Calendar):

    resource_types = (caldav.Calendar.resource_types +
                      [SCHEDULE_INBOX_RESOURCE_TYPE])

    def get_schedule_inbox_url(self):
        raise NotImplementedError(self.get_schedule_inbox_url)

    def get_schedule_outbox_url(self):
        raise NotImplementedError(self.get_schedule_outbox_url)

    def get_calendar_user_type(self):
        # Default, per section 2.4.2
        return CALENDAR_USER_TYPE_INDIVIDUAL


class ScheduleInboxURLProperty(webdav.Property):
    """Schedule-inbox-URL property.

    See https://tools.ietf.org/html/rfc6638, section 2.2
    """

    name = '{%s}schedule-inbox-URL' % caldav.NAMESPACE
    resource_type = caldav.CALENDAR_RESOURCE_TYPE
    in_allprops = True

    def get_value(self, href, resource, el):
        el.append(webdav.create_href(resource.get_schedule_inbox_url(), href))


class ScheduleOutboxURLProperty(webdav.Property):
    """Schedule-outbox-URL property.

    See https://tools.ietf.org/html/rfc6638, section 2.1
    """

    name = '{%s}schedule-outbox-URL' % caldav.NAMESPACE
    resource_type = caldav.CALENDAR_RESOURCE_TYPE
    in_allprops = True

    def get_value(self, href, resource, el):
        el.append(webdav.create_href(resource.get_schedule_outbox_url(), href))


class CalendarUserAddressSetProperty(webdav.Property):
    """calendar-user-address-set property

    See https://tools.ietf.org/html/rfc6638, section 2.4.1
    """

    name = '{%s}calendar-user-address-set' % caldav.NAMESPACE
    resource_type = webdav.PRINCIPAL_RESOURCE_TYPE
    in_allprops = False

    def get_value(self, base_href, resource, el):
        for href in resource.get_calendar_user_address_set():
            el.append(webdav.create_href(href, base_href))


class CalendarUserTypeProperty(webdav.Property):
    """calendar-user-type property

    See https://tools.ietf.org/html/rfc6638, section 2.4.2
    """

    name = '{urn:ietf:params:xml:ns:caldav}calendar-user-type'
    resource_type = webdav.PRINCIPAL_RESOURCE_TYPE
    in_allprops = False

    def get_value(self, href, resource, el):
        el.text = resource.get_calendar_user_type()
