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

CURRENT_USER_PRINCIPAL = '/user/'
DEFAULT_ENCODING = 'utf-8'


PropStatus = collections.namedtuple(
    'PropStatus', ['statuscode', 'responsedescription', 'prop'])


class NeedsMultiStatus(Exception):
    """Raised when a response needs multi-status (e.g. for propstat)."""


class DavStatus(object):
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


class DavResource(object):
    """A WebDAV resource."""

    def get_body(self):
        """Get resource contents."""
        raise NotImplementedError(self.get)

    def proplist(self):
        """List all properties."""
        return []

    def members(self):
        """Return all child resources."""
        raise NotImplementedError(self.members)

    def propget(self, name):
        """Get property with specified name.

        :param name: A property name.
        """
        if name == '{DAV:}current-user-principal':
            ret = ET.Element('{DAV:}current-user-principal')
            ET.SubElement(ret, '{DAV:}href').text = CURRENT_USER_PRINCIPAL
            return ret
        raise KeyError(name)


class DavEndpoint(Endpoint):
    """A webdav-enabled endpoint."""

    out_encoding = DEFAULT_ENCODING

    def __init__(self, resource):
        self.resource = resource

    def _readXmlBody(self, environ):
        try:
            request_body_size = int(environ['CONTENT_LENGTH'])
        except KeyError:
            return xmlparse(environ['wsgi.input'].read())
        else:
            return xmlparse(environ['wsgi.input'].read(request_body_size))

    @property
    def allowed_methods(self):
        """List of supported methods on this endpoint."""
        return (super(DavEndpoint, self).allowed_methods +
                [n[4:] for n in dir(self) if n.startswith('dav_')])

    def __call__(self, environ, start_response):
        method = environ['REQUEST_METHOD']
        try:
            dav = getattr(self, 'dav_' + method)
        except AttributeError:
            return super(DavEndpoint, self).__call__(environ, start_response)
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
        if depth == "0":
            return iter([(base_href, self.resource)])
        elif depth == "1":
            return iter(
                [(base_href, self.resource)] +
                [(urllib.parse.urljoin(base_href+'/', n), m)
                    for (n, m) in self.resource.members()])
        raise NotImplementedError

    def dav_PROPFIND(self, environ):
        depth = environ.get("HTTP_DEPTH", "0")
        #TODO(jelmer): check Content-Type; should be something like
        # 'text/xml; charset="utf-8"'
        et = self._readXmlBody(environ)
        if et.tag != '{DAV:}propfind':
            # TODO-ERROR(jelmer): What to return here?
            yield DavStatus(
                environ['PATH_INFO'], '500 Internal Error',
                'Expected propfind tag, got ' + et.tag)
            return
        try:
            [requested] = et
        except IndexError:
            yield DavStatus(
                environ['PATH_INFO'], '500 Internal Error',
                'Received more than one element in propfind.')
            return
        if requested.tag == '{DAV:}prop':
            for href, resource in self._browse(depth, environ['PATH_INFO']):
                propstat = []
                for propreq in list(requested):
                    propresp = ET.Element('{DAV:}prop')
                    responsedescription = None
                    try:
                        propresp.append(resource.propget(propreq.tag))
                    except KeyError:
                        statuscode = '404 Not Found'
                        propresp.append(ET.SubElement(propresp, propreq.tag))
                    else:
                        statuscode = '200 OK'
                    propstat.append(
                        PropStatus(statuscode, responsedescription, propresp))
                yield DavStatus(href, '200 OK', propstat=propstat)
        else:
            # TODO(jelmer): implement allprop and propname
            # TODO-ERROR(jelmer): What to return here?
            yield DavStatus(
                environ['PATH_INFO'], '500 Internal Error',
                'Expected prop tag, got ' + requested.tag)
            return

    def do_GET(self, environ, start_response):
        start_response('200 OK', [])
        return [self.resource.get_body()]


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


class WebDAVApp(object):
    """A wsgi App that provides a WebDAV server.

    A concrete implementation should provide an implementation of the
    lookup_resource function that can map a path to a DavResource object
    (returning None for nonexistant objects).
    """
    def __init__(self, lookup_resource):
        self.lookup_resource = lookup_resource

    def __call__(self, environ, start_response):
        p = environ['PATH_INFO']
        r = self.lookup_resource(p)
        if r is None:
            start_response('404 Not Found', [])
            return [b'Path ' + p.encode(DEFAULT_ENCODING) + b' not found.']
        ep = DavEndpoint(r)
        return ep(environ, start_response)
