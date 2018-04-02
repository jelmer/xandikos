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

from io import BytesIO
import logging
import unittest
from wsgiref.util import setup_testing_defaults

from xandikos import webdav
from xandikos.webdav import (
    Collection,
    ET,
    Property,
    Resource,
    WebDAVApp
)


class WebTestCase(unittest.TestCase):

    def setUp(self):
        super(WebTestCase, self).setUp()
        logging.disable(logging.WARNING)
        self.addCleanup(logging.disable, logging.NOTSET)

    def makeApp(self, resources, properties):
        class Backend(object):
            get_resource = resources.get
        app = WebDAVApp(Backend())
        app.register_properties(properties)
        return app


class WebTests(WebTestCase):

    def _method(self, app, method, path):
        environ = {'PATH_INFO': path, 'REQUEST_METHOD': method}
        setup_testing_defaults(environ)
        _code = []
        _headers = []

        def start_response(code, headers):
            _code.append(code)
            _headers.extend(headers)
        contents = b''.join(app(environ, start_response))
        return _code[0], _headers, contents

    def lock(self, app, path):
        return self._method(app, 'LOCK', path)

    def mkcol(self, app, path):
        environ = {'PATH_INFO': path, 'REQUEST_METHOD': 'MKCOL'}
        setup_testing_defaults(environ)
        _code = []
        _headers = []

        def start_response(code, headers):
            _code.append(code)
            _headers.extend(headers)
        contents = b''.join(app(environ, start_response))
        return _code[0], _headers, contents

    def delete(self, app, path):
        environ = {'PATH_INFO': path, 'REQUEST_METHOD': 'DELETE'}
        setup_testing_defaults(environ)
        _code = []
        _headers = []

        def start_response(code, headers):
            _code.append(code)
            _headers.extend(headers)
        contents = b''.join(app(environ, start_response))
        return _code[0], _headers, contents

    def get(self, app, path):
        environ = {'PATH_INFO': path, 'REQUEST_METHOD': 'GET'}
        setup_testing_defaults(environ)
        _code = []
        _headers = []

        def start_response(code, headers):
            _code.append(code)
            _headers.extend(headers)
        contents = b''.join(app(environ, start_response))
        return _code[0], _headers, contents

    def put(self, app, path, contents):
        environ = {
            'PATH_INFO': path,
            'REQUEST_METHOD': 'PUT',
            'wsgi.input': BytesIO(contents),
        }
        setup_testing_defaults(environ)
        _code = []
        _headers = []

        def start_response(code, headers):
            _code.append(code)
            _headers.extend(headers)
        list(app(environ, start_response))
        return _code[0], _headers

    def propfind(self, app, path, body):
        environ = {
            'PATH_INFO': path,
            'REQUEST_METHOD': 'PROPFIND',
            'wsgi.input': BytesIO(body),
        }
        setup_testing_defaults(environ)
        _code = []
        _headers = []

        def start_response(code, headers):
            _code.append(code)
            _headers.extend(headers)
        contents = b''.join(app(environ, start_response))
        return _code[0], _headers, contents

    def test_not_found(self):
        app = self.makeApp({}, [])
        code, headers, contents = self.get(app, '/.well-known/carddav')
        self.assertEqual('404 Not Found', code)

    def test_get_body(self):
        class TestResource(Resource):
            def get_body(self):
                return [b'this is content']

            def get_last_modified(self):
                raise KeyError

            def get_content_language(self):
                raise KeyError

            def get_etag(self):
                return "myetag"

            def get_content_type(self):
                return 'text/plain'
        app = self.makeApp({'/.well-known/carddav': TestResource()}, [])
        code, headers, contents = self.get(app, '/.well-known/carddav')
        self.assertEqual('200 OK', code)
        self.assertEqual(b'this is content', contents)

    def test_set_body(self):
        new_body = []

        class TestResource(Resource):
            def set_body(self, body, replace_etag=None):
                new_body.extend(body)

            def get_etag(self):
                return '"blala"'
        app = self.makeApp({'/.well-known/carddav': TestResource()}, [])
        code, headers = self.put(
            app, '/.well-known/carddav', b'New contents')
        self.assertEqual('204 No Content', code)
        self.assertEqual([b'New contents'], new_body)

    def test_lock_not_allowed(self):
        app = self.makeApp({}, [])
        code, headers, contents = self.lock(app, '/resource')
        self.assertEqual('405 Method Not Allowed', code)
        self.assertIn(
            ('Allow', ('DELETE, GET, HEAD, MKCOL, OPTIONS, '
                       'POST, PROPFIND, PROPPATCH, PUT, REPORT')),
            headers)
        self.assertEqual(b'', contents)

    def test_mkcol_ok(self):
        class Backend(object):
            def create_collection(self, relpath):
                pass

            def get_resource(self, relpath):
                return None
        app = WebDAVApp(Backend())
        code, headers, contents = self.mkcol(app, '/resource/bla')
        self.assertEqual('201 Created', code)
        self.assertEqual(b'', contents)

    def test_mkcol_exists(self):
        app = self.makeApp({
            '/resource': Resource(),
            '/resource/bla': Resource()}, [])
        code, headers, contents = self.mkcol(app, '/resource/bla')
        self.assertEqual('405 Method Not Allowed', code)
        self.assertEqual(b'', contents)

    def test_delete(self):
        class TestResource(Collection):

            def get_etag(self):
                return '"foo"'

            def delete_member(unused_self, name, etag=None):
                self.assertEqual(name, 'resource')
        app = self.makeApp({'/': TestResource(), '/resource': TestResource()},
                           [])
        code, headers, contents = self.delete(app, '/resource')
        self.assertEqual('204 No Content', code)
        self.assertEqual(b'', contents)

    def test_delete_not_found(self):
        class TestResource(Collection):
            pass

        app = self.makeApp({'/resource': TestResource()}, [])
        code, headers, contents = self.delete(app, '/resource')
        self.assertEqual('404 Not Found', code)
        self.assertTrue(contents.endswith(b'/resource not found.'))

    def test_propfind_prop_does_not_exist(self):
        app = self.makeApp({'/resource': Resource()}, [])
        code, headers, contents = self.propfind(app, '/resource', b"""\
<d:propfind xmlns:d="DAV:"><d:prop><d:resourcetype /></d:prop></d:propfind>""")
        self.assertMultiLineEqual(
            contents.decode('utf-8'),
            '<ns0:multistatus xmlns:ns0="DAV:"><ns0:response>'
            '<ns0:href>/resource</ns0:href>'
            '<ns0:propstat><ns0:status>HTTP/1.1 404 Not Found</ns0:status>'
            '<ns0:prop><ns0:resourcetype /></ns0:prop></ns0:propstat>'
            '</ns0:response></ns0:multistatus>')
        self.assertEqual(code, '207 Multi-Status')

    def test_propfind_prop_not_present(self):
        class TestProperty(Property):
            name = '{DAV:}current-user-principal'

            def get_value(self, href, resource, ret, environ):
                raise KeyError
        app = self.makeApp({'/resource': Resource()}, [TestProperty()])
        code, headers, contents = self.propfind(app, '/resource', b"""\
<d:propfind xmlns:d="DAV:"><d:prop><d:resourcetype /></d:prop></d:propfind>""")
        self.assertMultiLineEqual(
            contents.decode('utf-8'),
            '<ns0:multistatus xmlns:ns0="DAV:"><ns0:response>'
            '<ns0:href>/resource</ns0:href>'
            '<ns0:propstat><ns0:status>HTTP/1.1 404 Not Found</ns0:status>'
            '<ns0:prop><ns0:resourcetype /></ns0:prop></ns0:propstat>'
            '</ns0:response></ns0:multistatus>')
        self.assertEqual(code, '207 Multi-Status')

    def test_propfind_found(self):
        class TestProperty(Property):
            name = '{DAV:}current-user-principal'

            def get_value(self, href, resource, ret, environ):
                ET.SubElement(ret, '{DAV:}href').text = '/user/'
        app = self.makeApp({'/resource': Resource()}, [TestProperty()])
        code, headers, contents = self.propfind(app, '/resource', b"""\
<d:propfind xmlns:d="DAV:"><d:prop><d:current-user-principal/>\
</d:prop></d:propfind>""")
        self.assertMultiLineEqual(
            contents.decode('utf-8'),
            '<ns0:multistatus xmlns:ns0="DAV:"><ns0:response>'
            '<ns0:href>/resource</ns0:href>'
            '<ns0:propstat><ns0:status>HTTP/1.1 200 OK</ns0:status>'
            '<ns0:prop><ns0:current-user-principal><ns0:href>/user/</ns0:href>'
            '</ns0:current-user-principal></ns0:prop></ns0:propstat>'
            '</ns0:response></ns0:multistatus>')
        self.assertEqual(code, '207 Multi-Status')

    def test_propfind_found_multi(self):
        class TestProperty1(Property):
            name = '{DAV:}current-user-principal'

            def get_value(self, href, resource, el, environ):
                ET.SubElement(el, '{DAV:}href').text = '/user/'

        class TestProperty2(Property):
            name = '{DAV:}somethingelse'

            def get_value(self, href, resource, el, environ):
                pass
        app = self.makeApp(
            {'/resource': Resource()},
            [TestProperty1(), TestProperty2()]
        )
        code, headers, contents = self.propfind(app, '/resource', b"""\
<d:propfind xmlns:d="DAV:"><d:prop><d:current-user-principal/>\
<d:somethingelse/></d:prop></d:propfind>""")
        self.maxDiff = None
        self.assertMultiLineEqual(
            contents.decode('utf-8'),
            '<ns0:multistatus xmlns:ns0="DAV:"><ns0:response>'
            '<ns0:href>/resource</ns0:href>'
            '<ns0:propstat><ns0:status>HTTP/1.1 200 OK</ns0:status>'
            '<ns0:prop><ns0:current-user-principal><ns0:href>/user/</ns0:href>'
            '</ns0:current-user-principal><ns0:somethingelse /></ns0:prop>'
            '</ns0:propstat></ns0:response></ns0:multistatus>')
        self.assertEqual(code, '207 Multi-Status')

    def test_propfind_found_multi_status(self):
        class TestProperty(Property):
            name = '{DAV:}current-user-principal'

            def get_value(self, href, resource, ret, environ):
                ET.SubElement(ret, '{DAV:}href').text = '/user/'
        app = self.makeApp({'/resource': Resource()}, [TestProperty()])
        code, headers, contents = self.propfind(app, '/resource', b"""\
<d:propfind xmlns:d="DAV:"><d:prop><d:current-user-principal/>\
<d:somethingelse/></d:prop></d:propfind>""")
        self.maxDiff = None
        self.assertEqual(code, '207 Multi-Status')
        self.assertMultiLineEqual(
            contents.decode('utf-8'), """\
<ns0:multistatus xmlns:ns0="DAV:"><ns0:response><ns0:href>/resource</ns0:href>\
<ns0:propstat><ns0:status>HTTP/1.1 200 OK</ns0:status><ns0:prop>\
<ns0:current-user-principal><ns0:href>/user/</ns0:href>\
</ns0:current-user-principal></ns0:prop></ns0:propstat><ns0:propstat>\
<ns0:status>HTTP/1.1 404 Not Found</ns0:status><ns0:prop>\
<ns0:somethingelse /></ns0:prop></ns0:propstat>\
</ns0:response>\
</ns0:multistatus>""")


