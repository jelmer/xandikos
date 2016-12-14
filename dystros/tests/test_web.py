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

from io import BytesIO
import unittest

from dystros.web import DystrosApp


class WebTests(unittest.TestCase):

    def setUp(self):
        super(WebTests, self).setUp()
        self.app = DystrosApp()

    def delete(self, path):
        environ = {'PATH_INFO': path, 'REQUEST_METHOD': 'DELETE'}
        _code = []
        _headers = []
        def start_response(code, headers):
            _code.append(code)
            _headers.extend(headers)
        contents = b''.join(self.app(environ, start_response))
        return _code[0], _headers, contents

    def get(self, path):
        environ = {'PATH_INFO': path, 'REQUEST_METHOD': 'GET'}
        _code = []
        _headers = []
        def start_response(code, headers):
            _code.append(code)
            _headers.extend(headers)
        contents = b''.join(self.app(environ, start_response))
        return _code[0], _headers, contents

    def propfind(self, path, body):
        environ = {
                'PATH_INFO': path,
                'REQUEST_METHOD': 'PROPFIND',
                'wsgi.input': BytesIO(body)}
        _code = []
        _headers = []
        def start_response(code, headers):
            _code.append(code)
            _headers.extend(headers)
        contents = b''.join(self.app(environ, start_response))
        return _code[0], _headers, contents

    def test_wellknown_caldav(self):
        code, headers, contents = self.get('/.well-known/caldav')
        self.assertEqual('200 OK', code)
        self.assertEqual(b'/', contents)

    def test_wellknown_carddav(self):
        code, headers, contents = self.get('/.well-known/carddav')
        self.assertEqual('200 OK', code)
        self.assertEqual(b'/', contents)

    def test_delete_wellknown(self):
        code, headers, contents = self.delete('/.well-known/carddav')
        self.assertEqual('405 Method Not Allowed', code)
        self.assertIn(('Allow', 'GET, PROPFIND'), headers)
        self.assertEqual(b'', contents)

    def test_propfind_wellknown_carddav(self):
        code, headers, contents = self.propfind('/.well-known/carddav', b"""\
<d:propfind xmlns:d="DAV:"><d:prop><d:resourcetype /></d:prop></d:propfind>""")
        self.assertMultiLineEqual(
            contents.decode('utf-8'),
            '<ns0:propstat xmlns:ns0="DAV:"><ns0:status>HTTP/1.1 404 Not Found</ns0:status>'
            '<ns0:prop><ns0:resourcetype /><ns0:resourcetype /></ns0:prop></ns0:propstat>')
        self.assertEqual(code, '200 OK')

    def test_current_user_principal(self):
        code, headers, contents = self.propfind('/.well-known/carddav', b"""\
<d:propfind xmlns:d="DAV:"><d:prop><d:current-user-principal/></d:prop></d:propfind>""")
        self.assertMultiLineEqual(
            contents.decode('utf-8'),
            '<ns0:propstat xmlns:ns0="DAV:"><ns0:status>HTTP/1.1 200 OK</ns0:status>'
            '<ns0:prop><ns0:current-user-principal><ns0:href>/user/</ns0:href>'
            '</ns0:current-user-principal></ns0:prop></ns0:propstat>')
        self.assertEqual(code, '200 OK')
