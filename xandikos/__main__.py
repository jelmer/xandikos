# Xandikos
# Copyright (C) 2016-2018 Jelmer Vernooĳ <jelmer@jelmer.uk>, et al.
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

"""Xandikos command-line handling."""

import argparse
import asyncio
import sys
from . import __version__


# If no subparser is given, default to 'serve'
def set_default_subparser(self, argv, name):
    subparser_found = False
    for arg in argv:
        if arg in ["-h", "--help", "--version"]:
            break
    else:
        for x in self._subparsers._actions:
            if not isinstance(x, argparse._SubParsersAction):
                continue
            for sp_name in x._name_parser_map.keys():
                if sp_name in argv:
                    subparser_found = True
        if not subparser_found:
            print('No subcommand given, defaulting to "%s"' % name)
            argv.insert(0, name)


async def main(argv):
    # For now, just invoke xandikos.web
    from . import web

    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--version",
        action="version",
        version="%(prog)s " + ".".join(map(str, __version__)),
    )

    subparsers = parser.add_subparsers(help="Subcommands", dest="subcommand")
    web_parser = subparsers.add_parser(
        "serve", usage="%(prog)s -d ROOT-DIR [OPTIONS]", help="Run a Xandikos server"
    )
    web.add_parser(web_parser)

    set_default_subparser(parser, argv, "serve")
    args = parser.parse_args(argv)

    if args.subcommand == "serve":
        return await web.main(args, parser)
    else:
        parser.print_help()
        return 1


if __name__ == "__main__":
    import sys

    sys.exit(asyncio.run(main(sys.argv[1:])))
