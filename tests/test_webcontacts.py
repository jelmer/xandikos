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

"""Tests for the browser-facing contacts UI in xandikos.webcontacts."""

import io
import os
import shutil
import tempfile
import unittest
from urllib.parse import urlencode
from wsgiref.util import setup_testing_defaults

import vobject

from xandikos import webcontacts
from xandikos.store import STORE_TYPE_ADDRESSBOOK
from xandikos.store.git import TreeGitStore
from xandikos.vcard import VCardFile
from xandikos.web import AddressbookCollection, SingleUserFilesystemBackend, XandikosApp


EXAMPLE_VCARD = b"""\
BEGIN:VCARD
VERSION:3.0
UID:contact-1
FN:Alice Example
N:Example;Alice;;;
EMAIL;TYPE=WORK:alice@work.example.org
EMAIL;TYPE=HOME:alice@home.example.org
TEL;TYPE=CELL:+1-555-0100
ORG:ExampleCorp
TITLE:CEO
URL:https://alice.example.org/
NOTE:Important contact
END:VCARD
"""


class VCardConversionTests(unittest.TestCase):
    def _parse(self, data: bytes):
        return vobject.readOne(data.decode("utf-8"))

    def test_contact_summary(self):
        summary = webcontacts.contact_summary(self._parse(EXAMPLE_VCARD))
        self.assertEqual(summary["fn"], "Alice Example")
        self.assertEqual(
            sorted(summary["emails"]),
            ["alice@home.example.org", "alice@work.example.org"],
        )
        self.assertEqual(summary["tels"], ["+1-555-0100"])
        self.assertEqual(summary["org"], "ExampleCorp")

    def test_contact_to_form_round_trip(self):
        form_dict = webcontacts.contact_to_form(self._parse(EXAMPLE_VCARD))
        self.assertEqual(form_dict["fn"], "Alice Example")
        self.assertEqual(form_dict["n"]["family"], "Example")
        self.assertEqual(form_dict["n"]["given"], "Alice")
        self.assertEqual(form_dict["org"], "ExampleCorp")
        self.assertEqual(form_dict["title"], "CEO")
        self.assertEqual(form_dict["url"], "https://alice.example.org/")
        self.assertEqual(form_dict["note"], "Important contact")
        types = {e["value"]: e["type"] for e in form_dict["emails"]}
        self.assertEqual(types["alice@work.example.org"], "WORK")
        self.assertEqual(types["alice@home.example.org"], "HOME")

    def test_vcard_from_form_minimal(self):
        data = webcontacts.vcard_from_form({"fn": "Bob"}, uid="bob-uid")
        card = vobject.readOne(data.decode("utf-8"))
        self.assertEqual(str(card.fn.value), "Bob")
        self.assertEqual(str(card.uid.value), "bob-uid")
        # No emails / tels / org / title
        self.assertEqual([], [c for c in card.getChildren() if c.name == "EMAIL"])

    def test_vcard_from_form_with_emails_and_tels(self):
        form = {
            "fn": "Carol",
            "given_name": "Carol",
            "family_name": "Builder",
            "email_0": "carol@example.org",
            "email_type_0": "WORK",
            "email_1": "",  # gap row, should be skipped
            "email_type_1": "HOME",
            "email_2": "personal@example.org",
            "email_type_2": "HOME",
            "tel_0": "+1-555-9999",
            "tel_type_0": "CELL",
            "org": "BuilderCorp",
        }
        data = webcontacts.vcard_from_form(form, uid="carol")
        card = vobject.readOne(data.decode("utf-8"))
        emails = sorted(str(p.value) for p in card.contents.get("email", []))
        self.assertEqual(emails, ["carol@example.org", "personal@example.org"])
        self.assertEqual(str(card.tel.value), "+1-555-9999")
        self.assertEqual(str(card.n.value.family), "Builder")
        # ORG is structured (list)
        self.assertEqual(card.org.value, ["BuilderCorp"])

    def test_vcard_from_form_fills_fn_from_name_parts(self):
        data = webcontacts.vcard_from_form(
            {"given_name": "Eve", "family_name": "Smith"}, uid="eve"
        )
        card = vobject.readOne(data.decode("utf-8"))
        # FN must be set even when the form left it blank
        self.assertEqual(str(card.fn.value), "Eve Smith")

    def test_vcard_from_form_fn_falls_back_to_uid(self):
        data = webcontacts.vcard_from_form({}, uid="lone-uid")
        card = vobject.readOne(data.decode("utf-8"))
        self.assertEqual(str(card.fn.value), "lone-uid")


