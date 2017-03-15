# Xandikos
# Copyright (C) 2016-2017 Jelmer Vernooij <jelmer@jelmer.uk>
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

"""Abstract WebDAV server implementation..

This module contains an abstract WebDAV server. All caldav/carddav specific
functionality should live in xandikos.caldav/xandikos.carddav respectively.
"""

# TODO(jelmer): Add authorization support

import collections
import logging
import posixpath
import urllib.parse
from wsgiref.util import request_uri

from defusedxml.ElementTree import fromstring as xmlparse
# Hmm, defusedxml doesn't have XML generation functions? :(
from xml.etree import ElementTree as ET

DEFAULT_ENCODING = 'utf-8'
COLLECTION_RESOURCE_TYPE = '{DAV:}collection'
PRINCIPAL_RESOURCE_TYPE = '{DAV:}principal'


PropStatus = collections.namedtuple(
    'PropStatus', ['statuscode', 'responsedescription', 'prop'])


def etag_matches(condition, actual_etag):
    """Check if an etag matches an If-Matches condition.

    :param condition: Condition (e.g. '*', '"foo"' or '"foo", "bar"'
    :param actual_etag: ETag to compare to. None nonexistant
    :return: bool indicating whether condition matches
    """
    if actual_etag is None and condition:
        return False
    for etag in condition.split(','):
        if etag.strip(' ') == '*':
            return True
        if etag.strip(' ') == actual_etag:
            return True
    else:
        return False


class NeedsMultiStatus(Exception):
    """Raised when a response needs multi-status (e.g. for propstat)."""


def propstat_by_status(propstat):
    bystatus = {}
    for propstat in propstat:
        bystatus.setdefault(
            (propstat.statuscode, propstat.responsedescription), []).append(
                    propstat.prop)
    return bystatus


def propstat_as_xml(propstat):
    bystatus = propstat_by_status(propstat)
    for (status, rd), props in sorted(bystatus.items()):
        propstat = ET.Element('{DAV:}propstat')
        ET.SubElement(propstat,
            '{DAV:}status').text = 'HTTP/1.1 ' + status
        if rd:
            ET.SubElement(propstat,
                '{DAV:}responsedescription').text = responsedescription
        propresp = ET.SubElement(propstat, '{DAV:}prop')
        for prop in props:
            propresp.append(prop)
        yield propstat


