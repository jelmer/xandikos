# iMIP (RFC2447) interception for Xandikos.
#
# See README.sieve.rst for details.
#
require ["mime", "foreverypart", "vnd.dovecot.execute", "extracttext", "variables"];

foreverypart
{
  # Note that RFC2447 section 2.3 requires that content-type is text/calendar
  # and that the 'method' parameter is set. However, Google Calendar
  # sets it to application/ics and doesn't set method. Boo.
  if anyof(header :mime :contenttype "Content-Type" "application/ics",
           header :mime :contenttype "Content-Type" "text/calendar") {
    extracttext "ics";
    # TODO(jelmer): Verify S/MIME signer, if any, and pass it to
    # process-imip.py.
    execute :input "${ics}" "xandikos-itip";
    break;
  }
}
