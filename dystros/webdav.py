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

"""Abstract WebDAV server implementation..

This module contains an abstract WebDAV server. All caldav/carddav specific
functionality should live in dystros.caldav/dystros.carddav respectively.
"""

# TODO(jelmer): Add authorization support

import collections
import logging
import posixpath
import urllib.parse

from defusedxml.ElementTree import fromstring as xmlparse
# Hmm, defusedxml doesn't have XML generation functions? :(
from xml.etree import ElementTree as ET

DEFAULT_ENCODING = 'utf-8'
COLLECTION_RESOURCE_TYPE = '{DAV:}collection'
PRINCIPAL_RESOURCE_TYPE = '{DAV:}principal'


PropStatus = collections.namedtuple(
    'PropStatus', ['statuscode', 'responsedescription', 'prop'])


class NeedsMultiStatus(Exception):
    """Raised when a response needs multi-status (e.g. for propstat)."""


class DAVStatus(object):
    """A DAV response that can be used in multi-status."""

    def __init__(self, href, status, error=None, responsedescription=None,
                 propstat=None):
        self.href = href
        self.status = status
        self.error = error
        self.propstat = propstat
        self.responsedescription = responsedescription

    def __repr__(self):
        return "<%s(%r, %r, %r)>" % (
            type(self).__name__, self.href, self.status, self.responsedescription)

    def get_single_body(self, encoding):
        if self.propstat and len(self._propstat_by_status()) > 1:
            raise NeedsMultiStatus()
        if self.propstat:
            [ret] = list(self._propstat_xml())
            body = ET.tostringlist(ret, encoding)
            return body, ('text/xml; encoding="%s"' % encoding)
        else:
            body = self.responsedescription or ''
            return body, ('text/plain; encoding="%s"' % encoding)

    def _propstat_by_status(self):
        bystatus = {}
        for propstat in self.propstat:
            bystatus.setdefault(
                (propstat.statuscode, propstat.responsedescription), []).append(
                        propstat.prop)
        return bystatus

    def _propstat_xml(self):
        bystatus = self._propstat_by_status()
        for (status, rd), props in sorted(bystatus.items()):
            propstat = ET.Element('{DAV:}propstat')
            ET.SubElement(propstat,
                '{DAV:}status').text = 'HTTP/1.1 ' + status
            if rd:
                ET.SubElement(propstat,
                    '{DAV:}responsedescription').text = responsedescription
            for prop in props:
                propstat.append(prop)
            yield propstat

    def aselement(self):
        ret = ET.Element('{DAV:}response')
        ET.SubElement(ret, '{DAV:}href').text = self.href
        if self.status:
            ET.SubElement(ret, '{DAV:}status').text = 'HTTP/1.1 ' + self.status
        if self.error:
            ET.SubElement(ret, '{DAV:}error').text = self.error
        if self.responsedescription:
            ET.SubElement(ret,
                '{DAV:}responsedescription').text = self.responsedescription
        if self.propstat is not None:
            for ps in self._propstat_xml():
                ret.append(ps)
        return ret


class DAVProperty(object):
    """Handler for listing, retrieving and updating DAV Properties."""

    # Property name (e.g. '{DAV:}resourcetype')
    name = None

    # Whether to include this property in 'allprop' PROPFIND requests.
    # https://tools.ietf.org/html/rfc4918, section 14.2
    in_allprops = True

    # Whether this property is protected (i.e. read-only)
    protected = True

    def populate(self, resource, el):
        """Get property with specified name.

        :param resource: Resource for which to retrieve the property
        :param el: Element to populate
        :raise KeyError: if this property is not present
        """
        raise KeyError(self.name)


class DAVResourceTypeProperty(DAVProperty):
    """Provides {DAV:}resourcetype."""

    name = '{DAV:}resourcetype'

    protected = True

    def populate(self, resource, el):
        for rt in resource.resource_types:
            ET.SubElement(el, rt)


class DAVDisplayNameProperty(DAVProperty):
    """Provides {DAV:}displayname.

    https://tools.ietf.org/html/rfc4918, section 5.2
    """

    name = '{DAV:}displayname'

    def populate(self, resource, el):
        el.text = resource.get_displayname()

    # TODO(jelmer): allow modification of this property
    # protected = True


class DAVGetETagProperty(DAVProperty):
    """Provides {DAV:}getetag.

    https://tools.ietf.org/html/rfc4918, section 15.6
    """

    name = '{DAV:}getetag'
    protected = True

    def populate(self, resource, el):
        el.text = resource.get_etag()


class DAVGetContentTypeProperty(DAVProperty):
    """Provides {DAV:}getcontenttype.

    https://tools.ietf.org/html/rfc4918, section 13.5
    """

    name = '{DAV:}getcontenttype'
    protected = True

    def populate(self, resource, el):
        el.text = resource.get_content_type()


