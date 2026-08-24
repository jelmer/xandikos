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

"""Tests for WebDAV-Push (xandikos.webdav_push)."""

import asyncio
import base64
import os
import tempfile
import unittest
from xml.etree import ElementTree as ET

from xandikos import webdav, webdav_push


PUSH_NS = webdav_push.NAMESPACE


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _parse(body: bytes):
    """Parse a push-register body the way the WebDAV dispatcher would."""
    return ET.fromstring(body)


def _push_register_xml(
    *,
    push_resource: str = "https://push.example/endpoint",
    p256dh: bytes = b"\x04" + b"\x01" * 64,
    auth_secret: bytes = b"\x02" * 16,
    triggers_xml: str = (
        '<content-update xmlns="https://bitfire.at/webdav-push">'
        '<depth xmlns="DAV:">1</depth>'
        "</content-update>"
    ),
    expires: str | None = None,
) -> bytes:
    expires_el = f"<expires>{expires}</expires>" if expires else ""
    return (
        f'<?xml version="1.0" encoding="utf-8"?>'
        f'<push-register xmlns="{PUSH_NS}" xmlns:D="DAV:">'
        f"<subscription>"
        f"<web-push-subscription>"
        f"<push-resource>{push_resource}</push-resource>"
        f"<content-encoding>aes128gcm</content-encoding>"
        f'<subscription-public-key type="p256dh">{_b64url(p256dh)}'
        f"</subscription-public-key>"
        f"<auth-secret>{_b64url(auth_secret)}</auth-secret>"
        f"</web-push-subscription>"
        f"</subscription>"
        f"<trigger>{triggers_xml}</trigger>"
        f"{expires_el}"
        f"</push-register>"
    ).encode()


class ParsePushRegisterTests(unittest.TestCase):
    def test_minimal(self):
        sub, expires = webdav_push.parse_push_register(_parse(_push_register_xml()))
        self.assertEqual(sub.push_resource, "https://push.example/endpoint")
        self.assertEqual(sub.content_encoding, "aes128gcm")
        self.assertEqual(sub.p256dh, b"\x04" + b"\x01" * 64)
        self.assertEqual(sub.auth_secret, b"\x02" * 16)
        self.assertEqual(len(sub.triggers), 1)
        self.assertEqual(sub.triggers[0].kind, "content-update")
        self.assertEqual(sub.triggers[0].depth, "1")
        self.assertIsNone(expires)

    def test_property_update_with_props(self):
        triggers = (
            '<property-update xmlns="https://bitfire.at/webdav-push">'
            '<depth xmlns="DAV:">0</depth>'
            '<prop xmlns="DAV:"><displayname/></prop>'
            "</property-update>"
        )
        sub, _ = webdav_push.parse_push_register(
            _parse(_push_register_xml(triggers_xml=triggers))
        )
        self.assertEqual(len(sub.triggers), 1)
        self.assertEqual(sub.triggers[0].kind, "property-update")
        self.assertEqual(sub.triggers[0].props, ["{DAV:}displayname"])

    def test_invalid_root(self):
        root = ET.fromstring(b'<?xml version="1.0"?><other xmlns="urn:x"/>')
        with self.assertRaises(webdav_push.InvalidSubscriptionError):
            webdav_push.parse_push_register(root)

    def test_missing_subscription(self):
        root = ET.fromstring(
            b'<?xml version="1.0"?>'
            b'<push-register xmlns="https://bitfire.at/webdav-push">'
            b"<trigger/>"
            b"</push-register>"
        )
        with self.assertRaises(webdav_push.InvalidSubscriptionError):
            webdav_push.parse_push_register(root)

    def test_unsupported_content_encoding(self):
        body = _push_register_xml().replace(
            b"<content-encoding>aes128gcm</content-encoding>",
            b"<content-encoding>aesgcm</content-encoding>",
        )
        with self.assertRaises(webdav_push.InvalidSubscriptionError):
            webdav_push.parse_push_register(_parse(body))

    def test_no_supported_trigger(self):
        triggers = '<unknown-trigger xmlns="https://bitfire.at/webdav-push"/>'
        with self.assertRaises(webdav_push.NoSupportedTriggerError) as cm:
            webdav_push.parse_push_register(
                _parse(_push_register_xml(triggers_xml=triggers))
            )
        self.assertIn(
            "{https://bitfire.at/webdav-push}unknown-trigger", str(cm.exception)
        )

    def test_no_trigger_element(self):
        body = _push_register_xml(triggers_xml="")
        # Strip the empty <trigger> wrapper so no trigger element is present.
        body = body.replace(b"<trigger></trigger>", b"")
        with self.assertRaises(webdav_push.NoSupportedTriggerError) as cm:
            webdav_push.parse_push_register(_parse(body))
        self.assertEqual("no supported trigger requested", str(cm.exception))

    def test_expires_parsed(self):
        sub, expires = webdav_push.parse_push_register(
            _parse(_push_register_xml(expires="Wed, 20 Dec 2023 10:03:31 GMT"))
        )
        self.assertEqual(sub.expires, expires)
        self.assertEqual(expires.year, 2023)
        self.assertEqual(expires.month, 12)
        self.assertEqual(expires.day, 20)


class PushSubscriptionStoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.store = webdav_push.PushSubscriptionStore(self.tmp.name)

    def _make_sub(self, sub_id: str = "sub-1", push_resource: str = "https://x/y"):
        return webdav_push.Subscription(
            id=sub_id,
            push_resource=push_resource,
            content_encoding="aes128gcm",
            p256dh=b"\x04" + b"\x00" * 64,
            auth_secret=b"\x00" * 16,
            expires=None,
            triggers=[webdav_push.Trigger(kind="content-update", depth="1")],
        )

    def test_topic_is_stable(self):
        first = self.store.get_topic()
        again = self.store.get_topic()
        self.assertEqual(first, again)
        # Re-opening the store reads back the same topic.
        reopened = webdav_push.PushSubscriptionStore(self.tmp.name)
        self.assertEqual(first, reopened.get_topic())

    def test_put_list_remove_roundtrip(self):
        sub = self._make_sub()
        self.store.put(sub)
        listed = self.store.list()
        self.assertEqual(len(listed), 1)
        self.assertEqual(listed[0].push_resource, sub.push_resource)
        self.assertEqual(listed[0].p256dh, sub.p256dh)
        self.assertEqual(self.store.remove(sub.id), True)
        self.assertEqual(self.store.list(), [])

    def test_remove_unknown_returns_false(self):
        self.assertEqual(self.store.remove("nope"), False)

    def test_find_by_push_resource(self):
        sub = self._make_sub(push_resource="https://push/a")
        self.store.put(sub)
        self.assertEqual(self.store.find_by_push_resource("https://push/a").id, sub.id)
        self.assertIsNone(self.store.find_by_push_resource("https://push/b"))


class PushMessageXmlTests(unittest.TestCase):
    def test_content_update(self):
        body = webdav_push.build_push_message_xml("topic-123", sync_token="urn:x:42")
        root = ET.fromstring(body)
        self.assertEqual(root.tag, "{%s}push-message" % PUSH_NS)
        self.assertEqual(root.find("{%s}topic" % PUSH_NS).text, "topic-123")
        self.assertEqual(
            root.find("{%s}content-update/{DAV:}sync-token" % PUSH_NS).text,
            "urn:x:42",
        )

    def test_property_update(self):
        body = webdav_push.build_push_message_xml(
            "topic-123",
            sync_token=None,
            changed_properties=["{DAV:}displayname"],
        )
        root = ET.fromstring(body)
        prop = root.find("{%s}property-update/{DAV:}prop" % PUSH_NS)
        self.assertIsNotNone(prop)
        self.assertEqual([child.tag for child in prop], ["{DAV:}displayname"])


class HandlePushRegisterTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        import shutil

        from xandikos.store import STORE_TYPE_CALENDAR
        from xandikos.store.git import TreeGitStore
        from xandikos.web import SingleUserFilesystemBackend

        self.tempdir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tempdir)
        store_path = os.path.join(self.tempdir, "cal")
        s = TreeGitStore.create(store_path)
        s.set_type(STORE_TYPE_CALENDAR)
        self.backend = SingleUserFilesystemBackend(self.tempdir)
        self.collection = self.backend.get_resource("/cal")
        self.store = webdav_push.PushSubscriptionStore(store_path)

    def _fake_request(self):
        class _R:
            url = "http://example.com/cal/"
            path = "/cal/"
            headers: dict = {}

        return _R()

    def _headers_dict(self, response):
        return {k: v for (k, v) in response.headers}

    async def _dispatch(self, body: bytes):
        return await webdav_push._handle_push_register(
            self._fake_request(),
            {"SCRIPT_NAME": ""},
            "/cal/",
            _parse(body),
            self.collection,
        )

    async def test_register_creates_subscription(self):
        response = await self._dispatch(_push_register_xml())
        self.assertEqual(response.status, 201)
        headers = self._headers_dict(response)
        self.assertIn("Location", headers)
        self.assertIn("Expires", headers)
        listed = self.store.list()
        self.assertEqual(len(listed), 1)
        self.assertEqual(
            headers["Location"],
            "/" + webdav_push.SUBSCRIPTION_ROUTE + "/" + listed[0].id,
        )

    async def test_register_same_resource_updates(self):
        first = await self._dispatch(_push_register_xml())
        second = await self._dispatch(_push_register_xml())
        self.assertEqual(first.status, 201)
        self.assertEqual(second.status, 200)
        self.assertEqual(
            self._headers_dict(first)["Location"],
            self._headers_dict(second)["Location"],
        )
        self.assertEqual(len(self.store.list()), 1)

    async def test_register_invalid_returns_403(self):
        # An XML body whose root is push-register but contents are bogus.
        root = ET.fromstring(
            b'<push-register xmlns="https://bitfire.at/webdav-push">'
            b"<nonsense/></push-register>"
        )
        response = await webdav_push._handle_push_register(
            self._fake_request(),
            {"SCRIPT_NAME": ""},
            "/cal/",
            root,
            self.collection,
        )
        self.assertEqual(response.status, 403)


