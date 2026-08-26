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
- DAV:principal-collection-set [supported]

DAV Reports
^^^^^^^^^^^

- DAV:acl-principal-prop-set [not supported]
- DAV:principal-match [not supported]
- DAV:principal-property-search [supported]
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

Implemented. Local attendees are delivered to their schedule-inbox;
remote attendees can be reached over iMIP (RFC 6047) when
``--imip-send`` is configured (off by default — see the iMIP
section below).

DAV Properties
^^^^^^^^^^^^^^

- CALDAV:schedule-outbox-URL [supported]
- CALDAV:schedule-inbox-URL [supported]
- CALDAV:calendar-user-address-set [supported, PROPPATCH-able]
- CALDAV:calendar-user-type [supported, PROPPATCH-able]
- CALDAV:schedule-calendar-transp [supported, read-only]
- CALDAV:schedule-default-calendar-URL [supported, PROPPATCH-able]
- CALDAV:schedule-tag [supported]

Resource types
^^^^^^^^^^^^^^

- CALDAV:schedule-inbox [supported]
- CALDAV:schedule-outbox [supported]

Implicit scheduling (§3.1)
^^^^^^^^^^^^^^^^^^^^^^^^^^

When an organiser PUTs or DELETEs a scheduling object resource in
their own calendar, Xandikos generates the appropriate iTIP
REQUEST/CANCEL messages and delivers them into each local attendee's
schedule-inbox; attendee PUTs that change their PARTSTAT trigger an
iTIP REPLY back to the organiser. Inbox deliveries are also
auto-applied to the recipient's default calendar (REQUEST creates a
tentative copy preserving any existing PARTSTAT; CANCEL marks the
local copy STATUS:CANCELLED; REPLY updates the organiser's stored
ATTENDEE PARTSTAT). Remote attendees are skipped — see the iMIP
note above.

Attendee writes are restricted per §3.1: an attendee may only modify
their own ATTENDEE entry on a stored scheduling object; PUTs that
touch organiser-owned fields (DTSTART, DTEND, the attendee list,
ORGANIZER, SUMMARY, ...) are refused with the
{caldav}attendee-allowed precondition.

Each ATTENDEE on the organiser's stored event is annotated with a
SCHEDULE-STATUS parameter recording the delivery outcome (1.2 for
local-inbox delivery, 3.7 for unknown calendar users).

Free-busy (§6)
^^^^^^^^^^^^^^

POSTing a METHOD:REQUEST VFREEBUSY to a principal's schedule-outbox
returns a CalDAV schedule-response per attendee, with busy periods
gathered from the principal's calendars. Calendars marked
schedule-calendar-transp=transparent are excluded from busy time;
events where the queried user has PARTSTAT=DECLINED are excluded;
multi-day events are clipped to the requested time-range. VAVAILABILITY
windows are honored per RFC 7953 priority rules.

schedule-tag preconditions (§3.2.10, §8.1)
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

If-Schedule-Tag-Match is honored on PUT, DELETE, MOVE, and COPY.
The Schedule-Tag response header is emitted on PUT and GET of
scheduling resources. The schedule-tag value tracks
iTIP-significant changes only — bookkeeping property changes
(DTSTAMP, LAST-MODIFIED) don't move it.

SCHEDULE-FORCE-SEND (§3.2.4)
^^^^^^^^^^^^^^^^^^^^^^^^^^^^

A client may attach SCHEDULE-FORCE-SEND=REQUEST or =REPLY to an
ATTENDEE on a PUT to instruct the server to dispatch an iTIP
message to that attendee even when no iTIP-significant change has
happened. The parameter is consumed (stripped from the stored
representation) and triggers the appropriate delivery: REQUEST on
the organiser path, REPLY on the attendee path. Unrecognised values
are silently dropped per the spec.

Attendee delegation (§3.2.6)
^^^^^^^^^^^^^^^^^^^^^^^^^^^^

