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

"""Calendar synchronisation.

See https://tools.ietf.org/html/rfc6578
"""

import itertools
import urllib.parse

from xandikos import webdav

ET = webdav.ET


FEATURE = "sync-collection"


class SyncToken:
    """A sync token wrapper."""

    def __init__(self, token) -> None:
        self.token = token

    def aselement(self):
        ret = ET.Element("{DAV:}sync-token")
        ret.text = self.token
        return ret


class InvalidToken(Exception):
    """Requested token is invalid."""

    def __init__(self, token) -> None:
        self.token = token


class SyncCollectionReporter(webdav.Reporter):
    """sync-collection reporter implementation.

    See https://tools.ietf.org/html/rfc6578, section 3.2.
    """

    name = "{DAV:}sync-collection"

    @webdav.multistatus  # noqa: C901
    async def report(  # noqa: C901
        self,
        environ,
        request_body,
        resources_by_hrefs,
        properties,
        href,
        resource,
        depth,
        strict,
    ):
        old_token = None
        sync_level = None
        limit = None
        requested = None
        for el in request_body:
            if el.tag == "{DAV:}sync-token":
                old_token = el.text
            elif el.tag == "{DAV:}sync-level":
                sync_level = el.text
            elif el.tag == "{DAV:}limit":
                limit = el
            elif el.tag == "{DAV:}prop":
                requested = list(el)
            else:
                webdav.nonfatal_bad_request(f"unknown tag {el.tag}", strict)
        # TODO(jelmer): Implement sync_level infinite
        if sync_level not in ("1",):
            raise webdav.BadRequestError(f"sync level {sync_level!r} unsupported")

        new_token = resource.get_sync_token()
        try:
            try:
                diff_iter = resource.iter_differences_since(old_token, new_token)
            except NotImplementedError:
                yield webdav.Status(
                    href,
                    "403 Forbidden",
                    error=ET.Element("{DAV:}sync-traversal-supported"),
                )
                return

            if limit is not None:
                try:
                    [nresults_el] = list(limit)
                except ValueError:
                    webdav.nonfatal_bad_request(
                        "Invalid number of subelements in limit", strict
                    )
                else:
                    try:
                        nresults = int(nresults_el.text)
                    except ValueError:
                        webdav.nonfatal_bad_request("nresults not a number", strict)
                    else:
                        diff_iter = itertools.islice(diff_iter, nresults)

            for name, old_resource, new_resource in diff_iter:
                subhref = urllib.parse.urljoin(webdav.ensure_trailing_slash(href), name)
                if new_resource is None:
                    yield webdav.Status(subhref, status="404 Not Found")
                else:
                    propstat = []
                    for prop in requested:
                        if old_resource is not None:
                            old_propstat = await webdav.get_property_from_element(
                                href, old_resource, properties, environ, prop
                            )
                        else:
                            old_propstat = None
                        new_propstat = await webdav.get_property_from_element(
                            href, new_resource, properties, environ, prop
                        )
                        if old_propstat != new_propstat:
                            propstat.append(new_propstat)
                    yield webdav.Status(subhref, propstat=propstat)
        except InvalidToken as exc:
            raise webdav.PreconditionFailure(
                "{DAV:}valid-sync-token", f"Requested sync token {exc.token} is invalid"
            ) from exc
        yield SyncToken(new_token)


class SyncTokenProperty(webdav.Property):
    """sync-token property.

    See https://tools.ietf.org/html/rfc6578, section 4
    """

    name = "{DAV:}sync-token"
    resource_type = webdav.COLLECTION_RESOURCE_TYPE
    in_allprops = False
    live = True

    async def get_value(self, href, resource, el, environ):
        el.text = resource.get_sync_token()
