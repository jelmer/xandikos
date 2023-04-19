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
from wsgiref.util import setup_testing_defaults

from icalendar.cal import Calendar as ICalendar

from xandikos import caldav
from xandikos.tests import test_webdav

from ..webdav import ET, Property, WebDAVApp


class WebTests(test_webdav.WebTestCase):
    def makeApp(self, backend):
        app = WebDAVApp(backend)
        app.register_methods([caldav.MkcalendarMethod()])
        return app

    def mkcalendar(self, app, path):
        environ = {
            "PATH_INFO": path,
            "REQUEST_METHOD": "MKCALENDAR",
            "SCRIPT_NAME": "",
        }
        setup_testing_defaults(environ)
        _code = []
        _headers = []

        def start_response(code, headers):
            _code.append(code)
            _headers.extend(headers)

        contents = b"".join(app(environ, start_response))
        return _code[0], _headers, contents

    def test_mkcalendar_ok(self):
        class Backend:
            def create_collection(self, relpath):
                pass

            def get_resource(self, relpath):
                return None

        class ResourceTypeProperty(Property):
            name = "{DAV:}resourcetype"

            async def get_value(unused_self, href, resource, ret, environ):
                ET.SubElement(ret, "{DAV:}collection")

            async def set_value(unused_self, href, resource, ret):
                self.assertEqual(
                    [
                        "{DAV:}collection",
                        "{urn:ietf:params:xml:ns:caldav}calendar",
                    ],
                    [x.tag for x in ret],
                )

        app = self.makeApp(Backend())
        app.register_properties([ResourceTypeProperty()])
        code, headers, contents = self.mkcalendar(app, "/resource/bla")
        self.assertEqual("201 Created", code)
        self.assertEqual(b"", contents)