When an attendee delegates by changing their own ATTENDEE to
PARTSTAT=DELEGATED;DELEGATED-TO=… and adding an ATTENDEE for the
delegate with DELEGATED-FROM pointing back at themselves, the
server allows the addition (it would otherwise fall foul of the
§3.1 attendee-write restriction), sends an iTIP REPLY to the
organiser carrying the user's new PARTSTAT=DELEGATED, and sends an
iTIP REQUEST to the new delegate so the meeting appears on their
calendar. SCHEDULE-STATUS on the delegate ATTENDEE in the user's
stored copy records the delivery outcome.

iMIP (RFC 6047)
^^^^^^^^^^^^^^^

Outbound delivery is configurable, off by default. The
``--imip-send`` switch (or ``XANDIKOS_IMIP_SEND``) selects the
transport: ``sendmail`` pipes through a local sendmail-compatible
binary, ``smtp`` connects to a relay (``--smtp-host``,
``--smtp-port``, ``--smtp-encryption=none|starttls|ssl``,
``--smtp-user``, ``--smtp-password-file``). The ``From:`` header
uses the configured server identity (``--smtp-from``); the
originating organiser/attendee goes in ``Reply-To:``. Each message
carries ``Auto-Submitted: auto-generated`` so an inbound Sieve hook
that pipes calendar mail to ``xandikos import-imip`` will skip
server-generated traffic and not loop. SCHEDULE-STATUS reflects the
outcome: ``1.1;Sent`` on a successful hand-off,
``5.1;Service unavailable`` on transport failure, and
``3.7;Invalid calendar user`` when iMIP is off.

Inbound delivery happens via the ``xandikos import-imip``
subcommand, which parses an RFC 5322 message from stdin (typically
piped from a Dovecot Sieve rule) and POSTs the iTIP payload to a
principal's schedule-inbox.

Not implemented
^^^^^^^^^^^^^^^

- iMIP methods other than REQUEST, REPLY, and CANCEL (PUBLISH,
  ADD, REFRESH, COUNTER, DECLINECOUNTER).
- An outbound queue with retries — transport failures surface as
  ``SCHEDULE-STATUS=5.1`` and the operator is expected to retry
  by re-PUTting the event with ``SCHEDULE-FORCE-SEND=REQUEST``.

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

draft-bitfire-webdav-push (WebDAV-Push)
---------------------------------------

Implemented. Enabled with ``--webdav-push``; off by default. When
enabled, calendar and addressbook collections advertise the
``{https://bitfire.at/webdav-push}push-transports`` /
``push-topic`` / ``supported-triggers`` properties and accept a POST
of a ``{https://bitfire.at/webdav-push}push-register`` body. Each
successful registration returns a subscription URL of the form
``${route-prefix}.subscriptions/<sub-id>``; ``DELETE`` against that
URL cancels the subscription.

Notifications are delivered as Web Push messages
(`RFC 8030 <https://www.rfc-editor.org/rfc/rfc8030>`_) signed with
VAPID (`RFC 8292 <https://www.rfc-editor.org/rfc/rfc8292>`_) and
encrypted with ``aes128gcm``
(`RFC 8291 <https://www.rfc-editor.org/rfc/rfc8291>`_). The VAPID
keypair is generated under ``<state-dir>/vapid/`` on first start.

Triggers
^^^^^^^^

The server fires a notification when a member resource is created,
modified, or deleted in a subscribed collection, and when the
collection's displayname changes. Server-side changes that originate
from an authenticated client carrying the ``Push-Dont-Notify`` header
(per the draft) suppress the notification for the matching
subscription only.

Not implemented
^^^^^^^^^^^^^^^

- A web-push delivery queue with retries — transient delivery
  failures are logged; clients that miss a notification fall back to
  their configured polling interval. Push endpoints that return
  ``410 Gone`` or ``404`` drop the corresponding subscription.

Other Notable Specifications
----------------------------

rfc5842.txt (WebDAV BIND)
^^^^^^^^^^^^^^^^^^^^^^^^^

Partial: only the ``DAV:resource-id`` property is implemented.

- BIND method [not supported]
- UNBIND method [not supported]
- REBIND method [not supported]
- ``DAV:resource-id`` property [supported - urn:uuid: identifiers,
  derived from the file UID for calendar/addressbook object resources
  and auto-generated and persisted per collection]

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