class DAVCurrentUserPrincipalProperty(DAVProperty):

    name = '{DAV:}current-user-principal'
    in_allprops = False

    def __init__(self, current_user_principal):
        super(DAVCurrentUserPrincipalProperty, self).__init__()
        self.current_user_principal = current_user_principal

    def populate(self, resource, el):
        """Get property with specified name.

        :param name: A property name.
        """
        ET.SubElement(el, '{DAV:}href').text = self.current_user_principal


class DAVResource(object):
    """A WebDAV resource."""

    # A list of resource type names (e.g. '{DAV:}collection')
    resource_types = []

    def get_displayname(self):
        """Get the resource display name."""
        raise KeyError(name)

    def get_content_type(self):
        """Get the content type for the resource.

        This is a mime type like text/plain
        """
        raise NotImplementedError(self.get_content_type)

    def get_etag(self):
        """Get the etag for this resource.

        Contains the ETag header value (from Section 14.19 of [RFC2616]) as it
        would be returned by a GET without accept headers.
        """
        raise NotImplementedError(self.get_etag)

    def get_body(self):
        """Get resource contents.

        :return: Iterable over bytestrings."""
        raise NotImplementedError(self.get_body)

    def set_body(self, body):
        """Set resource contents.

        :param body: Iterable over bytestrings
        """
        raise NotImplementedError(self.set_body)


class DAVCollection(DAVResource):
    """Resource for a WebDAV Collection."""

    resource_types = DAVResource.resource_types + [COLLECTION_RESOURCE_TYPE]

    def members(self):
        raise NotImplementedError(self.members)

    def delete_member(self, name, etag=None):
        """Delete a member with a specific name.

        :param name: Member name
        :param etag: Optional required etag
        :raise KeyError: when the item doesn't exist
        """
        raise NotImplementedError(self.delete_member)


def resolve_properties(href, resource, properties, requested):
    """Resolve a set of properties.

    :param href: href for the resource
    :param resource: DAVResource object
    :param properties: Dictionary of properties
    :param requested: XML {DAV:}prop element with properties to look up
    :return: Iterator over PropStatus items
    """
    for propreq in list(requested):
        propresp = ET.Element('{DAV:}prop')
        responsedescription = None
        ret = ET.SubElement(propresp, propreq.tag)
        try:
            prop = properties[propreq.tag]
        except KeyError:
            statuscode = '404 Not Found'
            logging.warning(
                'Client requested unknown property %s',
                propreq.tag)
        else:
            try:
                prop.populate(resource, ret)
            except KeyError:
                statuscode = '404 Not Found'
            else:
                statuscode = '200 OK'
        yield PropStatus(statuscode, responsedescription, propresp)


def traverse_resource(resource, depth, base_href):
    """Traverse a resource.

    :param resource: Resource to traverse from
    :param depth: Depth ("0", "1", ...)
    :param base_href: href for base resource
    :return: Iterator over (URL, Resource) tuples
    """
    me = (base_href, resource)
    if depth == "0":
        return iter([me])
    elif depth == "1":
        ret = [me]
        if COLLECTION_RESOURCE_TYPE in resource.resource_types:
            ret += [(urllib.parse.urljoin(base_href+'/', n), m)
                    for (n, m) in resource.members()]
        return iter(ret)
    raise NotImplementedError


class DAVReporter(object):
    """Implementation for DAV REPORT requests."""

    name = None

    def report(self, request_body, properties, href, resource, depth):
        """Send a report.

        :param request_body: XML Element for request body
        :param properties: Dictionary mapping names to DAVProperty instances
        :param href: Base resource href
        :param resource: Resource to start from
        :param depth: Depth ("0", "1", ...)
        :return: Iterator over DAVStatus objects
        """
        raise NotImplementedError(self.report)


class WellknownResource(DAVResource):
    """Resource for well known URLs.

    See https://tools.ietf.org/html/rfc6764
    """

    def __init__(self, server_root):
        self.server_root = server_root

    def get_body(self):
        return [self.server_root.encode(DEFAULT_ENCODING)]


class NonDAVResource(DAVResource):
    """A non-DAV resource."""

    resource_types = []


class DAVBackend(object):
    """WebDAV backend."""

    def get_resoure(self, relpath):
        raise NotImplementedError(self.get_resource)