class ExtractfromCalendarTests(unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.requested = ET.Element("{%s}calendar-data" % caldav.NAMESPACE)

    def extractEqual(self, incal_str, outcal_str):
        incal = ICalendar.from_ical(incal_str)
        expected_outcal = ICalendar.from_ical(outcal_str)
        outcal = ICalendar()
        outcal = caldav.extract_from_calendar(incal, self.requested)
        self.maxDiff = None
        self.assertMultiLineEqual(
            expected_outcal.to_ical().decode(),
            outcal.to_ical().decode(),
            ET.tostring(self.requested),
        )

    def test_comp(self):
        comp = ET.SubElement(self.requested, "{%s}comp" % caldav.NAMESPACE)
        comp.set("name", "VCALENDAR")
        self.extractEqual(
            """\
BEGIN:VCALENDAR
BEGIN:VTODO
CLASS:PUBLIC
COMPLETED:20100829T234417Z
CREATED:20090606T042958Z
END:VTODO
END:VCALENDAR
""",
            """\
BEGIN:VCALENDAR
END:VCALENDAR
""",
        )

    def test_comp_nested(self):
        vcal_comp = ET.SubElement(
            self.requested, "{%s}comp" % caldav.NAMESPACE)
        vcal_comp.set("name", "VCALENDAR")
        vtodo_comp = ET.SubElement(vcal_comp, "{%s}comp" % caldav.NAMESPACE)
        vtodo_comp.set("name", "VTODO")
        self.extractEqual(
            """\
BEGIN:VCALENDAR
BEGIN:VTODO
COMPLETED:20100829T234417Z
CREATED:20090606T042958Z
END:VTODO
END:VCALENDAR
""",
            """\
BEGIN:VCALENDAR
BEGIN:VTODO
END:VTODO
END:VCALENDAR
""",
        )
        self.extractEqual(
            """\
BEGIN:VCALENDAR
BEGIN:VEVENT
COMPLETED:20100829T234417Z
CREATED:20090606T042958Z
END:VEVENT
END:VCALENDAR
""",
            """\
BEGIN:VCALENDAR
END:VCALENDAR
""",
        )

    def test_prop(self):
        vcal_comp = ET.SubElement(
            self.requested, "{%s}comp" % caldav.NAMESPACE)
        vcal_comp.set("name", "VCALENDAR")
        vtodo_comp = ET.SubElement(vcal_comp, "{%s}comp" % caldav.NAMESPACE)
        vtodo_comp.set("name", "VTODO")
        completed_prop = ET.SubElement(
            vtodo_comp, "{%s}prop" % caldav.NAMESPACE)
        completed_prop.set("name", "COMPLETED")
        self.extractEqual(
            """\
BEGIN:VCALENDAR
BEGIN:VTODO
COMPLETED:20100829T234417Z
CREATED:20090606T042958Z
END:VTODO
END:VCALENDAR
""",
            """\
BEGIN:VCALENDAR
BEGIN:VTODO
COMPLETED:20100829T234417Z
END:VTODO
END:VCALENDAR
""",
        )
        self.extractEqual(
            """\
BEGIN:VCALENDAR
BEGIN:VEVENT
CREATED:20090606T042958Z
END:VEVENT
END:VCALENDAR
""",
            """\
BEGIN:VCALENDAR
END:VCALENDAR
""",
        )

    def test_allprop(self):
        vcal_comp = ET.SubElement(
            self.requested, "{%s}comp" % caldav.NAMESPACE)
        vcal_comp.set("name", "VCALENDAR")
        vtodo_comp = ET.SubElement(vcal_comp, "{%s}comp" % caldav.NAMESPACE)
        vtodo_comp.set("name", "VTODO")
        ET.SubElement(vtodo_comp, "{%s}allprop" % caldav.NAMESPACE)
        self.extractEqual(
            """\
BEGIN:VCALENDAR
BEGIN:VTODO
COMPLETED:20100829T234417Z
CREATED:20090606T042958Z
END:VTODO
END:VCALENDAR
""",
            """\
BEGIN:VCALENDAR
BEGIN:VTODO
COMPLETED:20100829T234417Z
CREATED:20090606T042958Z
END:VTODO
END:VCALENDAR
""",
        )

    def test_allcomp(self):
        vcal_comp = ET.SubElement(
            self.requested, "{%s}comp" % caldav.NAMESPACE)
        vcal_comp.set("name", "VCALENDAR")
        ET.SubElement(vcal_comp, "{%s}allcomp" % caldav.NAMESPACE)
        self.extractEqual(
            """\
BEGIN:VCALENDAR
BEGIN:VTODO
COMPLETED:20100829T234417Z
CREATED:20090606T042958Z
END:VTODO
END:VCALENDAR
""",
            """\
BEGIN:VCALENDAR
BEGIN:VTODO
END:VTODO
END:VCALENDAR
""",
        )

    def test_expand(self):
        expand = ET.SubElement(self.requested, "{%s}expand" % caldav.NAMESPACE)
        expand.set("start", "20060103T000000Z")
        expand.set("end", "20060105T000000Z")
        self.extractEqual(
            """\
BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Example Corp.//CalDAV Client//EN
BEGIN:VTIMEZONE
LAST-MODIFIED:20040110T032845Z
TZID:US/Eastern
BEGIN:DAYLIGHT
DTSTART:20000404T020000
RRULE:FREQ=YEARLY;BYDAY=1SU;BYMONTH=4
TZNAME:EDT
TZOFFSETFROM:-0500
TZOFFSETTO:-0400
END:DAYLIGHT
BEGIN:STANDARD
DTSTART:20001026T020000
RRULE:FREQ=YEARLY;BYDAY=-1SU;BYMONTH=10
TZNAME:EST
TZOFFSETFROM:-0400
TZOFFSETTO:-0500
END:STANDARD
END:VTIMEZONE
BEGIN:VEVENT
DTSTAMP:20060206T001121Z
DTSTART;TZID=US/Eastern:20060102T120000
DURATION:PT1H
RRULE:FREQ=DAILY;COUNT=5
SUMMARY:Event #2
UID:00959BC664CA650E933C892C@example.com
END:VEVENT
BEGIN:VEVENT
DTSTAMP:20060206T001121Z
DTSTART;TZID=US/Eastern:20060104T140000
DURATION:PT1H
RECURRENCE-ID;TZID=US/Eastern:20060104T120000
SUMMARY:Event #2 bis
UID:00959BC664CA650E933C892C@example.com
END:VEVENT
END:VCALENDAR
""",
            """\
BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Example Corp.//CalDAV Client//EN
BEGIN:VEVENT
DTSTAMP:20060206T001121Z
DTSTART:20060103T170000
DURATION:PT1H
RECURRENCE-ID:20060103T170000
SUMMARY:Event #2
UID:00959BC664CA650E933C892C@example.com
END:VEVENT
BEGIN:VEVENT
DTSTAMP:20060206T001121Z
DTSTART:20060104T190000
DURATION:PT1H
RECURRENCE-ID:20060104T170000
SUMMARY:Event #2 bis
UID:00959BC664CA650E933C892C@example.com
END:VEVENT
END:VCALENDAR
""",
        )
