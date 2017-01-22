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

"""Calendar synchronisation.

See https://tools.ietf.org/html/rfc6578
"""

from dystros import webdav


class SyncCollectionReporter(webdav.DAVReporter):
    """sync-collection reporter implementation.

    See https://tools.ietf.org/html/rfc6578, section 3.2.
    """

    name = '{DAV:}sync-collection'

    def report(self, request_body, resource_by_href, properties, href,
               resource, depth):
        sync_token = None
        sync_level = None
        limit = None
        requested = None
        for el in request_body:
            if el.tag == 'sync-token':
                sync_token = el.text
            elif el.tag == 'sync-level':
                sync_level = el.text
            elif el.tag == 'limit':
                limit = el.text
            elif el.tag == 'prop':
                requested = list(el)
        assert sync_level in ("1", "infinite")
        # TODO(jelmer): Implement sync_level infinite
        # TODO(jelmer): Support limit

        new_token = resource.get_ctag()
        try:
            diff_iter = resource.iter_differences_since(old_token, new_token)
        except NotImplementedError:
            return DAVStatus(
                href, '403 Forbidden',
                error=ET.Element('{DAV:}sync-traversal-supported'))

        for (name, old_resource, new_resource) in diff_iter:
            propstat = []
            if new_resource is None:
                for prop in requested:
                    propstat.append(
                        webdav.PropStatus('404 Not Found', None, ET.Element(prop.tag)))
            else:
                for prop in requested:
                    if old_resource is not None:
                        old_propstat = resolve_property(old_resource, properties, prop.tag)
                    else:
                        old_propstat = None
                    new_propstat = resolve_property(new_resource, properties, prop.tag)
                    if old_propstat != new_propstat:
                        propstat.append(new_propstat)
            yield webdav.DAVstatus(
                urllib.parse.urljoin(href+'/', name), propstat=propstat,
                sync_token=new_token)
