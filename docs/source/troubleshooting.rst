Troubleshooting
===============

Support channels
----------------

For help, please try the `Xandikos Discussions Forum
<https://github.com/jelmer/xandikos/discussions/categories/q-a>`_,
IRC (``#xandikos`` on irc.oftc.net), or Matrix (`#xandikos:matrix.org
<https://matrix.to/#/#xandikos:matrix.org>`_).

Debugging \*DAV
---------------

Your client may have a way of increasing log verbosity; this can often be very
helpful.

Xandikos also has several command-line flags that may help with debugging:

 * ``--dump-dav-xml``: Write all \*DAV communication to standard out;
   interpreting the contents may require in-depth \*DAV knowledge, but
   providing this data is usually sufficient for one of the Xandikos
   developers to identify the cause of an issue.

 * ``--no-strict``: Don't follow a strict interpretation of the
   various standards, for clients that don't follow them.

 * ``--debug``: Print extra information about Xandikos' internal state.

If you do find that a particular server requires ``--no-strict``, please
do report it - either to the servers' authors or in the
[Xandikos Discussions](https://github.com/jelmer/xandikos/discussions).
