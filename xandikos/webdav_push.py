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

"""WebDAV-Push support.

Implements draft-bitfire-webdav-push-00 so CalDAV/CardDAV clients can
subscribe to Web Push notifications instead of polling.

The runtime dependencies (``pywebpush`` and ``py_vapid``) are optional;
``VapidKeystore`` and ``deliver_push_message`` raise ``RuntimeError`` if
they are not installed. The surrounding machinery (properties, register
handler, hooks) is only wired up via :func:`install`, so xandikos
deployments without push support stay unaffected.
"""

from __future__ import annotations

import asyncio
import base64
import binascii
import contextvars
import dataclasses
import email.utils
import json
import logging
import os
import secrets
import tempfile
import urllib.parse
from collections.abc import Iterable
from datetime import datetime, timezone
from typing import Any

from . import webdav


logger = logging.getLogger(__name__)

NAMESPACE = "https://bitfire.at/webdav-push"
FEATURE = "webdav-push"

CONTENT_TYPE_PUSH_REGISTER = "application/xml"
# Server-private path under the route prefix where push-subscription
# registration URLs live (``${route_prefix}.subscriptions/<sub-id>``).
# Not a WebDAV resource — served by a dedicated aiohttp handler.
SUBSCRIPTION_ROUTE = ".subscriptions"
SUBSCRIPTIONS_FILE = "push-subscriptions.json"
SUBSCRIPTION_INDEX_FILE = "push-subscription-index.json"

# Server-wide subscription index, set by :func:`install`. ``None``
# means push isn't enabled — the POST handler and the DELETE route
# won't be in play in that case, so anything that touches this should
# already be gated.
_index: SubscriptionIndex | None = None

# Default expiry when the client does not request one. 30 days matches
# DAVx5's default refresh cadence.
DEFAULT_EXPIRY_SECONDS = 30 * 24 * 3600

# Header that lets a client suppress notifications for the request that
# caused them (RFC-style draft, section "Suppressing notifications").
PUSH_DONT_NOTIFY_HEADER = "Push-Dont-Notify"

# Carries the parsed Push-Dont-Notify value (set of subscription ids, or
# the literal string "*") through the request so notification hooks can
# honour it without changing every hook signature.
_PUSH_DONT_NOTIFY: contextvars.ContextVar[set[str] | str | None] = (
    contextvars.ContextVar("xandikos_push_dont_notify", default=None)
)


def set_push_dont_notify(value: str | None) -> contextvars.Token:
    """Set the Push-Dont-Notify context value for the current request.

    Returns the contextvars token so callers can reset it on the way
    out.
    """
    if value is None:
        return _PUSH_DONT_NOTIFY.set(None)
    value = value.strip()
    if value == "*":
        return _PUSH_DONT_NOTIFY.set("*")
    ids: set[str] = set()
    for part in value.split(","):
        part = part.strip()
        if not part:
            continue
        # Quoted URL form: "<url>" or "url". Strip surrounding quotes.
        if part.startswith('"') and part.endswith('"'):
            part = part[1:-1]
        # Spec allows either the registration URL itself or a server-issued
        # id; we accept both forms and resolve by trailing path segment.
        ids.add(part.rsplit("/", 1)[-1])
    return _PUSH_DONT_NOTIFY.set(ids)


def reset_push_dont_notify(token: contextvars.Token) -> None:
    _PUSH_DONT_NOTIFY.reset(token)


def _is_suppressed(sub_id: str) -> bool:
    value = _PUSH_DONT_NOTIFY.get()
    if value is None:
        return False
    if value == "*":
        return True
    assert isinstance(value, set)
    return sub_id in value


# Trigger kinds advertised in supported-triggers and accepted in
# push-register.
TRIGGER_CONTENT_UPDATE = "content-update"
TRIGGER_PROPERTY_UPDATE = "property-update"


def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64url_decode(data: str) -> bytes:
    data = data.strip()
    padding = "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(data + padding)


@dataclasses.dataclass
class Trigger:
    kind: str  # TRIGGER_CONTENT_UPDATE or TRIGGER_PROPERTY_UPDATE
    depth: str = "0"  # "0", "1", or "infinity"
    # Property names (e.g. "{DAV:}displayname") this trigger filters on;
    # empty means any property change.
    props: list[str] = dataclasses.field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {"kind": self.kind, "depth": self.depth, "props": list(self.props)}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Trigger:
        return cls(
            kind=data["kind"],
            depth=data.get("depth", "0"),
            props=list(data.get("props", [])),
        )


