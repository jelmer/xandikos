# Xandikos
# Copyright (C) 2016-2017 Jelmer Vernooĳ <jelmer@jelmer.uk>, et al.
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

"""iTIP handling.

See:
    https://tools.ietf.org/html/rfc5546

Also relevant:

    https://tools.ietf.org/html/rfc2447 (iMIP)
"""

from icalendar.cal import Calendar


def main(argv):
    import argparse
    import logging
    import sys
    from xandikos import __version__
    parser = argparse.ArgumentParser(
        usage="%(prog)s [OPTIONS]",
        prog=argv[0])

    parser.add_argument(
        '--version',
        action='version',
        version='%(prog)s ' + '.'.join(map(str, __version__)))

    access_group = parser.add_argument_group(title="iTIP Options")
    access_group.add_argument(
        "-s", "--signer", dest="signer", help="Name of e-mail signer.")
    options = parser.parse_args(argv[1:])

    if options.directory is None:
        parser.print_usage()
        sys.exit(1)

    logging.basicConfig(level=logging.INFO)

    request = Calendar.from_ical(sys.stdin)

    # TODO(jelmer): Process request


if __name__ == '__main__':
    import sys
    main(sys.argv)
