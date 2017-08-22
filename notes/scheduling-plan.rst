CalDAV Scheduling
=================

TODO:

- When a new calendar object is uploaded to a calendar collection:
 * Check if the ORGANIZER property is present, and if so, process it
  + Send out invitations to all invitees

- Support CALDAV:schedule-tag
 * When comparing with if-schedule-tag-match, simply retrieve the blob by schedule-tag and compare delta between newly uploaded and current
 * When determining schedule-tag, scroll back until last revision that didn't have attendee changes?
  + Perhaps include a hint in e.g. commit message?

- support configuring inbox/output resource types in config

- Inbox "contains copies of incoming scheduling messages"
- Outbox "at which busy time information requests are targeted."

- support freebusy requests by POST