@dataclasses.dataclass
class Subscription:
    id: str
    push_resource: str
    content_encoding: str
    p256dh: bytes
    auth_secret: bytes
    expires: datetime | None
    triggers: list[Trigger]

    def is_expired(self, now: datetime | None = None) -> bool:
        if self.expires is None:
            return False
        if now is None:
            now = datetime.now(timezone.utc)
        return self.expires <= now

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "push_resource": self.push_resource,
            "content_encoding": self.content_encoding,
            "p256dh": _b64url_encode(self.p256dh),
            "auth_secret": _b64url_encode(self.auth_secret),
            "expires": self.expires.isoformat() if self.expires else None,
            "triggers": [t.to_dict() for t in self.triggers],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Subscription:
        expires = data.get("expires")
        return cls(
            id=data["id"],
            push_resource=data["push_resource"],
            content_encoding=data["content_encoding"],
            p256dh=_b64url_decode(data["p256dh"]),
            auth_secret=_b64url_decode(data["auth_secret"]),
            expires=datetime.fromisoformat(expires) if expires else None,
            triggers=[Trigger.from_dict(t) for t in data["triggers"]],
        )


class InvalidSubscriptionError(Exception):
    """Subscription XML failed validation."""


class NoSupportedTriggerError(Exception):
    """No supported trigger was requested."""


class PushSubscriptionStore:
    """Persist push subscriptions for one collection.

    Backed by a JSON file inside the collection directory. The file
    deliberately lives outside any tracked git tree (TreeGitStore only
    commits files it explicitly stages; BareGitStore has no working
    tree).
    """

    def __init__(self, collection_dir: str) -> None:
        self._dir = collection_dir
        self._path = os.path.join(collection_dir, SUBSCRIPTIONS_FILE)

    def _load(self) -> dict[str, Any]:
        try:
            with open(self._path) as f:
                return json.load(f)
        except FileNotFoundError:
            return {"topic": None, "subscriptions": {}}

    def _save(self, data: dict[str, Any]) -> None:
        os.makedirs(self._dir, exist_ok=True)
        # Atomic write: tempfile in same dir + rename.
        fd, tmp = tempfile.mkstemp(
            prefix=".push-subscriptions.", suffix=".tmp", dir=self._dir
        )
        try:
            with os.fdopen(fd, "w") as f:
                json.dump(data, f, indent=2, sort_keys=True)
            os.chmod(tmp, 0o600)
            os.replace(tmp, self._path)
        except BaseException:
            try:
                os.unlink(tmp)
            except FileNotFoundError:
                pass
            raise

    def get_topic(self) -> str:
        """Return the stable per-collection topic id, generating it once."""
        data = self._load()
        topic = data.get("topic")
        if topic:
            return topic
        topic = secrets.token_urlsafe(16)
        data["topic"] = topic
        data.setdefault("subscriptions", {})
        self._save(data)
        return topic

    def list(self) -> list[Subscription]:
        data = self._load()
        return [
            Subscription.from_dict(s) for s in data.get("subscriptions", {}).values()
        ]

    def get(self, sub_id: str) -> Subscription | None:
        data = self._load()
        raw = data.get("subscriptions", {}).get(sub_id)
        if raw is None:
            return None
        return Subscription.from_dict(raw)

    def find_by_push_resource(self, push_resource: str) -> Subscription | None:
        for sub in self.list():
            if sub.push_resource == push_resource:
                return sub
        return None

    def put(self, sub: Subscription) -> None:
        data = self._load()
        data.setdefault("subscriptions", {})[sub.id] = sub.to_dict()
        self._save(data)

    def remove(self, sub_id: str) -> bool:
        data = self._load()
        subs = data.get("subscriptions", {})
        if sub_id not in subs:
            return False
        del subs[sub_id]
        self._save(data)
        return True


