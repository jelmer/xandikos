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

import asyncio
import logging
import unittest
from io import BytesIO
from wsgiref.util import setup_testing_defaults

from xandikos import webdav

from xandikos.webdav import (
    ET,
    Collection,
    Property,
    ProtectedPropertyError,
    Resource,
    WebDAVApp,
    href_to_path,
    split_path_preserving_encoding,
    DisplayNameProperty,
    ResourceTypeProperty,
    apply_modify_prop,
)


class WebTestCase(unittest.TestCase):
    def setUp(self):
        super().setUp()
        logging.disable(logging.WARNING)
        self.addCleanup(logging.disable, logging.NOTSET)

    def makeApp(self, resources, properties):
        class Backend:
            get_resource = resources.get

            async def copy_collection(self, source_path, dest_path, overwrite=True):
                raise NotImplementedError()

            async def move_collection(self, source_path, dest_path, overwrite=True):
                raise NotImplementedError()

        app = WebDAVApp(Backend())
        app.register_properties(properties)
        return app


class WebTests(WebTestCase):
    def _method(self, app, method, path):
        environ = {"PATH_INFO": path, "REQUEST_METHOD": method}
        setup_testing_defaults(environ)
        _code = []
        _headers = []

        def start_response(code, headers):
            _code.append(code)
            _headers.extend(headers)

        contents = b"".join(app(environ, start_response))
        return _code[0], _headers, contents

    def lock(self, app, path):
        return self._method(app, "LOCK", path)

    def options(self, app, path):
        return self._method(app, "OPTIONS", path)

    def mkcol(self, app, path, body=None):
        environ = {
            "PATH_INFO": path,
            "REQUEST_METHOD": "MKCOL",
        }
        if body is not None:
            environ["CONTENT_TYPE"] = "text/xml"
            environ["wsgi.input"] = BytesIO(body)
        setup_testing_defaults(environ)
        _code = []
        _headers = []

        def start_response(code, headers):
            _code.append(code)
            _headers.extend(headers)

        contents = b"".join(app(environ, start_response))
        return _code[0], _headers, contents

    def delete(self, app, path, if_match=None):
        environ = {"PATH_INFO": path, "REQUEST_METHOD": "DELETE"}
        if if_match is not None:
            environ["HTTP_IF_MATCH"] = if_match
        setup_testing_defaults(environ)
        _code = []
        _headers = []

        def start_response(code, headers):
            _code.append(code)
            _headers.extend(headers)

        contents = b"".join(app(environ, start_response))
        return _code[0], _headers, contents

    def get(self, app, path, if_none_match=None):
        environ = {"PATH_INFO": path, "REQUEST_METHOD": "GET"}
        if if_none_match is not None:
            environ["HTTP_IF_NONE_MATCH"] = if_none_match
        setup_testing_defaults(environ)
        _code = []
        _headers = []

        def start_response(code, headers):
            _code.append(code)
            _headers.extend(headers)

        contents = b"".join(app(environ, start_response))
        return _code[0], _headers, contents

    def put(self, app, path, contents, if_match=None, if_none_match=None):
        environ = {
            "PATH_INFO": path,
            "REQUEST_METHOD": "PUT",
            "wsgi.input": BytesIO(contents),
        }
        if if_match is not None:
            environ["HTTP_IF_MATCH"] = if_match
        if if_none_match is not None:
            environ["HTTP_IF_NONE_MATCH"] = if_none_match
        setup_testing_defaults(environ)
        _code = []
        _headers = []

        def start_response(code, headers):
            _code.append(code)
            _headers.extend(headers)

        list(app(environ, start_response))
        return _code[0], _headers

    def move(self, app, path, destination, overwrite=None, depth=None):
        environ = {
            "PATH_INFO": path,
            "REQUEST_METHOD": "MOVE",
        }
        if destination is not None:
            environ["HTTP_DESTINATION"] = destination
        if overwrite is not None:
            environ["HTTP_OVERWRITE"] = "T" if overwrite else "F"
        if depth is not None:
            environ["HTTP_DEPTH"] = depth
        setup_testing_defaults(environ)
        # Add HTTP_HOST for proper destination parsing
        environ["HTTP_HOST"] = "localhost"
        _code = []
        _headers = []

        def start_response(code, headers):
            _code.append(code)
            _headers.extend(headers)

        contents = b"".join(app(environ, start_response))
        return _code[0], _headers, contents

    def copy(self, app, path, destination, overwrite=None, depth=None):
        environ = {
            "PATH_INFO": path,
            "REQUEST_METHOD": "COPY",
        }
        if destination is not None:
            environ["HTTP_DESTINATION"] = destination
        if overwrite is not None:
            environ["HTTP_OVERWRITE"] = "T" if overwrite else "F"
        if depth is not None:
            environ["HTTP_DEPTH"] = depth
        setup_testing_defaults(environ)
        # Add HTTP_HOST for proper destination parsing
        environ["HTTP_HOST"] = "localhost"
        _code = []
        _headers = []

        def start_response(code, headers):
            _code.append(code)
            _headers.extend(headers)

        contents = b"".join(app(environ, start_response))
        return _code[0], _headers, contents

    def propfind(self, app, path, body, depth=None):
        environ = {
            "PATH_INFO": path,
            "REQUEST_METHOD": "PROPFIND",
            "CONTENT_TYPE": "text/xml",
            "wsgi.input": BytesIO(body),
        }
        if depth is not None:
            environ["HTTP_DEPTH"] = depth
        setup_testing_defaults(environ)
        _code = []
        _headers = []

        def start_response(code, headers):
            _code.append(code)
            _headers.extend(headers)

        contents = b"".join(app(environ, start_response))
        return _code[0], _headers, contents

    def proppatch(self, app, path, body):
        environ = {
            "PATH_INFO": path,
            "REQUEST_METHOD": "PROPPATCH",
            "CONTENT_TYPE": "text/xml",
            "wsgi.input": BytesIO(body),
        }
        setup_testing_defaults(environ)
        _code = []
        _headers = []

        def start_response(code, headers):
            _code.append(code)
            _headers.extend(headers)

        contents = b"".join(app(environ, start_response))
        return _code[0], _headers, contents

    def test_not_found(self):
        app = self.makeApp({}, [])
        code, headers, contents = self.get(app, "/.well-known/carddav")
        self.assertEqual("404 Not Found", code)

    def test_get_body(self):
        class TestResource(Resource):
            async def get_body(self):
                return [b"this is content"]

            def get_last_modified(self):
                raise KeyError

            def get_content_language(self):
                raise KeyError

            async def get_etag(self):
                return "myetag"

            def get_content_type(self):
                return "text/plain"

        app = self.makeApp({"/.well-known/carddav": TestResource()}, [])
        code, headers, contents = self.get(app, "/.well-known/carddav")
        self.assertEqual("200 OK", code)
        self.assertEqual(b"this is content", contents)

    def test_set_body(self):
        new_body = []

        class TestResource(Resource):
            async def set_body(self, body, replace_etag=None):
                new_body.extend(body)

            async def get_etag(self):
                return '"blala"'

        app = self.makeApp({"/.well-known/carddav": TestResource()}, [])
        code, headers = self.put(app, "/.well-known/carddav", b"New contents")
        self.assertEqual("204 No Content", code)
        self.assertEqual([b"New contents"], new_body)

    def test_lock_not_allowed(self):
        app = self.makeApp({}, [])
        code, headers, contents = self.lock(app, "/resource")
        self.assertEqual("405 Method Not Allowed", code)
        self.assertIn(
            (
                "Allow",
                (
                    "COPY, DELETE, GET, HEAD, MKCOL, MOVE, OPTIONS, "
                    "PROPFIND, PROPPATCH, PUT, REPORT"
                ),
            ),
            headers,
        )
        self.assertEqual(b"", contents)

    def test_post_allowed_on_collection(self):
        """Test that POST is included in Allow header for collections."""

        class TestCollection(Collection):
            resource_types = Collection.resource_types

            def members(self):
                return []

            def get_member(self, name):
                raise KeyError(name)

            def delete_member(self, name, etag=None):
                raise KeyError(name)

            async def create_member(self, name, contents, content_type, requester=None):
                return ("new_item", '"new_etag"')

            def get_ctag(self):
                return "test-ctag"

            def destroy(self):
                pass

        app = self.makeApp({"/collection": TestCollection()}, [])
        code, headers, contents = self.options(app, "/collection")
        self.assertEqual("200 OK", code)

        # Find the Allow header
        allow_header = None
        for header_name, header_value in headers:
            if header_name == "Allow":
                allow_header = header_value
                break

        self.assertIsNotNone(allow_header, "Allow header should be present")
        self.assertIn("POST", allow_header, "POST should be allowed on collections")

    def test_post_not_allowed_on_resource(self):
        """Test that POST is NOT included in Allow header for regular resources."""
        app = self.makeApp({"/resource": Resource()}, [])
        code, headers, contents = self.options(app, "/resource")
        self.assertEqual("200 OK", code)

        # Find the Allow header
        allow_header = None
        for header_name, header_value in headers:
            if header_name == "Allow":
                allow_header = header_value
                break

        self.assertIsNotNone(allow_header, "Allow header should be present")
        self.assertNotIn(
            "POST", allow_header, "POST should NOT be allowed on regular resources"
        )

    def test_mkcol_ok(self):
        class Backend:
            def create_collection(self, relpath):
                pass

            def get_resource(self, relpath):
                return None

        app = WebDAVApp(Backend())
        code, headers, contents = self.mkcol(app, "/resource/bla")
        self.assertEqual("201 Created", code)
        self.assertEqual(b"", contents)

    def test_mkcol_exists(self):
        app = self.makeApp({"/resource": Resource(), "/resource/bla": Resource()}, [])
        code, headers, contents = self.mkcol(app, "/resource/bla")
        self.assertEqual("405 Method Not Allowed", code)
        self.assertEqual(b"", contents)

    # RFC 5689 - Extended MKCOL tests
    def test_rfc5689_extended_mkcol_with_properties(self):
        """Test Extended MKCOL (RFC 5689) with property set at creation."""
        created_collections = []

        class TestProperty(Property):
            name = "{DAV:}displayname"
            live = False

            async def get_value(self, href, resource, el, environ):
                el.text = resource.get_displayname()

            async def set_value(self, href, resource, el):
                resource.set_displayname(el.text if el is not None else None)

        class TestCollection(Collection):
            def __init__(self):
                self._displayname = None

            def get_displayname(self):
                if self._displayname is None:
                    raise KeyError
                return self._displayname

            def set_displayname(self, name):
                self._displayname = name

            def members(self):
                return []

            def get_member(self, name):
                raise KeyError(name)

        class Backend:
            def create_collection(self, relpath):
                collection = TestCollection()
                created_collections.append((relpath, collection))
                return collection

            def get_resource(self, relpath):
                return None

        app = WebDAVApp(Backend())
        app.properties = {"{DAV:}displayname": TestProperty()}

        code, headers, contents = self.mkcol(
            app,
            "/newcol",
            b'<d:mkcol xmlns:d="DAV:"><d:set><d:prop>'
            b"<d:displayname>My Collection</d:displayname>"
            b"</d:prop></d:set></d:mkcol>",
        )

        self.assertEqual("201 Created", code)
        self.assertEqual(len(created_collections), 1)
        self.assertEqual(created_collections[0][0], "/newcol")
        # Verify property was set
        self.assertEqual(created_collections[0][1].get_displayname(), "My Collection")
        # Response should contain mkcol-response with propstat
        self.assertMultiLineEqual(
            contents.decode("utf-8"),
            '<ns0:mkcol-response xmlns:ns0="DAV:"><ns0:propstat>'
            "<ns0:status>HTTP/1.1 200 OK</ns0:status>"
            "<ns0:prop><ns0:displayname /></ns0:prop>"
            "</ns0:propstat></ns0:mkcol-response>",
        )

    def test_rfc5689_extended_mkcol_protected_property(self):
        """Test Extended MKCOL with protected property returns 403 Forbidden."""

        class TestProperty(Property):
            name = "{DAV:}getetag"
            live = True

            async def get_value(self, href, resource, el, environ):
                el.text = '"test-etag"'

            async def set_value(self, href, resource, el):
                # Protected property - cannot be set
                raise ProtectedPropertyError("Cannot set protected property")

        class TestCollection(Collection):
            def members(self):
                return []

            def get_member(self, name):
                raise KeyError(name)

        class Backend:
            def create_collection(self, relpath):
                return TestCollection()

            def get_resource(self, relpath):
                return None

        app = WebDAVApp(Backend())
        app.properties = {"{DAV:}getetag": TestProperty()}

        code, headers, contents = self.mkcol(
            app,
            "/newcol",
            b'<d:mkcol xmlns:d="DAV:"><d:set><d:prop>'
            b"<d:getetag>test-value</d:getetag>"
            b"</d:prop></d:set></d:mkcol>",
        )

        self.assertEqual("201 Created", code)
        # Response contains mkcol-response with 403 Forbidden for protected property
        self.assertMultiLineEqual(
            contents.decode("utf-8"),
            '<ns0:mkcol-response xmlns:ns0="DAV:"><ns0:propstat>'
            "<ns0:status>HTTP/1.1 403 Forbidden</ns0:status>"
            "<ns0:prop><ns0:getetag /></ns0:prop>"
            "</ns0:propstat></ns0:mkcol-response>",
        )

    def test_rfc5689_extended_mkcol_parent_not_found(self):
        """Test Extended MKCOL with non-existent parent returns 409 Conflict."""

        class Backend:
            def create_collection(self, relpath):
                # Simulate parent not found
                raise FileNotFoundError("Parent does not exist")

            def get_resource(self, relpath):
                return None

        app = WebDAVApp(Backend())
        app.properties = {}

        code, headers, contents = self.mkcol(
            app,
            "/nonexistent/newcol",
            b'<d:mkcol xmlns:d="DAV:"><d:set><d:prop>'
            b"<d:displayname>Test</d:displayname>"
            b"</d:prop></d:set></d:mkcol>",
        )

        self.assertEqual("409 Conflict", code)

    def test_rfc5689_extended_mkcol_multiple_properties(self):
        """Test Extended MKCOL with multiple properties."""
        created_collections = []

        class DisplayNameProperty(Property):
            name = "{DAV:}displayname"
            live = False

            async def get_value(self, href, resource, el, environ):
                el.text = resource.get_displayname()

            async def set_value(self, href, resource, el):
                resource.set_displayname(el.text if el is not None else None)

        class CommentProperty(Property):
            name = "{DAV:}comment"
            live = False

            async def get_value(self, href, resource, el, environ):
                el.text = resource.get_comment()

            async def set_value(self, href, resource, el):
                resource.set_comment(el.text if el is not None else None)

        class TestCollection(Collection):
            def __init__(self):
                self._displayname = None
                self._comment = None

            def get_displayname(self):
                if self._displayname is None:
                    raise KeyError
                return self._displayname

            def set_displayname(self, name):
                self._displayname = name

            def get_comment(self):
                if self._comment is None:
                    raise KeyError
                return self._comment

            def set_comment(self, comment):
                self._comment = comment

            def members(self):
                return []

            def get_member(self, name):
                raise KeyError(name)

        class Backend:
            def create_collection(self, relpath):
                collection = TestCollection()
                created_collections.append((relpath, collection))
                return collection

            def get_resource(self, relpath):
                return None

        app = WebDAVApp(Backend())
        app.properties = {
            "{DAV:}displayname": DisplayNameProperty(),
            "{DAV:}comment": CommentProperty(),
        }

        code, headers, contents = self.mkcol(
            app,
            "/newcol",
            b'<d:mkcol xmlns:d="DAV:"><d:set><d:prop>'
            b"<d:displayname>My Collection</d:displayname>"
            b"<d:comment>Test comment</d:comment>"
            b"</d:prop></d:set></d:mkcol>",
        )

        self.assertEqual("201 Created", code)
        self.assertEqual(len(created_collections), 1)
        # Verify both properties were set
        self.assertEqual(created_collections[0][1].get_displayname(), "My Collection")
        self.assertEqual(created_collections[0][1].get_comment(), "Test comment")
        # Response contains mkcol-response with propstat for both properties
        self.assertMultiLineEqual(
            contents.decode("utf-8"),
            '<ns0:mkcol-response xmlns:ns0="DAV:"><ns0:propstat>'
            "<ns0:status>HTTP/1.1 200 OK</ns0:status>"
            "<ns0:prop><ns0:displayname /><ns0:comment /></ns0:prop>"
            "</ns0:propstat></ns0:mkcol-response>",
        )

    # RFC 4918 Section 10.4 - If-Match and If-None-Match tests
    def test_rfc4918_10_4_put_if_match_success(self):
        """Test PUT with If-Match header matching ETag succeeds."""

        class TestResource(Resource):
            async def get_etag(self):
                return '"test-etag-123"'

            async def set_body(self, body, replace_etag=None):
                return '"new-etag"'

        app = self.makeApp({"/resource": TestResource()}, [])
        code, headers = self.put(
            app, "/resource", b"new content", if_match='"test-etag-123"'
        )
        self.assertEqual("204 No Content", code)

    def test_rfc4918_10_4_put_if_match_fail(self):
        """Test PUT with If-Match header not matching ETag returns 412."""

        class TestResource(Resource):
            async def get_etag(self):
                return '"test-etag-123"'

            async def set_body(self, body, replace_etag=None):
                return '"new-etag"'

        app = self.makeApp({"/resource": TestResource()}, [])
        code, headers = self.put(
            app, "/resource", b"new content", if_match='"wrong-etag"'
        )
        self.assertEqual("412 Precondition Failed", code)

    def test_rfc4918_10_4_put_if_match_wildcard(self):
        """Test PUT with If-Match: * succeeds for existing resource."""

        class TestResource(Resource):
            async def get_etag(self):
                return '"test-etag-123"'

            async def set_body(self, body, replace_etag=None):
                return '"new-etag"'

        app = self.makeApp({"/resource": TestResource()}, [])
        code, headers = self.put(app, "/resource", b"new content", if_match="*")
        self.assertEqual("204 No Content", code)

    def test_rfc4918_10_4_put_if_match_wildcard_nonexistent(self):
        """Test PUT with If-Match: * fails for nonexistent resource."""
        created_items = []

        class TestCollection(Collection):
            async def create_member(self, name, contents, content_type, requester=None):
                created_items.append(name)
                return (name, '"new-etag"')

            def members(self):
                return []

            def get_member(self, name):
                raise KeyError(name)

        app = self.makeApp({"/collection": TestCollection()}, [])
        code, headers = self.put(
            app, "/collection/newitem", b"new content", if_match="*"
        )
        self.assertEqual("412 Precondition Failed", code)
        self.assertEqual(len(created_items), 0)

    def test_rfc4918_10_4_put_if_none_match_success(self):
        """Test PUT with If-None-Match on nonexistent resource succeeds."""
        created_items = []

        class TestCollection(Collection):
            async def create_member(self, name, contents, content_type, requester=None):
                created_items.append(name)
                return (name, '"new-etag"')

            def members(self):
                return []

            def get_member(self, name):
                raise KeyError(name)

        app = self.makeApp({"/collection": TestCollection()}, [])
        code, headers = self.put(
            app, "/collection/newitem", b"new content", if_none_match='"any-etag"'
        )
        self.assertEqual("201 Created", code)
        self.assertEqual(len(created_items), 1)

    def test_rfc4918_10_4_put_if_none_match_fail(self):
        """Test PUT with If-None-Match matching existing ETag returns 412."""

        class TestResource(Resource):
            async def get_etag(self):
                return '"test-etag-123"'

            async def set_body(self, body, replace_etag=None):
                return '"new-etag"'

        app = self.makeApp({"/resource": TestResource()}, [])
        code, headers = self.put(
            app, "/resource", b"new content", if_none_match='"test-etag-123"'
        )
        self.assertEqual("412 Precondition Failed", code)

    def test_rfc4918_10_4_put_if_none_match_wildcard_create(self):
        """Test PUT with If-None-Match: * succeeds for nonexistent resource."""
        created_items = []

        class TestCollection(Collection):
            async def create_member(self, name, contents, content_type, requester=None):
                created_items.append(name)
                return (name, '"new-etag"')

            def members(self):
                return []

            def get_member(self, name):
                raise KeyError(name)

        app = self.makeApp({"/collection": TestCollection()}, [])
        code, headers = self.put(
            app, "/collection/newitem", b"new content", if_none_match="*"
        )
        self.assertEqual("201 Created", code)
        self.assertEqual(len(created_items), 1)

    def test_rfc4918_10_4_put_if_none_match_wildcard_exists(self):
        """Test PUT with If-None-Match: * fails for existing resource."""

        class TestResource(Resource):
            async def get_etag(self):
                return '"test-etag-123"'

            async def set_body(self, body, replace_etag=None):
                return '"new-etag"'

        app = self.makeApp({"/resource": TestResource()}, [])
        code, headers = self.put(app, "/resource", b"new content", if_none_match="*")
        self.assertEqual("412 Precondition Failed", code)

    def test_rfc4918_10_4_delete_if_match_success(self):
        """Test DELETE with If-Match header matching ETag succeeds."""
        deleted_items = []

        class TestResource(Resource):
            async def get_etag(self):
                return '"test-etag-123"'

        class TestCollection(Collection):
            async def get_etag(self):
                return '"parent-etag"'

            def delete_member(self, name, etag=None):
                deleted_items.append((name, etag))

            def get_member(self, name):
                if name == "resource":
                    return TestResource()
                raise KeyError(name)

            def members(self):
                return [("resource", TestResource())]

        app = self.makeApp(
            {"/collection": TestCollection(), "/collection/resource": TestResource()},
            [],
        )
        code, headers, contents = self.delete(
            app, "/collection/resource", if_match='"test-etag-123"'
        )
        self.assertEqual("204 No Content", code)
        self.assertEqual(len(deleted_items), 1)

    def test_rfc4918_10_4_delete_if_match_fail(self):
        """Test DELETE with If-Match header not matching ETag returns 412."""

        class TestResource(Resource):
            async def get_etag(self):
                return '"test-etag-123"'

        class TestCollection(Collection):
            def get_member(self, name):
                if name == "resource":
                    return TestResource()
                raise KeyError(name)

        app = self.makeApp(
            {"/collection": TestCollection(), "/collection/resource": TestResource()},
            [],
        )
        code, headers, contents = self.delete(
            app, "/collection/resource", if_match='"wrong-etag"'
        )
        self.assertEqual("412 Precondition Failed", code)

    # RFC 4918 Section 9.1/9.2 - Multi-Status error scenario tests
    def test_rfc4918_propfind_mixed_success_failure(self):
        """Test PROPFIND with mix of found and not-found properties."""

        class FoundProperty(Property):
            name = "{DAV:}displayname"

            async def get_value(self, href, resource, el, environ):
                el.text = "Test Resource"

        class NotFoundProperty(Property):
            name = "{DAV:}nonexistent"

            async def get_value(self, href, resource, el, environ):
                raise KeyError("Property not found")

        app = self.makeApp(
            {"/resource": Resource()}, [FoundProperty(), NotFoundProperty()]
        )
        code, headers, contents = self.propfind(
            app,
            "/resource",
            b'<d:propfind xmlns:d="DAV:"><d:prop>'
            b"<d:displayname/><d:nonexistent/>"
            b"</d:prop></d:propfind>",
        )
        self.assertEqual("207 Multi-Status", code)
        # Response should have separate propstat elements for different status codes
        self.assertMultiLineEqual(
            contents.decode("utf-8"),
            '<ns0:multistatus xmlns:ns0="DAV:"><ns0:response>'
            "<ns0:href>/resource</ns0:href>"
            "<ns0:propstat><ns0:status>HTTP/1.1 200 OK</ns0:status>"
            "<ns0:prop><ns0:displayname>Test Resource</ns0:displayname></ns0:prop>"
            "</ns0:propstat>"
            "<ns0:propstat><ns0:status>HTTP/1.1 404 Not Found</ns0:status>"
            "<ns0:prop><ns0:nonexistent /></ns0:prop>"
            "</ns0:propstat>"
            "</ns0:response></ns0:multistatus>",
        )

    def test_rfc4918_proppatch_mixed_success_failure(self):
        """Test PROPPATCH with mix of successful and failed property updates."""

        class WritableProperty(Property):
            name = "{DAV:}displayname"
            live = False

            async def get_value(self, href, resource, el, environ):
                el.text = resource.get_displayname()

            async def set_value(self, href, resource, el):
                resource.set_displayname(el.text if el is not None else None)

        class ReadOnlyProperty(Property):
            name = "{DAV:}getetag"
            live = True

            async def get_value(self, href, resource, el, environ):
                el.text = '"readonly"'

            async def set_value(self, href, resource, el):
                raise ProtectedPropertyError("Cannot modify getetag")

        class TestResource(Resource):
            def __init__(self):
                self._displayname = None

            def get_displayname(self):
                if self._displayname is None:
                    raise KeyError
                return self._displayname

            def set_displayname(self, name):
                self._displayname = name

        app = self.makeApp(
            {"/resource": TestResource()}, [WritableProperty(), ReadOnlyProperty()]
        )
        code, headers, contents = self.proppatch(
            app,
            "/resource",
            b'<d:propertyupdate xmlns:d="DAV:"><d:set><d:prop>'
            b"<d:displayname>New Name</d:displayname>"
            b"<d:getetag>should-fail</d:getetag>"
            b"</d:prop></d:set></d:propertyupdate>",
        )
        self.assertEqual("207 Multi-Status", code)
        # Response should have separate propstat elements for success and failure
        self.assertMultiLineEqual(
            contents.decode("utf-8"),
            '<ns0:multistatus xmlns:ns0="DAV:"><ns0:response>'
            "<ns0:href>http%3A//127.0.0.1/resource</ns0:href>"
            "<ns0:propstat><ns0:status>HTTP/1.1 200 OK</ns0:status>"
            "<ns0:prop><ns0:displayname /></ns0:prop>"
            "</ns0:propstat>"
            "<ns0:propstat><ns0:status>HTTP/1.1 403 Forbidden</ns0:status>"
            "<ns0:prop><ns0:getetag /></ns0:prop>"
            "</ns0:propstat>"
            "</ns0:response></ns0:multistatus>",
        )

    def test_rfc4918_proppatch_all_fail(self):
        """Test PROPPATCH where all properties fail returns 207 with errors."""

        class ProtectedProperty1(Property):
            name = "{DAV:}creationdate"

            async def set_value(self, href, resource, el):
                raise ProtectedPropertyError("Cannot modify creationdate")

        class ProtectedProperty2(Property):
            name = "{DAV:}getlastmodified"

            async def set_value(self, href, resource, el):
                raise ProtectedPropertyError("Cannot modify getlastmodified")

        app = self.makeApp(
            {"/resource": Resource()}, [ProtectedProperty1(), ProtectedProperty2()]
        )
        code, headers, contents = self.proppatch(
            app,
            "/resource",
            b'<d:propertyupdate xmlns:d="DAV:"><d:set><d:prop>'
            b"<d:creationdate>2024-01-01</d:creationdate>"
            b"<d:getlastmodified>2024-01-01</d:getlastmodified>"
            b"</d:prop></d:set></d:propertyupdate>",
        )
        self.assertEqual("207 Multi-Status", code)
        # Both properties should have 403 Forbidden status in single propstat
        self.assertMultiLineEqual(
            contents.decode("utf-8"),
            '<ns0:multistatus xmlns:ns0="DAV:"><ns0:response>'
            "<ns0:href>http%3A//127.0.0.1/resource</ns0:href>"
            "<ns0:propstat><ns0:status>HTTP/1.1 403 Forbidden</ns0:status>"
            "<ns0:prop><ns0:creationdate /><ns0:getlastmodified /></ns0:prop>"
            "</ns0:propstat>"
            "</ns0:response></ns0:multistatus>",
        )

    # RFC 4918 Section 9.6 - DELETE on collections tests
    def test_rfc4918_9_6_delete_empty_collection(self):
        """Test DELETE on empty collection succeeds."""
        deleted_items = []

        class TestCollection(Collection):
            async def get_etag(self):
                return '"collection-etag"'

            def members(self):
                return []

            def get_member(self, name):
                raise KeyError(name)

            def delete_member(self, name, etag=None):
                deleted_items.append((name, etag))

        app = self.makeApp({"/": TestCollection(), "/emptycol": TestCollection()}, [])
        code, headers, contents = self.delete(app, "/emptycol")
        self.assertEqual("204 No Content", code)
        self.assertEqual(b"", contents)
        self.assertEqual(len(deleted_items), 1)
        self.assertEqual(deleted_items[0][0], "emptycol")

    def test_rfc4918_9_6_delete_collection_with_members(self):
        """Test DELETE on collection with members succeeds."""
        deleted_items = []

        class TestResource(Resource):
            async def get_etag(self):
                return '"resource-etag"'

        class TestCollection(Collection):
            def __init__(self, has_members=False):
                self._has_members = has_members

            async def get_etag(self):
                return '"collection-etag"'

            def members(self):
                if self._has_members:
                    return [
                        ("file1.txt", TestResource()),
                        ("file2.txt", TestResource()),
                    ]
                return []

            def get_member(self, name):
                if self._has_members and name in ("file1.txt", "file2.txt"):
                    return TestResource()
                if name == "collection":
                    return TestCollection(has_members=True)
                raise KeyError(name)

            def delete_member(self, name, etag=None):
                deleted_items.append((name, etag))

        app = self.makeApp(
            {"/": TestCollection(), "/collection": TestCollection(has_members=True)},
            [],
        )
        code, headers, contents = self.delete(app, "/collection")
        self.assertEqual("204 No Content", code)
        self.assertEqual(b"", contents)
        # Backend is responsible for recursive deletion
        self.assertEqual(len(deleted_items), 1)
        self.assertEqual(deleted_items[0][0], "collection")

    def test_rfc4918_9_6_delete_collection_not_found(self):
        """Test DELETE on non-existent collection returns 404."""

        class TestCollection(Collection):
            def members(self):
                return []

            def get_member(self, name):
                raise KeyError(name)

        app = self.makeApp({"/": TestCollection()}, [])
        code, headers, contents = self.delete(app, "/nonexistent")
        self.assertEqual("404 Not Found", code)

    def test_rfc4918_9_6_delete_nested_collection(self):
        """Test DELETE on nested collection succeeds."""
        deleted_items = []

        class TestCollection(Collection):
            def __init__(self, children=None):
                self._children = children or {}

            async def get_etag(self):
                return '"nested-etag"'

            def members(self):
                return list(self._children.items())

            def get_member(self, name):
                if name in self._children:
                    return self._children[name]
                raise KeyError(name)

            def delete_member(self, name, etag=None):
                deleted_items.append((name, etag))

        subcol = TestCollection()
        parent = TestCollection({"subdir": subcol})

        app = self.makeApp(
            {"/": parent, "/parent": parent, "/parent/subdir": subcol}, []
        )
        code, headers, contents = self.delete(app, "/parent/subdir")
        self.assertEqual("204 No Content", code)
        self.assertEqual(b"", contents)
        self.assertEqual(len(deleted_items), 1)
        self.assertEqual(deleted_items[0][0], "subdir")

    def test_delete(self):
        class TestResource(Collection):
            async def get_etag(self):
                return '"foo"'

            def delete_member(unused_self, name, etag=None):
                self.assertEqual(name, "resource")

        app = self.makeApp({"/": TestResource(), "/resource": TestResource()}, [])
        code, headers, contents = self.delete(app, "/resource")
        self.assertEqual("204 No Content", code)
        self.assertEqual(b"", contents)

    def test_delete_not_found(self):
        class TestResource(Collection):
            pass

        app = self.makeApp({"/resource": TestResource()}, [])
        code, headers, contents = self.delete(app, "/resource")
        self.assertEqual("404 Not Found", code)
        self.assertTrue(contents.endswith(b"/resource not found."))

    def test_delete_percent_encoded_slash(self):
        """Test DELETE with percent-encoded slash in filename."""
        deleted_items = []

        class TestResource(Collection):
            async def get_etag(self):
                return '"foo"'

            def delete_member(unused_self, name, etag=None):
                deleted_items.append(name)

        # Create resources for the test
        # /collection/itemwith%2fslash.ics should be treated as a single filename
        # The backend expects decoded paths as keys
        app = self.makeApp(
            {
                "/collection": TestResource(),
                "/collection/itemwith/slash.ics": TestResource(),
            },
            [],
        )
        code, headers, contents = self.delete(app, "/collection/itemwith%2fslash.ics")
        self.assertEqual("204 No Content", code)
        self.assertEqual(b"", contents)
        # Verify that the correct item name was passed to delete_member
        self.assertEqual(["itemwith/slash.ics"], deleted_items)

    def test_put_percent_encoded_slash(self):
        """Test PUT with percent-encoded slash in filename."""
        created_items = []

        class TestResource(Collection):
            async def create_member(
                unused_self, name, contents, content_type, requester=None
            ):
                created_items.append((name, contents))
                return (name, '"new-etag"')

        # Create resources for the test
        app = self.makeApp({"/collection": TestResource()}, [])
        code, headers = self.put(app, "/collection/itemwith%2fslash.ics", b"test data")
        self.assertEqual("201 Created", code)
        # Verify that the correct item name was passed to create_member
        self.assertEqual(1, len(created_items))
        self.assertEqual("itemwith/slash.ics", created_items[0][0])
        self.assertEqual([b"test data"], created_items[0][1])

    def test_put_with_precondition_failure_returns_412_not_207(self):
        """Test that PUT with precondition failure returns 412, not 207."""

        class TestResource(Resource):
            async def get_etag(self):
                return '"existing-etag"'

            async def set_body(self, data, replace_etag=None):
                # Simulate a precondition failure (e.g., invalid calendar data)
                raise webdav.PreconditionFailure(
                    "{urn:ietf:params:xml:ns:caldav}valid-calendar-data",
                    "Not a valid calendar file: test error",
                )

        app = self.makeApp({"/test.ics": TestResource()}, [])
        code, headers = self.put(app, "/test.ics", b"invalid data")

        # Should return 412, not 207
        self.assertEqual("412 Precondition Failed", code)
        # Verify it's not a multi-status response
        self.assertNotEqual("207 Multi-Status", code)

    def test_propfind_prop_does_not_exist(self):
        app = self.makeApp({"/resource": Resource()}, [])
        code, headers, contents = self.propfind(
            app,
            "/resource",
            b"""\
<d:propfind xmlns:d="DAV:"><d:prop><d:resourcetype /></d:prop></d:propfind>""",
        )
        self.assertMultiLineEqual(
            contents.decode("utf-8"),
            '<ns0:multistatus xmlns:ns0="DAV:"><ns0:response>'
            "<ns0:href>/resource</ns0:href>"
            "<ns0:propstat><ns0:status>HTTP/1.1 404 Not Found</ns0:status>"
            "<ns0:prop><ns0:resourcetype /></ns0:prop></ns0:propstat>"
            "</ns0:response></ns0:multistatus>",
        )
        self.assertEqual(code, "207 Multi-Status")

    def test_propfind_prop_not_present(self):
        class TestProperty(Property):
            name = "{DAV:}current-user-principal"

            async def get_value(self, href, resource, ret, environ):
                raise KeyError

        app = self.makeApp({"/resource": Resource()}, [TestProperty()])
        code, headers, contents = self.propfind(
            app,
            "/resource",
            b"""\
<d:propfind xmlns:d="DAV:"><d:prop><d:resourcetype /></d:prop></d:propfind>""",
        )
        self.assertMultiLineEqual(
            contents.decode("utf-8"),
            '<ns0:multistatus xmlns:ns0="DAV:"><ns0:response>'
            "<ns0:href>/resource</ns0:href>"
            "<ns0:propstat><ns0:status>HTTP/1.1 404 Not Found</ns0:status>"
            "<ns0:prop><ns0:resourcetype /></ns0:prop></ns0:propstat>"
            "</ns0:response></ns0:multistatus>",
        )
        self.assertEqual(code, "207 Multi-Status")

    def test_propfind_found(self):
        class TestProperty(Property):
            name = "{DAV:}current-user-principal"

            async def get_value(self, href, resource, ret, environ):
                ET.SubElement(ret, "{DAV:}href").text = "/user/"

        app = self.makeApp({"/resource": Resource()}, [TestProperty()])
        code, headers, contents = self.propfind(
            app,
            "/resource",
            b"""\
<d:propfind xmlns:d="DAV:"><d:prop><d:current-user-principal/>\
</d:prop></d:propfind>""",
        )
        self.assertMultiLineEqual(
            contents.decode("utf-8"),
            '<ns0:multistatus xmlns:ns0="DAV:"><ns0:response>'
            "<ns0:href>/resource</ns0:href>"
            "<ns0:propstat><ns0:status>HTTP/1.1 200 OK</ns0:status>"
            "<ns0:prop><ns0:current-user-principal><ns0:href>/user/</ns0:href>"
            "</ns0:current-user-principal></ns0:prop></ns0:propstat>"
            "</ns0:response></ns0:multistatus>",
        )
        self.assertEqual(code, "207 Multi-Status")

    def test_propfind_found_multi(self):
        class TestProperty1(Property):
            name = "{DAV:}current-user-principal"

            async def get_value(self, href, resource, el, environ):
                ET.SubElement(el, "{DAV:}href").text = "/user/"

        class TestProperty2(Property):
            name = "{DAV:}somethingelse"

            async def get_value(self, href, resource, el, environ):
                pass

        app = self.makeApp(
            {"/resource": Resource()}, [TestProperty1(), TestProperty2()]
        )
        code, headers, contents = self.propfind(
            app,
            "/resource",
            b"""\
<d:propfind xmlns:d="DAV:"><d:prop><d:current-user-principal/>\
<d:somethingelse/></d:prop></d:propfind>""",
        )
        self.maxDiff = None
        self.assertMultiLineEqual(
            contents.decode("utf-8"),
            '<ns0:multistatus xmlns:ns0="DAV:"><ns0:response>'
            "<ns0:href>/resource</ns0:href>"
            "<ns0:propstat><ns0:status>HTTP/1.1 200 OK</ns0:status>"
            "<ns0:prop><ns0:current-user-principal><ns0:href>/user/</ns0:href>"
            "</ns0:current-user-principal><ns0:somethingelse /></ns0:prop>"
            "</ns0:propstat></ns0:response></ns0:multistatus>",
        )
        self.assertEqual(code, "207 Multi-Status")

    def test_propfind_found_multi_status(self):
        class TestProperty(Property):
            name = "{DAV:}current-user-principal"

            async def get_value(self, href, resource, ret, environ):
                ET.SubElement(ret, "{DAV:}href").text = "/user/"

        app = self.makeApp({"/resource": Resource()}, [TestProperty()])
        code, headers, contents = self.propfind(
            app,
            "/resource",
            b"""\
<d:propfind xmlns:d="DAV:"><d:prop><d:current-user-principal/>\
<d:somethingelse/></d:prop></d:propfind>""",
        )
        self.maxDiff = None
        self.assertEqual(code, "207 Multi-Status")
        self.assertMultiLineEqual(
            contents.decode("utf-8"),
            """\
<ns0:multistatus xmlns:ns0="DAV:"><ns0:response><ns0:href>/resource</ns0:href>\
<ns0:propstat><ns0:status>HTTP/1.1 200 OK</ns0:status><ns0:prop>\
<ns0:current-user-principal><ns0:href>/user/</ns0:href>\
</ns0:current-user-principal></ns0:prop></ns0:propstat><ns0:propstat>\
<ns0:status>HTTP/1.1 404 Not Found</ns0:status><ns0:prop>\
<ns0:somethingelse /></ns0:prop></ns0:propstat>\
</ns0:response>\
</ns0:multistatus>""",
        )

    # RFC 4918 Section 9.2 - PROPPATCH tests
    def test_rfc4918_9_2_proppatch_set_property(self):
        """Test PROPPATCH set operation on displayname property."""
        set_values = {}

        class TestProperty(Property):
            name = "{DAV:}displayname"

            async def get_value(self, href, resource, el, environ):
                if href in set_values:
                    el.text = set_values[href]
                else:
                    raise KeyError

            async def set_value(self, href, resource, el):
                set_values[href] = el.text

        app = self.makeApp({"/resource": Resource()}, [TestProperty()])
        code, headers, contents = self.proppatch(
            app,
            "/resource",
            b"""\
<d:propertyupdate xmlns:d="DAV:">
  <d:set>
    <d:prop>
      <d:displayname>My Resource</d:displayname>
    </d:prop>
  </d:set>
</d:propertyupdate>""",
        )
        self.assertEqual(code, "207 Multi-Status")
        self.assertMultiLineEqual(
            contents.decode("utf-8"),
            '<ns0:multistatus xmlns:ns0="DAV:"><ns0:response>'
            "<ns0:href>http%3A//127.0.0.1/resource</ns0:href>"
            "<ns0:propstat><ns0:status>HTTP/1.1 200 OK</ns0:status><ns0:prop><ns0:displayname /></ns0:prop></ns0:propstat>"
            "</ns0:response></ns0:multistatus>",
        )
        # Verify the property was set (href key may vary)
        self.assertEqual(len(set_values), 1)
        self.assertEqual(list(set_values.values())[0], "My Resource")

    def test_rfc4918_9_2_proppatch_remove_property(self):
        """Test PROPPATCH remove operation."""
        set_values = {}
        removed = []

        class TestProperty(Property):
            name = "{DAV:}displayname"

            async def get_value(self, href, resource, el, environ):
                if href in set_values:
                    el.text = set_values[href]
                else:
                    raise KeyError

            async def set_value(self, href, resource, el):
                if el is None:
                    removed.append(href)
                    if href in set_values:
                        del set_values[href]
                else:
                    set_values[href] = el.text

        # Set an initial value
        set_values["/resource"] = "Old Name"

        app = self.makeApp({"/resource": Resource()}, [TestProperty()])
        code, headers, contents = self.proppatch(
            app,
            "/resource",
            b"""\
<d:propertyupdate xmlns:d="DAV:">
  <d:remove>
    <d:prop>
      <d:displayname />
    </d:prop>
  </d:remove>
</d:propertyupdate>""",
        )
        self.assertEqual(code, "207 Multi-Status")
        self.assertMultiLineEqual(
            contents.decode("utf-8"),
            '<ns0:multistatus xmlns:ns0="DAV:"><ns0:response>'
            "<ns0:href>http%3A//127.0.0.1/resource</ns0:href>"
            "<ns0:propstat><ns0:status>HTTP/1.1 200 OK</ns0:status><ns0:prop><ns0:displayname /></ns0:prop></ns0:propstat>"
            "</ns0:response></ns0:multistatus>",
        )
        # Verify remove was called
        self.assertEqual(len(removed), 1)

    def test_rfc4918_9_2_proppatch_not_found(self):
        """Test PROPPATCH on non-existent resource returns 207 with 404 status."""
        self.maxDiff = None
        app = self.makeApp({}, [DisplayNameProperty()])
        code, headers, contents = self.proppatch(
            app,
            "/nonexistent",
            b"""\
<d:propertyupdate xmlns:d="DAV:">
  <d:set>
    <d:prop>
      <d:displayname>Test</d:displayname>
    </d:prop>
  </d:set>
</d:propertyupdate>""",
        )
        # PROPPATCH on non-existent resource returns 207 with 404 status
        self.assertEqual(code, "207 Multi-Status")
        self.assertMultiLineEqual(
            contents.decode("utf-8"),
            '<ns0:multistatus xmlns:ns0="DAV:"><ns0:response>'
            "<ns0:href>http%3A//127.0.0.1/nonexistent</ns0:href>"
            "<ns0:status>HTTP/1.1 404 Not Found</ns0:status>"
            "</ns0:response></ns0:multistatus>",
        )

    def test_rfc4918_9_2_proppatch_protected_property(self):
        """Test PROPPATCH on protected property returns 403 Forbidden."""

        class ProtectedProperty(Property):
            name = "{DAV:}getetag"

            async def get_value(self, href, resource, el, environ):
                el.text = "protected-etag"

            async def set_value(self, href, resource, el):
                raise ProtectedPropertyError("Cannot modify protected property")

        app = self.makeApp({"/resource": Resource()}, [ProtectedProperty()])
        code, headers, contents = self.proppatch(
            app,
            "/resource",
            b"""\
<d:propertyupdate xmlns:d="DAV:">
  <d:set>
    <d:prop>
      <d:getetag>new-etag</d:getetag>
    </d:prop>
  </d:set>
</d:propertyupdate>""",
        )
        self.assertEqual(code, "207 Multi-Status")
        self.assertMultiLineEqual(
            contents.decode("utf-8"),
            '<ns0:multistatus xmlns:ns0="DAV:"><ns0:response>'
            "<ns0:href>http%3A//127.0.0.1/resource</ns0:href>"
            "<ns0:propstat><ns0:status>HTTP/1.1 403 Forbidden</ns0:status><ns0:prop><ns0:getetag /></ns0:prop></ns0:propstat>"
            "</ns0:response></ns0:multistatus>",
        )

    def test_rfc4918_9_2_proppatch_set_and_remove(self):
        """Test PROPPATCH with both set and remove operations."""
        set_values = {}
        removed_props = []

        class TestProperty(Property):
            name = "{DAV:}displayname"

            async def get_value(self, href, resource, el, environ):
                if href in set_values:
                    el.text = set_values[href]
                else:
                    raise KeyError

            async def set_value(self, href, resource, el):
                if el is None:
                    removed_props.append("displayname")
                    if href in set_values:
                        del set_values[href]
                else:
                    set_values[href] = el.text

        class AnotherProperty(Property):
            name = "{DAV:}comment"

            async def get_value(self, href, resource, el, environ):
                raise KeyError

            async def set_value(self, href, resource, el):
                set_values[f"{href}_comment"] = el.text

        app = self.makeApp(
            {"/resource": Resource()}, [TestProperty(), AnotherProperty()]
        )
        code, headers, contents = self.proppatch(
            app,
            "/resource",
            b"""\
<d:propertyupdate xmlns:d="DAV:">
  <d:set>
    <d:prop>
      <d:comment>New comment</d:comment>
    </d:prop>
  </d:set>
  <d:remove>
    <d:prop>
      <d:displayname />
    </d:prop>
  </d:remove>
</d:propertyupdate>""",
        )
        self.assertEqual(code, "207 Multi-Status")
        # Verify remove was called for displayname
        self.assertEqual(removed_props, ["displayname"])
        # Verify comment was set (one key ending with _comment)
        comment_keys = [k for k in set_values.keys() if "_comment" in k]
        self.assertEqual(len(comment_keys), 1)
        # Verify the comment value
        self.assertEqual(list(set_values.values())[0], "New comment")

    def test_rfc4918_9_2_proppatch_unknown_property(self):
        """Test PROPPATCH on unknown property returns 403 Forbidden.

        RFC 4918 Section 9.2.1: Dead properties are not supported, so
        attempts to set unknown properties should return 403 Forbidden
        rather than 404 Not Found.
        """
        self.maxDiff = None
        app = self.makeApp({"/resource": Resource()}, [])
        code, headers, contents = self.proppatch(
            app,
            "/resource",
            b"""\
<d:propertyupdate xmlns:d="DAV:" xmlns:custom="http://example.com/ns">
  <d:set>
    <d:prop>
      <custom:deadproperty>Custom Value</custom:deadproperty>
    </d:prop>
  </d:set>
</d:propertyupdate>""",
        )
        self.assertEqual(code, "207 Multi-Status")
        self.assertMultiLineEqual(
            contents.decode("utf-8"),
            '<ns0:multistatus xmlns:ns0="DAV:" xmlns:ns1="http://example.com/ns"><ns0:response>'
            "<ns0:href>http%3A//127.0.0.1/resource</ns0:href>"
            "<ns0:propstat><ns0:status>HTTP/1.1 403 Forbidden</ns0:status><ns0:prop><ns1:deadproperty /></ns0:prop></ns0:propstat>"
            "</ns0:response></ns0:multistatus>",
        )

    # RFC 4918 Section 9.1 - PROPFIND Depth tests
    def test_rfc4918_9_1_propfind_depth_0(self):
        """Test PROPFIND with Depth: 0 (resource only, no children)."""

        class TestProperty(Property):
            name = "{DAV:}displayname"

            async def get_value(self, href, resource, el, environ):
                el.text = f"Name-{href}"

        class TestCollection(Collection):
            def __init__(self, child_members):
                self._members = child_members

            def members(self):
                return self._members

            def get_member(self, name):
                for member_name, member_resource in self._members:
                    if member_name == name:
                        return member_resource
                raise KeyError(name)

        child_resource = Resource()
        parent = TestCollection([("child", child_resource)])

        app = self.makeApp(
            {"/parent/": parent, "/parent/child": child_resource}, [TestProperty()]
        )
        code, headers, contents = self.propfind(
            app,
            "/parent/",
            b'<d:propfind xmlns:d="DAV:"><d:prop><d:displayname/></d:prop></d:propfind>',
            depth="0",
        )
        self.assertEqual(code, "207 Multi-Status")
        # Depth 0 should only include the parent collection, not children
        self.assertMultiLineEqual(
            contents.decode("utf-8"),
            '<ns0:multistatus xmlns:ns0="DAV:"><ns0:response>'
            "<ns0:href>/parent/</ns0:href><ns0:propstat>"
            "<ns0:status>HTTP/1.1 200 OK</ns0:status>"
            "<ns0:prop><ns0:displayname>Name-/parent/</ns0:displayname></ns0:prop>"
            "</ns0:propstat></ns0:response></ns0:multistatus>",
        )

    def test_rfc4918_9_1_propfind_depth_1(self):
        """Test PROPFIND with Depth: 1 (resource and immediate children)."""

        class TestProperty(Property):
            name = "{DAV:}displayname"

            async def get_value(self, href, resource, el, environ):
                el.text = f"Name-{href}"

        class TestCollection(Collection):
            def __init__(self, child_members):
                self._members = child_members

            def members(self):
                return self._members

            def get_member(self, name):
                for member_name, member_resource in self._members:
                    if member_name == name:
                        return member_resource
                raise KeyError(name)

        child1 = Resource()
        child2 = Resource()
        parent = TestCollection([("child1", child1), ("child2", child2)])

        app = self.makeApp(
            {"/parent/": parent, "/parent/child1": child1, "/parent/child2": child2},
            [TestProperty()],
        )
        code, headers, contents = self.propfind(
            app,
            "/parent/",
            b'<d:propfind xmlns:d="DAV:"><d:prop><d:displayname/></d:prop></d:propfind>',
            depth="1",
        )
        self.assertEqual(code, "207 Multi-Status")
        # Depth 1 should include parent and immediate children
        self.assertMultiLineEqual(
            contents.decode("utf-8"),
            '<ns0:multistatus xmlns:ns0="DAV:">'
            "<ns0:response><ns0:href>/parent/</ns0:href><ns0:propstat>"
            "<ns0:status>HTTP/1.1 200 OK</ns0:status>"
            "<ns0:prop><ns0:displayname>Name-/parent/</ns0:displayname></ns0:prop>"
            "</ns0:propstat></ns0:response>"
            "<ns0:response><ns0:href>/parent/child1</ns0:href><ns0:propstat>"
            "<ns0:status>HTTP/1.1 200 OK</ns0:status>"
            "<ns0:prop><ns0:displayname>Name-/parent/child1</ns0:displayname></ns0:prop>"
            "</ns0:propstat></ns0:response>"
            "<ns0:response><ns0:href>/parent/child2</ns0:href><ns0:propstat>"
            "<ns0:status>HTTP/1.1 200 OK</ns0:status>"
            "<ns0:prop><ns0:displayname>Name-/parent/child2</ns0:displayname></ns0:prop>"
            "</ns0:propstat></ns0:response>"
            "</ns0:multistatus>",
        )

    def test_rfc4918_9_1_propfind_depth_infinity(self):
        """Test PROPFIND with Depth: infinity (resource and all descendants)."""

        class TestProperty(Property):
            name = "{DAV:}displayname"

            async def get_value(self, href, resource, el, environ):
                el.text = f"Name-{href}"

        class TestCollection(Collection):
            def __init__(self, child_members):
                self._members = child_members

            def members(self):
                return self._members

            def get_member(self, name):
                for member_name, member_resource in self._members:
                    if member_name == name:
                        return member_resource
                raise KeyError(name)

        grandchild = Resource()
        child = TestCollection([("grandchild", grandchild)])
        parent = TestCollection([("child/", child)])

        app = self.makeApp(
            {
                "/parent/": parent,
                "/parent/child/": child,
                "/parent/child/grandchild": grandchild,
            },
            [TestProperty()],
        )
        code, headers, contents = self.propfind(
            app,
            "/parent/",
            b'<d:propfind xmlns:d="DAV:"><d:prop><d:displayname/></d:prop></d:propfind>',
            depth="infinity",
        )
        self.assertEqual(code, "207 Multi-Status")
        # Depth infinity should include all levels
        self.assertMultiLineEqual(
            contents.decode("utf-8"),
            '<ns0:multistatus xmlns:ns0="DAV:">'
            "<ns0:response><ns0:href>/parent/</ns0:href><ns0:propstat>"
            "<ns0:status>HTTP/1.1 200 OK</ns0:status>"
            "<ns0:prop><ns0:displayname>Name-/parent/</ns0:displayname></ns0:prop>"
            "</ns0:propstat></ns0:response>"
            "<ns0:response><ns0:href>/parent/child/</ns0:href><ns0:propstat>"
            "<ns0:status>HTTP/1.1 200 OK</ns0:status>"
            "<ns0:prop><ns0:displayname>Name-/parent/child/</ns0:displayname></ns0:prop>"
            "</ns0:propstat></ns0:response>"
            "<ns0:response><ns0:href>/parent/child/grandchild</ns0:href><ns0:propstat>"
            "<ns0:status>HTTP/1.1 200 OK</ns0:status>"
            "<ns0:prop><ns0:displayname>Name-/parent/child/grandchild</ns0:displayname></ns0:prop>"
            "</ns0:propstat></ns0:response>"
            "</ns0:multistatus>",
        )

    def test_rfc4918_9_1_propfind_allprop(self):
        """Test PROPFIND with allprop request."""
        app = self.makeApp(
            {"/resource": Resource()},
            [DisplayNameProperty(), ResourceTypeProperty()],
        )
        code, headers, contents = self.propfind(
            app,
            "/resource",
            b'<d:propfind xmlns:d="DAV:"><d:allprop/></d:propfind>',
        )
        self.assertEqual(code, "207 Multi-Status")
        # allprop returns all properties that succeed (200 OK status)
        # Resource doesn't have displayname by default, so only resourcetype is returned
        self.assertMultiLineEqual(
            contents.decode("utf-8"),
            '<ns0:multistatus xmlns:ns0="DAV:"><ns0:response>'
            "<ns0:href>/resource</ns0:href><ns0:propstat>"
            "<ns0:status>HTTP/1.1 200 OK</ns0:status>"
            "<ns0:prop><ns0:resourcetype /></ns0:prop>"
            "</ns0:propstat></ns0:response></ns0:multistatus>",
        )

    def test_rfc4918_9_1_propfind_propname(self):
        """Test PROPFIND with propname request (property names only)."""
        app = self.makeApp(
            {"/resource": Resource()},
            [DisplayNameProperty(), ResourceTypeProperty()],
        )
        code, headers, contents = self.propfind(
            app,
            "/resource",
            b'<d:propfind xmlns:d="DAV:"><d:propname/></d:propfind>',
        )
        self.assertEqual(code, "207 Multi-Status")
        # propname returns names of properties that are set on the resource
        # Resource doesn't have displayname by default, so only resourcetype is returned
        self.assertMultiLineEqual(
            contents.decode("utf-8"),
            '<ns0:multistatus xmlns:ns0="DAV:"><ns0:response>'
            "<ns0:href>/resource</ns0:href><ns0:propstat>"
            "<ns0:status>HTTP/1.1 200 OK</ns0:status>"
            "<ns0:prop><ns0:resourcetype /></ns0:prop>"
            "</ns0:propstat></ns0:response></ns0:multistatus>",
        )

    def test_move_success(self):
        """Test successful MOVE operation."""
        moved_items = []

        class TestResource(Resource):
            async def get_etag(self):
                return '"test-etag"'

            async def get_body(self):
                yield b"test content"

            def get_content_type(self):
                return "text/plain"

        class TestCollection(Collection):
            def get_member(self, name):
                if name == "source.txt":
                    return TestResource()
                raise KeyError(name)

            async def move_member(self, name, destination, dest_name, overwrite=True):
                moved_items.append((name, destination, dest_name, overwrite))

        source_collection = TestCollection()
        dest_collection = TestCollection()
        app = self.makeApp(
            {
                "/": source_collection,
                "/source.txt": TestResource(),
                "/dest": dest_collection,
            },
            [],
        )
        code, headers, contents = self.move(
            app, "/source.txt", "http://localhost/dest/target.txt"
        )
        self.assertEqual("201 Created", code)
        self.assertEqual(b"", contents)
        self.assertEqual(
            [("source.txt", dest_collection, "target.txt", True)], moved_items
        )

    def test_move_no_destination_header(self):
        """Test MOVE without Destination header."""
        app = self.makeApp({"/source.txt": Resource()}, [])
        # Manually create the request without Destination header
        environ = {
            "PATH_INFO": "/source.txt",
            "REQUEST_METHOD": "MOVE",
        }
        setup_testing_defaults(environ)
        _code = []
        _headers = []

        def start_response(code, headers):
            _code.append(code)
            _headers.extend(headers)

        contents = b"".join(app(environ, start_response))
        self.assertEqual("400 Bad Request", _code[0])
        self.assertIn(b"Destination header required", contents)

    def test_move_source_not_found(self):
        """Test MOVE with non-existent source."""
        app = self.makeApp({}, [])
        code, headers, contents = self.move(
            app, "/nonexistent.txt", "http://localhost/dest.txt"
        )
        self.assertEqual("404 Not Found", code)

    def test_move_overwrite_false_destination_exists(self):
        """Test MOVE with Overwrite: F when destination exists."""

        class TestCollection(Collection):
            def get_member(self, name):
                if name in ("source.txt", "dest.txt"):
                    return Resource()
                raise KeyError(name)

            async def move_member(self, name, destination, dest_name, overwrite=True):
                if not overwrite:
                    raise FileExistsError(f"Destination {dest_name} already exists")

        collection = TestCollection()
        app = self.makeApp(
            {
                "/": collection,
                "/source.txt": Resource(),
                "/dest.txt": Resource(),
            },
            [],
        )
        code, headers, contents = self.move(
            app, "/source.txt", "http://localhost/dest.txt", overwrite=False
        )
        self.assertEqual("412 Precondition Failed", code)
        self.assertIn(b"Destination exists", contents)

    def test_move_same_source_and_destination(self):
        """Test MOVE with same source and destination."""
        app = self.makeApp({"/file.txt": Resource()}, [])
        code, headers, contents = self.move(
            app, "/file.txt", "http://localhost/file.txt"
        )
        self.assertEqual("403 Forbidden", code)
        self.assertIn(b"Source and destination cannot be the same", contents)

    def test_move_destination_container_not_found(self):
        """Test MOVE when destination container doesn't exist."""
        app = self.makeApp({"/": Collection(), "/source.txt": Resource()}, [])
        code, headers, contents = self.move(
            app, "/source.txt", "http://localhost/nonexistent/dest.txt"
        )
        self.assertEqual("409 Conflict", code)
        self.assertIn(b"Destination container does not exist", contents)

    def test_move_collection_not_implemented(self):
        """Test MOVE on a collection (not implemented)."""

        class TestCollection(Collection):
            resource_types = Collection.resource_types

        app = self.makeApp({"/collection/": TestCollection()}, [])
        code, headers, contents = self.move(
            app, "/collection/", "http://localhost/newcollection/"
        )
        self.assertEqual("501 Not Implemented", code)
        self.assertIn(b"MOVE for collections not implemented", contents)

    def test_copy_success(self):
        """Test successful COPY operation."""
        copied_items = []

        class TestResource(Resource):
            async def get_etag(self):
                return '"test-etag"'

            async def get_body(self):
                yield b"test content"

            def get_content_type(self):
                return "text/plain"

        class TestCollection(Collection):
            def get_member(self, name):
                if name == "source.txt":
                    return TestResource()
                raise KeyError(name)

            async def copy_member(self, name, destination, dest_name, overwrite=True):
                copied_items.append((name, destination, dest_name, overwrite))

        source_collection = TestCollection()
        dest_collection = TestCollection()
        app = self.makeApp(
            {
                "/": source_collection,
                "/source.txt": TestResource(),
                "/dest": dest_collection,
            },
            [],
        )
        code, headers, contents = self.copy(
            app, "/source.txt", "http://localhost/dest/target.txt"
        )
        self.assertEqual("201 Created", code)
        self.assertEqual(b"", contents)
        self.assertEqual(
            [("source.txt", dest_collection, "target.txt", True)], copied_items
        )

    def test_copy_no_destination_header(self):
        """Test COPY without Destination header."""
        app = self.makeApp({"/source.txt": Resource()}, [])
        # Manually create the request without Destination header
        environ = {
            "PATH_INFO": "/source.txt",
            "REQUEST_METHOD": "COPY",
        }
        setup_testing_defaults(environ)
        environ["HTTP_HOST"] = "localhost"
        _code = []

        def start_response(code, headers):
            _code.append(code)

        contents = b"".join(app(environ, start_response))
        self.assertEqual("400 Bad Request", _code[0])
        self.assertIn(b"Destination header required for COPY", contents)

    def test_copy_collection_not_implemented(self):
        """Test COPY on a collection (not implemented)."""

        class TestCollection(Collection):
            resource_types = Collection.resource_types

        app = self.makeApp({"/collection/": TestCollection()}, [])
        code, headers, contents = self.copy(
            app, "/collection/", "http://localhost/newcollection/"
        )
        self.assertEqual("501 Not Implemented", code)
        self.assertIn(b"COPY for collections not implemented", contents)

    def test_rfc4918_9_8_copy_collection_depth_0(self):
        """Test COPY on collection with Depth: 0 creates empty collection.

        RFC 4918 Section 9.8.3: Depth of 0 means only copy the collection,
        not its members (create empty collection at destination).
        """

        class TestBackend:
            def __init__(self):
                self.created_collections = []

            def get_resource(self, path):
                if path == "/":
                    return Collection()
                if path == "/source/":
                    return Collection()
                if path == "/dest":
                    return Collection()
                return None

            def create_collection(self, path):
                self.created_collections.append(path)

        backend = TestBackend()

        class TestApp:
            def __init__(self):
                self.backend = backend
                self.strict = True

            def _get_resource_from_environ(self, request, environ):
                path = environ["PATH_INFO"]
                return path, path, backend.get_resource(path)

        app_instance = TestApp()

        from xandikos.webdav import CopyMethod, WSGIRequest

        method = CopyMethod()
        environ = {
            "PATH_INFO": "/source/",
            "REQUEST_METHOD": "COPY",
            "SCRIPT_NAME": "",
        }
        setup_testing_defaults(environ)
        environ["HTTP_DESTINATION"] = "http://localhost/newcollection/"
        environ["HTTP_DEPTH"] = "0"
        environ["HTTP_HOST"] = "localhost"

        request = WSGIRequest(environ)
        response = asyncio.run(method.handle(request, environ, app_instance))

        self.assertEqual(201, response.status)
        self.assertEqual(["/newcollection/"], backend.created_collections)

    def test_rfc4918_9_8_copy_collection_depth_infinity(self):
        """Test COPY on collection with Depth: infinity (default).

        RFC 4918 Section 9.8.3: Depth of infinity means copy the collection
        and all its members recursively.
        """

        class TestCollection(Collection):
            resource_types = Collection.resource_types

        # Test with default depth (infinity)
        app = self.makeApp({"/collection/": TestCollection()}, [])
        code, headers, contents = self.copy(
            app, "/collection/", "http://localhost/newcollection/"
        )
        # Current implementation returns 501 Not Implemented for collection copy
        self.assertEqual("501 Not Implemented", code)
        self.assertIn(b"COPY for collections not implemented", contents)

    def test_rfc4918_9_8_copy_collection_invalid_depth(self):
        """Test COPY on collection with invalid Depth header.

        RFC 4918 Section 9.8.3: Depth must be 0 or infinity for COPY on collections.
        Other values should return 400 Bad Request.
        """

        class TestCollection(Collection):
            resource_types = Collection.resource_types

        app = self.makeApp({"/collection/": TestCollection()}, [])
        code, headers, contents = self.copy(
            app, "/collection/", "http://localhost/newcollection/", depth="1"
        )
        self.assertEqual("400 Bad Request", code)
        self.assertEqual(
            b"Depth must be 0 or infinity for COPY on collection", contents
        )

    def test_rfc4918_9_9_move_collection_depth_0(self):
        """Test MOVE on collection with Depth: 0.

        RFC 4918 Section 9.9.2: The MOVE method on a collection MUST act as if
        a 'Depth: infinity' header was used. Depth: 0 should return 400 Bad Request.
        """

        class TestCollection(Collection):
            resource_types = Collection.resource_types

        app = self.makeApp({"/collection/": TestCollection()}, [])
        code, headers, contents = self.move(
            app, "/collection/", "http://localhost/newcollection/", depth="0"
        )
        self.assertEqual("400 Bad Request", code)
        self.assertEqual(b"Depth must be infinity for MOVE on collection", contents)

    def test_rfc4918_9_9_move_collection_depth_infinity(self):
        """Test MOVE on collection with Depth: infinity (default).

        RFC 4918 Section 9.9.2: The MOVE method on a collection MUST act as if
        a 'Depth: infinity' header was used.
        """

        class TestCollection(Collection):
            resource_types = Collection.resource_types

        # Test with explicit depth=infinity
        app = self.makeApp({"/collection/": TestCollection()}, [])
        code, headers, contents = self.move(
            app, "/collection/", "http://localhost/newcollection/", depth="infinity"
        )
        # Current implementation returns 501 Not Implemented for collection move
        self.assertEqual("501 Not Implemented", code)
        self.assertEqual(b"MOVE for collections not implemented", contents)

    def test_rfc4918_9_9_move_collection_invalid_depth(self):
        """Test MOVE on collection with invalid Depth header.

        RFC 4918 Section 9.9.2: The MOVE method on a collection MUST use
        Depth: infinity. Other values should return 400 Bad Request.
        """

        class TestCollection(Collection):
            resource_types = Collection.resource_types

        app = self.makeApp({"/collection/": TestCollection()}, [])
        code, headers, contents = self.move(
            app, "/collection/", "http://localhost/newcollection/", depth="1"
        )
        self.assertEqual("400 Bad Request", code)
        self.assertEqual(b"Depth must be infinity for MOVE on collection", contents)

    def test_rfc4918_9_7_put_missing_intermediate_collection(self):
        """Test PUT returns 409 when intermediate collection is missing.

        RFC 4918 Section 9.7.1: A PUT that would result in the creation of a
        resource without an appropriately scoped parent collection MUST fail
        with a 409 (Conflict).
        """

        class TestCollection(Collection):
            resource_types = Collection.resource_types

        app = self.makeApp({"/": TestCollection()}, [])
        code, headers = self.put(app, "/nonexistent/file.txt", b"test content")
        self.assertEqual("409 Conflict", code)

    def test_rfc4918_9_3_mkcol_missing_parent(self):
        """Test MKCOL returns 409 when parent collection doesn't exist.

        RFC 4918 Section 9.3.1: If the Request-URI is such that a resource
        cannot be created as the child of an existing collection, then the
        server MUST fail with a 409 (Conflict).
        """

        class Backend:
            def create_collection(self, relpath):
                # Simulate missing parent by raising FileNotFoundError
                raise FileNotFoundError(f"Parent of {relpath} does not exist")

            def get_resource(self, relpath):
                if relpath == "/":
                    return Collection()
                return None

        app = WebDAVApp(Backend())
        code, headers, contents = self.mkcol(app, "/nonexistent/newcollection/")
        self.assertEqual("409 Conflict", code)

    def test_rfc4918_9_8_copy_destination_not_collection(self):
        """Test COPY returns 409 when destination container is not a collection.

        RFC 4918 Section 9.8.4: If the destination is not a collection, the
        server MUST fail the request with 409 (Conflict).
        """

        class TestResource(Resource):
            async def get_etag(self):
                return '"etag1"'

            async def get_body(self):
                yield b"content"

            def get_content_type(self):
                return "text/plain"

        class TestCollection(Collection):
            def get_member(self, name):
                if name == "source.txt":
                    return TestResource()
                if name == "notacollection":
                    return TestResource()
                raise KeyError(name)

            async def copy_member(self, name, destination, dest_name, overwrite=True):
                pass

        app = self.makeApp(
            {
                "/": TestCollection(),
                "/source.txt": TestResource(),
                "/notacollection": TestResource(),
            },
            [],
        )
        code, headers, contents = self.copy(
            app, "/source.txt", "http://localhost/notacollection/dest.txt"
        )
        self.assertEqual("409 Conflict", code)
        self.assertEqual(b"Destination container is not a collection", contents)

    def test_rfc4918_9_9_move_destination_not_collection(self):
        """Test MOVE returns 409 when destination container is not a collection.

        RFC 4918 Section 9.9.3: If a resource exists at the destination and
        the Overwrite header is "T", then prior to performing the move, the
        server MUST perform a DELETE with "Depth: infinity" on the destination.
        If the destination is not a collection, the server MUST fail with
        409 (Conflict).
        """

        class TestResource(Resource):
            async def get_etag(self):
                return '"etag1"'

            async def get_body(self):
                yield b"content"

            def get_content_type(self):
                return "text/plain"

        class TestCollection(Collection):
            def get_member(self, name):
                if name == "source.txt":
                    return TestResource()
                if name == "notacollection":
                    return TestResource()
                raise KeyError(name)

            async def move_member(self, name, destination, dest_name, overwrite=True):
                pass

        app = self.makeApp(
            {
                "/": TestCollection(),
                "/source.txt": TestResource(),
                "/notacollection": TestResource(),
            },
            [],
        )
        code, headers, contents = self.move(
            app, "/source.txt", "http://localhost/notacollection/dest.txt"
        )
        self.assertEqual("409 Conflict", code)
        self.assertEqual(b"Destination container is not a collection", contents)

    def test_rfc4918_propfind_distinguish_404_vs_empty(self):
        """Test PROPFIND distinguishes between property not found (404) vs empty value.

        RFC 4918: When a property is requested but doesn't exist, the propstat
        should contain 404 Not Found. This is different from a property that
        exists but has no value.
        """

        class EmptyProperty(Property):
            name = "{DAV:}empty-prop"

            async def get_value(self, href, resource, el, environ):
                # Property exists but has empty value
                el.text = ""

        # Test requesting a property that doesn't exist
        app = self.makeApp({"/resource": Resource()}, [EmptyProperty()])
        body = b"""<?xml version="1.0" encoding="utf-8" ?>
<D:propfind xmlns:D="DAV:">
  <D:prop>
    <D:nonexistent-prop/>
  </D:prop>
</D:propfind>"""
        code, headers, contents = self.propfind(app, "/resource", body, depth="0")
        self.assertEqual("207 Multi-Status", code)
        self.assertMultiLineEqual(
            contents.decode("utf-8"),
            '<ns0:multistatus xmlns:ns0="DAV:"><ns0:response><ns0:href>/resource</ns0:href>'
            "<ns0:propstat><ns0:status>HTTP/1.1 404 Not Found</ns0:status>"
            "<ns0:prop><ns0:nonexistent-prop /></ns0:prop></ns0:propstat>"
            "</ns0:response></ns0:multistatus>",
        )

    def test_rfc4918_proppatch_distinguish_errors(self):
        """Test PROPPATCH correctly distinguishes different error types.

        RFC 4918: Protected properties should return 403 Forbidden,
        while non-existent properties attempting to be modified should
        also be handled appropriately.
        """

        class ProtectedProperty(Property):
            name = "{DAV:}getetag"

            async def get_value(self, href, resource, el, environ):
                el.text = "protected-value"

            async def set_value(self, href, resource, el):
                raise ProtectedPropertyError("Cannot modify protected property")

        app = self.makeApp({"/resource": Resource()}, [ProtectedProperty()])

        # Try to modify protected property
        body = b"""<?xml version="1.0" encoding="utf-8" ?>
<D:propertyupdate xmlns:D="DAV:">
  <D:set>
    <D:prop>
      <D:getetag>new-value</D:getetag>
    </D:prop>
  </D:set>
</D:propertyupdate>"""
        code, headers, contents = self.proppatch(app, "/resource", body)
        self.assertEqual("207 Multi-Status", code)
        self.assertMultiLineEqual(
            contents.decode("utf-8"),
            '<ns0:multistatus xmlns:ns0="DAV:"><ns0:response>'
            "<ns0:href>http%3A//127.0.0.1/resource</ns0:href>"
            "<ns0:propstat><ns0:status>HTTP/1.1 403 Forbidden</ns0:status>"
            "<ns0:prop><ns0:getetag /></ns0:prop></ns0:propstat>"
            "</ns0:response></ns0:multistatus>",
        )

    def test_rfc4918_propstat_multiple_status_codes(self):
        """Test that propstat correctly groups properties by status code.

        RFC 4918 Section 14.22: propstat contains one or more prop elements
        and a status indicating the result of the properties in the prop.
        Multiple propstat elements can be returned for different status codes.
        """

        class SuccessProperty(Property):
            name = "{DAV:}success-prop"

            async def get_value(self, href, resource, el, environ):
                el.text = "success"

        class FailProperty(Property):
            name = "{DAV:}fail-prop"

            async def get_value(self, href, resource, el, environ):
                raise KeyError("Property not available")

        app = self.makeApp(
            {"/resource": Resource()}, [SuccessProperty(), FailProperty()]
        )

        # Request both properties
        body = b"""<?xml version="1.0" encoding="utf-8" ?>
<D:propfind xmlns:D="DAV:">
  <D:prop>
    <D:success-prop/>
    <D:fail-prop/>
  </D:prop>
</D:propfind>"""
        code, headers, contents = self.propfind(app, "/resource", body, depth="0")
        self.assertEqual("207 Multi-Status", code)
        # Properties are correctly grouped in separate propstat elements by status code
        self.assertMultiLineEqual(
            contents.decode("utf-8"),
            '<ns0:multistatus xmlns:ns0="DAV:"><ns0:response><ns0:href>/resource</ns0:href>'
            "<ns0:propstat><ns0:status>HTTP/1.1 200 OK</ns0:status>"
            "<ns0:prop><ns0:success-prop>success</ns0:success-prop></ns0:prop></ns0:propstat>"
            "<ns0:propstat><ns0:status>HTTP/1.1 404 Not Found</ns0:status>"
            "<ns0:prop><ns0:fail-prop /></ns0:prop></ns0:propstat>"
            "</ns0:response></ns0:multistatus>",
        )


