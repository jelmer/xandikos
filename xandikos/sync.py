# Xandikos
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

"""Calendar synchronisation.

See https://tools.ietf.org/html/rfc6578
"""

import urllib.parse
from xml.etree import ElementTree as ET

from xandikos import webdav


class SyncToken(object):
    """A sync token wrapper."""

    def __init__(self, token):
        self.token = token

    def aselement(self):
        ret = ET.Element('{DAV:}sync-token')
        ret.text = self.token
        return ret


class SyncCollectionReporter(webdav.Reporter):
    """sync-collection reporter implementation.

    See https://tools.ietf.org/html/rfc6578, section 3.2.
    """

    name = '{DAV:}sync-collection'

    @webdav.multistatus
    def report(self, environ, request_body, resources_by_hrefs, properties, href,
               resource, depth):
        old_token = None
        sync_level = None
        limit = None
        requested = None
        for el in request_body:
            if el.tag == '{DAV:}sync-token':
                old_token = el.text
            elif el.tag == '{DAV:}sync-level':
                sync_level = el.text
            elif el.tag == '{DAV:}limit':
                limit = el.text
            elif el.tag == '{DAV:}prop':
                requested = list(el)
            else:
                assert 'unknown tag %s', el.tag
        assert sync_level in ("1", "infinite"), "sync level is %r" % sync_level
        # TODO(jelmer): Implement sync_level infinite
        # TODO(jelmer): Support limit

        new_token = resource.get_sync_token()
        try:
            diff_iter = resource.iter_differences_since(old_token, new_token)
        except NotImplementedError:
            return Status(
                href, '403 Forbidden',
                error=ET.Element('{DAV:}sync-traversal-supported'))

        for (name, old_resource, new_resource) in diff_iter:
            propstat = []
            if new_resource is None:
                for prop in requested:
                    propstat.append(
                        webdav.PropStatus('404 Not Found', None,
                            ET.Element(prop.tag)))
            else:
                for prop in requested:
                    if old_resource is not None:
                        old_propstat = webdav.get_property(
                            old_resource, properties, prop.tag)
                    else:
                        old_propstat = None
                    new_propstat = webdav.get_property(
                            new_resource, properties, prop.tag)
                    if old_propstat != new_propstat:
                        propstat.append(new_propstat)
            yield webdav.Status(
                urllib.parse.urljoin(href+'/', name), propstat=propstat)
        # TODO(jelmer): This is a bit of a hack..
        yield SyncToken(new_token)


class SyncTokenProperty(webdav.Property):
    """sync-token property.

    See https://tools.ietf.org/html/rfc6578, section 4
    """

    name = '{DAV:}sync-token'
    protected = True
    in_allprops = False
    live = True

    def get_value(self, resource, el):
        el.text = resource.get_sync_token()
