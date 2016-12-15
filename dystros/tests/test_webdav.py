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
import defusedxml.ElementTree
from xml.etree import ElementTree as ET

from dystros.webdav import (
    DavResource,
    WebDAVApp,
    )


class WebTests(unittest.TestCase):

    def makeApp(self, resources):
        return WebDAVApp(resources.get)

    def delete(self, app, path):
        environ = {'PATH_INFO': path, 'REQUEST_METHOD': 'DELETE'}
        _code = []
        _headers = []
        def start_response(code, headers):
            _code.append(code)
            _headers.extend(headers)
        contents = b''.join(app(environ, start_response))
        return _code[0], _headers, contents

    def get(self, app, path):
        environ = {'PATH_INFO': path, 'REQUEST_METHOD': 'GET'}
        _code = []
        _headers = []
        def start_response(code, headers):
            _code.append(code)
            _headers.extend(headers)
        contents = b''.join(app(environ, start_response))
        return _code[0], _headers, contents

    def propfind(self, app, path, body):
        environ = {
                'PATH_INFO': path,
                'REQUEST_METHOD': 'PROPFIND',
                'wsgi.input': BytesIO(body)}
        _code = []
        _headers = []
        def start_response(code, headers):
            _code.append(code)
            _headers.extend(headers)
        contents = b''.join(app(environ, start_response))
        return _code[0], _headers, contents

    def test_not_found(self):
        app = self.makeApp({})
        code, headers, contents = self.get(app, '/.well-known/carddav')
        self.assertEqual('404 Not Found', code)

    def test_get_body(self):
        class TestResource(DavResource):

            def get_body(self):
                return b'this is content'
        app = self.makeApp({'/.well-known/carddav': TestResource()})
        code, headers, contents = self.get(app, '/.well-known/carddav')
        self.assertEqual('200 OK', code)
        self.assertEqual(b'this is content', contents)

    def test_delete_not_allowed(self):
        # TODO(jelmer): Implement DELETE
        class TestResource(DavResource):
            pass
        app = self.makeApp({'/resource': TestResource()})
        code, headers, contents = self.delete(app, '/resource')
        self.assertEqual('405 Method Not Allowed', code)
        self.assertIn(('Allow', 'GET, PROPFIND'), headers)
        self.assertEqual(b'', contents)

    def test_propfind_prop_does_not_exist(self):
        class TestResource(DavResource):

            def propget(self, name):
                raise KeyError

        app = self.makeApp({'/resource': TestResource()})
        code, headers, contents = self.propfind(app, '/resource', b"""\
<d:propfind xmlns:d="DAV:"><d:prop><d:resourcetype /></d:prop></d:propfind>""")
        self.assertMultiLineEqual(
            contents.decode('utf-8'),
            '<ns0:propstat xmlns:ns0="DAV:"><ns0:status>HTTP/1.1 404 Not Found</ns0:status>'
            '<ns0:prop><ns0:resourcetype /><ns0:resourcetype /></ns0:prop></ns0:propstat>')
        self.assertEqual(code, '200 OK')

    def test_propfind_found(self):
        class TestResource(DavResource):

            def propget(self, name):
                if name == '{DAV:}current-user-principal':
                    ret = ET.Element('{DAV:}current-user-principal')
                    ET.SubElement(ret, '{DAV:}href').text = '/user/'
                    return ret
                raise KeyError
        app = self.makeApp({'/resource': TestResource()})
        code, headers, contents = self.propfind(app, '/resource', b"""\
<d:propfind xmlns:d="DAV:"><d:prop><d:current-user-principal/>\
</d:prop></d:propfind>""")
        self.assertMultiLineEqual(
            contents.decode('utf-8'),
            '<ns0:propstat xmlns:ns0="DAV:"><ns0:status>HTTP/1.1 200 OK</ns0:status>'
            '<ns0:prop><ns0:current-user-principal><ns0:href>/user/</ns0:href>'
            '</ns0:current-user-principal></ns0:prop></ns0:propstat>')
        self.assertEqual(code, '200 OK')

    def test_propfind_found_multi(self):
        class TestResource(DavResource):

            def propget(self, name):
                if name == '{DAV:}current-user-principal':
                    ret = ET.Element('{DAV:}current-user-principal')
                    ET.SubElement(ret, '{DAV:}href').text = '/user/'
                    return ret
                if name == '{DAV:}somethingelse':
                    ret = ET.Element('{DAV:}somethingelse')
                    return ret
                raise KeyError
        app = self.makeApp({'/resource': TestResource()})
        code, headers, contents = self.propfind(app, '/resource', b"""\
<d:propfind xmlns:d="DAV:"><d:prop><d:current-user-principal/>\
<d:somethingelse/></d:prop></d:propfind>""")
        self.maxDiff = None
        self.assertMultiLineEqual(
            contents.decode('utf-8'),
            '<ns0:propstat xmlns:ns0="DAV:"><ns0:status>HTTP/1.1 200 OK</ns0:status>'
            '<ns0:prop><ns0:current-user-principal><ns0:href>/user/</ns0:href>'
            '</ns0:current-user-principal></ns0:prop>'
            '<ns0:prop><ns0:somethingelse /></ns0:prop>'
            '</ns0:propstat>')
        self.assertEqual(code, '200 OK')

    def test_propfind_found_multi_status(self):
        class TestResource(DavResource):

            def propget(self, name):
                if name == '{DAV:}current-user-principal':
                    ret = ET.Element('{DAV:}current-user-principal')
                    ET.SubElement(ret, '{DAV:}href').text = '/user/'
                    return ret
                if name == '{DAV:}somethingelse':
                    raise KeyError
                raise KeyError
        app = self.makeApp({'/resource': TestResource()})
        code, headers, contents = self.propfind(app, '/resource', b"""\
<d:propfind xmlns:d="DAV:"><d:prop><d:current-user-principal/>\
<d:somethingelse/></d:prop></d:propfind>""")
        self.maxDiff = None
        self.assertEqual(code, '207 Multi-Status')
        self.assertMultiLineEqual(
            contents.decode('utf-8'), """\
<ns0:multistatus xmlns:ns0="DAV:"><ns0:response><ns0:href>/resource</ns0:href>\
<ns0:status>HTTP/1.1 200 OK</ns0:status>\
<ns0:propstat><ns0:status>HTTP/1.1 200 OK</ns0:status><ns0:prop>\
<ns0:current-user-principal><ns0:href>/user/</ns0:href>\
</ns0:current-user-principal></ns0:prop></ns0:propstat><ns0:propstat>\
<ns0:status>HTTP/1.1 404 Not Found</ns0:status><ns0:prop>\
<ns0:somethingelse /><ns0:somethingelse /></ns0:prop></ns0:propstat>\
</ns0:response>\
</ns0:multistatus>""")