class Status(object):
    """A DAV response that can be used in multi-status."""

    def __init__(self, href, status=None, error=None, responsedescription=None,
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
        if self.propstat and len(propstat_by_status(self.propstat)) > 1:
            raise NeedsMultiStatus()
        if self.propstat:
            [ret] = list(propstat_as_xml(self.propstat))
            body = ET.tostringlist(ret, encoding)
            return body, ('text/xml; encoding="%s"' % encoding)
        else:
            body = self.responsedescription or ''
            return body, ('text/plain; encoding="%s"' % encoding)

    def aselement(self):
        ret = ET.Element('{DAV:}response')
        ret.append(create_href(self.href))
        if self.status:
            ET.SubElement(ret, '{DAV:}status').text = 'HTTP/1.1 ' + self.status
        if self.error:
            ET.SubElement(ret, '{DAV:}error').append(self.error)
        if self.responsedescription:
            ET.SubElement(ret,
                '{DAV:}responsedescription').text = self.responsedescription
        if self.propstat is not None:
            for ps in propstat_as_xml(self.propstat):
                ret.append(ps)
        return ret


def multistatus(req_fn):

    def wrapper(self, environ, start_response, *args, **kwargs):
        responses = req_fn(self, environ, *args, **kwargs)
        return _send_dav_responses(start_response, responses,
                DEFAULT_ENCODING)

    return wrapper


class Property(object):
    """Handler for listing, retrieving and updating DAV Properties."""

    # Property name (e.g. '{DAV:}resourcetype')
    name = None

    # Whether to include this property in 'allprop' PROPFIND requests.
    # https://tools.ietf.org/html/rfc4918, section 14.2
    in_allprops = True

    # Resource type this property belongs to. If None, get_value()
    # will always be called.
    resource_type = None

    # Whether this property is live (i.e set by the server)
    live = None

    def supported_on(self, resource):
        return (self.resource_type is None or
                self.resource_type in resource.resource_types)

    def is_set(self, href, resource):
        """Check if this property is set on a resource."""
        if not self.supported_on(resource):
            return False
        try:
            self.get_value('/', resource, ET.Element(self.name))
        except KeyError:
            return False
        else:
            return True

    def get_value(self, href, resource, el):
        """Get property with specified name.

        :param href: Resource href
        :param resource: Resource for which to retrieve the property
        :param el: Element to populate
        :raise KeyError: if this property is not present
        """
        raise KeyError(self.name)

    def set_value(self, href, resource, el):
        """Set property.

        :param href: Resource href
        :param resource: Resource to modify
        :param el: Element to get new value from (None to remove property)
        :raise NotImplementedError: to indicate this property can not be set
            (i.e. is protected)
        """
        raise NotImplementedError(self.set_value)


class ResourceTypeProperty(Property):
    """Provides {DAV:}resourcetype."""

    name = '{DAV:}resourcetype'

    resource_type = None

    live = True

    def get_value(self, href, resource, el):
        for rt in resource.resource_types:
            ET.SubElement(el, rt)

    def set_value(self, href, resource, el):
        # TODO(jelmer): set resource types
        raise NotImplementedError(self.set_value)


class DisplayNameProperty(Property):
    """Provides {DAV:}displayname.

    https://tools.ietf.org/html/rfc4918, section 5.2
    """

    name = '{DAV:}displayname'
    resource_type = None

    def get_value(self, href, resource, el):
        el.text = resource.get_displayname()

    # TODO(jelmer): allow modification of this property
    def set_value(self, href, resource, el):
        raise NotImplementedError


class GetETagProperty(Property):
    """Provides {DAV:}getetag.

    https://tools.ietf.org/html/rfc4918, section 15.6
    """

    name = '{DAV:}getetag'
    resource_type = None
    live = True

    def get_value(self, href, resource, el):
        el.text = resource.get_etag()


class AddMemberProperty(Property):
    """Provides {DAV:}add-member.

    https://tools.ietf.org/html/rfc5995, section 3.2.1
    """

    name = '{DAV:}add-member'
    resource_type = COLLECTION_RESOURCE_TYPE
    live = True

    def get_value(self, href, resource, el):
        # Support POST against collection URL
        el.append(create_href('.', href))


class GetLastModifiedProperty(Property):
    """Provides {DAV:}getlastmodified.

    https://tools.ietf.org/html/rfc4918, section 15.7
    """

    name = '{DAV:}getlastmodified'
    resource_type = None
    live = True
    in_allprops = True

    def get_value(self, href, resource, el):
        # Use rfc1123 date (section 3.3.1 of RFC2616)
        el.text = resource.get_last_modified().strftime(
            '%a, %d %b %Y %H:%M:%S GMT')


def format_datetime(dt):
    s = "%04d%02d%02dT%02d%02d%02dZ" % (
        dt.year,
        dt.month,
        dt.day,
        dt.hour,
        dt.minute,
        dt.second
    )
    return s.encode('utf-8')


class CreationDateProperty(Property):
    """Provides {DAV:}creationdate.

    https://tools.ietf.org/html/rfc4918, section 23.2
    """

    name = '{DAV:}creationdate'
    resource_type = None
    live = True

    def get_value(self, href, resource, el):
        el.text = format_datetime(resource.get_creationdate())


class GetContentLanguageProperty(Property):
    """Provides {DAV:}getcontentlanguage.

    https://tools.ietf.org/html/rfc4918, section 15.3
    """

    name = '{DAV:}getcontentlanguage'
    resource_type = None

    def get_value(self, href, resource, el):
        el.text = ', '.join(resource.get_content_language())


class GetContentLengthProperty(Property):
    """Provides {DAV:}getcontentlength.

    https://tools.ietf.org/html/rfc4918, section 15.4
    """

    name = '{DAV:}getcontentlength'
    resource_type = None

    def get_value(self, href, resource, el):
        el.text = str(resource.get_content_length())


class GetContentTypeProperty(Property):
    """Provides {DAV:}getcontenttype.

    https://tools.ietf.org/html/rfc4918, section 13.5
    """

    name = '{DAV:}getcontenttype'
    resource_type = None

    def get_value(self, href, resource, el):
        el.text = resource.get_content_type()


class CurrentUserPrincipalProperty(Property):
    """Provides {DAV:}current-user-principal.

    See https://tools.ietf.org/html/rfc5397
    """

    name = '{DAV:}current-user-principal'
    resource_type = None
    in_allprops = False
    live = True

    def __init__(self, current_user_principal):
        super(CurrentUserPrincipalProperty, self).__init__()
        self.current_user_principal = ensure_trailing_slash(
            current_user_principal)

    def get_value(self, href, resource, el):
        """Get property with specified name.

        :param name: A property name.
        """
        el.append(create_href(self.current_user_principal, href))


class PrincipalURLProperty(Property):

    name = '{DAV:}principal-URL'
    resource_type = '{DAV:}principal'
    in_allprops = True
    live = True

    def get_value(self, href, resource, el):
        """Get property with specified name.

        :param name: A property name.
        """
        el.append(create_href(
            ensure_trailing_slash(resource.get_principal_url()), href))


class SupportedReportSetProperty(Property):

    name = '{DAV:}supported-report-set'
    resource_type = '{DAV:}collection'
    in_allprops = False
    live = True

    def __init__(self, reporters):
        self._reporters = reporters

    def get_value(self, href, resource, el):
        for name, reporter in self._reporters.items():
            if reporter.supported_on(resource):
                ET.SubElement(el, name)


class GetCTagProperty(Property):
    """getctag property

    """

    name = None
    resource_type = COLLECTION_RESOURCE_TYPE
    in_allprops = False
    live = True

    def get_value(self, href, resource, el):
        el.text = resource.get_ctag()


class DAVGetCTagProperty(GetCTagProperty):
    """getctag property

    """

    name = '{DAV:}getctag'


class AppleGetCTagProperty(GetCTagProperty):
    """getctag property

    """

    name = '{http://calendarserver.org/ns/}getctag'


LOCK_SCOPE_EXCLUSIVE = '{DAV:}exclusive'
LOCK_SCOPE_SHARED = '{DAV:}shared'
LOCK_TYPE_WRITE = '{DAV:}write'


ActiveLock = collections.namedtuple(
    'ActiveLock',
    ['lockscope', 'locktype', 'depth', 'owner', 'timeout','locktoken',
        'lockroot'])


class Resource(object):
    """A WebDAV resource."""

    # A list of resource type names (e.g. '{DAV:}collection')
    resource_types = []

    def get_displayname(self):
        """Get the resource display name."""
        raise KeyError

    def get_creationdate(self):
        """Get the resource creation date.

        :return: A datetime object
        """
        raise NotImplementedError(self.get_creationdate)

    def get_supported_locks(self):
        """Get the list of supported locks.

        This should return a list of (lockscope, locktype) tuples.
        Known lockscopes are LOCK_SCOPE_EXCLUSIVE, LOCK_SCOPE_SHARED
        Known locktypes are LOCK_TYPE_WRITE
        """
        raise NotImplementedError(self.get_supported_locks)

    def get_active_locks(self):
        """Return the list of active locks.

        :return: A list of ActiveLock tuples
        """
        raise NotImplementedError(self.get_active_locks)

    def get_content_type(self):
        """Get the content type for the resource.

        This is a mime type like text/plain
        """
        raise NotImplementedError(self.get_content_type)

    def get_owner(self):
        """Get an href identifying the owner of the resource.

        Can be None if owner information is not known.
        """
        raise NotImplementedError(self.get_owner)

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

    def get_content_length(self):
        """Get content length.

        :return: Length of this objects content.
        """
        return sum(map(len, self.get_body()))

    def get_content_language(self):
        """Get content language.

        :return: Language, as used in HTTP Accept-Language
        """
        raise NotImplementedError(self.get_content_language)

    def set_body(self, body, replace_etag=None):
        """Set resource contents.

        :param body: Iterable over bytestrings
        :return: New ETag
        """
        raise NotImplementedError(self.set_body)

    def set_comment(self, comment):
        """Set resource comment.

        :param comment: New comment
        """
        raise NotImplementedError(self.set_comment)

    def get_comment(self, comment):
        """Get resource comment.

        :return: comment
        """
        raise NotImplementedError(self.get_comment)

    def get_last_modified(self):
        """Get last modified time.

        :return: Last modified time
        """
        raise NotImplementedError(self.get_last_modified)


class Collection(Resource):
    """Resource for a WebDAV Collection."""

    resource_types = Resource.resource_types + [COLLECTION_RESOURCE_TYPE]

    def members(self):
        """List all members.

        :return: List of (name, Resource) tuples
        """
        raise NotImplementedError(self.members)

    def get_member(self, name):
        """Retrieve a member by name.

        :param name: Name of member to retrieve
        :return: A Resource
        """
        raise NotImplementedError(self.get_member)

    def delete_member(self, name, etag=None):
        """Delete a member with a specific name.

        :param name: Member name
        :param etag: Optional required etag
        :raise KeyError: when the item doesn't exist
        """
        raise NotImplementedError(self.delete_member)

    def create_member(self, name, contents, content_type):
        """Create a new member with specified name and contents.

        :param name: Member name (can be None)
        :param contents: Chunked contents
        :param etag: Optional required etag
        :return: (name, etag) for the new member
        """
        raise NotImplementedError(self.create_member)

    def get_sync_token(self):
        """Get sync-token for the current state of this collection.
        """
        raise NotImplementedError(self.get_sync_token)

    def iter_differences_since(self, old_token, new_token):
        """Iterate over differences in this collection.

        Should return an iterator over (name, old resource, new resource) tuples.
        If one of the two didn't exist previously or now, they should be None.

        If old_token is None, this should return full contents of the
        collection.

        May raise NotImplementedError if iterating differences is not
        supported.
        """
        raise NotImplementedError(self.iter_differences_since)

    def get_ctag(self):
        raise NotImplementedError(self.getctag)

    def get_headervalue(self):
        raise NotImplementedError(self.get_headervalue)

    def destroy(self):
        """Destroy this collection itself.
        """
        raise NotImplementedError(self.destroy)


class Principal(Resource):
    """Resource for a DAV Principal."""

    resource_Types = Resource.resource_types + [PRINCIPAL_RESOURCE_TYPE]

    def get_principal_url(self):
        """Return the principal URL for this principal.

        :return: A URL identifying this principal.
        """
        raise NotImplementedError(self.get_principal_url)

    def get_infit_settings(self):
        """Return inf-it settings string.
        """
        raise NotImplementedError(self.get_infit_settings)

    def set_infit_settings(self, settings):
        """Set inf-it settings string."""
        raise NotImplementedError(self.get_infit_settings)

    def get_group_membership(self):
        """Get group membership URLs."""
        raise NotImplementedError(self.get_group_membership)


def get_property(href, resource, properties, name):
    """Get a single property on a resource.

    :param href: Resource href
    :param resource: Resource object
    :param properties: Dictionary of properties
    :param name: name of property to resolve
    :return: PropStatus items
    """
    responsedescription = None
    ret = ET.Element(name)
    try:
        prop = properties[name]
    except KeyError:
        statuscode = '404 Not Found'
        logging.warning(
            'Client requested unknown property %s',
            name)
    else:
        try:
            if not prop.supported_on(resource):
                raise KeyError
            prop.get_value(href, resource, ret)
        except KeyError:
            statuscode = '404 Not Found'
        else:
            statuscode = '200 OK'
    return PropStatus(statuscode, responsedescription, ret)


def get_properties(href, resource, properties, requested):
    """Get a set of properties.

    :param href: Resource Href
    :param resource: Resource object
    :param properties: Dictionary of properties
    :param requested: XML {DAV:}prop element with properties to look up
    :return: Iterator over PropStatus items
    """
    for propreq in list(requested):
        yield get_property(href, resource, properties, propreq.tag)


def ensure_trailing_slash(href):
    """Ensure that a href has a trailing slash.

    Useful for collection hrefs, e.g. when used with urljoin.

    :param href: href to possibly add slash to
    :return: href with trailing slash
    """
    if href.endswith('/'):
        return href
    return href + '/'


def traverse_resource(base_resource, base_href, depth):
    """Traverse a resource.

    :param base_resource: Resource to traverse from
    :param base_href: href for base resource
    :param depth: Depth ("0", "1", "infinity")
    :return: Iterator over (URL, Resource) tuples
    """
    todo = collections.deque([(base_href, base_resource, depth)])
    while todo:
        (href, resource, depth) = todo.popleft()
        if COLLECTION_RESOURCE_TYPE in resource.resource_types:
            # caldavzap/carddavmate require this
            href = ensure_trailing_slash(href)
        yield (href, resource)
        if depth == "0":
            continue
        elif depth == "1":
            nextdepth = "0"
        elif depth == "infinity":
            nextdepth = "infinity"
        else:
            raise AssertionError("invalid depth %r" % depth)
        if COLLECTION_RESOURCE_TYPE in base_resource.resource_types:
            for (child_name, child_resource) in resource.members():
                child_href = urllib.parse.urljoin(href, child_name)
                todo.append((child_href, child_resource, nextdepth))


class Reporter(object):
    """Implementation for DAV REPORT requests."""

    name = None

    resource_type = None

    def supported_on(self, resource):
        """Check if this reporter is available for the specified resource.

        :param resource: Resource to check for
        :return: boolean indicating whether this reporter is available
        """
        return (self.resource_type is None or
                self.resource_type in resource.resource_types)

    def report(self, environ, start_response, request_body, resources_by_hrefs,
               properties, href, resource, depth):
        """Send a report.

        :param environ: wsgi environ
        :param start_response: WSGI start_response function
        :param request_body: XML Element for request body
        :param resources_by_hrefs: Function for retrieving resource by HREF
        :param properties: Dictionary mapping names to DAVProperty instances
        :param href: Base resource href
        :param resource: Resource to start from
        :param depth: Depth ("0", "1", ...)
        :return: chunked body
        """
        raise NotImplementedError(self.report)


def create_href(href, base_href=None):
    if '//' in href:
        logging.warning('invalidly formatted href: %s' % href)
    et = ET.Element('{DAV:}href')
    if base_href is not None:
        href = urllib.parse.urljoin(base_href+'/', href)
    et.text = urllib.parse.quote(href)
    return et


def read_href_element(et):
    return urllib.parse.unquote(et.text)


class ExpandPropertyReporter(Reporter):
    """A expand-property reporter.

    See https://tools.ietf.org/html/rfc3253, section 3.8
    """

    name = '{DAV:}expand-property'

    def _populate(self, prop_list, resources_by_hrefs, properties, href,
                  resource):
        """Expand properties for a resource.

        :param prop_list: DAV:property elements to retrieve and expand
        :param resources_by_hrefs: Resolve resource by HREF
        :param properties: Available properties
        :param href: href for current resource
        :param resource: current resource
        :return: Status object
        """
        ret = []
        for prop in prop_list:
            prop_name = prop.get('name')
            # FIXME: Resolve prop_name on resource
            propstat = get_property(href, resource, properties, prop_name)
            new_prop = ET.Element(propstat.prop.tag)
            child_hrefs = [
                read_href_element(prop_child)
                for prop_child in propstat.prop
                if prop_child.tag == '{DAV:}href']
            child_resources = resources_by_hrefs(child_hrefs)
            for prop_child in propstat.prop:
                if prop_child.tag != '{DAV:}href':
                    new_prop.append(prop_child)
                else:
                    child_href = read_href_element(prop_child)
                    child_resource = child_resources[child_href]
                    if child_resource is None:
                        # FIXME: What to do if the referenced href is invalid?
                        # For now, let's just keep the unresolved href around
                        new_prop.append(prop_child)
                    else:
                        response = self._populate(
                            prop, properties, child_href, child_resource)
                        new_prop.append(response.aselement())
            propstat = PropStatus(
                propstat.statuscode, propstat.responsedescription, prop=new_prop)
            ret.append(propstat)
        return Status(href, '200 OK', propstat=ret)

    @multistatus
    def report(self, environ, request_body, resources_by_hrefs, properties, href,
               resource, depth):
        return self._populate(request_body, resources_by_hrefs, properties,
                              href, resource)


class SupportedLockProperty(Property):
    """supportedlock property.

    See rfc4918, section 15.10.
    """

    name = '{DAV:}supportedlock'
    resource_type = None
    live = True

    def get_value(self, href, resource, el):
        for (lockscope, locktype) in resource.get_supported_locks():
            entry = ET.SubElement(el, '{DAV:}lockentry')
            scope_el = ET.SubElement(entry, '{DAV:}lockscope')
            ET.SubElement(scope_el, lockscope)
            type_el = ET.SubElement(entry, '{DAV:}locktype')
            ET.SubElement(type_el, locktype)


class LockDiscoveryProperty(Property):
    """lockdiscovery property.

    See rfc4918, section 15.8
    """

    name = '{DAV:}lockdiscovery'
    resource_type = None
    live = True

    def get_value(self, href, resource, el):
        for activelock in resource.get_active_locks():
            entry = ET.SubElement(el, '{DAV:}activelock')
            type_el = ET.SubElement(entry, '{DAV:}locktype')
            ET.SubElement(type_el, activelock.locktype)
            scope_el = ET.SubElement(entry, '{DAV:}lockscope')
            ET.SubElement(scope_el, activelock.lockscope)
            ET.SubElement(entry, '{DAV:}depth').text = str(activelock.depth)
            if activelock.owner:
                ET.SubElement(entry, '{DAV:}owner').text = activelock.owner
            if activelock.timeout:
                ET.SubElement(entry, '{DAV:}timeout').text = activelock.timeout
            if activelock.locktoken:
                locktoken_el = ET.SubElement(entry, '{DAV:}locktoken')
                locktoken_el.append(create_href(activelock.locktoken))
            if activelock.lockroot:
                lockroot_el = ET.SubElement(entry, '{DAV:}lockroot')
                lockroot_el.append(create_href(activelock.lockroot))


class CommentProperty(Property):
    """comment property.

    See RFC3253, section 3.1.1
    """
    name = '{DAV:}comment'
    live = False
    in_allprops = False

    def get_value(self, href, resource, el):
        el.text = resource.get_comment()

    def set_value(self, href, resource, el):
        resource.set_comment(el.text)


class Backend(object):
    """WebDAV backend."""

    def create_collection(self, relpath):
        """Create a collection with the specified relpath.

        :param relpath: Collection path
        """
        raise NotImplementedError(self.create_collection)

    def get_resoure(self, relpath):
        raise NotImplementedError(self.get_resource)


def _send_xml_response(start_response, status, et, out_encoding):
    body_type = 'text/xml; charset="%s"' % out_encoding
    body = ET.tostringlist(et, encoding=out_encoding)
    start_response(status, [
        ('Content-Type', body_type),
        ('Content-Length', str(sum(map(len, body))))])
    return body


def _send_dav_responses(start_response, responses, out_encoding):
    if isinstance(responses, Status):
        try:
            (body, body_type) = responses.get_single_body(
                out_encoding)
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
    return _send_xml_response(start_response, '207 Multi-Status',
        ret, out_encoding)


def _send_simple_dav_error(environ, start_response, statuscode, error):
    status = Status(request_uri(environ), statuscode, error)
    return _send_dav_responses(start_response, status, DEFAULT_ENCODING)


def _send_not_found(environ, start_response):
    path = request_uri(environ)
    start_response('404 Not Found', [])
    return [b'Path ' + path.encode(DEFAULT_ENCODING) + b' not found.']


def _send_method_not_allowed(environ, start_response, allowed_methods):
    start_response('405 Method Not Allowed', [
        ('Allow', ', '.join(allowed_methods))])
    return []


class WebDAVApp(object):
    """A wsgi App that provides a WebDAV server.

    A concrete implementation should provide an implementation of the
    lookup_resource function that can map a path to a Resource object
    (returning None for nonexistant objects).
    """

    def __init__(self, backend):
        self.backend = backend
        self.properties = {}
        self.reporters = {}

    def _request_href(self, environ):
        """Returns a href that can be used externally."""
        return environ['SCRIPT_NAME'] + environ['PATH_INFO']

    def register_properties(self, properties):
        for p in properties:
            self.properties[p.name] = p

    def register_reporters(self, reporters):
        for r in reporters:
            self.reporters[r.name] = r

    def _get_dav_features(self, resource):
        # TODO(jelmer): Support access-control
        return ['1', '2', '3', 'calendar-access', 'addressbook']

    def _get_allowed_methods(self, environ):
        """List of supported methods on this endpoint."""
        # TODO(jelmer): Look up resource to determine supported methods.
        return sorted([n[3:] for n in dir(self) if n.startswith('do_')])

    def do_HEAD(self, environ, start_response):
        return self._do_get(environ, start_response, send_body=False)

    def do_GET(self, environ, start_response):
        return self._do_get(environ, start_response, send_body=True)

    def _do_get(self, environ, start_response, send_body):
        r = self.backend.get_resource(environ['PATH_INFO'])
        if r is None:
            return _send_not_found(environ, start_response)
        current_etag = r.get_etag()
        if_none_match = environ.get('HTTP_IF_NONE_MATCH', None)
        if if_none_match and etag_matches(if_none_match, current_etag):
            start_response('304 Not Modified', [])
            return []
        headers = [
            ('ETag', current_etag),
            ('Content-Length', str(r.get_content_length())),
        ]
        try:
            content_type = r.get_content_type()
        except KeyError:
            pass
        else:
            headers.append(('Content-Type', content_type))
        try:
            last_modified = r.get_last_modified()
        except KeyError:
            pass
        else:
            headers.append(('Last-Modified', last_modified))
        try:
            languages = r.get_content_language()
        except KeyError:
            pass
        else:
            headers.append(('Content-Language', ', '.join(languages)))
        start_response('200 OK', headers)
        if send_body:
            return r.get_body()
        else:
            return []

    def do_DELETE(self, environ, start_response):
        r = self.backend.get_resource(environ['PATH_INFO'])
        if r is None:
            return _send_not_found(environ, start_response)
        container_path, item_name = posixpath.split(posixpath.normpath(environ['PATH_INFO']))
        pr = self.backend.get_resource(container_path)
        if pr is None:
            return _send_not_found(environ, start_response)
        current_etag = r.get_etag()
        if_match = environ.get('HTTP_IF_MATCH', None)
        if if_match is not None and not etag_matches(if_match, current_etag):
            start_response('412 Precondition Failed', [])
            return []
        pr.delete_member(item_name, current_etag)
        start_response('204 No Content', [])
        return []

    def do_POST(self, environ, start_response):
        # see RFC5995
        new_contents = self._readBody(environ)
        path = posixpath.normpath(environ['PATH_INFO'])
        r = self.backend.get_resource(path)
        if r is None:
            return _send_not_found(environ, start_response)
        if not COLLECTION_RESOURCE_TYPE in r.resource_types:
            start_response('405 Method Not Allowed', [])
            return []
        content_type = environ['CONTENT_TYPE'].split(';')[0]
        (name, etag) = r.create_member(None, new_contents, content_type)
        href = environ['SCRIPT_NAME'] + urllib.parse.urljoin(path+'/', name)
        start_response('200 OK', [
            ('Location', href)
            ])
        return []

    def do_PUT(self, environ, start_response):
        new_contents = self._readBody(environ)
        path = posixpath.normpath(environ['PATH_INFO'])
        r = self.backend.get_resource(path)
        if r is not None:
            current_etag = r.get_etag()
        else:
            current_etag = None
        if_match = environ.get('HTTP_IF_MATCH', None)
        if if_match is not None and not etag_matches(if_match, current_etag):
            start_response('412 Precondition Failed', [])
            return []
        if r is not None:
            new_etag = r.set_body(new_contents, current_etag)
            start_response('204 No Content', [
                ('ETag', new_etag)])
            return []
        content_type = environ.get('CONTENT_TYPE')
        container_path, name = posixpath.split(path)
        r = self.backend.get_resource(container_path)
        if r is not None:
            (new_name, new_etag) = r.create_member(
                name, new_contents, content_type)
            start_response('201 Created', [
                ('ETag', new_etag)])
            return []
        return _send_not_found(environ, start_response)

    def _readBody(self, environ):
        try:
            request_body_size = int(environ['CONTENT_LENGTH'])
        except KeyError:
            return [environ['wsgi.input'].read()]
        else:
            return [environ['wsgi.input'].read(request_body_size)]

    def _readXmlBody(self, environ):
        #TODO(jelmer): check Content-Type; should be something like
        # 'text/xml; charset="utf-8"'
        body = b''.join(self._readBody(environ))
        return xmlparse(body)

    def _get_resources_by_hrefs(self, environ, hrefs):
        """Retrieve multiple resources by href.
        """
        # TODO(jelmer): Bulk query hrefs in a more efficient manner
        for href in hrefs:
            if not href.startswith(environ['SCRIPT_NAME']):
                resource = None
            else:
                resource = self.backend.get_resource(href[len(environ['SCRIPT_NAME']):])
            yield (href, resource)

    def do_REPORT(self, environ, start_response):
        # See https://tools.ietf.org/html/rfc3253, section 3.6
        r = self.backend.get_resource(environ['PATH_INFO'])
        if r is None:
            return _send_not_found(environ, start_response)
        depth = environ.get("HTTP_DEPTH", "0")
        try:
            et = self._readXmlBody(environ)
        except ET.ParseError:
            start_response('400 Bad Request', [])
            return [b'Unable to parse body.']
        try:
            reporter = self.reporters[et.tag]
        except KeyError:
            logging.warning( 'Client requested unknown REPORT %s',
                et.tag)
            return _send_simple_dav_error(environ, start_response,
                '403 Forbidden', error=ET.Element('{DAV:}supported-report'))
        if not reporter.supported_on(r):
            return _send_simple_dav_error(environ, start_response,
                '403 Forbidden', error=ET.Element('{DAV:}supported-report'))
        return reporter.report(
            environ, start_response, et, lambda hrefs: self._get_resources_by_hrefs(environ, hrefs),
            self.properties, self._request_href(environ), r, depth)

    @multistatus
    def do_PROPFIND(self, environ):
        base_resource = self.backend.get_resource(environ['PATH_INFO'])
        if base_resource is None:
            return Status(request_uri(environ), '404 Not Found')
        # Default depth is infinity, per RFC2518
        depth = environ.get("HTTP_DEPTH", "infinity")
        if 'CONTENT_TYPE' not in environ and environ.get('CONTENT_LENGTH') == '0':
            requested = ET.Element('{DAV:}allprop')
        else:
            try:
                et = self._readXmlBody(environ)
            except ET.ParseError:
                return Status(request_uri(environ), '400 Bad Request',
                    'Unable to parse body.')
            if et.tag != '{DAV:}propfind':
                return Status(
                    request_uri(environ), '400 Bad Request',
                    'Expected propfind tag, got ' + et.tag)
            try:
                [requested] = et
            except ValueError:
                return Status(request_uri(environ), '400 Bad Request',
                    'Received more than one element in propfind.')
        if requested.tag == '{DAV:}prop':
            ret = []
            for href, resource in traverse_resource(
                    base_resource, self._request_href(environ), depth):
                propstat = get_properties(
                    href, resource, self.properties, requested)
                ret.append(Status(href, '200 OK', propstat=list(propstat)))
            # By my reading of the WebDAV RFC, it should be legal to return
            # '200 OK' here if Depth=0, but the RFC is not super clear and
            # some clients don't seem to like it .
            return ret
        elif requested.tag == '{DAV:}allprop':
            ret = []
            for href, resource in traverse_resource(
                    base_resource, self._request_href(environ), depth):
                propstat = []
                for name in self.properties:
                    ps = get_property(href, resource, self.properties, name)
                    if ps.statuscode == '200 OK':
                        propstat.append(ps)
                ret.append(Status(href, '200 OK', propstat=propstat))
            return ret
        elif requested.tag == '{DAV:}propname':
            ret = []
            for href, resource in traverse_resource(
                    base_resource, self._request_href(environ), depth):
                propstat = []
                for name, prop in self.properties.items():
                    if prop.is_set(resource):
                        propstat.append(ET.Element(name))
                ret.append(Status(href, '200 OK', propstat=propstat))
            return ret
        else:
            return Status(
                request_uri(environ), '400 Bad Request',
                'Expected prop/allprop/propname tag, got ' + requested.tag)

    @multistatus
    def do_PROPPATCH(self, environ):
        href = self._request_href(environ)
        resource = self.backend.get_resource(environ['PATH_INFO'])
        if resource is None:
            return Status(request_uri(environ), '404 Not Found')
        try:
            et = self._readXmlBody(environ)
        except ET.ParseError:
            return Status(request_uri(environ), '400 Bad Request',
                'Unable to parse body.')

        if et.tag != '{DAV:}propertyupdate':
            return Status(
                request_uri(environ), '400 Bad Request',
                'Expected properyupdate tag, got ' + et.tag)
        propstat = []
        for el in et:
            if el.tag not in ('{DAV:}set', '{DAV:}remove'):
                return Status(request_uri(environ), '400 Bad Request',
                    'Unknown tag %s in propertyupdate' % el.tag)
            try:
                [requested] = el
            except IndexError:
                return Status(request_uri(environ), '400 Bad Request',
                    'Received more than one element in propertyupdate/set.')
            if requested.tag != '{DAV:}prop':
                return Status(
                    request_uri(environ), '400 Bad Request',
                    'Expected prop tag, got ' + requested.tag)
            for propel in requested:
                try:
                    handler = self.properties[propel.tag]
                except KeyError:
                    logging.warning(
                        'client attempted to modify unknown property %r on %r',
                        propel.tag, environ['PATH_INFO'])
                    propstat.append(
                        PropStatus('404 Not Found', None,
                            ET.Element(propel.tag)))
                else:
                    if el.tag == '{DAV:}remove':
                        newval = None
                    elif el.tag == '{DAV:}set':
                        newval = propel
                    if not handler.supported_on(resource):
                        statuscode = '404 Not Found'
                    else:
                        try:
                            handler.set_value(href, resource, newval)
                        except NotImplementedError:
                            # TODO(jelmer): Signal
                            # {DAV:}cannot-modify-protected-property error
                            statuscode = '409 Conflict'
                        else:
                            statuscode = '200 OK'
                    propstat.append(
                        PropStatus(statuscode, None, ET.Element(propel.tag)))

        return [Status(
            request_uri(environ), propstat=propstat)]

    def do_MKCOL(self, environ, start_response):
        href = self._request_href(environ)
        base_content_type = environ.get('CONTENT_TYPE', '').split(';')[0]
        if base_content_type not in ('text/plain', 'text/xml', 'application/xml', ''):
            start_response('415 Unsupported Media Type', [])
            return [('Unsupported media type %r' % base_content_type).encode(DEFAULT_ENCODING)]
        resource = self.backend.get_resource(environ['PATH_INFO'])
        if resource is not None:
            start_response('405 Method Not Allowed', [])
            return []
        try:
            resource = self.backend.create_collection(environ['PATH_INFO'])
        except FileNotFoundError:
            start_response('409 Conflict', [])
            return []
        if base_content_type in ('text/xml', 'application/xml'):
            # Extended MKCOL (RFC5689)
            try:
                et = self._readXmlBody(environ)
            except ET.ParseError:
                start_response('400 Bad Request', [])
                return [b'Unable to parse body.']
            if et.tag != '{DAV:}mkcol':
                start_response('400 Bad Request', [])
                return [('Expected mkcol tag, got ' + et.tag).encode(DEFAULT_ENCODING)]
            propstat = []
            for el in et:
                if el.tag != '{DAV:}set':
                    start_response('400 Bad Request', [])
                    return [('Unknown tag %s in mkcol' % el.tag).encode(DEFAULT_ENCODING)]
                try:
                    [requested] = el
                except IndexError:
                    start_response('400 Bad Request', [])
                    return [b'Received more than one element in mkcol/set.']
                if requested.tag != '{DAV:}prop':
                    start_response('400 Bad Request', [])
                    return [('Expected prop tag, got ' + requested.tag).encode(DEFAULT_ENCODING)]
                for propel in requested:
                    try:
                        handler = self.properties[propel.tag]
                    except KeyError:
                        logging.warning(
                            'client attempted to modify unknown property %r on %r',
                            propel.tag, environ['PATH_INFO'])
                        propstat.append(
                            PropStatus('404 Not Found', None,
                                ET.Element(propel.tag)))
                    else:
                        if not handler.supported_on(resource):
                            statuscode = '404 Not Found'
                        else:
                            try:
                                handler.set_value(href, resource, propel)
                            except NotImplementedError:
                                # TODO(jelmer): Signal
                                # {DAV:}cannot-modify-protected-property error
                                statuscode = '409 Conflict'
                            else:
                                statuscode = '200 OK'
                        propstat.append(
                            PropStatus(statuscode, None, ET.Element(propel.tag)))
            ret = ET.Element('{DAV:}mkcol-response')
            for propstat_el in propstat_as_xml(propstat):
                ret.append(propstat_el)
            return _send_xml_response(start_response, '201 Created',
                ret, DEFAULT_ENCODING)
        else:
            start_response('201 Created', [])
            return []

    def do_OPTIONS(self, environ, start_response):
        headers = []
        if environ['PATH_INFO'] != '*':
            r = self.backend.get_resource(environ['PATH_INFO'])
            if r is None:
                return _send_not_found(environ, start_response)
            dav_features = self._get_dav_features(r)
            headers.append(('DAV', ', '.join(dav_features)))
            allowed_methods = self._get_allowed_methods(environ)
            headers.append(('Allow', ', '.join(allowed_methods)))

        # RFC7231 requires that if there is no response body,
        # Content-Length: 0 must be sent. This implies that there is
        # content (albeit empty), and thus a 204 is not a valid reply.
        # Thunderbird also fails if a 204 is sent rather than a 200.
        start_response('200 OK', headers + [
            ('Content-Length', '0')])
        return []

    def __call__(self, environ, start_response):
        method = environ['REQUEST_METHOD']
        do = getattr(self, 'do_' + method, None)
        if do is not None:
            return do(environ, start_response)
        return _send_method_not_allowed(environ, start_response,
            self._get_allowed_methods(environ))