class WebDAVApp(object):
    """A wsgi App that provides a WebDAV server.

    A concrete implementation should provide an implementation of the
    lookup_resource function that can map a path to a DAVResource object
    (returning None for nonexistant objects).
    """

    out_encoding = DEFAULT_ENCODING

    def __init__(self, backend):
        self.backend = backend
        self.properties = {}
        self.reporters = {}

    def register_properties(self, properties):
        for p in properties:
            self.properties[p.name] = p

    def register_reporters(self, reporters):
        for r in reporters:
            self.reporters[r.name] = r

    def _get_allowed_methods(self, environ):
        """List of supported methods on this endpoint."""
        return ([n[3:] for n in dir(self) if n.startswith('do_')] +
                [n[4:] for n in dir(self) if n.startswith('dav_')])

    def _send_not_found(self, environ, start_response):
        path = environ['PATH_INFO']
        start_response('404 Not Found', [])
        return [b'Path ' + path.encode(DEFAULT_ENCODING) + b' not found.']

    def _send_method_not_allowed(self, environ, start_response):
        start_response('405 Method Not Allowed', [
            ('Allow', ', '.join(self._get_allowed_methods(environ)))])
        return []

    def do_GET(self, environ, start_response):
        r = self.backend.get_resource(environ['PATH_INFO'])
        if r is None:
            return self._send_not_found(environ, start_response)
        start_response('200 OK', [])
        return r.get_body()

    def do_DELETE(self, environ, start_response):
        container_path, item_name = posixpath.split(environ['PATH_INFO'])
        r = self.backend.get_resource(container_path)
        if r is None:
            return self._send_not_found(environ, start_response)
        r.delete_member(item_name)
        start_response('200 OK', [])
        return []

    def do_PUT(self, environ, start_response):
        new_contents = self._readBody(environ)
        r = self.backend.get_resource(environ['PATH_INFO'])
        if r is None:
            return self._send_not_found(environ, start_response)
        start_response('200 OK', [])
        r.set_body([new_contents])
        return []

    def _readBody(self, environ):
        try:
            request_body_size = int(environ['CONTENT_LENGTH'])
        except KeyError:
            return environ['wsgi.input'].read()
        else:
            return environ['wsgi.input'].read(request_body_size)

    def _send_dav_responses(self, start_response, responses):
        if isinstance(responses, DAVStatus):
            try:
                (body, body_type) = responses.get_single_body(
                    self.out_encoding)
            except NeedsMultiStatus:
                responses = [responses]
            else:
                start_response(responses.status, [
                    ('Content-Type', body_type),
                    ('Content-Length', str(sum(map(len, body))))])
                return body
        ret = ET.Element('{DAV:}multistatus')
        for response in responses:
            ret.append(response.aselement())
        body_type = 'text/xml; charset="%s"' % self.out_encoding
        body = ET.tostringlist(ret, encoding=self.out_encoding)
        start_response('207 Multi-Status', [
            ('Content-Type', body_type),
            ('Content-Length', str(sum(map(len, body))))])
        return body

    def dav_REPORT(self, environ):
        # See https://tools.ietf.org/html/rfc3253, section 3.6
        r = self.backend.get_resource(environ['PATH_INFO'])
        if r is None:
            return self._send_not_found(environ, start_response)
        depth = environ.get("HTTP_DEPTH", "0")
        #TODO(jelmer): check Content-Type; should be something like
        # 'text/xml; charset="utf-8"'
        et = xmlparse(self._readBody(environ))
        return self.reporters[et.tag].report(
            et, self.properties, environ['PATH_INFO'], r, depth)

    def dav_PROPFIND(self, environ):
        base_resource = self.backend.get_resource(environ['PATH_INFO'])
        if base_resource is None:
            return self._send_not_found(environ, start_response)
        depth = environ.get("HTTP_DEPTH", "0")
        #TODO(jelmer): check Content-Type; should be something like
        # 'text/xml; charset="utf-8"'
        et = xmlparse(self._readBody(environ))
        if et.tag != '{DAV:}propfind':
            # TODO-ERROR(jelmer): What to return here?
            return DAVStatus(
                environ['PATH_INFO'], '500 Internal Error',
                'Expected propfind tag, got ' + et.tag)
        try:
            [requested] = et
        except IndexError:
            return DAVStatus(
                environ['PATH_INFO'], '500 Internal Error',
                'Received more than one element in propfind.')
        if requested.tag == '{DAV:}prop':
            ret = []
            for href, resource in traverse_resource(
                    base_resource, depth, environ['PATH_INFO']):
                propstat = resolve_properties(
                    href, resource, self.properties, requested)
                ret.append(DAVStatus(href, '200 OK', propstat=list(propstat)))
            if len(ret) == 1:
                # Allow non-207 responses
                return ret[0]
            return ret
        else:
            # TODO(jelmer): implement allprop and propname
            # TODO-ERROR(jelmer): What to return here?
            return DAVStatus(
                environ['PATH_INFO'], '500 Internal Error',
                'Expected prop tag, got ' + requested.tag)

    def __call__(self, environ, start_response):
        p = environ['PATH_INFO']
        method = environ['REQUEST_METHOD']
        dav = getattr(self, 'dav_' + method, None)
        if dav is not None:
            return self._send_dav_responses(start_response, dav(environ))
        do = getattr(self, 'do_' + method, None)
        if do is not None:
            return do(environ, start_response)
        return self._send_method_not_allowed(environ, start_response)