class PickContentTypesTests(unittest.TestCase):
    def test_not_acceptable(self):
        self.assertRaises(
            webdav.NotAcceptableError,
            webdav.pick_content_types,
            [("text/plain", {})],
            ["text/html"],
        )
        self.assertRaises(
            webdav.NotAcceptableError,
            webdav.pick_content_types,
            [("text/plain", {}), ("text/html", {"q": "0"})],
            ["text/html"],
        )

    def test_highest_q(self):
        self.assertEqual(
            ["text/plain"],
            webdav.pick_content_types(
                [("text/html", {"q": "0.3"}), ("text/plain", {"q": "0.4"})],
                ["text/plain", "text/html"],
            ),
        )
        self.assertEqual(
            ["text/html", "text/plain"],
            webdav.pick_content_types(
                [("text/html", {}), ("text/plain", {"q": "1"})],
                ["text/plain", "text/html"],
            ),
        )

    def test_no_q(self):
        self.assertEqual(
            ["text/html", "text/plain"],
            webdav.pick_content_types(
                [("text/html", {}), ("text/plain", {})],
                ["text/plain", "text/html"],
            ),
        )

    def test_wildcard(self):
        self.assertEqual(
            ["text/plain"],
            webdav.pick_content_types(
                [("text/*", {"q": "0.3"}), ("text/plain", {"q": "0.4"})],
                ["text/plain", "text/html"],
            ),
        )
        self.assertEqual(
            {"text/plain", "text/html"},
            set(
                webdav.pick_content_types(
                    [("text/*", {"q": "0.4"}), ("text/plain", {"q": "0.3"})],
                    ["text/plain", "text/html"],
                )
            ),
        )
        self.assertEqual(
            ["application/html"],
            webdav.pick_content_types(
                [
                    ("application/*", {"q": "0.4"}),
                    ("text/plain", {"q": "0.3"}),
                ],
                ["text/plain", "application/html"],
            ),
        )


