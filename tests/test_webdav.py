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

import logging
import unittest
from io import BytesIO
from wsgiref.util import setup_testing_defaults

from xandikos import webdav

from xandikos.webdav import (
    ET,
    Collection,
    Property,
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

    def mkcol(self, app, path):
        environ = {
            "PATH_INFO": path,
            "REQUEST_METHOD": "MKCOL",
        }
        setup_testing_defaults(environ)
        _code = []
        _headers = []

        def start_response(code, headers):
            _code.append(code)
            _headers.extend(headers)

        contents = b"".join(app(environ, start_response))
        return _code[0], _headers, contents

    def delete(self, app, path):
        environ = {"PATH_INFO": path, "REQUEST_METHOD": "DELETE"}
        setup_testing_defaults(environ)
        _code = []
        _headers = []

        def start_response(code, headers):
            _code.append(code)
            _headers.extend(headers)

        contents = b"".join(app(environ, start_response))
        return _code[0], _headers, contents

    def get(self, app, path):
        environ = {"PATH_INFO": path, "REQUEST_METHOD": "GET"}
        setup_testing_defaults(environ)
        _code = []
        _headers = []

        def start_response(code, headers):
            _code.append(code)
            _headers.extend(headers)

        contents = b"".join(app(environ, start_response))
        return _code[0], _headers, contents

    def put(self, app, path, contents):
        environ = {
            "PATH_INFO": path,
            "REQUEST_METHOD": "PUT",
            "wsgi.input": BytesIO(contents),
        }
        setup_testing_defaults(environ)
        _code = []
        _headers = []

        def start_response(code, headers):
            _code.append(code)
            _headers.extend(headers)

        list(app(environ, start_response))
        return _code[0], _headers

    def move(self, app, path, destination, overwrite=None):
        environ = {
            "PATH_INFO": path,
            "REQUEST_METHOD": "MOVE",
        }
        if destination is not None:
            environ["HTTP_DESTINATION"] = destination
        if overwrite is not None:
            environ["HTTP_OVERWRITE"] = "T" if overwrite else "F"
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

    def copy(self, app, path, destination, overwrite=None):
        environ = {
            "PATH_INFO": path,
            "REQUEST_METHOD": "COPY",
        }
        if destination is not None:
            environ["HTTP_DESTINATION"] = destination
        if overwrite is not None:
            environ["HTTP_OVERWRITE"] = "T" if overwrite else "F"
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

    def propfind(self, app, path, body):
        environ = {
            "PATH_INFO": path,
            "REQUEST_METHOD": "PROPFIND",
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
        chunks = []
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
