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
import logging
import sys
from . import __version__
from .store import STORE_TYPE_CALENDAR, STORE_TYPE_ADDRESSBOOK


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


def add_create_collection_parser(parser):
    """Add arguments for the create-collection subcommand."""
    parser.add_argument(
        "-d",
        "--directory",
        type=str,
        required=True,
        help="Root directory containing collections",
    )
    parser.add_argument(
        "--type",
        choices=["calendar", "addressbook"],
        required=True,
        help="Type of collection to create",
    )
    parser.add_argument(
        "--name",
        type=str,
        required=True,
        help="Name of the collection (used as path component)",
    )
    parser.add_argument(
        "--displayname", type=str, help="Display name for the collection"
    )
    parser.add_argument(
        "--description", type=str, help="Description for the collection"
    )
    parser.add_argument(
        "--color", type=str, help="Color for the collection (hex format, e.g., #FF0000)"
    )


async def create_collection_main(args, parser):
    """Main function for the create-collection subcommand."""
    from .web import XandikosBackend

    logger = logging.getLogger(__name__)

    backend = XandikosBackend(args.directory)
    collection_path = args.name
    collection_type = (
        STORE_TYPE_CALENDAR if args.type == "calendar" else STORE_TYPE_ADDRESSBOOK
    )

    try:
        resource = backend.create_collection(collection_path)
    except FileExistsError:
        logger.error(f"Collection '{collection_path}' already exists")
        return 1

    resource.store.set_type(collection_type)

    if args.displayname:
        resource.store.set_displayname(args.displayname)

    if args.description:
        resource.store.set_description(args.description)

    if args.color:
        resource.store.set_color(args.color)

    logger.info(f"Successfully created {args.type} collection: {collection_path}")
    return 0


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

    create_parser = subparsers.add_parser(
        "create-collection", help="Create a calendar or address book collection"
    )
    add_create_collection_parser(create_parser)

    set_default_subparser(parser, argv, "serve")
    args = parser.parse_args(argv)

    if args.subcommand == "serve":
        return await web.main(args, parser)
    elif args.subcommand == "create-collection":
        # Configure logging for create-collection subcommand
        logging.basicConfig(level=logging.INFO, format="%(message)s")
        return await create_collection_main(args, parser)
    else:
        parser.print_help()
        return 1


def cli_main():
    """Entry point for the command-line interface (for setuptools console_scripts)."""
    sys.exit(asyncio.run(main(sys.argv[1:])))


if __name__ == "__main__":
    cli_main()