class ParseAcceptHeaderTests(unittest.TestCase):
    def test_parse(self):
        self.assertEqual([], webdav.parse_accept_header(""))
        self.assertEqual(
            [("text/plain", {"q": "0.1"})],
            webdav.parse_accept_header("text/plain; q=0.1"),
        )
        self.assertEqual(
            [("text/plain", {"q": "0.1"}), ("text/plain", {})],
            webdav.parse_accept_header("text/plain; q=0.1, text/plain"),
        )


class ETagMatchesTests(unittest.TestCase):
    def test_matches(self):
        self.assertTrue(webdav.etag_matches("etag1, etag2", "etag1"))
        self.assertFalse(webdav.etag_matches("etag3, etag2", "etag1"))
        self.assertFalse(webdav.etag_matches("etag1 etag2", "etag1"))
        self.assertFalse(webdav.etag_matches("etag1, etag2", None))
        self.assertTrue(webdav.etag_matches("*, etag2", "etag1"))
        self.assertTrue(webdav.etag_matches("*", "etag1"))
        self.assertFalse(webdav.etag_matches("*", None))


class PropstatByStatusTests(unittest.TestCase):
    def test_none(self):
        self.assertEqual({}, webdav.propstat_by_status([]))

    def test_one(self):
        self.assertEqual(
            {("200 OK", None): ["foo"]},
            webdav.propstat_by_status([webdav.PropStatus("200 OK", None, "foo")]),
        )

    def test_multiple(self):
        self.assertEqual(
            {
                ("200 OK", None): ["foo"],
                ("404 Not Found", "Cannot find"): ["bar"],
            },
            webdav.propstat_by_status(
                [
                    webdav.PropStatus("200 OK", None, "foo"),
                    webdav.PropStatus("404 Not Found", "Cannot find", "bar"),
                ]
            ),
        )