class SubscriptionIndex:
    """Server-wide mapping of subscription id to owning collection path.

    Lookup accelerator for the DELETE handler: registration URLs carry
    only the sub-id, but the authoritative subscription record lives in
    the owning collection's :class:`PushSubscriptionStore`. The
    per-collection store is canonical — the index is rebuildable from
    it.
    """

    def __init__(self, state_dir: str) -> None:
        self._dir = state_dir
        self._path = os.path.join(state_dir, SUBSCRIPTION_INDEX_FILE)

    def _load(self) -> dict[str, str]:
        try:
            with open(self._path) as f:
                return json.load(f)
        except FileNotFoundError:
            return {}

    def _save(self, data: dict[str, str]) -> None:
        os.makedirs(self._dir, exist_ok=True)
        fd, tmp = tempfile.mkstemp(
            prefix=".push-subscription-index.", suffix=".tmp", dir=self._dir
        )
        try:
            with os.fdopen(fd, "w") as f:
                json.dump(data, f, indent=2, sort_keys=True)
            os.chmod(tmp, 0o600)
            os.replace(tmp, self._path)
        except BaseException:
            try:
                os.unlink(tmp)
            except FileNotFoundError:
                pass
            raise

    def add(self, sub_id: str, collection_path: str) -> None:
        data = self._load()
        data[sub_id] = collection_path
        self._save(data)

    def remove(self, sub_id: str) -> None:
        data = self._load()
        if sub_id not in data:
            return
        del data[sub_id]
        self._save(data)

    def get(self, sub_id: str) -> str | None:
        return self._load().get(sub_id)


def parse_push_register(root) -> tuple[Subscription, datetime | None]:
    """Parse a ``{NS}push-register`` element into a Subscription.

    ``root`` must already be parsed (the WebDAV POST dispatcher does the
    parse, then routes by root tag). Returns the parsed Subscription
    (with a fresh id) plus the requested expiry, or ``None`` if not
    specified. Raises InvalidSubscriptionError or
    NoSupportedTriggerError on validation failures.
    """
    if root.tag != "{%s}push-register" % NAMESPACE:
        raise InvalidSubscriptionError(f"unexpected root element {root.tag!r}")

    sub_el = root.find("{%s}subscription" % NAMESPACE)
    if sub_el is None:
        raise InvalidSubscriptionError("missing <subscription>")
    wp = sub_el.find("{%s}web-push-subscription" % NAMESPACE)
    if wp is None:
        raise InvalidSubscriptionError("only web-push subscriptions are supported")

    push_resource_el = wp.find("{%s}push-resource" % NAMESPACE)
    push_resource_text = (
        (push_resource_el.text or "").strip() if push_resource_el is not None else ""
    )
    if not push_resource_text:
        raise InvalidSubscriptionError("missing push-resource")
    push_resource = push_resource_text

    ce_el = wp.find("{%s}content-encoding" % NAMESPACE)
    content_encoding = (
        (ce_el.text or "aes128gcm").strip() if ce_el is not None else "aes128gcm"
    )
    if content_encoding != "aes128gcm":
        raise InvalidSubscriptionError(
            f"unsupported content-encoding {content_encoding!r}"
        )

    pk_el = wp.find("{%s}subscription-public-key" % NAMESPACE)
    pk_text = (pk_el.text or "").strip() if pk_el is not None else ""
    if not pk_text:
        raise InvalidSubscriptionError("missing subscription-public-key")
    assert pk_el is not None
    if pk_el.get("type", "p256dh") != "p256dh":
        raise InvalidSubscriptionError("subscription-public-key must be p256dh")
    try:
        p256dh = _b64url_decode(pk_text)
    except (ValueError, binascii.Error) as exc:
        raise InvalidSubscriptionError(
            f"subscription-public-key is not valid base64url: {exc}"
        ) from exc

    auth_el = wp.find("{%s}auth-secret" % NAMESPACE)
    auth_text = (auth_el.text or "").strip() if auth_el is not None else ""
    if not auth_text:
        raise InvalidSubscriptionError("missing auth-secret")
    try:
        auth_secret = _b64url_decode(auth_text)
    except (ValueError, binascii.Error) as exc:
        raise InvalidSubscriptionError(
            f"auth-secret is not valid base64url: {exc}"
        ) from exc

    triggers, unsupported = _parse_triggers(root)
    if not triggers:
        if unsupported:
            raise NoSupportedTriggerError(
                "no supported trigger requested; unsupported: " + ", ".join(unsupported)
            )
        raise NoSupportedTriggerError("no supported trigger requested")

    expires_el = root.find("{%s}expires" % NAMESPACE)
    expires: datetime | None = None
    expires_text = (expires_el.text or "").strip() if expires_el is not None else ""
    if expires_text:
        try:
            expires = email.utils.parsedate_to_datetime(expires_text)
        except (TypeError, ValueError) as exc:
            raise InvalidSubscriptionError(f"invalid expires value: {exc}") from exc

    sub = Subscription(
        id=secrets.token_urlsafe(16),
        push_resource=push_resource,
        content_encoding=content_encoding,
        p256dh=p256dh,
        auth_secret=auth_secret,
        expires=expires,
        triggers=triggers,
    )
    return sub, expires