class PickContentTypesTests(unittest.TestCase):

    def test_not_acceptable(self):
        self.assertRaises(
            webdav.NotAcceptableError, webdav.pick_content_types,
            [('text/plain', {})], ['text/html'])
        self.assertRaises(
            webdav.NotAcceptableError, webdav.pick_content_types,
            [('text/plain', {}), ('text/html', {'q': '0'})], ['text/html'])

    def test_highest_q(self):
        self.assertEqual(
            ['text/plain'], webdav.pick_content_types(
                [('text/html', {'q': '0.3'}), ('text/plain', {'q': '0.4'})],
                ['text/plain', 'text/html']))
        self.assertEqual(
            ['text/html', 'text/plain'], webdav.pick_content_types(
                [('text/html', {}), ('text/plain', {'q': '1'})],
                ['text/plain', 'text/html']))

    def test_no_q(self):
        self.assertEqual(
            ['text/html', 'text/plain'], webdav.pick_content_types(
                [('text/html', {}), ('text/plain', {})],
                ['text/plain', 'text/html']))

    def test_wildcard(self):
        self.assertEqual(
            ['text/plain'], webdav.pick_content_types(
                [('text/*', {'q': '0.3'}), ('text/plain', {'q': '0.4'})],
                ['text/plain', 'text/html']))
        self.assertEqual(
            set(['text/plain', 'text/html']), set(webdav.pick_content_types(
                [('text/*', {'q': '0.4'}), ('text/plain', {'q': '0.3'})],
                ['text/plain', 'text/html'])))
        self.assertEqual(
            ['application/html'], webdav.pick_content_types(
                [('application/*', {'q': '0.4'}),
                 ('text/plain', {'q': '0.3'})],
                ['text/plain', 'application/html']))