class PropstatAsXmlTests(unittest.TestCase):
    def test_none(self):
        self.assertEqual([], list(webdav.propstat_as_xml([])))

    def test_one(self):
        self.assertEqual(
            [
                b'<ns0:propstat xmlns:ns0="DAV:"><ns0:status>HTTP/1.1 200 '
                b"OK</ns0:status><ns0:prop><foo /></ns0:prop></ns0:propstat>"
            ],
            [
                ET.tostring(x)
                for x in webdav.propstat_as_xml(
                    [webdav.PropStatus("200 OK", None, ET.Element("foo"))]
                )
            ],
        )


class PathFromEnvironTests(unittest.TestCase):
    def test_ascii(self):
        self.assertEqual(
            "/bla",
            webdav.path_from_environ({"PATH_INFO": "/bla"}, "PATH_INFO"),
        )

    def test_recode(self):
        self.assertEqual(
            "/blü",
            webdav.path_from_environ({"PATH_INFO": "/bl\xc3\xbc"}, "PATH_INFO"),
        )


class HrefToPathTests(unittest.TestCase):
    def test_outside(self):
        self.assertIs(None, href_to_path({"SCRIPT_NAME": "/dav"}, "/bar"))

    def test_root(self):
        self.assertEqual("/", href_to_path({"SCRIPT_NAME": "/dav"}, "/dav"))
        self.assertEqual("/", href_to_path({"SCRIPT_NAME": "/dav/"}, "/dav"))
        self.assertEqual("/", href_to_path({"SCRIPT_NAME": "/dav/"}, "/dav/"))
        self.assertEqual("/", href_to_path({"SCRIPT_NAME": "/dav"}, "/dav/"))

    def test_relpath(self):
        self.assertEqual("/foo", href_to_path({"SCRIPT_NAME": "/dav"}, "/dav/foo"))
        self.assertEqual("/foo", href_to_path({"SCRIPT_NAME": "/dav/"}, "/dav/foo"))
        self.assertEqual("/foo/", href_to_path({"SCRIPT_NAME": "/dav/"}, "/dav/foo/"))


