# Dystros
# Copyright (C) 2016 Jelmer Vernooij <jelmer@jelmer.uk>
#
# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; version 2
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

"""Web server implementation..

This is the concrete web server implementation. It provides the
high level application logic that combines the WebDAV server,
the carddav support, the caldav support and the DAV store.
"""

from dystros import caldav, carddav
from dystros.webdav import DAVBackend, WebDAVApp, NonDAVResource, WellknownResource

WELLKNOWN_DAV_PATHS = set([caldav.WELLKNOWN_CALDAV_PATH, carddav.WELLKNOWN_CARDDAV_PATH])
CALENDAR_HOME_SET = '/user/calendars/'
CURRENT_USER_PRINCIPAL = '/user/'


class DystrosBackend(DAVBackend):

    def get_resource(self, p):
        if p in WELLKNOWN_DAV_PATHS:
            r = WellknownResource("/")
        elif p == "/":
            return NonDAVResource()
        elif p == CURRENT_USER_PRINCIPAL:
            return caldav.UserPrincipalResource()
        elif p == CALENDAR_HOME_SET:
            return caldav.CalendarSetResource()
        else:
            return None


class DystrosApp(WebDAVApp):
    """A wsgi App that provides a Dystros web server.
    """

    def __init__(self):
        super(DystrosApp, self).__init__(DystrosBackend())


if __name__ == '__main__':
    import optparse
    import sys
    parser = optparse.OptionParser()
    parser.add_option("-l", "--listen_address", dest="listen_address",
                      default="localhost",
                      help="Binding IP address.")
    parser.add_option("-p", "--port", dest="port", type=int,
                      default=8000,
                      help="Port to listen on.")
    options, args = parser.parse_args(sys.argv)

    from wsgiref.simple_server import make_server
    app = DystrosApp()
    server = make_server(options.listen_address, options.port, app)
    server.serve_forever()