class PushDontNotifyTests(unittest.TestCase):
    def test_star_suppresses_everything(self):
        token = webdav_push.set_push_dont_notify("*")
        try:
            self.assertTrue(webdav_push._is_suppressed("any-id"))
        finally:
            webdav_push.reset_push_dont_notify(token)
        self.assertFalse(webdav_push._is_suppressed("any-id"))

    def test_id_list_suppresses_matching(self):
        token = webdav_push.set_push_dont_notify("abc, def")
        try:
            self.assertTrue(webdav_push._is_suppressed("abc"))
            self.assertTrue(webdav_push._is_suppressed("def"))
            self.assertFalse(webdav_push._is_suppressed("ghi"))
        finally:
            webdav_push.reset_push_dont_notify(token)

    def test_url_form_resolves_to_trailing_id(self):
        token = webdav_push.set_push_dont_notify(
            '"http://x/.well-known/webdav-push/abc"'
        )
        try:
            self.assertTrue(webdav_push._is_suppressed("abc"))
        finally:
            webdav_push.reset_push_dont_notify(token)


class NotifySubscribersTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def _put_sub(self, store):
        store.put(
            webdav_push.Subscription(
                id="abc",
                push_resource="https://push/x",
                content_encoding="aes128gcm",
                p256dh=b"\x04" + b"\x00" * 64,
                auth_secret=b"\x00" * 16,
                expires=None,
                triggers=[webdav_push.Trigger(kind="content-update")],
            )
        )

    async def test_no_subscribers_no_delivery(self):
        store = webdav_push.PushSubscriptionStore(self.tmp.name)
        sent: list = []

        async def fake_deliver(keystore, sub, payload):
            sent.append((sub.id, payload))
            return 200

        original = webdav_push.deliver_push_message
        webdav_push.deliver_push_message = fake_deliver
        try:
            await webdav_push.notify_subscribers(store, keystore=None, sync_token="t1")
        finally:
            webdav_push.deliver_push_message = original
        self.assertEqual(sent, [])

    async def test_dont_notify_skips(self):
        store = webdav_push.PushSubscriptionStore(self.tmp.name)
        self._put_sub(store)
        sent: list = []

        async def fake_deliver(keystore, sub, payload):
            sent.append(sub.id)
            return 200

        original = webdav_push.deliver_push_message
        webdav_push.deliver_push_message = fake_deliver
        token = webdav_push.set_push_dont_notify("*")
        try:
            await webdav_push.notify_subscribers(store, keystore=None, sync_token="t1")
        finally:
            webdav_push.deliver_push_message = original
            webdav_push.reset_push_dont_notify(token)
        self.assertEqual(sent, [])

    async def test_410_evicts_subscription(self):
        store = webdav_push.PushSubscriptionStore(self.tmp.name)
        self._put_sub(store)

        async def fake_deliver(keystore, sub, payload):
            return 410

        original = webdav_push.deliver_push_message
        webdav_push.deliver_push_message = fake_deliver
        try:
            await webdav_push.notify_subscribers(store, keystore=None, sync_token="t1")
        finally:
            webdav_push.deliver_push_message = original
        self.assertEqual(store.list(), [])


