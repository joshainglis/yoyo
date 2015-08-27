# Copyright 2015 Oliver Cope
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from __future__ import print_function
import logging
import argparse
import os
import re
import sys

from getpass import getpass

from yoyo.compat import SafeConfigParser, NoSectionError, NoOptionError
from yoyo.connections import connect, parse_uri, unparse_uri
from yoyo.utils import prompt, plural
from yoyo import read_migrations, default_migration_table
from yoyo import logger

verbosity_levels = {
    0: logging.ERROR,
    1: logging.WARN,
    2: logging.INFO,
    3: logging.DEBUG
}

min_verbosity = min(verbosity_levels)
max_verbosity = max(verbosity_levels)

CONFIG_FILENAME = '.yoyorc'


class InvalidArgument(Exception):
    pass


def readconfig(path):
    if path is None:
        return SafeConfigParser()
    config = SafeConfigParser()
    config.read([path])
    return config


def saveconfig(config, path):
    os.umask(0o77)
    f = open(path, 'w')
    try:
        return config.write(f)
    finally:
        f.close()


class prompted_migration(object):

    def __init__(self, migration, default=None):
        super(prompted_migration, self).__init__()
        self.migration = migration
        self.choice = default


def prompt_migrations(conn, paramstyle, migrations, direction):
    """
    Iterate through the list of migrations and prompt the user to
    apply/rollback each. Return a list of user selected migrations.

    direction
        one of 'apply' or 'rollback'
    """
    migrations = migrations.replace(prompted_migration(m) for m in migrations)

    position = 0
    while position < len(migrations):
        mig = migrations[position]

        choice = mig.choice
        if choice is None:
            isapplied = mig.migration.isapplied(conn, paramstyle,
                                                migrations.migration_table)
            if direction == 'apply':
                choice = 'n' if isapplied else 'y'
            else:
                choice = 'y' if isapplied else 'n'
        options = ''.join(o.upper() if o == choice else o.lower()
                          for o in 'ynvdaqjk?')

        print("")
        print('[%s]' % (mig.migration.id,))
        response = prompt("Shall I %s this migration?" % (direction,), options)

        if response == '?':
            print("")
            print("y: %s this migration" % (direction,))
            print("n: don't %s it" % (direction,))
            print("")
            print("v: view this migration in full")
            print("")
            print("d: %s the selected migrations, skipping any remaining" %
                    (direction,))
            print("a: %s all the remaining migrations" % (direction,))
            print("q: cancel without making any changes")
            print("")
            print("j: skip to next migration")
            print("k: back up to previous migration")
            print("")
            print("?: show this help")
            continue

        if response in 'yn':
            mig.choice = response
            position += 1
            continue

        if response == 'v':
            print(mig.migration.source)
            continue

        if response == 'j':
            position = min(len(migrations), position + 1)
            continue

        if response == 'k':
            position = max(0, position - 1)

        if response == 'd':
            break

        if response == 'a':
            for mig in migrations[position:]:
                mig.choice = 'y'
            break

        if response == 'q':
            for mig in migrations:
                mig.choice = 'n'
            break

    return migrations.replace(m.migration
                              for m in migrations
                              if m.choice == 'y')


def parse_args(argv=None):
    """
    Parse the config file and command line args.

    :return: tuple of (argparser, parsed_args)
    """
    globalparser, argparser, subparsers = make_argparser()

    # Initial parse to extract --config and any global arguments
    global_args, _ = globalparser.parse_known_args(argv)

    # Read the config file and set the argparser defaults to config file values
    config = readconfig(global_args.config or find_config())
    defaults_from_config = dict(config.items('DEFAULT'))
    argparser.set_defaults(**defaults_from_config)
    for subp in subparsers.choices.values():
        subp.set_defaults(**defaults_from_config)

    # Now parse for real
    args = argparser.parse_args(argv)

    # Update the args namespace with the previously parsed global args
    # result. This ensures that global args (eg '-v) are recognized regardless
    # of whether they were placed before or after the subparser command.
    # If we do not do this then the sub_parser copy of the argument takes
    # precedence, and overwrites any global args set before the command name.
    args.__dict__.update(global_args.__dict__)

    return config, argparser, args


def get_migrations(args):

    sources = args.sources
    dburi = args.database
    migration_table = args.migration_table

    if sources is None or dburi is None:
        raise InvalidArgument("Please specify command, migrations directory "
                              "and database connection arguments")

    if args.prompt_password:
        password = getpass('Password for %s: ' % dburi)
        scheme, username, _, host, port, database, db_params = parse_uri(dburi)
        dburi = unparse_uri((scheme, username, password, host, port, database, db_params))


    conn, paramstyle = connect(dburi)

    migrations = read_migrations(conn, paramstyle, sources,
                                 migration_table=migration_table)

    if args.match:
        migrations = migrations.filter(
            lambda m: re.search(args.match, m.id) is not None)

    if not args.all:
        if apply in args.funcs:
            migrations = migrations.to_apply()

        elif {rollback, reapply} & set(args.funcs):
            migrations = migrations.to_rollback()

    if not args.batch_mode:
        migrations = prompt_migrations(conn, paramstyle, migrations,
                                       args.command_name)

    if not args.batch_mode and migrations:
        if prompt(args.command_name.title() +
                  plural(len(migrations), " %d migration", " %d migrations") +
                  " to %s?" % dburi, "Yn") != 'y':
            return migrations.replace([])
    return migrations