class WebContactsAppTests(unittest.TestCase):
    """End-to-end tests via XandikosApp to exercise the WSGI integration."""

    def setUp(self):
        super().setUp()
        self.tempdir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tempdir)

        store_path = os.path.join(self.tempdir, "addressbook")
        self.store = TreeGitStore.create(store_path)
        self.store.set_type(STORE_TYPE_ADDRESSBOOK)
        self.store.load_extra_file_handler(VCardFile)
        self.backend = SingleUserFilesystemBackend(self.tempdir)
        self.collection = AddressbookCollection(self.backend, "addressbook", self.store)
        self.app = XandikosApp(self.backend, "user")

    def _request(self, method, path, body=b"", extra_environ=None, accept="text/html"):
        environ = {
            "PATH_INFO": path,
            "REQUEST_METHOD": method,
            "QUERY_STRING": "",
            "HTTP_ACCEPT": accept,
        }
        if body:
            environ["wsgi.input"] = io.BytesIO(body)
            environ["CONTENT_LENGTH"] = str(len(body))
            environ["CONTENT_TYPE"] = "application/x-www-form-urlencoded"
        setup_testing_defaults(environ)
        if extra_environ:
            environ.update(extra_environ)
        captured = {}

        def start_response(status, headers):
            captured["status"] = status
            captured["headers"] = headers

        body_bytes = b"".join(self.app(environ, start_response))
        return captured["status"], dict(captured["headers"]), body_bytes

    def test_get_addressbook_lists_contacts(self):
        self.store.import_one("alice.vcf", "text/vcard", [EXAMPLE_VCARD])
        status, headers, body = self._request("GET", "/addressbook/")
        self.assertEqual(status, "200 OK")
        self.assertIn("text/html", headers["Content-Type"])
        text = body.decode("utf-8")
        self.assertIn("Alice Example", text)
        self.assertIn("alice@work.example.org", text)
        self.assertIn("ExampleCorp", text)
        self.assertIn("Add contact", text)

    def test_addressbook_has_parent_link(self):
        _s, _h, body = self._request("GET", "/addressbook/")
        text = body.decode("utf-8")
        self.assertIn('class="parent-link"', text)
        self.assertIn('href="http://127.0.0.1/"', text)

    def test_empty_addressbook_renders(self):
        status, _headers, body = self._request("GET", "/addressbook/")
        self.assertEqual(status, "200 OK")
        self.assertIn(b"No contacts yet", body)

    def test_get_contact_html_renders_edit_form(self):
        self.store.import_one("alice.vcf", "text/vcard", [EXAMPLE_VCARD])
        status, headers, body = self._request("GET", "/addressbook/alice.vcf")
        self.assertEqual(status, "200 OK")
        self.assertIn("text/html", headers["Content-Type"])
        text = body.decode("utf-8")
        self.assertIn('name="fn"', text)
        self.assertIn('value="Alice Example"', text)
        self.assertIn('value="alice@work.example.org"', text)

    def test_get_contact_vcard_returns_raw(self):
        # CardDAV clients must still get the raw vCard.
        self.store.import_one("alice.vcf", "text/vcard", [EXAMPLE_VCARD])
        status, headers, body = self._request(
            "GET", "/addressbook/alice.vcf", accept="text/vcard"
        )
        self.assertEqual(status, "200 OK")
        self.assertIn("text/vcard", headers["Content-Type"])
        self.assertIn(b"BEGIN:VCARD", body)

    def test_new_contact_form(self):
        status, _headers, body = self._request("GET", "/addressbook/+new")
        self.assertEqual(status, "200 OK")
        text = body.decode("utf-8")
        self.assertIn("New contact", text)
        # No pre-filled name
        self.assertIn('name="fn"', text)
        self.assertNotIn('value="Alice Example"', text)

    def test_create_contact_via_post(self):
        body = urlencode(
            {
                "action": "create",
                "name": "newperson.vcf",
                "fn": "New Person",
                "given_name": "New",
                "family_name": "Person",
                "email_0": "new@example.org",
                "email_type_0": "WORK",
            }
        ).encode("utf-8")
        status, headers, _ = self._request("POST", "/addressbook/", body=body)
        self.assertEqual(status, "303 See Other")
        self.assertTrue(headers["Location"].endswith("/addressbook/newperson.vcf"))
        # File was actually persisted
        members = dict(self.collection.members())
        self.assertIn("newperson.vcf", members)
        text = b"".join(
            self.store.get_file("newperson.vcf", "text/vcard").content
        ).decode("utf-8")
        self.assertIn("FN:New Person", text)
        self.assertIn("new@example.org", text)

    def test_create_without_name_generates_one(self):
        body = urlencode({"action": "create", "fn": "Anon Person"}).encode("utf-8")
        status, headers, _ = self._request("POST", "/addressbook/", body=body)
        self.assertEqual(status, "303 See Other")
        # Generated name ends with .vcf
        self.assertTrue(headers["Location"].endswith(".vcf"))
        # Exactly one stored item
        items = list(self.store.iter_with_etag())
        self.assertEqual(1, len(items))

    def test_update_contact_via_post_preserves_uid(self):
        self.store.import_one("alice.vcf", "text/vcard", [EXAMPLE_VCARD])
        body = urlencode(
            {
                "action": "update",
                "name": "alice.vcf",
                "fn": "Alice Updated",
                "given_name": "Alice",
                "family_name": "Updated",
                "email_0": "alice@new.example.org",
                "email_type_0": "WORK",
            }
        ).encode("utf-8")
        status, headers, _ = self._request("POST", "/addressbook/", body=body)
        self.assertEqual(status, "303 See Other")
        self.assertTrue(headers["Location"].endswith("/addressbook/alice.vcf"))
        text = b"".join(self.store.get_file("alice.vcf", "text/vcard").content).decode(
            "utf-8"
        )
        self.assertIn("FN:Alice Updated", text)
        self.assertIn("UID:contact-1", text)  # preserved
        self.assertIn("alice@new.example.org", text)
        self.assertNotIn("alice@work.example.org", text)

    def test_delete_contact_via_post(self):
        self.store.import_one("alice.vcf", "text/vcard", [EXAMPLE_VCARD])
        body = urlencode({"action": "delete", "name": "alice.vcf"}).encode("utf-8")
        status, headers, _ = self._request("POST", "/addressbook/", body=body)
        self.assertEqual(status, "303 See Other")
        self.assertTrue(headers["Location"].endswith("/addressbook/"))
        with self.assertRaises(KeyError):
            self.store.get_file("alice.vcf", "text/vcard")

    def test_delete_with_path_traversal_rejected(self):
        body = urlencode({"action": "delete", "name": "../escape"}).encode("utf-8")
        status, _headers, _ = self._request("POST", "/addressbook/", body=body)
        self.assertEqual(status, "400 Bad Request")

    def test_post_target_url_accepts_yarl_url(self):
        # Regression: under aiohttp, request.url is a yarl.URL, not a
        # str. _post_target_url must handle both.
        from types import SimpleNamespace

        from yarl import URL

        from xandikos.webcontacts import _post_target_url

        req = SimpleNamespace(url=URL("https://example.com/user/contacts/addressbook/"))
        result = _post_target_url(req, {}, "/user/contacts/addressbook")
        self.assertEqual(result, "https://example.com/user/contacts/addressbook/")

    def test_redirect_clean_when_script_name_is_slash(self):
        # Regression: a reverse proxy that sets SCRIPT_NAME='/' used
        # to produce a Location: //user/... header, which browsers
        # interpret as protocol-relative (host becomes the next
        # segment). Verify the fix collapses the double slash.
        body = urlencode({"action": "create", "fn": "Slash Test"}).encode("utf-8")
        environ = {
            "PATH_INFO": "/addressbook/",
            "REQUEST_METHOD": "POST",
            "QUERY_STRING": "",
            "HTTP_HOST": "example.com",
            "wsgi.url_scheme": "https",
            "CONTENT_LENGTH": str(len(body)),
            "CONTENT_TYPE": "application/x-www-form-urlencoded",
            "wsgi.input": io.BytesIO(body),
        }
        setup_testing_defaults(environ)
        environ["SCRIPT_NAME"] = "/"
        environ["PATH_INFO"] = "/addressbook/"
        environ["HTTP_HOST"] = "example.com"
        environ["wsgi.url_scheme"] = "https"
        captured = {}

        def sr(status, headers):
            captured["s"] = status
            captured["h"] = dict(headers)

        b"".join(self.app(environ, sr))
        self.assertEqual(captured["s"], "303 See Other")
        location = captured["h"]["Location"]
        self.assertTrue(
            location.startswith("https://example.com/addressbook/"),
            f"unexpected Location header: {location!r}",
        )
        # No "//" anywhere in the path component
        self.assertNotIn("//", location.split("://", 1)[1])

    def test_untyped_collection_under_contacts_home_promoted(self):
        # Regression: a collection created without an explicit type
        # (e.g. plain MKCOL) that lives directly under the addressbook
        # home set must still surface the contacts UI when visited in
        # a browser.
        backend = SingleUserFilesystemBackend(self.tempdir)
        backend.create_principal("/u", create_defaults=False)
        backend.create_collection("/u/contacts/book")
        resource = backend.get_resource("/u/contacts/book")
        self.assertIsInstance(resource, AddressbookCollection)

    def test_post_without_action_falls_through(self):
        # An RFC 5995 add-member POST with a real vCard body still works:
        # the form parser only acts on application/x-www-form-urlencoded.
        environ = {
            "PATH_INFO": "/addressbook/",
            "REQUEST_METHOD": "POST",
            "QUERY_STRING": "",
            "HTTP_ACCEPT": "*/*",
            "CONTENT_TYPE": "text/vcard",
            "CONTENT_LENGTH": str(len(EXAMPLE_VCARD)),
            "wsgi.input": io.BytesIO(EXAMPLE_VCARD),
        }
        setup_testing_defaults(environ)
        captured = {}

        def start_response(status, headers):
            captured["status"] = status
            captured["headers"] = headers

        b"".join(self.app(environ, start_response))
        # Should not be 400 — the add-member path returned 200/201 with
        # a Location header.
        self.assertIn(captured["status"], ("200 OK", "201 Created"))

    def test_addressbook_shows_inline_photo(self):
        card = (
            b"BEGIN:VCARD\r\nVERSION:3.0\r\nUID:p1\r\nFN:Photo Person\r\n"
            b"PHOTO;ENCODING=b;TYPE=JPEG:/9j/4AAQSkZJRg==\r\n"
            b"END:VCARD\r\n"
        )
        self.store.import_one("p1.vcf", "text/vcard", [card])
        _status, _headers, body = self._request("GET", "/addressbook/")
        text = body.decode("utf-8")
        self.assertIn('class="photo"', text)
        self.assertIn("data:image/jpeg;base64,/9j/4AAQSkZJRg==", text)

    def test_addressbook_shows_categories(self):
        card = (
            b"BEGIN:VCARD\r\nVERSION:3.0\r\nUID:c1\r\nFN:Tagged Person\r\n"
            b"CATEGORIES:Friends,Work\r\nEND:VCARD\r\n"
        )
        self.store.import_one("c1.vcf", "text/vcard", [card])
        _status, _headers, body = self._request("GET", "/addressbook/")
        text = body.decode("utf-8")
        self.assertIn('class="cat"', text)
        self.assertIn("Friends", text)
        self.assertIn("Work", text)

    def test_addressbook_groups_alphabetically(self):
        alice = (
            b"BEGIN:VCARD\r\nVERSION:3.0\r\nUID:a1\r\nFN:Alice Adams\r\nEND:VCARD\r\n"
        )
        bob = b"BEGIN:VCARD\r\nVERSION:3.0\r\nUID:b1\r\nFN:Bob Brown\r\nEND:VCARD\r\n"
        self.store.import_one("a1.vcf", "text/vcard", [alice])
        self.store.import_one("b1.vcf", "text/vcard", [bob])
        _status, _headers, body = self._request("GET", "/addressbook/")
        text = body.decode("utf-8")
        self.assertIn('class="section"', text)
        self.assertIn(">A<", text)
        self.assertIn(">B<", text)
        self.assertLess(text.index(">A<"), text.index(">B<"))
        self.assertLess(text.index("Alice Adams"), text.index("Bob Brown"))

    def test_addressbook_search_box_present(self):
        _status, _headers, body = self._request("GET", "/addressbook/")
        self.assertIn('name="q"', body.decode("utf-8"))

    def test_addressbook_search_filters(self):
        alice = (
            b"BEGIN:VCARD\r\nVERSION:3.0\r\nUID:a1\r\nFN:Alice Adams\r\n"
            b"EMAIL:alice@example.org\r\nEND:VCARD\r\n"
        )
        bob = b"BEGIN:VCARD\r\nVERSION:3.0\r\nUID:b1\r\nFN:Bob Brown\r\nEND:VCARD\r\n"
        self.store.import_one("a1.vcf", "text/vcard", [alice])
        self.store.import_one("b1.vcf", "text/vcard", [bob])
        _status, _headers, body = self._request(
            "GET", "/addressbook/", extra_environ={"QUERY_STRING": "q=alice"}
        )
        text = body.decode("utf-8")
        self.assertIn("Alice Adams", text)
        self.assertNotIn("Bob Brown", text)

    def test_addressbook_search_no_match(self):
        self.store.import_one("alice.vcf", "text/vcard", [EXAMPLE_VCARD])
        _status, _headers, body = self._request(
            "GET", "/addressbook/", extra_environ={"QUERY_STRING": "q=zzzznomatch"}
        )
        self.assertIn("No contacts match", body.decode("utf-8"))