class DavFeatureTests(unittest.TestCase):
    def test_extra_features_propagate(self):
        class FakeBackend:
            pass

        app = webdav.WebDAVApp(FakeBackend())
        app.extra_features.append(webdav_push.FEATURE)
        self.assertIn(webdav_push.FEATURE, app._get_dav_features(None))

    def test_default_features_omit_push(self):
        class FakeBackend:
            pass

        app = webdav.WebDAVApp(FakeBackend())
        self.assertNotIn(webdav_push.FEATURE, app._get_dav_features(None))


class SubscriptionIndexTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.index = webdav_push.SubscriptionIndex(self.tmp.name)

    def test_round_trip(self):
        self.index.add("abc", "/calendars/foo")
        self.assertEqual(self.index.get("abc"), "/calendars/foo")
        # Reopened index sees the same data.
        reopened = webdav_push.SubscriptionIndex(self.tmp.name)
        self.assertEqual(reopened.get("abc"), "/calendars/foo")

    def test_unknown_returns_none(self):
        self.assertIsNone(self.index.get("nope"))

    def test_remove(self):
        self.index.add("abc", "/calendars/foo")
        self.index.remove("abc")
        self.assertIsNone(self.index.get("abc"))

    def test_remove_unknown_is_noop(self):
        self.index.remove("nope")  # must not raise


class DeleteSubscriptionTests(unittest.IsolatedAsyncioTestCase):
    """End-to-end tests for ``webdav_push.delete_subscription``."""

    def setUp(self):
        import shutil

        from xandikos.store import STORE_TYPE_CALENDAR
        from xandikos.store.git import TreeGitStore
        from xandikos.web import SingleUserFilesystemBackend, XandikosApp

        self.tempdir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tempdir)
        store_path = os.path.join(self.tempdir, "cal")
        s = TreeGitStore.create(store_path)
        s.set_type(STORE_TYPE_CALENDAR)
        self.backend = SingleUserFilesystemBackend(self.tempdir)
        self.collection = self.backend.get_resource("/cal")
        self.sub_store = webdav_push.PushSubscriptionStore(store_path)

        self.state_dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.state_dir)

        # Build a single-user XandikosApp without a real keystore so
        # check_access is the open default and delete_subscription
        # can rely on app.backend.
        self.app = XandikosApp.__new__(XandikosApp)
        self.app.backend = self.backend
        self.app.extra_features = []

        # Wire the global subscription index ourselves (cf. install()).
        self._prev_index = webdav_push._index
        webdav_push._index = webdav_push.SubscriptionIndex(self.state_dir)
        self.addCleanup(self._restore_index)

    def _restore_index(self):
        webdav_push._index = self._prev_index

    def _seed(self, sub_id: str = "abc"):
        self.sub_store.put(
            webdav_push.Subscription(
                id=sub_id,
                push_resource="https://push/" + sub_id,
                content_encoding="aes128gcm",
                p256dh=b"\x04" + b"\x00" * 64,
                auth_secret=b"\x00" * 16,
                expires=None,
                triggers=[webdav_push.Trigger(kind="content-update")],
            )
        )
        webdav_push._index.add(sub_id, "/cal")

    async def test_removes_existing(self):
        self._seed("abc")
        status, _reason = await webdav_push.delete_subscription(self.app, {}, "abc")
        self.assertEqual(status, 204)
        self.assertEqual(self.sub_store.list(), [])
        self.assertIsNone(webdav_push._index.get("abc"))

    async def test_unknown_id_returns_404(self):
        status, _ = await webdav_push.delete_subscription(self.app, {}, "nope")
        self.assertEqual(status, 404)

    async def test_collection_gone_cleans_index_and_returns_404(self):
        self._seed("abc")
        import shutil

        shutil.rmtree(os.path.join(self.tempdir, "cal"))
        self.backend._open_store.cache_clear()
        status, _ = await webdav_push.delete_subscription(self.app, {}, "abc")
        self.assertEqual(status, 404)
        self.assertIsNone(webdav_push._index.get("abc"))

    async def test_forbidden_propagates(self):
        self._seed("abc")
        from xandikos import webdav

        def deny(environ, path, method):
            raise webdav.ForbiddenError("nope")

        self.app.check_access = deny
        status, _ = await webdav_push.delete_subscription(self.app, {}, "abc")
        self.assertEqual(status, 403)
        # Subscription still present — auth denial doesn't delete.
        self.assertEqual(len(self.sub_store.list()), 1)


class _FakeKeystore:
    """Stand-in for VapidKeystore that needs no py_vapid dependency."""

    public_key_b64 = "BfakePublicKey"
    subject = "mailto:test@example.invalid"
    vapid = None