def _parse_triggers(root) -> tuple[list[Trigger], list[str]]:
    """Parse trigger children.

    Returns ``(supported, unsupported)``. ``unsupported`` holds the tag
    names of trigger children we don't understand, so the caller can
    surface them in the error response.
    """
    triggers: list[Trigger] = []
    unsupported: list[str] = []
    trigger_el = root.find("{%s}trigger" % NAMESPACE)
    if trigger_el is None:
        return triggers, unsupported
    for child in trigger_el:
        if child.tag == "{%s}content-update" % NAMESPACE:
            depth_el = child.find("{DAV:}depth")
            depth = (depth_el.text or "0").strip() if depth_el is not None else "0"
            triggers.append(Trigger(kind=TRIGGER_CONTENT_UPDATE, depth=depth))
        elif child.tag == "{%s}property-update" % NAMESPACE:
            depth_el = child.find("{DAV:}depth")
            depth = (depth_el.text or "0").strip() if depth_el is not None else "0"
            prop_el = child.find("{DAV:}prop")
            props: list[str] = []
            if prop_el is not None:
                for p in prop_el:
                    props.append(p.tag)
            triggers.append(
                Trigger(kind=TRIGGER_PROPERTY_UPDATE, depth=depth, props=props)
            )
        else:
            unsupported.append(child.tag)
    return triggers, unsupported


def build_push_message_xml(
    topic: str,
    *,
    sync_token: str | None,
    changed_properties: Iterable[str] | None = None,
) -> bytes:
    """Build a <push-message> XML body for delivery to a Web Push service."""
    root = webdav.ET.Element("{%s}push-message" % NAMESPACE)
    webdav.ET.SubElement(root, "{%s}topic" % NAMESPACE).text = topic
    if sync_token is not None:
        cu = webdav.ET.SubElement(root, "{%s}content-update" % NAMESPACE)
        webdav.ET.SubElement(cu, "{DAV:}sync-token").text = sync_token
    if changed_properties is not None:
        pu = webdav.ET.SubElement(root, "{%s}property-update" % NAMESPACE)
        prop = webdav.ET.SubElement(pu, "{DAV:}prop")
        for name in changed_properties:
            webdav.ET.SubElement(prop, name)
    return webdav.ET.tostring(root, encoding="utf-8", xml_declaration=True)


class TransportsProperty(webdav.Property):
    """{NS}transports — advertise Web Push parameters.

    Emits a single <web-push> child with the server's VAPID public key.
    """

    name = "{%s}transports" % NAMESPACE
    in_allprops = False
    live = True

    def __init__(self, vapid_public_key_b64: str | None) -> None:
        self._vapid_public_key_b64 = vapid_public_key_b64

    def supported_on(self, resource):
        return _is_push_collection(resource)

    async def get_value(self, href, resource, el, environ):
        wp = webdav.ET.SubElement(el, "{%s}web-push" % NAMESPACE)
        if self._vapid_public_key_b64 is not None:
            vapid_el = webdav.ET.SubElement(wp, "{%s}vapid-public-key" % NAMESPACE)
            vapid_el.set("type", "p256ecdsa")
            vapid_el.text = self._vapid_public_key_b64


class TopicProperty(webdav.Property):
    """{NS}topic — stable per-collection identifier."""

    name = "{%s}topic" % NAMESPACE
    in_allprops = False
    live = True

    def supported_on(self, resource):
        return _is_push_collection(resource)

    async def get_value(self, href, resource, el, environ):
        store = _push_store_for(resource)
        if store is None:
            raise KeyError(self.name)
        el.text = store.get_topic()


