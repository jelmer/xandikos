DAV Compliance
==============

This document aims to document the compliance with various RFCs.

rfc4918.txt (Core WebDAV) (obsoletes rfc2518)
---------------------------------------------

Mostly supported.

HTTP Methods
^^^^^^^^^^^^

- PROPFIND [supported]
- PROPPATCH [supported]
- MKCOL [supported]
- DELETE [supported]
- PUT [supported]
- COPY [supported]
- MOVE [supported]
- LOCK [not implemented]
- UNLOCK [not implemented]

HTTP Headers
^^^^^^^^^^^^

- (9.1) Dav [supported]
- (9.2) Depth ['0, '1' and 'infinity' are supported]
- (9.3) Destination [supported]
- (9.4) If [partially supported - If-Match and If-None-Match headers are supported]
- (9.5) Lock-Token [not supported]
- (9.6) Overwrite [supported, used with COPY/MOVE]
- (9.7) Status-URI [not supported]
- (9.8) Timeout [not supported, only used for locks]

DAV Properties
^^^^^^^^^^^^^^

- (15.1) creationdate [supported]
- (15.2) displayname [supported]
- (15.3) getcontentlanguage [supported]
- (15.4) getcontentlength [supported]
- (15.5) getcontenttype [supported]
- (15.6) getetag [supported]
- (15.7) getlastmodified [supported]
- (15.8) lockdiscovery [supported - returns empty, no actual locking]
- (15.9) resourcetype [supported]
- (15.10) supportedlock [supported - returns empty, no actual locking]
- (RFC2518 ONLY - 13.10) source [not supported]

Known Limitations
^^^^^^^^^^^^^^^^^

**Dead Properties**: Arbitrary custom (dead) properties are not supported.
PROPPATCH operations on unknown properties return 403 Forbidden per RFC 4918
Section 9.2.1, indicating the operation cannot be performed. This affects
litmus test suite compatibility where some property tests expect full dead
property storage and retrieval support.

**URI Fragment Handling**: URI fragments (text after #) are properly stripped
per RFC 3986 Section 3.5 before server-side processing. Percent-encoded hashes
(%23) are correctly decoded and preserved as part of resource names.

rfc3253.txt (Versioning Extensions)
-----------------------------------

Broadly speaking, only features related to the REPORT method are supported.

HTTP Methods
^^^^^^^^^^^^

- REPORT [supported]
- CHECKOUT [not supported]
- CHECKIN [not supported]
- UNCHECKOUT [not supported]
- MKWORKSPACE [not supported]
- UPDATE [not supported]
- LABEL [not supported]
- MERGE [not supported]
- VERSION-CONTROL [not supported]
- BASELINE-CONTROL [not supported]
- MKACTIVITY [not supported]

DAV Properties
^^^^^^^^^^^^^^

- DAV:comment [supported]
- DAV:creator-displayname [not supported]
- DAV:supported-method-set [not supported]
- DAV:supported-live-property-set [not supported]
- DAV:supported-report-set [supported]
- DAV:predecessor-set [not supported]
- DAV:successor-set [not supported]
- DAV:checkout-set [not supported]
- DAV:version-name [not supported]
- DAV:checked-out [not supported]
- DAV:chcked-in [not supported]
- DAV:auto-version [not supported]

DAV Reports
^^^^^^^^^^^

- DAV:expand-property [supported]
- DAV:version-tree [not supported]

rfc5323.txt (WebDAV "SEARCH")
-----------------------------

Not supported

HTTP Methods
^^^^^^^^^^^^

- SEARCH [not supported]

DAV Properties
^^^^^^^^^^^^^^

- DAV:datatype [not supported]
- DAV:searchable [not supported]
- DAV:selectable [not supported]
- DAV:sortable [not supported]
- DAV:caseless [not supported]
- DAV:operators [not supported]

rfc3744.txt (WebDAV access control)
-----------------------------------

Not really supported

DAV Properties
^^^^^^^^^^^^^^

- DAV:alternate-uri-set [not supported]
- DAV:principal-URL [supported]
- DAV:group-member-set [not supported]
- DAV:group-membership [supported]
- DAV:owner [supported]
- DAV:group [not supported]
- DAV:current-user-privilege-set [supported]
- DAV:supported-privilege-set [not supported]
- DAV:acl [not supported]
- DAV:acl-restrictions [not supported]
- DAV:inherited-acl-set [not supported]
- DAV:principal-collection-set [not supported]

DAV Reports
^^^^^^^^^^^

- DAV:acl-principal-prop-set [not supported]
- DAV:principal-match [not supported]
- DAV:principal-property-search [not supported]
- DAV:principal-search-property-set [not supported]

rfc4791.txt (CalDAV)
--------------------

Fully supported.

DAV Properties
^^^^^^^^^^^^^^

- CALDAV:calendar-description [supported]
- CALDAV:calendar-home-set [supported]
- CALDAV:calendar-timezone [supported]
- CALDAV:supported-calendar-component-set [supported]
- CALDAV:supported-calendar-data [supported]
- CALDAV:max-resource-size [supported]
- CALDAV:min-date-time [supported]
- CALDAV:max-date-time [supported]
- CALDAV:max-instances [supported]
- CALDAV:max-attendees-per-instance [supported]

HTTP Methods
^^^^^^^^^^^^

- MKCALENDAR [supported]

DAV Reports
^^^^^^^^^^^

- CALDAV:calendar-query [supported - includes limit-recurrence-set support]
- CALDAV:calendar-multiget [supported]
- CALDAV:free-busy-query [supported]

rfc6352.txt (CardDAV)
---------------------

Fully supported.

DAV Properties
^^^^^^^^^^^^^^

- CARDDAV:addressbook-description [supported]
- CARDDAV:supported-address-data [supported]
- CARDDAV:max-resource-size [supported]
- CARDDAV:addressbook-home-set [supported]
- CARDDAV:princial-address [supported]

DAV Reports
^^^^^^^^^^^

- CARDDAV:addressbook-query [supported]
- CARDDAV:addressbook-multiget [supported]

rfc6638.txt (CalDAV scheduling extensions)
------------------------------------------

DAV Properties
^^^^^^^^^^^^^^

- CALDAV:schedule-outbox-URL [supported]
- CALDAV:schedule-inbox-URL [supported]
- CALDAV:calendar-user-address-set [supported]
- CALDAV:calendar-user-type [supported]
- CALDAV:schedule-calendar-transp [supported]
- CALDAV:schedule-default-calendar-URL [supported]
- CALDAV:schedule-tag [supported]

rfc6764.txt (Locating groupware services)
-----------------------------------------

Most of this is outside of the scope of xandikos, but it does support
DAV:current-user-principal

rfc7809.txt (CalDAV Time Zone Extensions)
-----------------------------------------

Not supported

DAV Properties
^^^^^^^^^^^^^^

- CALDAV:timezone-service-set [supported]
- CALDAV:calendar-timezone-id [not supported]

rfc5397.txt (WebDAV Current Principal Extension)
------------------------------------------------

DAV Properties
^^^^^^^^^^^^^^

- CALDAV:current-user-principal [supported]

Proprietary extensions
----------------------

Custom properties used by various clients
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

- CARDDAV:max-image-size [supported]

https://github.com/apple/ccs-calendarserver/blob/master/doc/Extensions/caldav-ctag.txt

- DAV:getctag [supported]

https://github.com/apple/ccs-calendarserver/blob/master/doc/Extensions/caldav-proxy.txt

- DAV:calendar-proxy-read-for [supported]
- DAV:calendar-proxy-write-for [supported]

Apple-specific Properties
^^^^^^^^^^^^^^^^^^^^^^^^^

- calendar-color [supported]
- calendar-order [supported]
- getctag [supported]
- refreshrate [supported]
- source

XMPP Subscriptions
^^^^^^^^^^^^^^^^^^

- xmpp-server
- xmpp-heartbeat
- xmpp-uri

inf-it properties
^^^^^^^^^^^^^^^^^

- headervalue [supported]
- settings [supported]
- addressbook-color [supported]

AgendaV properties
^^^^^^^^^^^^^^^^^^

https://tools.ietf.org/id/draft-ietf-calext-caldav-attachments-03.html

- CALDAV:max-attachments-per-resource [supported]
- CALDAV:max-attachment-size [supported]
- CALDAV:managed-attachments-server-URL [supported]

rfc5995.txt (POST to create members)
------------------------------------

Fully supported.

DAV Properties
^^^^^^^^^^^^^^

- DAV:add-member [supported]

HTTP Methods
^^^^^^^^^^^^

- POST [supported]

rfc5689 (Extended MKCOL)
------------------------

Fully supported

HTTP Methods
^^^^^^^^^^^^

- MKCOL [supported]

rfc7529.txt (WebDAV Quota)
--------------------------

DAV properties
^^^^^^^^^^^^^^

- {DAV:}quota-available-bytes [supported]
- {DAV:}quota-used-bytes [supported]

rfc4709 (WebDAV Mount)
----------------------

This RFC documents a mechanism that allows clients to find the WebDAV mount
associated with a specific page. It's unclear to the writer what the value of
this is - an alternate resource in the HTML page would also do.

As far as I can tell, there is only a single server side implementation and a
single client side implementation of this RFC.  I don't have access to the
client implementation (Xythos Drive) and the server side implementation is in
SabreDAV.

Experimental support for WebDAV Mount is available in the 'mount' branch, but
won't be merged without a good use case.

rfc6578.txt (WebDAV Sync)
-------------------------

Fully supported.

DAV Properties
^^^^^^^^^^^^^^

- {DAV:}sync-token [supported]

DAV Reports
^^^^^^^^^^^

- {DAV:}sync-collection [supported]

rfc4790.txt (Internet Application Protocol Collation Registry)
--------------------------------------------------------------

Used for text-match operations in CalDAV and CardDAV queries.

Supported collations:
- i;ascii-casemap (case-insensitive ASCII)
- i;octet (exact octet-by-octet matching)

Other Notable Specifications
----------------------------

rfc5842.txt (WebDAV BIND)
^^^^^^^^^^^^^^^^^^^^^^^^^

Not supported.

- BIND method [not supported]
- UNBIND method [not supported]
- REBIND method [not supported]

rfc8144.txt (Prefer Header)
^^^^^^^^^^^^^^^^^^^^^^^^^^^

Not supported. The Prefer header would allow clients to indicate preferences
for server behavior (e.g., return=minimal for reduced response verbosity).

rfc7953.txt (Calendar Availability)
-----------------------------------

Fully supported.

This RFC extends CalDAV to support VAVAILABILITY components that define when
a calendar user is available for scheduling. Availability information affects
free/busy queries by marking time periods as busy or available with different
priority levels.

Supported Components
^^^^^^^^^^^^^^^^^^^^

- VAVAILABILITY [supported - time-range filtering, priority-based processing]
- AVAILABLE [supported - marks free time within VAVAILABILITY periods]

Supported Properties
^^^^^^^^^^^^^^^^^^^^

- BUSYTYPE [supported - BUSY, BUSY-UNAVAILABLE, BUSY-TENTATIVE]
- PRIORITY [supported - 1-9 priority levels with proper precedence]

DAV Properties
^^^^^^^^^^^^^^

- CALDAV:calendar-availability [supported]

Free/Busy Integration
^^^^^^^^^^^^^^^^^^^^^

The implementation follows RFC 7953 section 4.4 for priority-based availability
processing. Higher priority (lower number) VAVAILABILITY components override
lower priority ones. For same priority levels, BUSYTYPE precedence is:
BUSY > BUSY-UNAVAILABLE > BUSY-TENTATIVE > FREE.

AVAILABLE subcomponents create free time periods within their parent 
VAVAILABILITY component's busy time, following the same priority rules.

Managed Attachments
-------------------

Apple extension:

https://datatracker.ietf.org/doc/html/draft-ietf-calext-caldav-attachments-04

Currently unsupported.