def _make_calendar(tempdir: str, name: str = "cal"):
    """Build a real CalendarCollection on disk under ``tempdir``."""
    from xandikos.store import STORE_TYPE_CALENDAR
    from xandikos.store.git import TreeGitStore
    from xandikos.web import SingleUserFilesystemBackend

    store_path = os.path.join(tempdir, name)
    s = TreeGitStore.create(store_path)
    s.set_type(STORE_TYPE_CALENDAR)
    backend = SingleUserFilesystemBackend(tempdir)
    return backend, backend.get_resource("/" + name), store_path


class _InstallationFixture:
    """Helper that installs webdav_push and tears it down cleanly.

    Class-level state on ``StoreBasedCollection._change_listeners`` and
    ``webdav_push._index`` must be restored after each test or listeners
    leak across the suite.
    """

    def __init__(self, testcase, state_dir):
        from xandikos.web import StoreBasedCollection

        self.testcase = testcase
        self.state_dir = state_dir
        self._prev_listeners = list(StoreBasedCollection._change_listeners)
        self._prev_index = webdav_push._index
        self.StoreBasedCollection = StoreBasedCollection

    def install(self, app, keystore=None):
        webdav_push.install(app, keystore or _FakeKeystore(), state_dir=self.state_dir)

    def restore(self):
        self.StoreBasedCollection._change_listeners[:] = self._prev_listeners
        webdav_push._index = self._prev_index


async def _drain_pending_tasks():
    """Yield to the event loop until every other task has finished."""
    # Give scheduled tasks (listener-fired coroutines) a chance to run.
    # One yield is enough when the work doesn't itself await anything; we
    # do two for headroom.
    await asyncio.sleep(0)
    await asyncio.sleep(0)


class PropertyTests(unittest.IsolatedAsyncioTestCase):
    """Cover the three discovery properties."""

    def setUp(self):
        import shutil

        self.tempdir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tempdir)
        self.backend, self.cal, self.store_path = _make_calendar(self.tempdir)

    async def test_transports_emits_vapid_key(self):
        prop = webdav_push.TransportsProperty("BfakePublicKey")
        el = ET.Element(prop.name)
        await prop.get_value("/cal", self.cal, el, {})
        web_push = el.find("{%s}web-push" % PUSH_NS)
        self.assertIsNotNone(web_push)
        vapid = web_push.find("{%s}vapid-public-key" % PUSH_NS)
        self.assertIsNotNone(vapid)
        self.assertEqual(vapid.get("type"), "p256ecdsa")
        self.assertEqual(vapid.text, "BfakePublicKey")

    async def test_transports_without_key_emits_empty_web_push(self):
        prop = webdav_push.TransportsProperty(None)
        el = ET.Element(prop.name)
        await prop.get_value("/cal", self.cal, el, {})
        # Still advertises web-push, just without a VAPID key.
        self.assertIsNotNone(el.find("{%s}web-push" % PUSH_NS))
        self.assertIsNone(
            el.find("{%s}web-push/{%s}vapid-public-key" % (PUSH_NS, PUSH_NS))
        )

    def test_supported_on_only_calendar_addressbook(self):
        prop = webdav_push.TopicProperty()
        self.assertTrue(prop.supported_on(self.cal))

        class NotAPushResource:
            resource_types = ["{DAV:}collection"]

        self.assertFalse(prop.supported_on(NotAPushResource()))

    async def test_topic_is_stable_across_invocations(self):
        prop = webdav_push.TopicProperty()
        el1 = ET.Element(prop.name)
        await prop.get_value("/cal", self.cal, el1, {})
        el2 = ET.Element(prop.name)
        await prop.get_value("/cal", self.cal, el2, {})
        self.assertTrue(el1.text)
        self.assertEqual(el1.text, el2.text)

    async def test_supported_triggers_advertises_content_and_property(self):
        prop = webdav_push.SupportedTriggersProperty()
        el = ET.Element(prop.name)
        await prop.get_value("/cal", self.cal, el, {})
        cu = el.find("{%s}content-update" % PUSH_NS)
        pu = el.find("{%s}property-update" % PUSH_NS)
        self.assertIsNotNone(cu)
        self.assertEqual(cu.find("{DAV:}depth").text, "1")
        self.assertIsNotNone(pu)
        self.assertEqual(pu.find("{DAV:}depth").text, "0")