class PropertyRemovalTests(unittest.TestCase):
    def test_displayname_removal(self):
        """Test that removing displayname property works correctly."""
        import asyncio

        class TestResource(Resource):
            def __init__(self):
                self._displayname = "Test Name"

            def get_displayname(self):
                return self._displayname

            def set_displayname(self, value):
                self._displayname = value

        resource = TestResource()
        prop = DisplayNameProperty()
        properties = {prop.name: prop}

        # Create a remove element
        remove_el = ET.Element("{DAV:}remove")
        prop_el = ET.SubElement(remove_el, "{DAV:}prop")
        ET.SubElement(prop_el, "{DAV:}displayname")

        # Apply the removal
        async def run_test():
            propstat_list = []
            async for ps in apply_modify_prop(remove_el, "/test", resource, properties):
                propstat_list.append(ps)
            return propstat_list

        propstat_list = asyncio.run(run_test())

        self.assertEqual(len(propstat_list), 1)
        self.assertEqual(propstat_list[0].statuscode, "200 OK")
        self.assertIsNone(resource._displayname)

    def test_resourcetype_removal(self):
        """Test that removing resourcetype property works correctly."""
        import asyncio

        class TestResource(Resource):
            def __init__(self):
                self.resource_types = ["{DAV:}collection"]

            def set_resource_types(self, types):
                self.resource_types = types

        resource = TestResource()
        prop = ResourceTypeProperty()
        properties = {prop.name: prop}

        # Create a remove element
        remove_el = ET.Element("{DAV:}remove")
        prop_el = ET.SubElement(remove_el, "{DAV:}prop")
        ET.SubElement(prop_el, "{DAV:}resourcetype")

        # Apply the removal
        async def run_test():
            propstat_list = []
            async for ps in apply_modify_prop(remove_el, "/test", resource, properties):
                propstat_list.append(ps)
            return propstat_list

        propstat_list = asyncio.run(run_test())

        self.assertEqual(len(propstat_list), 1)
        self.assertEqual(propstat_list[0].statuscode, "200 OK")
        self.assertEqual(resource.resource_types, [])