class SupportedTriggersProperty(webdav.Property):
    """{NS}supported-triggers — advertise content/property update support."""

    name = "{%s}supported-triggers" % NAMESPACE
    in_allprops = False
    live = True

    def supported_on(self, resource):
        return _is_push_collection(resource)

    async def get_value(self, href, resource, el, environ):
        cu = webdav.ET.SubElement(el, "{%s}content-update" % NAMESPACE)
        webdav.ET.SubElement(cu, "{DAV:}depth").text = "1"
        pu = webdav.ET.SubElement(el, "{%s}property-update" % NAMESPACE)
        webdav.ET.SubElement(pu, "{DAV:}depth").text = "0"


def _is_push_collection(resource) -> bool:
    """Return True if resource is a calendar or addressbook collection."""
    from . import caldav, carddav

    return isinstance(resource, (caldav.Calendar, carddav.Addressbook))


def _push_store_for(resource) -> PushSubscriptionStore | None:
    """Return a PushSubscriptionStore for resource, or None.

    The resource must be a Calendar/Addressbook backed by an on-disk
    store. Other collection types (e.g. virtual subscription collections,
    schedule inbox/outbox) return None.
    """
    from .web import StoreBasedCollection

    if not isinstance(resource, StoreBasedCollection):
        return None
    return PushSubscriptionStore(resource.store.path)


def build_subscription_location(script_name: str, sub_id: str) -> str:
    """Construct the Location header URL for a registered subscription.

    The URL is rooted at the app's ``script_name`` (route prefix) and
    sits in a server-private namespace — it is not a WebDAV resource,
    it's served by a dedicated aiohttp DELETE handler.
    """
    base = script_name.rstrip("/")
    return urllib.parse.quote(
        base + "/" + SUBSCRIPTION_ROUTE + "/" + sub_id, safe="/:%"
    )


async def _handle_push_register(
    request, environ, collection_path: str, root, collection
) -> webdav.Response:
    """POST handler for ``{NS}push-register`` — registered via :func:`install`.

    The WebDAV POST dispatcher (``PostMethod`` in :mod:`xandikos.webdav`)
    parses the XML once and routes by root element tag, calling this
    with the parsed root and the addressed collection.
    """
    store = _push_store_for(collection)
    if store is None:
        return webdav._send_simple_dav_error(
            request,
            "403 Forbidden",
            error=webdav.ET.Element("{%s}push-not-available" % NAMESPACE),
            description="WebDAV-Push is not available on this resource.",
        )
    try:
        sub, _requested_expiry = parse_push_register(root)
    except InvalidSubscriptionError as exc:
        logger.debug("push-register rejected: %s", exc)
        return webdav._send_simple_dav_error(
            request,
            "403 Forbidden",
            error=webdav.ET.Element("{%s}invalid-subscription" % NAMESPACE),
            description=str(exc),
        )
    except NoSupportedTriggerError as exc:
        logger.debug("push-register rejected: %s", exc)
        return webdav._send_simple_dav_error(
            request,
            "403 Forbidden",
            error=webdav.ET.Element("{%s}no-supported-trigger" % NAMESPACE),
            description=str(exc),
        )

    # Update if a subscription for this push-resource already exists.
    existing = store.find_by_push_resource(sub.push_resource)
    if existing is not None:
        sub.id = existing.id

    if sub.expires is None:
        sub.expires = (
            datetime.now(timezone.utc).replace(microsecond=0) + _expires_offset()
        )

    store.put(sub)
    if _index is not None:
        _index.add(sub.id, collection_path)

    script_name = environ.get("SCRIPT_NAME", "")
    location = build_subscription_location(script_name, sub.id)
    expires_header = email.utils.format_datetime(sub.expires, usegmt=True)
    headers = {"Location": location, "Expires": expires_header}
    status = 200 if existing is not None else 201
    reason = "OK" if existing is not None else "Created"
    return webdav.Response(status=status, reason=reason, headers=headers)


def _expires_offset():
    from datetime import timedelta

    return timedelta(seconds=DEFAULT_EXPIRY_SECONDS)