class HandlePushRegisterIndexTests(unittest.IsolatedAsyncioTestCase):
    """The push-register handler must add an entry to the subscription index."""

    def setUp(self):
        import shutil

        self.tempdir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tempdir)
        self.backend, self.collection, self.store_path = _make_calendar(self.tempdir)
        self.sub_store = webdav_push.PushSubscriptionStore(self.store_path)

        self.state_dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.state_dir)

        self._prev_index = webdav_push._index
        webdav_push._index = webdav_push.SubscriptionIndex(self.state_dir)
        self.addCleanup(self._restore_index)

    def _restore_index(self):
        webdav_push._index = self._prev_index

    def _request(self):
        class _R:
            url = "http://example.com/cal/"
            path = "/cal/"
            headers: dict = {}

        return _R()

    async def test_subscribe_populates_index(self):
        response = await webdav_push._handle_push_register(
            self._request(),
            {"SCRIPT_NAME": ""},
            "/cal",
            _parse(_push_register_xml()),
            self.collection,
        )
        self.assertEqual(response.status, 201)
        [sub] = self.sub_store.list()
        self.assertEqual(webdav_push._index.get(sub.id), "/cal")

    async def test_resubscribe_keeps_same_id_and_index_entry(self):
        first = await webdav_push._handle_push_register(
            self._request(),
            {"SCRIPT_NAME": ""},
            "/cal",
            _parse(_push_register_xml()),
            self.collection,
        )
        second = await webdav_push._handle_push_register(
            self._request(),
            {"SCRIPT_NAME": ""},
            "/cal",
            _parse(_push_register_xml()),
            self.collection,
        )
        self.assertEqual(first.status, 201)
        self.assertEqual(second.status, 200)
        [sub] = self.sub_store.list()
        # Same id retained → same index entry.
        self.assertEqual(webdav_push._index.get(sub.id), "/cal")
        self.assertEqual(len(webdav_push._index._load()), 1)


class HandlePushRegisterPushNotAvailableTests(unittest.IsolatedAsyncioTestCase):
    """A push-register against a non-Calendar/Addressbook resource → 403."""

    async def test_non_push_collection_returns_push_not_available(self):
        # A non-store-based, non-push resource: ``RootPage`` or anything
        # ``_push_store_for`` rejects.
        class NotPushCapable:
            resource_types: list[str] = []

        class _R:
            url = "http://example.com/foo"
            path = "/foo"
            headers: dict = {}

        response = await webdav_push._handle_push_register(
            _R(),
            {"SCRIPT_NAME": ""},
            "/foo",
            _parse(_push_register_xml()),
            NotPushCapable(),
        )
        self.assertEqual(response.status, 403)
        body = b"".join(response.body)
        # The 403 body is a {DAV:}error containing the documented
        # {NS}push-not-available marker (see _send_simple_dav_error).
        root = ET.fromstring(body)
        self.assertEqual(root.tag, "{DAV:}error")
        self.assertIsNotNone(
            root.find("{%s}push-not-available" % PUSH_NS),
            f"missing push-not-available; got {ET.tostring(root)!r}",
        )