class SplitPathPreservingEncodingTests(unittest.TestCase):
    def test_normal_path(self):
        """Test splitting a normal path without encoded slashes."""

        class MockRequest:
            raw_path = "/collection/item.ics"

        environ = {"SCRIPT_NAME": ""}
        container, item = split_path_preserving_encoding(MockRequest(), environ)
        self.assertEqual("/collection", container)
        self.assertEqual("item.ics", item)

    def test_percent_encoded_slash(self):
        """Test splitting a path with percent-encoded slash."""

        class MockRequest:
            raw_path = "/collection/itemwith%2Fslash.ics"

        environ = {"SCRIPT_NAME": ""}
        container, item = split_path_preserving_encoding(MockRequest(), environ)
        self.assertEqual("/collection", container)
        self.assertEqual("itemwith/slash.ics", item)

    def test_with_script_name(self):
        """Test splitting a path with SCRIPT_NAME prefix."""

        class MockRequest:
            raw_path = "/dav/collection/itemwith%2Fslash.ics"

        environ = {"SCRIPT_NAME": "/dav"}
        container, item = split_path_preserving_encoding(MockRequest(), environ)
        self.assertEqual("/collection", container)
        self.assertEqual("itemwith/slash.ics", item)

    def test_multiple_encoded_slashes(self):
        """Test splitting a path with multiple percent-encoded slashes."""

        class MockRequest:
            raw_path = "/collection/item%2Fwith%2Fslashes.ics"

        environ = {"SCRIPT_NAME": ""}
        container, item = split_path_preserving_encoding(MockRequest(), environ)
        self.assertEqual("/collection", container)
        self.assertEqual("item/with/slashes.ics", item)

    def test_encoded_slash_in_container(self):
        """Test splitting a path with percent-encoded slash in container name.

        According to RFC 3986, the path should be split BEFORE decoding.
        So /calendars/cal%2Fender/item.ics means:
        - Collection at path: /calendars/cal/ender (after decoding cal%2Fender)
        - Item: item.ics
        """

        class MockRequest:
            raw_path = "/calendars/cal%2Fender/item.ics"

        environ = {"SCRIPT_NAME": ""}
        container, item = split_path_preserving_encoding(MockRequest(), environ)
        # After splitting at the last /, we decode each component
        # cal%2Fender becomes cal/ender, creating a nested path
        self.assertEqual("/calendars/cal/ender", container)
        self.assertEqual("item.ics", item)

    def test_encoded_space_in_names(self):
        """Test that other percent-encoding (like spaces) is properly decoded."""

        class MockRequest:
            raw_path = "/my%20calendars/my%20file.ics"

        environ = {"SCRIPT_NAME": ""}
        container, item = split_path_preserving_encoding(MockRequest(), environ)
        self.assertEqual("/my calendars", container)
        self.assertEqual("my file.ics", item)

    def test_mixed_encoding(self):
        """Test path with both encoded slashes and other encoded characters."""

        class MockRequest:
            raw_path = "/my%20calendars/file%2Fwith%20slash.ics"

        environ = {"SCRIPT_NAME": ""}
        container, item = split_path_preserving_encoding(MockRequest(), environ)
        self.assertEqual("/my calendars", container)
        self.assertEqual("file/with slash.ics", item)

    def test_root_level_item(self):
        """Test splitting a path for item at root level."""

        class MockRequest:
            raw_path = "/item.ics"

        environ = {"SCRIPT_NAME": ""}
        container, item = split_path_preserving_encoding(MockRequest(), environ)
        self.assertEqual("/", container)
        self.assertEqual("item.ics", item)

    def test_root_level_item_with_encoded_slash(self):
        """Test splitting a path for root level item with encoded slash."""

        class MockRequest:
            raw_path = "/item%2Fwith%2Fslash.ics"

        environ = {"SCRIPT_NAME": ""}
        container, item = split_path_preserving_encoding(MockRequest(), environ)
        self.assertEqual("/", container)
        self.assertEqual("item/with/slash.ics", item)

    def test_fragment_stripped(self):
        """Test that URI fragments are stripped per RFC 3986.

        Fragments (the part after #) should not be sent to the server,
        but if they are, they should be stripped before processing.
        """

        class MockRequest:
            raw_path = "/litmus/frag/#ment"

        environ = {"SCRIPT_NAME": ""}
        container, item = split_path_preserving_encoding(MockRequest(), environ)
        self.assertEqual("/litmus", container)
        self.assertEqual("frag", item)

    def test_fragment_in_middle(self):
        """Test fragment stripping when fragment is in the middle of path."""

        class MockRequest:
            raw_path = "/collection#fragment/item.ics"

        environ = {"SCRIPT_NAME": ""}
        container, item = split_path_preserving_encoding(MockRequest(), environ)
        # Everything after # should be stripped
        self.assertEqual("/", container)
        self.assertEqual("collection", item)

    def test_encoded_hash_preserved(self):
        """Test that percent-encoded hash (%23) is preserved as part of name."""

        class MockRequest:
            raw_path = "/collection/item%23name.ics"

        environ = {"SCRIPT_NAME": ""}
        container, item = split_path_preserving_encoding(MockRequest(), environ)
        self.assertEqual("/collection", container)
        # %23 should decode to # and be part of the item name
        self.assertEqual("item#name.ics", item)