class AddressbookExportImportTests(unittest.TestCase):
    """Export and import of vCards via the addressbook webview."""

    def setUp(self):
        super().setUp()
        self.tempdir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tempdir)
        store_path = os.path.join(self.tempdir, "addressbook")
        self.store = TreeGitStore.create(store_path)
        self.store.set_type(STORE_TYPE_ADDRESSBOOK)
        self.store.load_extra_file_handler(VCardFile)
        self.backend = SingleUserFilesystemBackend(self.tempdir)
        self.collection = AddressbookCollection(self.backend, "addressbook", self.store)
        self.app = XandikosApp(self.backend, "user")

    def _request(self, method, path, body=b"", query=""):
        environ = {
            "PATH_INFO": path,
            "REQUEST_METHOD": method,
            "QUERY_STRING": query,
            "HTTP_ACCEPT": "text/html",
        }
        if body:
            environ["wsgi.input"] = io.BytesIO(body)
            environ["CONTENT_LENGTH"] = str(len(body))
            environ["CONTENT_TYPE"] = "application/x-www-form-urlencoded"
        setup_testing_defaults(environ)
        environ["QUERY_STRING"] = query
        captured = {}

        def sr(status, headers):
            captured["s"] = status
            captured["h"] = dict(headers)

        out = b"".join(self.app(environ, sr))
        return captured["s"], captured["h"], out

    def test_addressbook_export(self):
        self.store.import_one("alice.vcf", "text/vcard", [EXAMPLE_VCARD])
        status, headers, body = self._request("GET", "/addressbook/", query="export")
        self.assertEqual(status, "200 OK")
        self.assertEqual(headers["Content-Type"], "text/vcard; charset=utf-8")
        card = vobject.readOne(body.decode("utf-8"))
        self.assertEqual(card.fn.value, "Alice Example")

    def test_addressbook_import(self):
        vcf = (
            "BEGIN:VCARD\r\nVERSION:3.0\r\nUID:imp-1\r\n"
            "FN:Imported Person\r\nEMAIL:imp@example.org\r\nEND:VCARD\r\n"
        )
        body = urlencode({"action": "import", "data": vcf}).encode("utf-8")
        status, _headers, _ = self._request("POST", "/addressbook/", body=body)
        self.assertEqual(status, "303 See Other")
        names = [n for n, _ct, _e in self.store.iter_with_etag()]
        self.assertEqual(names, ["imp-1.vcf"])
        card = vobject.readOne(
            b"".join(self.store.get_file("imp-1.vcf", "text/vcard").content).decode(
                "utf-8"
            )
        )
        self.assertEqual(card.fn.value, "Imported Person")


if __name__ == "__main__":
    unittest.main()