class NotifySubscribersFilteringTests(unittest.IsolatedAsyncioTestCase):
    """Property-update trigger filtering by ``<DAV:prop>`` list."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.store = webdav_push.PushSubscriptionStore(self.tmp.name)

    def _add_sub(self, sub_id: str, *, prop_names: list[str]):
        self.store.put(
            webdav_push.Subscription(
                id=sub_id,
                push_resource=f"https://push/{sub_id}",
                content_encoding="aes128gcm",
                p256dh=b"\x04" + b"\x00" * 64,
                auth_secret=b"\x00" * 16,
                expires=None,
                triggers=[
                    webdav_push.Trigger(
                        kind="property-update", depth="0", props=prop_names
                    )
                ],
            )
        )

    async def _capture_deliveries(self, **kwargs):
        sent: list = []

        async def fake_deliver(keystore, sub, payload):
            sent.append(sub.id)
            return 200

        original = webdav_push.deliver_push_message
        webdav_push.deliver_push_message = fake_deliver
        try:
            await webdav_push.notify_subscribers(self.store, keystore=None, **kwargs)
        finally:
            webdav_push.deliver_push_message = original
        return sent

    async def test_property_subscriber_with_matching_prop_receives(self):
        self._add_sub("matching", prop_names=["{DAV:}displayname"])
        sent = await self._capture_deliveries(changed_properties=["{DAV:}displayname"])
        self.assertEqual(sent, ["matching"])

    async def test_property_subscriber_with_non_matching_prop_skipped(self):
        self._add_sub("matching", prop_names=["{DAV:}displayname"])
        sent = await self._capture_deliveries(changed_properties=["{DAV:}owner"])
        self.assertEqual(sent, [])

    async def test_empty_prop_list_subscribes_to_any_property_change(self):
        # The spec: omitting <prop> means "any property change".
        self._add_sub("any-prop", prop_names=[])
        sent = await self._capture_deliveries(changed_properties=["{DAV:}owner"])
        self.assertEqual(sent, ["any-prop"])

    async def test_expired_subscription_is_evicted_not_delivered(self):
        from datetime import datetime, timedelta, timezone

        self.store.put(
            webdav_push.Subscription(
                id="expired",
                push_resource="https://push/expired",
                content_encoding="aes128gcm",
                p256dh=b"\x04" + b"\x00" * 64,
                auth_secret=b"\x00" * 16,
                expires=datetime.now(timezone.utc) - timedelta(hours=1),
                triggers=[webdav_push.Trigger(kind="content-update")],
            )
        )
        sent = await self._capture_deliveries(sync_token="t1")
        self.assertEqual(sent, [])
        # Expired subscription must be removed from the store.
        self.assertEqual(self.store.list(), [])


class ChangeListenerIntegrationTests(unittest.IsolatedAsyncioTestCase):
    """End-to-end change-listener wiring.

    ``install()`` must register a listener that fires notifications on
    create / update / delete and property changes.
    """

    def setUp(self):
        import shutil

        from xandikos.web import XandikosApp

        self.tempdir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tempdir)
        self.backend, self.collection, self.store_path = _make_calendar(self.tempdir)
        self.sub_store = webdav_push.PushSubscriptionStore(self.store_path)
        # Seed one subscription so the listener has someone to notify.
        self.sub_store.put(
            webdav_push.Subscription(
                id="abc",
                push_resource="https://push/abc",
                content_encoding="aes128gcm",
                p256dh=b"\x04" + b"\x00" * 64,
                auth_secret=b"\x00" * 16,
                expires=None,
                triggers=[
                    webdav_push.Trigger(kind="content-update", depth="1"),
                    webdav_push.Trigger(kind="property-update", depth="0"),
                ],
            )
        )

        self.state_dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.state_dir)

        # Bare-bones app — install() registers properties/handlers/listener.
        self.app = XandikosApp.__new__(XandikosApp)
        self.app.backend = self.backend
        self.app.properties = {}
        self.app.reporters = {}
        self.app.methods = {}
        self.app.post_handlers = {}
        self.app.extra_features = []
        self.app.strict = True

        self.fixture = _InstallationFixture(self, self.state_dir)
        self.fixture.install(self.app)
        self.addCleanup(self.fixture.restore)

        # Replace notify_subscribers to record calls instead of delivering.
        self._calls: list = []

        async def recorder(
            store, *, keystore, sync_token=None, changed_properties=None
        ):
            self._calls.append(
                {
                    "store_path": store._dir,
                    "sync_token": sync_token,
                    "changed_properties": (
                        list(changed_properties)
                        if changed_properties is not None
                        else None
                    ),
                }
            )

        self._prev_notify = webdav_push.notify_subscribers
        webdav_push.notify_subscribers = recorder
        self.addCleanup(self._restore_notify)

    def _restore_notify(self):
        webdav_push.notify_subscribers = self._prev_notify

    async def test_create_member_fires_content_notification(self):
        await self.collection.create_member(
            "evt.ics",
            [
                b"BEGIN:VCALENDAR\r\nVERSION:2.0\r\nPRODID:-//x//EN\r\n"
                b"BEGIN:VEVENT\r\nUID:1\r\nDTSTAMP:20250101T000000Z\r\n"
                b"DTSTART:20250101T000000Z\r\nSUMMARY:t\r\nEND:VEVENT\r\n"
                b"END:VCALENDAR\r\n"
            ],
            "text/calendar",
        )
        await _drain_pending_tasks()
        self.assertEqual(len(self._calls), 1)
        call = self._calls[0]
        self.assertEqual(call["store_path"], self.store_path)
        self.assertIsNotNone(call["sync_token"])
        self.assertIsNone(call["changed_properties"])

    async def test_set_displayname_fires_property_notification(self):
        self.collection.set_displayname("New name")
        await _drain_pending_tasks()
        self.assertEqual(len(self._calls), 1)
        self.assertIsNone(self._calls[0]["sync_token"])
        self.assertEqual(self._calls[0]["changed_properties"], ["{DAV:}displayname"])

    async def test_listener_skips_non_push_collections(self):
        from xandikos.store import STORE_TYPE_OTHER
        from xandikos.store.git import TreeGitStore
        from xandikos.web import SingleUserFilesystemBackend

        other_dir = tempfile.mkdtemp()
        self.addCleanup(__import__("shutil").rmtree, other_dir)
        store_path = os.path.join(other_dir, "misc")
        s = TreeGitStore.create(store_path)
        s.set_type(STORE_TYPE_OTHER)
        backend = SingleUserFilesystemBackend(other_dir)
        misc = backend.get_resource("/misc")
        misc.set_displayname("ignored")
        await _drain_pending_tasks()
        self.assertEqual(self._calls, [])


class SubscriptionDeleteHandlerTests(unittest.IsolatedAsyncioTestCase):
    """The aiohttp handler closure built by ``_make_subscription_delete_handler``.

    The handler extracts the sub-id from match_info, forwards
    ``X-Remote-User`` into the environ, and translates
    ``delete_subscription``'s ``(status, reason)`` tuple into an
    aiohttp response.
    """

    def setUp(self):
        import shutil

        from xandikos.store import STORE_TYPE_CALENDAR
        from xandikos.store.git import TreeGitStore
        from xandikos.web import SingleUserFilesystemBackend, XandikosApp

        self.tempdir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tempdir)
        store_path = os.path.join(self.tempdir, "cal")
        s = TreeGitStore.create(store_path)
        s.set_type(STORE_TYPE_CALENDAR)
        self.backend = SingleUserFilesystemBackend(self.tempdir)
        self.collection = self.backend.get_resource("/cal")
        self.sub_store = webdav_push.PushSubscriptionStore(store_path)

        self.state_dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.state_dir)

        # Bare-bones app — no XandikosApp.__init__, just attribute hookup.
        self.app = XandikosApp.__new__(XandikosApp)
        self.app.backend = self.backend
        self.app.extra_features = [webdav_push.FEATURE]

        self._prev_index = webdav_push._index
        webdav_push._index = webdav_push.SubscriptionIndex(self.state_dir)
        self.addCleanup(self._restore_index)

    def _restore_index(self):
        webdav_push._index = self._prev_index

    def _seed(self, sub_id: str = "abc"):
        self.sub_store.put(
            webdav_push.Subscription(
                id=sub_id,
                push_resource=f"https://push/{sub_id}",
                content_encoding="aes128gcm",
                p256dh=b"\x04" + b"\x00" * 64,
                auth_secret=b"\x00" * 16,
                expires=None,
                triggers=[webdav_push.Trigger(kind="content-update")],
            )
        )
        webdav_push._index.add(sub_id, "/cal")

    async def _invoke(self, sub_id: str, headers: dict | None = None):
        from xandikos.web import _make_subscription_delete_handler

        class _Request:
            def __init__(self, sub_id, headers):
                self.match_info = {"sub_id": sub_id}
                self.headers = headers or {}

        handler = _make_subscription_delete_handler(self.app)
        return await handler(_Request(sub_id, headers))

    async def test_happy_path_returns_204(self):
        self._seed("abc")
        response = await self._invoke("abc")
        self.assertEqual(response.status, 204)
        self.assertEqual(self.sub_store.list(), [])

    async def test_unknown_id_returns_404(self):
        response = await self._invoke("missing")
        self.assertEqual(response.status, 404)

    async def test_x_remote_user_propagated_to_check_access(self):
        # Multi-user-style: deny when REMOTE_USER doesn't match. The
        # handler only forwards REMOTE_USER into environ when the backend
        # supports set_principal (matches WebDAVApp._handle_request).
        from xandikos.webdav import ForbiddenError

        self._seed("abc")
        principals_seen: list = []
        self.backend.set_principal = principals_seen.append

        seen: dict = {}

        def check_access(environ, path, method):
            seen["environ"] = environ
            seen["path"] = path
            seen["method"] = method
            if environ.get("REMOTE_USER") != "alice":
                raise ForbiddenError("not your subscription")

        self.app.check_access = check_access

        # Bob is forbidden.
        bob = await self._invoke("abc", headers={"X-Remote-User": "bob"})
        self.assertEqual(bob.status, 403)
        self.assertEqual(seen["method"], "DELETE")
        self.assertEqual(seen["path"], "/cal")
        self.assertEqual(seen["environ"]["REMOTE_USER"], "bob")
        self.assertEqual(principals_seen[-1], "bob")
        # Subscription still present after denied DELETE.
        self.assertEqual(len(self.sub_store.list()), 1)

        # Alice (the owner) succeeds.
        alice = await self._invoke("abc", headers={"X-Remote-User": "alice"})
        self.assertEqual(alice.status, 204)
        self.assertEqual(principals_seen[-1], "alice")


if __name__ == "__main__":
    unittest.main()
