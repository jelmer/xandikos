# iMIP (RFC2447) interception for Xandikos.
#
# See README.sieve.rst for details.
#
require ["mime", "foreverypart", "vnd.dovecot.execute", "extracttext", "variables"];

foreverypart
{
  # Note that RFC2447 section 2.3 requires that content-type is text/calendar
  # and that the 'method' parameter is set.
  if allof(header :mime :contenttype "Content-Type" "text/calendar",
           header :mime :param "method" :contains "Content-Type" "REQUEST") {
    extracttext "ics";
    # TODO(jelmer): Verify S/MIME signer, if any, and pass it to
    # process-imip.py.
    execute :input "${ics}" "xandikos-itip";
    break;
  }
}