async def delete_subscription(app, environ: dict, sub_id: str) -> tuple[int, str]:
    """Remove the subscription with id ``sub_id``.

    Authorizes the caller against the owning collection via
    ``app.check_access(environ, collection_path, "DELETE")``. Returns
    ``(status_code, reason)`` so the aiohttp handler can map directly
    to an HTTP response.

    Status codes:
      * 204 — removed.
      * 404 — unknown sub-id, owning collection gone, or not push-capable.
      * 403 — authenticated user not authorized for the owning collection.
      * 401 — authentication required but not provided.
    """
    if _index is None:
        # Push isn't installed; shouldn't be reachable because the
        # route gate matches, but be safe.
        return (404, "Not Found")
    collection_path = _index.get(sub_id)
    if collection_path is None:
        return (404, "Not Found")
    collection = app.backend.get_resource(collection_path)
    if collection is None:
        # Owning collection vanished; clean up the stale index entry.
        _index.remove(sub_id)
        return (404, "Not Found")
    try:
        app.check_access(environ, collection_path, "DELETE")
    except webdav.UnauthorizedError:
        return (401, "Unauthorized")
    except webdav.ForbiddenError:
        return (403, "Forbidden")
    store = _push_store_for(collection)
    if store is None:
        # Defence in depth: collection is no longer push-capable.
        _index.remove(sub_id)
        return (404, "Not Found")
    removed = store.remove(sub_id)
    _index.remove(sub_id)
    if not removed:
        return (404, "Not Found")
    return (204, "No Content")


class VapidKeystore:
    """Holds the server's long-lived VAPID keypair.

    The private key file is generated on first use with mode ``0600``.
    A ``RuntimeError`` is raised if ``py_vapid`` is not installed.
    """

    KEY_FILENAME = "private.pem"

    def __init__(
        self, vapid_dir: str, *, subject: str = "mailto:admin@xandikos.local"
    ) -> None:
        self.vapid_dir = vapid_dir
        self.key_path = os.path.join(vapid_dir, self.KEY_FILENAME)
        self.subject = subject
        self._vapid: Any | None = None
        self._public_key_b64: str | None = None

    def _load_or_create(self) -> None:
        try:
            from py_vapid import Vapid  # type: ignore[import-not-found]
        except ImportError as exc:  # pragma: no cover - exercised only without dep
            raise RuntimeError(
                "py_vapid is required for WebDAV-Push; install xandikos[webdav-push]"
            ) from exc

        if os.path.exists(self.key_path):
            v = Vapid.from_file(self.key_path)
        else:
            os.makedirs(self.vapid_dir, exist_ok=True)
            v = Vapid()
            v.generate_keys()
            v.save_key(self.key_path)
            try:
                os.chmod(self.key_path, 0o600)
            except OSError:
                logger.warning("could not chmod %s to 0600", self.key_path)
        self._vapid = v
        # Public key in uncompressed P-256 form, base64url-encoded.
        from cryptography.hazmat.primitives import serialization

        raw = v.public_key.public_bytes(
            encoding=serialization.Encoding.X962,
            format=serialization.PublicFormat.UncompressedPoint,
        )
        self._public_key_b64 = _b64url_encode(raw)

    @property
    def vapid(self) -> Any:  # noqa: ANN401 - py_vapid.Vapid is an optional dep
        if self._vapid is None:
            self._load_or_create()
        return self._vapid

    @property
    def public_key_b64(self) -> str:
        if self._public_key_b64 is None:
            self._load_or_create()
        assert self._public_key_b64 is not None
        return self._public_key_b64


async def deliver_push_message(
    keystore: VapidKeystore | None,
    subscription: Subscription,
    payload: bytes,
) -> int:
    """Encrypt and POST a push message to the subscriber.

    Returns the HTTP status code from the push service. A ``404`` or
    ``410`` means the subscription is gone and callers should evict it.
    """
    try:
        from pywebpush import webpush, WebPushException  # type: ignore[import-not-found]
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError(
            "pywebpush is required for WebDAV-Push; install xandikos[webdav-push]"
        ) from exc

    sub_info = {
        "endpoint": subscription.push_resource,
        "keys": {
            "p256dh": _b64url_encode(subscription.p256dh),
            "auth": _b64url_encode(subscription.auth_secret),
        },
    }
    vapid_claims: dict[str, Any] = {"sub": keystore.subject} if keystore else {}
    vapid_private_key = keystore.vapid if keystore else None

    def _send() -> int:
        try:
            response = webpush(
                subscription_info=sub_info,
                data=payload,
                vapid_private_key=vapid_private_key,
                vapid_claims=vapid_claims,
                content_encoding=subscription.content_encoding,
                headers={"Content-Type": "application/xml; charset=utf-8"},
            )
            return response.status_code
        except WebPushException as exc:
            if exc.response is not None:
                return exc.response.status_code
            logger.warning(
                "push delivery to %s failed: %s",
                subscription.push_resource,
                exc,
            )
            return 0

    return await asyncio.to_thread(_send)