def apply(args, migrations):
    migrations.apply(args.force)


def reapply(args, migrations):
    migrations.rollback(args.force)
    migrations.apply(args.force)


def rollback(args, migrations):
    migrations.rollback(args.force)


def make_argparser():
    """
    Return a top-level ArgumentParser parser object,
    plus a list of sub_parsers
    """
    global_args = argparse.ArgumentParser(add_help=False)
    global_args.add_argument("--config", "-c", default=None,
                             help="Path to config file")
    global_args.add_argument("-v",
                             dest="verbosity",
                             action="count",
                             default=min_verbosity,
                             help="Verbose output. Use multiple times "
                             "to increase level of verbosity")
    global_args.add_argument("-b",
                             "--batch",
                             dest="batch_mode",
                             action="store_true",
                             help="Run in batch mode"
                             ". Turns off all user prompts")

    migration_args = argparse.ArgumentParser(add_help=False)
    migration_args.add_argument('sources',
                                nargs="?",
                                help="Source directory of migration scripts")

    migration_args.add_argument("database",
                                nargs="?",
                                default=None,
                                help="Database, eg 'sqlite:///path/to/sqlite.db' "
                                "or 'postgresql://user@host/db'")

    migration_args.add_argument("-m", "--match",
                                help="Select migrations matching PATTERN (regular expression)",
                                metavar='PATTERN')

    migration_args.add_argument("-a",
                                "--all",
                                dest="all",
                                action="store_true",
                                help="Select all migrations, regardless of whether "
                                "they have been previously applied")

    migration_args.add_argument("-f", "--force", dest="force", action="store_true",
                                help="Force apply/rollback of steps even if "
                                "previous steps have failed")

    migration_args.add_argument("-p", "--prompt-password", dest="prompt_password",
                                action="store_true",
                                help="Prompt for the database password")

    migration_args.add_argument("--no-cache", dest="cache", action="store_false",
                                default=True,
                                help="Don't cache database login credentials")

    migration_args.add_argument("--migration-table", dest="migration_table",
                                action="store",
                                default=default_migration_table,
                                help="Name of table to use for storing "
                                "migration metadata")

    argparser = argparse.ArgumentParser(prog='yoyo-migrate',
                                        parents=[global_args])

    subparsers = argparser.add_subparsers(help='Commands help')
    parser_apply = subparsers.add_parser('apply',
                                         help="Apply migrations",
                                         parents=[global_args, migration_args])
    parser_apply.set_defaults(funcs=[get_migrations, apply],
                              command_name='apply')

    parser_rollback = subparsers.add_parser('rollback',
                                            parents=[global_args,
                                                     migration_args],
                                            help="Rollback migrations")
    parser_rollback.set_defaults(funcs=[get_migrations, rollback],
                                 command_name='rollback')

    parser_reapply = subparsers.add_parser('reapply',
                                           parents=[global_args,
                                                    migration_args],
                                           help="Reapply migrations")
    parser_reapply.set_defaults(funcs=[get_migrations, reapply],
                                command_name='reapply')

    return global_args, argparser, subparsers


def configure_logging(level):
    """
    Configure the python logging module with the requested loglevel
    """
    logging.basicConfig(level=verbosity_levels[level])


def find_config():
    """Find the closest config file in the cwd or a parent directory"""
    d = os.getcwd()
    while d != os.path.dirname(d):
        path = os.path.join(d, CONFIG_FILENAME)
        if os.path.isfile(path):
            return path
        d = os.path.dirname(d)
    return None


def prompt_save_config(config, path):
    # Offer to save the current configuration for future runs
    # Don't cache anything in batch mode (because we can't prompt to find the
    # user's preference).

    response = prompt("Save migration configuration to {}?\n"
                      "This is saved in plain text and "
                      "contains your database password.\n\n"
                      "Answering 'y' means you do not have to specify "
                      "the migration source or database connection "
                      "for future runs".format(path),
                      "yn")

    if response == 'y':
        saveconfig(config, CONFIG_FILENAME)


def main(argv=None):
    config, argparser, args = parse_args(argv)
    config_is_empty = (config.sections() == [] and
                       config.items('DEFAULT') == [])

    verbosity = args.verbosity
    verbosity = min(max_verbosity, max(min_verbosity, verbosity))
    configure_logging(verbosity)

    command_args = (args,)
    for f in args.funcs:
        try:
            result = f(*command_args)
        except InvalidArgument as e:
            argparser.error(e.args[0])

        if result is not None:
            command_args += (result,)

    if config_is_empty and args.cache and not args.batch_mode:
        config.set('DEFAULT', 'sources', args.sources)
        config.set('DEFAULT', 'database', args.database)
        config.set('DEFAULT', 'migration_table', args.migration_table)
        config.set('DEFAULT', 'batch_mode', 'off' if args.batch_mode else 'on')

        prompt_save_config(config, args.config or CONFIG_FILENAME)


if __name__ == "__main__":
    main(sys.argv[1:])
