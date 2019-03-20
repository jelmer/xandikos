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

from wsgiref.util import setup_testing_defaults

from xandikos import caldav
from xandikos.webdav import Property, WebDAVApp, ET

from xandikos.tests import test_webdav


class WebTests(test_webdav.WebTestCase):

    def makeApp(self, backend):
        app = WebDAVApp(backend)
        app.register_methods([caldav.MkcalendarMethod()])
        return app

    def mkcalendar(self, app, path):
        environ = {'PATH_INFO': path, 'REQUEST_METHOD': 'MKCALENDAR',
                   'SCRIPT_NAME': ''}
        setup_testing_defaults(environ)
        _code = []
        _headers = []

        def start_response(code, headers):
            _code.append(code)
            _headers.extend(headers)
        contents = b''.join(app(environ, start_response))
        return _code[0], _headers, contents

    def test_mkcalendar_ok(self):
        class Backend(object):
            def create_collection(self, relpath):
                pass

            def get_resource(self, relpath):
                return None

        class ResourceTypeProperty(Property):
            name = '{DAV:}resourcetype'

            def get_value(unused_self, href, resource, ret, environ):
                ET.SubElement(ret, '{DAV:}collection')

            def set_value(unused_self, href, resource, ret):
                self.assertEqual(
                    ['{DAV:}collection',
                     '{urn:ietf:params:xml:ns:caldav}calendar'],
                    [x.tag for x in ret])

        app = self.makeApp(Backend())
        app.register_properties([ResourceTypeProperty()])
        code, headers, contents = self.mkcalendar(app, '/resource/bla')
        self.assertEqual('201 Created', code)
        self.assertEqual(b'', contents)