async def notify_subscribers(
    store: PushSubscriptionStore,
    *,
    keystore: VapidKeystore | None,
    sync_token: str | None = None,
    changed_properties: Iterable[str] | None = None,
) -> None:
    """Fire push notifications for subscriptions in ``store``.

    ``sync_token`` triggers a content-update; ``changed_properties``
    triggers a property-update. Either or both may be provided. Errors
    are logged but never propagated.
    """
    try:
        subs = store.list()
    except OSError as exc:
        logger.warning("could not read subscriptions: %s", exc)
        return
    if not subs:
        return

    topic = store.get_topic()
    changed_props = list(changed_properties) if changed_properties is not None else None
    payload = build_push_message_xml(
        topic, sync_token=sync_token, changed_properties=changed_props
    )

    now = datetime.now(timezone.utc)
    for sub in subs:
        if sub.is_expired(now):
            logger.debug("evicting expired subscription %s", sub.id)
            store.remove(sub.id)
            continue
        if _is_suppressed(sub.id):
            logger.debug(
                "suppressing notification for subscription %s (Push-Dont-Notify)",
                sub.id,
            )
            continue
        # Filter property-update triggers by the changed property name.
        if changed_props is not None and sync_token is None:
            wants = False
            for t in sub.triggers:
                if t.kind != TRIGGER_PROPERTY_UPDATE:
                    continue
                if not t.props or any(p in changed_props for p in t.props):
                    wants = True
                    break
            if not wants:
                continue
        try:
            status = await deliver_push_message(keystore, sub, payload)
        except Exception as exc:  # noqa: BLE001 - notifications must never crash a request
            logger.warning("push delivery to %s raised: %s", sub.push_resource, exc)
            continue
        if status in (404, 410):
            logger.info(
                "push service returned %d for %s; removing subscription",
                status,
                sub.push_resource,
            )
            store.remove(sub.id)


def install(app, keystore: VapidKeystore, *, state_dir: str) -> None:
    """Install WebDAV-Push support into ``app``.

    Adds the feature token to the DAV header, registers the three
    discovery properties, registers the ``{NS}push-register`` POST
    handler, sets up the server-wide :class:`SubscriptionIndex` under
    ``state_dir``, and attaches a change listener that fires push
    notifications on content/property changes.

    The DELETE route for ``${SUBSCRIPTION_ROUTE}/<sub-id>`` is mounted
    by the aiohttp wiring layer (``xandikos.web``), gated on
    ``FEATURE in app.extra_features``.

    Safe to call only once per app.
    """
    global _index
    _index = SubscriptionIndex(state_dir)
    if FEATURE not in app.extra_features:
        app.extra_features.append(FEATURE)
    app.register_post_handlers(
        [("{%s}push-register" % NAMESPACE, _handle_push_register)]
    )
    app.register_properties(
        [
            TransportsProperty(keystore.public_key_b64),
            TopicProperty(),
            SupportedTriggersProperty(),
        ]
    )

    from .web import StoreBasedCollection

    def _listener(collection, kind, **details):
        if not _is_push_collection(collection):
            return None
        store = _push_store_for(collection)
        if store is None:
            return None
        if kind == "content":
            try:
                token = collection.get_sync_token()
            except NotImplementedError:
                token = None
            return notify_subscribers(store, keystore=keystore, sync_token=token)
        if kind == "property":
            return notify_subscribers(
                store,
                keystore=keystore,
                changed_properties=details.get("changed_properties"),
            )
        return None

    StoreBasedCollection.add_change_listener(_listener)
