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
import urllib.parse

from defusedxml.ElementTree import fromstring as xmlparse
# Hmm, defusedxml doesn't have XML generation functions? :(
from xml.etree import ElementTree as ET

DEFAULT_ENCODING = 'utf-8'
COLLECTION_RESOURCE_TYPE = '{DAV:}collection'


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


class Endpoint(object):
    """Endpoint."""

    @property
    def allowed_methods(self):
        """List of supported methods on this endpoint."""
        return [n[3:] for n in dir(self) if n.startswith('do_')]

    def __call__(self, environ, start_response):
        method = environ['REQUEST_METHOD']
        try:
            do = getattr(self, 'do_' + method)
        except AttributeError:
            start_response('405 Method Not Allowed', [
                ('Allow', ', '.join(self.allowed_methods))])
            return []
        else:
            return do(environ, start_response)


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


class DAVEndpoint(Endpoint):
    """A webdav-enabled endpoint."""

    out_encoding = DEFAULT_ENCODING

    def __init__(self, properties, resource):
        self.properties = properties
        self.resource = resource

    def _readBody(self, environ):
        try:
            request_body_size = int(environ['CONTENT_LENGTH'])
        except KeyError:
            return environ['wsgi.input'].read()
        else:
            return environ['wsgi.input'].read(request_body_size)

    @property
    def allowed_methods(self):
        """List of supported methods on this endpoint."""
        return (super(DAVEndpoint, self).allowed_methods +
                [n[4:] for n in dir(self) if n.startswith('dav_')])

    def __call__(self, environ, start_response):
        method = environ['REQUEST_METHOD']
        try:
            dav = getattr(self, 'dav_' + method)
        except AttributeError:
            return super(DAVEndpoint, self).__call__(environ, start_response)
        else:
            return self._send_dav_responses(start_response, dav(environ))

    def _send_dav_responses(self, start_response, responses):
        responses = list(responses)
        if len(responses) == 1:
            try:
                (body, body_type) = responses[0].get_single_body(
                    self.out_encoding)
            except NeedsMultiStatus:
                pass
            else:
                start_response(responses[0].status, [
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

    def _browse(self, depth, base_href):
        me = (base_href, self.resource)
        if depth == "0":
            return iter([me])
        elif depth == "1":
            ret = [me]
            if COLLECTION_RESOURCE_TYPE in self.resource.resource_types:
                ret += [(urllib.parse.urljoin(base_href+'/', n), m)
                        for (n, m) in self.resource.members()]
            return iter(ret)
        raise NotImplementedError

    def dav_PROPFIND(self, environ):
        depth = environ.get("HTTP_DEPTH", "0")
        #TODO(jelmer): check Content-Type; should be something like
        # 'text/xml; charset="utf-8"'
        et = xmlparse(self._readBody(environ))
        if et.tag != '{DAV:}propfind':
            # TODO-ERROR(jelmer): What to return here?
            yield DAVStatus(
                environ['PATH_INFO'], '500 Internal Error',
                'Expected propfind tag, got ' + et.tag)
            return
        try:
            [requested] = et
        except IndexError:
            yield DAVStatus(
                environ['PATH_INFO'], '500 Internal Error',
                'Received more than one element in propfind.')
            return
        if requested.tag == '{DAV:}prop':
            for href, resource in self._browse(depth, environ['PATH_INFO']):
                propstat = []
                for propreq in list(requested):
                    propresp = ET.Element('{DAV:}prop')
                    responsedescription = None
                    ret = ET.SubElement(propresp, propreq.tag)
                    try:
                        prop = self.properties[propreq.tag]
                        prop.populate(resource, ret)
                    except KeyError:
                        statuscode = '404 Not Found'
                    else:
                        statuscode = '200 OK'
                    propstat.append(
                        PropStatus(statuscode, responsedescription, propresp))
                yield DAVStatus(href, '200 OK', propstat=propstat)
        else:
            # TODO(jelmer): implement allprop and propname
            # TODO-ERROR(jelmer): What to return here?
            yield DAVStatus(
                environ['PATH_INFO'], '500 Internal Error',
                'Expected prop tag, got ' + requested.tag)
            return

    def do_GET(self, environ, start_response):
        start_response('200 OK', [])
        return self.resource.get_body()

    def do_PUT(self, environ, start_response):
        new_contents = self._readBody(environ)
        start_response('200 OK', [])
        self.resource.set_body([new_contents])
        return []


class DAVReporter(object):
    """Implementation for DAV REPORT requests."""


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


class DebugEndpoint(Endpoint):
    """A simple endpoint implementation that dumps queries to stdout."""

    def do_GET(self, environ, start_response):
        print('GET: ' + environ['PATH_INFO'].decode(DEFAULT_ENCODING))
        start_response('200 OK', [])
        return []

    def do_PROPFIND(self, environ, start_response):
        print('PROPFIND: ' + environ['PATH_INFO'].decode(DEFAULT_ENCODING))
        try:
            request_body_size = int(environ['CONTENT_LENGTH'])
        except KeyError:
            print(environ['wsgi.input'].read())
        else:
            print(environ['wsgi.input'].read(request_body_size))
        start_response('200 OK', [])
        return []


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
    def __init__(self, backend):
        self.backend = backend
        self.properties = {}

    def register_properties(self, properties):
        for p in properties:
            self.properties[p.name] = p

    def __call__(self, environ, start_response):
        p = environ['PATH_INFO']
        r = self.backend.get_resource(p)
        if r is None:
            start_response('404 Not Found', [])
            return [b'Path ' + p.encode(DEFAULT_ENCODING) + b' not found.']
        ep = DAVEndpoint(self.properties, r)
        return ep(environ, start_response)