class CollectionMoveMemberTests(unittest.TestCase):
    """Test the Collection.move_member method."""

    def test_move_member_success(self):
        """Test successful move_member operation."""
        import asyncio

        class TestResource(Resource):
            def __init__(self, content, content_type="text/plain"):
                self.content = content
                self.content_type = content_type

            async def get_etag(self):
                return '"test-etag"'

            async def get_body(self):
                return [self.content]

            def get_content_type(self):
                return self.content_type

        class TestCollection(Collection):
            def __init__(self):
                self.members = {}
                self.deleted = []
                self.created = []

            def get_member(self, name):
                if name in self.members:
                    return self.members[name]
                raise KeyError(name)

            def delete_member(self, name, etag=None):
                if name not in self.members:
                    raise KeyError(name)
                del self.members[name]
                self.deleted.append((name, etag))

            async def create_member(self, name, contents, content_type, requester=None):
                body = b"".join(contents)
                self.members[name] = TestResource(body, content_type)
                self.created.append((name, body, content_type))
                return (name, '"new-etag"')

        async def run_test():
            source = TestCollection()
            dest = TestCollection()
            source.members["file.txt"] = TestResource(b"Hello, World!")

            # Test move without overwrite
            await source.move_member("file.txt", dest, "newfile.txt")

            # Check source deleted
            self.assertEqual([("file.txt", '"test-etag"')], source.deleted)
            self.assertNotIn("file.txt", source.members)

            # Check destination created
            self.assertEqual(
                [("newfile.txt", b"Hello, World!", "text/plain")], dest.created
            )
            self.assertIn("newfile.txt", dest.members)

        asyncio.run(run_test())

    def test_move_member_overwrite_false_exists(self):
        """Test move_member with overwrite=False when destination exists."""
        import asyncio

        class TestResource(Resource):
            async def get_etag(self):
                return '"test-etag"'

            async def get_body(self):
                return [b"content"]

            def get_content_type(self):
                return "text/plain"

        class TestCollection(Collection):
            def __init__(self):
                self.members = {}

            def get_member(self, name):
                if name in self.members:
                    return self.members[name]
                raise KeyError(name)

            async def create_member(self, name, contents, content_type, requester=None):
                if name in self.members:
                    raise FileExistsError(f"{name} already exists")
                return (name, '"new-etag"')

        async def run_test():
            source = TestCollection()
            dest = TestCollection()
            source.members["file.txt"] = TestResource()
            dest.members["existing.txt"] = TestResource()

            # Test move with overwrite=False when destination exists
            with self.assertRaises(FileExistsError):
                await source.move_member(
                    "file.txt", dest, "existing.txt", overwrite=False
                )

        asyncio.run(run_test())


