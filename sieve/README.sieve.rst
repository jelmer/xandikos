Xandikos supports e-mail based calendar interoperability using iMIP (RFC2447).
In essence, these are emails with .ics file attached to notify your calendar
of invites and modifications to events.

At the moment, the only way to do iMIP filtering is using sieve filters in
dovecot, using dovecot's extprograms extensions to pipe iTIP calendar objects
to Xandikos.

Installation
============

1. Enable the dovecot sieve plugin and extprograms plugin for sieve in dovecot.
   On most systems, you can do this by making sure the plugins are installed,
   then copying 90-sieve-xandikos.conf.example in this directory to
   /etc/dovecot/conf.d/90-sieve-xandikos.conf, and restarting dovecot.

2. Copy or symlink bin/xandikos-itip to /usr/lib/dovecot/sieve-pipe
   (or whatever you have set $sieve_execute_bin_dir to).

3. Copy xandikos.sieve to /var/libdovecot/sieve/global
   (or $sieve_global_dir, if you're using a different directory).

4. Enable the filtering by adding::

     require ["global"];

     include :global "xandikos";

   to ~/.dovecot.sieve.

Caveats
=======

RFC2447 suggests that all iMIP messages be S/MIME signed. In practice, this
doesn't happen often, and Xandikos currently does not verify S/MIME signatures.

This means that at the moment the authenticity of messages is not verified,
allowing anybody that is able to send you an e-mail that makes it through
to the filter to modify your calendar.