class ParseAcceptHeaderTests(unittest.TestCase):

    def test_parse(self):
        self.assertEqual([], webdav.parse_accept_header(''))
        self.assertEqual([('text/plain', {'q': '0.1'})],
                         webdav.parse_accept_header('text/plain; q=0.1'))
        self.assertEqual([('text/plain', {'q': '0.1'}), ('text/plain', {})],
                         webdav.parse_accept_header(
                             'text/plain; q=0.1, text/plain'))


class ETagMatchesTests(unittest.TestCase):

    def test_matches(self):
        self.assertTrue(webdav.etag_matches('etag1, etag2', 'etag1'))
        self.assertFalse(webdav.etag_matches('etag3, etag2', 'etag1'))
        self.assertFalse(webdav.etag_matches('etag1 etag2', 'etag1'))
        self.assertFalse(webdav.etag_matches('etag1, etag2', None))
        self.assertTrue(webdav.etag_matches('*, etag2', 'etag1'))
        self.assertTrue(webdav.etag_matches('*', 'etag1'))
        self.assertFalse(webdav.etag_matches('*', None))


class PropstatByStatusTests(unittest.TestCase):

    def test_none(self):
        self.assertEqual({}, webdav.propstat_by_status([]))

    def test_one(self):
        self.assertEqual({
            ('200 OK', None): ['foo']},
            webdav.propstat_by_status([
                webdav.PropStatus('200 OK', None, 'foo')]))

    def test_multiple(self):
        self.assertEqual({
            ('200 OK', None): ['foo'],
            ('404 Not Found', 'Cannot find'): ['bar']},
            webdav.propstat_by_status([
                webdav.PropStatus('200 OK', None, 'foo'),
                webdav.PropStatus('404 Not Found', 'Cannot find', 'bar')]))


class PropstatAsXmlTests(unittest.TestCase):

    def test_none(self):
        self.assertEqual([], list(webdav.propstat_as_xml([])))

    def test_one(self):
        self.assertEqual([
            b'<ns0:propstat xmlns:ns0="DAV:"><ns0:status>HTTP/1.1 200 '
            b'OK</ns0:status><ns0:prop><foo /></ns0:prop></ns0:propstat>'],
            [ET.tostring(x) for x in webdav.propstat_as_xml([
                webdav.PropStatus('200 OK', None, ET.Element('foo'))])])


class PathFromEnvironTests(unittest.TestCase):

    def test_ascii(self):
        self.assertEqual(
            '/bla',
            webdav.path_from_environ({'PATH_INFO': '/bla'}, 'PATH_INFO'))

    def test_recode(self):
        self.assertEqual(
            '/blü',
            webdav.path_from_environ(
                {'PATH_INFO': '/bl\xc3\xbc'}, 'PATH_INFO'))
