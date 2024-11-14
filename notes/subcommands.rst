Subcommands
===========

At the moment, the Xandikos command just supports running a
(debug) webserver. In various situations it would also be useful
to have subcommands for administrative operations.

Propose subcommands:

 * ``xandikos init [--defaults] [--autocreate] [-d DIRECTORY]`` -
   create a Xandikos database
 * ``xandikos stats`` - dump stats, similar to those exposed by prometheus
 * ``xandikos web`` - run a debug web server