class CollectionCopyMemberTests(unittest.TestCase):
    """Test the Collection.copy_member method."""

    def test_copy_member_success(self):
        """Test successful copy_member operation."""
        import asyncio

        class TestResource(Resource):
            def __init__(self, content, content_type="text/plain"):
                self.content = content
                self.content_type = content_type

            async def get_etag(self):
                return '"test-etag"'

            async def get_body(self):
                return [self.content]

            def get_content_type(self):
                return self.content_type

        class TestCollection(Collection):
            def __init__(self):
                self.members = {}
                self.created = []

            def get_member(self, name):
                if name in self.members:
                    return self.members[name]
                raise KeyError(name)

            async def create_member(self, name, contents, content_type, requester=None):
                body = b"".join(contents)
                self.members[name] = TestResource(body, content_type)
                self.created.append((name, body, content_type))
                return (name, '"new-etag"')

        async def run_test():
            source = TestCollection()
            dest = TestCollection()
            source.members["file.txt"] = TestResource(b"Hello, World!")

            # Test copy without affecting source
            await source.copy_member("file.txt", dest, "newfile.txt")

            # Check source NOT deleted (key difference from move)
            self.assertIn("file.txt", source.members)

            # Check destination created
            self.assertEqual(
                [("newfile.txt", b"Hello, World!", "text/plain")], dest.created
            )
            self.assertIn("newfile.txt", dest.members)

        asyncio.run(run_test())

    def test_copy_member_overwrite_false_exists(self):
        """Test copy_member with overwrite=False when destination exists."""
        import asyncio

        class TestResource(Resource):
            async def get_etag(self):
                return '"test-etag"'

            async def get_body(self):
                return [b"content"]

            def get_content_type(self):
                return "text/plain"

        class TestCollection(Collection):
            def __init__(self):
                self.members = {}

            def get_member(self, name):
                if name in self.members:
                    return self.members[name]
                raise KeyError(name)

            async def create_member(self, name, contents, content_type, requester=None):
                if name in self.members:
                    raise FileExistsError(f"Member {name} already exists")
                self.members[name] = TestResource()
                return (name, '"new-etag"')

        async def run_test():
            source = TestCollection()
            dest = TestCollection()
            source.members["source.txt"] = TestResource()
            dest.members["dest.txt"] = TestResource()

            # Test copy with overwrite=False when destination exists
            with self.assertRaises(FileExistsError):
                await source.copy_member(
                    "source.txt", dest, "dest.txt", overwrite=False
                )

        asyncio.run(run_test())


class ChunkedTransferEncodingTests(WebTestCase):
    """Tests for chunked transfer encoding support in WSGI requests."""

    @staticmethod
    def encode_chunked(data: bytes) -> bytes:
        """Encode data using chunked transfer encoding format."""
        if not data:
            # Just the terminating chunk
            return b"0\r\n\r\n"

        # For testing, we'll split the data into chunks
        # We'll use varying chunk sizes to test the decoder properly
        chunks: list[bytes] = []
        offset = 0
        chunk_sizes = [5, 10, 7, 15]  # Varying sizes for testing

        while offset < len(data):
            chunk_size = chunk_sizes[len(chunks) % len(chunk_sizes)]
            chunk = data[offset : offset + chunk_size]
            if chunk:
                # Format: {size in hex}\r\n{data}\r\n
                chunks.append(f"{len(chunk):X}\r\n".encode() + chunk + b"\r\n")
            offset += chunk_size

        # Add terminating chunk
        chunks.append(b"0\r\n\r\n")
        return b"".join(chunks)

    def put_chunked(self, app, path, contents):
        """Helper to perform PUT request with chunked encoding."""
        chunked_body = self.encode_chunked(contents)
        environ = {
            "PATH_INFO": path,
            "REQUEST_METHOD": "PUT",
            "wsgi.input": BytesIO(chunked_body),
            "HTTP_TRANSFER_ENCODING": "chunked",
        }
        setup_testing_defaults(environ)
        # Remove CONTENT_LENGTH as it's not used with chunked encoding
        if "CONTENT_LENGTH" in environ:
            del environ["CONTENT_LENGTH"]

        _code = []
        _headers = []

        def start_response(code, headers):
            _code.append(code)
            _headers.extend(headers)

        list(app(environ, start_response))
        return _code[0], _headers

    def test_put_chunked_simple(self):
        """Test PUT with simple chunked body."""

        class TestResource(Resource):
            def __init__(self) -> None:
                self.contents = None

            def get_content_language(self):
                return None

            def get_content_type(self):
                return "text/plain"

            def get_content_length(self):
                return len(self.contents) if self.contents else 0

            async def get_body(self):
                return [self.contents] if self.contents else []

            async def set_body(self, data, replace_etag=None):
                self.contents = b"".join(data)

            def get_last_modified(self):
                return None

            async def get_etag(self):
                return "test-etag"

        resources = {"/test.txt": TestResource()}
        app = self.makeApp(resources, [])

        test_data = b"Hello, chunked world!"
        code, headers = self.put_chunked(app, "/test.txt", test_data)

        # Should succeed
        self.assertIn(code.split()[0], ["200", "201", "204"])
        # Verify the data was correctly decoded and stored
        self.assertEqual(resources["/test.txt"].contents, test_data)

    def test_put_chunked_empty(self):
        """Test PUT with empty chunked body."""

        class TestResource(Resource):
            def __init__(self) -> None:
                self.contents = None

            def get_content_language(self):
                return None

            def get_content_type(self):
                return "text/plain"

            def get_content_length(self):
                return len(self.contents) if self.contents else 0

            async def get_body(self):
                return [self.contents] if self.contents else []

            async def set_body(self, data, replace_etag=None):
                self.contents = b"".join(data)

            def get_last_modified(self):
                return None

            async def get_etag(self):
                return "test-etag"

        resources = {"/empty.txt": TestResource()}
        app = self.makeApp(resources, [])

        code, headers = self.put_chunked(app, "/empty.txt", b"")

        # Should succeed
        self.assertIn(code.split()[0], ["200", "201", "204"])
        # Verify empty data was stored
        self.assertEqual(resources["/empty.txt"].contents, b"")

    def test_put_chunked_large(self):
        """Test PUT with larger chunked body."""

        class TestResource(Resource):
            def __init__(self) -> None:
                self.contents = None

            def get_content_language(self):
                return None

            def get_content_type(self):
                return "text/plain"

            def get_content_length(self):
                return len(self.contents) if self.contents else 0

            async def get_body(self):
                return [self.contents] if self.contents else []

            async def set_body(self, data, replace_etag=None):
                self.contents = b"".join(data)

            def get_last_modified(self):
                return None

            async def get_etag(self):
                return "test-etag"

        resources = {"/large.txt": TestResource()}
        app = self.makeApp(resources, [])

        # Create a larger test payload (1KB)
        test_data = b"x" * 1024
        code, headers = self.put_chunked(app, "/large.txt", test_data)

        # Should succeed
        self.assertIn(code.split()[0], ["200", "201", "204"])
        # Verify the data was correctly decoded and stored
        self.assertEqual(resources["/large.txt"].contents, test_data)
        self.assertEqual(len(resources["/large.txt"].contents), 1024)

    def test_put_chunked_binary(self):
        """Test PUT with binary data in chunked encoding."""

        class TestResource(Resource):
            def __init__(self) -> None:
                self.contents = None

            def get_content_language(self):
                return None

            def get_content_type(self):
                return "application/octet-stream"

            def get_content_length(self):
                return len(self.contents) if self.contents else 0

            async def get_body(self):
                return [self.contents] if self.contents else []

            async def set_body(self, data, replace_etag=None):
                self.contents = b"".join(data)

            def get_last_modified(self):
                return None

            async def get_etag(self):
                return "test-etag"

        resources = {"/binary.dat": TestResource()}
        app = self.makeApp(resources, [])

        # Binary data with all byte values
        test_data = bytes(range(256))
        code, headers = self.put_chunked(app, "/binary.dat", test_data)

        # Should succeed
        self.assertIn(code.split()[0], ["200", "201", "204"])
        # Verify binary data integrity
        self.assertEqual(resources["/binary.dat"].contents, test_data)
