#
# This file is part of SickGear.
#
# SickGear is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# SickGear is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with SickGear.  If not, see <http://www.gnu.org/licenses/>.

import datetime
import itertools
import os.path
import re
import sqlite3
import threading
import time

from exceptions_helper import ex

import sickgear
from . import logger, sgdatetime
from .sgdatetime import SGDatetime

from sg_helpers import make_path, compress_file, remove_file_perm, scantree

from _23 import scandir

# noinspection PyUnreachableCode
if False:
    # noinspection PyUnresolvedReferences
    from typing import Any, AnyStr, Dict, List, Optional, Tuple, Union


db_lock = threading.Lock()
db_support_multiple_insert = (3, 7, 11) <= sqlite3.sqlite_version_info  # type: bool
db_support_partial_index = (3, 8, 0) <= sqlite3.sqlite_version_info  # type: bool
db_support_column_rename = (3, 25, 0) <= sqlite3.sqlite_version_info  # type: bool
db_support_upsert = (3, 25, 0) <= sqlite3.sqlite_version_info  # type: bool
db_supports_backup = hasattr(sqlite3.Connection, 'backup') and (3, 6, 11) <= sqlite3.sqlite_version_info  # type: bool
db_supports_setconfig_dqs = (hasattr(sqlite3.Connection, 'setconfig') and hasattr(sqlite3, 'SQLITE_DBCONFIG_DQS_DDL')
                             and hasattr(sqlite3, 'SQLITE_DBCONFIG_DQS_DML'))  # type: bool


def db_filename(filename='sickbeard.db', suffix=None):
    # type: (AnyStr, Optional[AnyStr]) -> AnyStr
    """
    @param filename: The sqlite database filename to use. If not specified,
                     will be made to be sickbeard.db
    @param suffix: The suffix to append to the filename. A '.' will be added
                   automatically, i.e. suffix='v0' will make dbfile.db.v0
    @return: the correct location of the database file.
    """
    if suffix:
        filename = f'{filename}.{suffix}'
    return os.path.join(sickgear.DATA_DIR, filename)


def mass_upsert_sql(table_name, value_dict, key_dict, sanitise=True):
    # type: (AnyStr, Dict, Dict, bool) -> List[List[AnyStr]]
    """
    use with cl.extend(mass_upsert_sql(tableName, valueDict, keyDict))

    :param table_name: table name
    :param value_dict: dict of values to be set {'table_fieldname': value}
    :param key_dict: dict of restrains for update {'table_fieldname': value}
    :param sanitise: True to remove k, v pairs in keyDict from valueDict as they must not exist in both.
    This option has a performance hit, so it's best to remove key_dict keys from value_dict and set this False instead.
    :type sanitise: Boolean
    :return: list of 2 sql command
    """
    # sanity: remove k, v pairs in keyDict from valueDict
    if sanitise:
        value_dict = dict(filter(lambda k: k[0] not in key_dict, value_dict.items()))

    gen_params = (lambda my_dict: [f'{x} = ?' for x in my_dict.keys()])

    if db_support_upsert:
        # noinspection SqlResolve
        update_sql = [f'UPDATE SET {", ".join(gen_params(value_dict))}'
                      f' WHERE {" AND ".join(gen_params(key_dict))}',
                      list(value_dict.values()) + list(key_dict.values())]

        ks = list(itertools.chain(value_dict.keys(), key_dict.keys()))
        if not sanitise:
            value_dict = dict(filter(lambda k: k[0] not in key_dict, value_dict.items()))
        vs = list(itertools.chain(value_dict.values(), key_dict.values()))
        # noinspection SqlResolve
        return [[
            'INSERT INTO [' + table_name + '] (' +
            ', '.join(["'%s'" % ('%s' % v).replace("'", "''") for v in ks]) + ')' +
            ' VALUES (' + ','.join(['?'] * len(ks)) + ')' +
            ' ON CONFLICT DO ' +
            update_sql[0],
            vs + update_sql[1]]]

    # noinspection SqlResolve
    update_sql = [f'UPDATE [{table_name}] SET {", ".join(gen_params(value_dict))}'
                  f' WHERE {" AND ".join(gen_params(key_dict))}',
                  list(value_dict.values()) + list(key_dict.values())]

    sql_l = [update_sql]

    # noinspection SqlResolve
    sql_l.append(['INSERT INTO [' + table_name + '] ('
                  + ', '.join(["'%s'" % ('%s' % v).replace("'", "''") for v in
                               itertools.chain(value_dict.keys(), key_dict.keys())]) + ')'
                  + ' SELECT ' + ', '.join(["'%s'" % ('%s' % v).replace("'", "''") for v in
                                            itertools.chain(value_dict.values(), key_dict.values())])
                  + ' WHERE changes() = 0'])
    return sql_l


class DBConnection(object):
    def __init__(self, filename='sickbeard.db', row_type=None, **kwargs):
        # type: (AnyStr, Optional[AnyStr], Dict) -> None

        self.new_db = False
        db_src = db_filename(filename)

        self.filename = filename
        self.connection = sqlite3.connect(db_src, timeout=20)   # , check_same_thread=False)
        # enable legacy double quote support
        if db_supports_setconfig_dqs:
            self.connection.setconfig(sqlite3.SQLITE_DBCONFIG_DQS_DDL, True)
            self.connection.setconfig(sqlite3.SQLITE_DBCONFIG_DQS_DML, True)

        if 'dict' == row_type:
            self.connection.row_factory = self._dict_factory
        else:
            self.connection.row_factory = sqlite3.Row

    def __enter__(self):
        # type: (...) -> DBConnection
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if getattr(self, 'connection', None):
            self.connection.close()

    def backup_db(self, target, backup_filename=None):
        # type: (AnyStr, AnyStr) -> Tuple[bool, AnyStr]
        """
        backup the db to target dir + optional filename

        Availability: SQLite 3.6.11 or higher
        New in version 3.7

        :param target: target dir
        :param backup_filename: optional backup filename (default is the source name)
        :return: success, message
        """
        if not db_supports_backup:
            logger.debug('this python sqlite3 version doesn\'t support backups')
            return False, 'this python sqlite3 version doesn\'t support backups'

        if not os.path.isdir(target):
            logger.error('Backup target invalid')
            return False, 'Backup target invalid'

        target_db = os.path.join(target, (backup_filename, self.filename)[None is backup_filename])
        if os.path.exists(target_db):
            logger.error('Backup target file already exists')
            return False, 'Backup target file already exists'

        # noinspection PyUnusedLocal
        def progress(status, remaining, total):
            logger.debug(f'Copied {total - remaining} of {total} pages...')

        backup_con = None

        try:
            # copy into this DB
            backup_con = sqlite3.connect(target_db, timeout=20)
            with backup_con:
                with db_lock:
                    self.connection.backup(backup_con, progress=progress)
            logger.debug(f'{self.filename} backup successful')
        except sqlite3.Error as error:
            logger.error(f'Error while taking backup: {ex(error)}')
            return False, 'Backup failed'
        finally:
            if backup_con:
                try:
                    backup_con.close()
                except (BaseException, Exception):
                    pass

        return True, 'Backup successful'

    def check_db_version(self):
        # type: (...) -> int

        try:
            if self.has_table('db_version'):
                result = self.select('SELECT db_version FROM db_version')
            else:
                version = self.select('PRAGMA user_version')[0]['user_version']
                if version:
                    self.action('PRAGMA user_version = 0')
                    self.action('CREATE TABLE db_version (db_version INTEGER);')
                    self.action(f'INSERT INTO db_version (db_version) VALUES ({version});')
                return version
        except (BaseException, Exception):
            return 0

        if result:
            version = int(result[0]['db_version'])
            if 10000 > version and self.has_column('db_version', 'db_minor_version'):
                # noinspection SqlResolve
                minor = self.select('SELECT db_minor_version FROM db_version')
                return version * 100 + int(minor[0]['db_minor_version'])
            return version
        return 0

    def mass_action(self, queries, log_transaction=False):
        # type: (List[Union[List[AnyStr], Tuple[AnyStr, List], Tuple[AnyStr]]], bool) -> Optional[List, sqlite3.Cursor]

        from . import helpers
        with db_lock:

            if None is queries:
                return

            if not queries:
                return []

            attempt = 0

            sql_result = []
            affected = 0
            while 5 > attempt:
                try:
                    cursor = self.connection.cursor()
                    if not log_transaction:
                        for cur_query in queries:
                            sql_result.append(cursor.execute(*tuple(cur_query)).fetchall())
                            affected += abs(cursor.rowcount)
                    else:
                        for cur_query in queries:
                            logger.log(cur_query[0] if 1 == len(cur_query)
                                       else '%s with args %s' % tuple(cur_query), logger.DB)
                            sql_result.append(cursor.execute(*tuple(cur_query)).fetchall())
                            affected += abs(cursor.rowcount)

                    self.connection.commit()
                    if 0 < affected:
                        logger.debug(f'Transaction with {len(queries)} queries executed affected at least {affected:d}'
                                     f' row{helpers.maybe_plural(affected)}')
                    return sql_result
                except sqlite3.OperationalError as e:
                    sql_result = []
                    if self.connection:
                        self.connection.rollback()
                    if not self.action_error(e):
                        raise
                    attempt += 1
                except sqlite3.DatabaseError as e:
                    if self.connection:
                        self.connection.rollback()
                    logger.error(f'Fatal error executing query: {ex(e)}')
                    raise

            return sql_result

    @staticmethod
    def action_error(e):

        if 'unable to open database file' in e.args[0] or 'database is locked' in e.args[0]:
            logger.warning(f'DB error: {ex(e)}')
            time.sleep(1)
            return True
        logger.error(f'DB error: {ex(e)}')

    def action(self, query, args=None):
        # type: (AnyStr, Optional[List, Tuple]) -> Optional[Union[List, sqlite3.Cursor]]

        with db_lock:

            if None is query:
                return

            sql_result = None
            attempt = 0

            while 5 > attempt:
                try:
                    if None is args:
                        logger.log(f'{self.filename}: {query}', logger.DB)
                        sql_result = self.connection.execute(query)
                    else:
                        logger.log(f'{self.filename}: {query} with args {args!s}', logger.DB)
                        sql_result = self.connection.execute(query, args)
                    self.connection.commit()
                    # get out of the connection attempt loop since we were successful
                    break
                except sqlite3.OperationalError as e:
                    if not self.action_error(e):
                        raise
                    attempt += 1
                except sqlite3.DatabaseError as e:
                    logger.error(f'Fatal error executing query: {ex(e)}')
                    raise

            return sql_result

    def select(self, query, args=None):
        # type: (AnyStr, Optional[List, Tuple]) -> List

        sql_results = self.action(query, args).fetchall()

        if None is sql_results:
            return []

        return sql_results

    def upsert(self, table_name, value_dict, key_dict):
        # type: (AnyStr, Dict, Dict) -> None

        changes_before = self.connection.total_changes

        gen_params = (lambda my_dict: [f'{x} = ?' for x in my_dict.keys()])

        # noinspection SqlResolve
        query = (f'UPDATE [{table_name}]'
                 f' SET {", ".join(gen_params(value_dict))}'
                 f' WHERE {" AND ".join(gen_params(key_dict))}')

        self.action(query, list(value_dict.values()) + list(key_dict.values()))

        if self.connection.total_changes == changes_before:
            # noinspection SqlResolve
            query = (f'INSERT INTO [{table_name}]'
                     f' ({", ".join(itertools.chain(value_dict.keys(), key_dict.keys()))})'
                     f' VALUES ({", ".join(["?"] * (len(value_dict) + len(key_dict)))})')
            self.action(query, list(value_dict.values()) + list(key_dict.values()))

    def table_info(self, table_name):
        # type: (AnyStr) -> Dict[AnyStr, Dict[AnyStr, AnyStr]]

        # SQLite 3.16.0+ supports bindings with the table-valued pragma_table_info() function
        # and replaces the unsafe self.select(f'PRAGMA table_info([{table_name}])')
        return {_r['name']: {'type': _r['type']}
                for _r in self.select('SELECT * FROM pragma_table_info(?)', (table_name,))}

    @staticmethod
    def _dict_factory(cursor, row):
        return {col[0]: row[idx] for idx, col in enumerate(cursor.description)}

    def has_table(self, table_name):
        # type: (AnyStr) -> bool
        return 0 < len(self.select('SELECT 1 FROM sqlite_master WHERE name = ?;', (table_name,)))

    def has_column(self, table_name, column):
        # type: (AnyStr, AnyStr) -> bool
        return column in self.table_info(table_name)

    def has_index(self, table_name, index):
        # type: (AnyStr, AnyStr) -> bool
        return any([index == _r['name']
                    for _r in self.select('SELECT name FROM pragma_index_list(?)', (table_name,))])

    def remove_index(self, table, name):
        # type: (AnyStr, AnyStr) -> None
        if self.has_index(table, name):
            self.action(f'DROP INDEX [{name}]')

    def remove_table(self, name):
        # type: (AnyStr) -> None
        if self.has_table(name):
            self.action(f'DROP TABLE [{name}]')

    def has_flag(self, flag_name):
        # type: (AnyStr) -> bool
        sql_result = self.select('SELECT flag FROM flags WHERE flag = ?', [flag_name])
        return 0 < len(sql_result)

    def add_flag(self, flag_name):
        # type: (AnyStr) -> bool
        has_flag = self.has_flag(flag_name)
        if not has_flag:
            self.action('INSERT INTO flags (flag) VALUES (?)', [flag_name])
        return not has_flag

    def remove_flag(self, flag_name):
        # type: (AnyStr) -> bool
        has_flag = self.has_flag(flag_name)
        if has_flag:
            self.action('DELETE FROM flags WHERE flag = ?', [flag_name])
        return has_flag

    def toggle_flag(self, flag_name):
        # type: (AnyStr) -> bool
        """
        Add or remove a flag
        :param flag_name: Name of flag
        :return: True if this call added the flag, False if flag is removed
        """
        if self.remove_flag(flag_name):
            return False
        self.add_flag(flag_name)
        return True

    def set_flag(self, flag_name, state=True):
        # type: (AnyStr, bool) -> bool
        """
        Set state of flag
        :param flag_name: Name of flag
        :param state: If true, create flag otherwise remove flag
        :return: Previous state of flag
        """
        return (self.add_flag, self.remove_flag)[not bool(state)](flag_name)

    def close(self):
        """Close database connection"""
        if None is not getattr(self, 'connection', None):
            self.connection.close()
        self.connection = None

    def upgrade_log(self, to_log, log_level=logger.MESSAGE):
        # type: (AnyStr, int) -> None
        logger.load_log(f'Upgrading {self.filename}', to_log, log_level)


def sanity_check_db(connection, sanity_check):
    sanity_check(connection).check()


class DBSanityCheck(object):
    def __init__(self, connection):
        self.connection = connection

    def check(self):
        pass


def upgrade_database(connection, schema):
    logger.log('Checking database structure...', logger.MESSAGE)
    connection.is_upgrading = False
    connection.new_db = 0 == connection.check_db_version()
    _process_upgrade(connection, schema)
    if connection.is_upgrading:
        connection.upgrade_log('Finished')


def _pretty_name(class_name):
    # type: (AnyStr) -> AnyStr
    return ' '.join([x.group() for x in re.finditer('([A-Z])([a-z0-9]+)', class_name)])


def _restore_database(filename, version):
    logger.log('Restoring database before trying upgrade again')
    if not sickgear.helpers.restore_versioned_file(db_filename(filename=filename, suffix=f'v{version}'), version):
        logger.log_error_and_exit('Database restore failed, abort upgrading database')
        return False
    return True


def _process_upgrade(connection, upgrade_class):
    instance = upgrade_class(connection)
    logger.debug(f'Checking {_pretty_name(upgrade_class.__name__)} database upgrade')
    if not instance.test():
        connection.is_upgrading = True
        connection.upgrade_log(f'{getattr(upgrade_class, "pretty_name", None) or _pretty_name(upgrade_class.__name__)}')
        logger.log(f'Database upgrade required: "{_pretty_name(upgrade_class.__name__)}"', logger.MESSAGE)
        db_version = connection.check_db_version()
        try:
            # only do backup if it's not a new db
            0 < db_version and backup_database(connection, connection.filename, db_version)
            instance.execute()
            cleanup_old_db_backups(connection.filename)
        except (BaseException, Exception):
            # attempting to restore previous DB backup and perform upgrade
            if db_version:
                # close db before attempting restore
                connection.close()

                if _restore_database(connection.filename, db_version):
                    logger.log_error_and_exit(f'Successfully restored database version: {db_version}')
                else:
                    logger.log_error_and_exit(f'Failed to restore database version: {db_version}')
            else:
                logger.log_error_and_exit('Database upgrade failed, can\'t determine old db version, not restoring.')

        logger.debug(f'{upgrade_class.__name__} upgrade completed')
    else:
        logger.debug(f'{upgrade_class.__name__} upgrade not required')

    for upgradeSubClass in upgrade_class.__subclasses__():
        _process_upgrade(connection, upgradeSubClass)


# Base migration class. All future DB changes should be subclassed from this class
class SchemaUpgrade(object):
    def __init__(self, connection, **kwargs):
        self.connection = connection

    def has_table(self, table_name):
        return 0 < len(self.connection.select('SELECT 1 FROM sqlite_master WHERE name = ?;', (table_name,)))

    def has_column(self, table_name, column):
        return column in self.connection.table_info(table_name)

    def list_tables(self):
        # type: (...) -> List[AnyStr]
        """
        returns list of all table names in db
        """
        return [s['name'] for s in self.connection.select('SELECT name FROM main.sqlite_master WHERE type = ?;',
                                                          ['table'])]

    def list_indexes(self):
        # type: (...) -> List[AnyStr]
        """
        returns list of all index names in db
        """
        return [s['name'] for s in self.connection.select('SELECT name FROM main.sqlite_master WHERE type = ?;',
                                                          ['index'])]

    # noinspection SqlResolve
    def add_column(self, table, column, data_type='NUMERIC', default=0, set_default=False):
        self.connection.action('ALTER TABLE [%s] ADD %s %s%s' %
                               (table, column, data_type, ('', ' DEFAULT "%s"' % default)[set_default]))
        self.connection.action(f'UPDATE [{table}] SET {column} = ?', (default,))

    # noinspection SqlResolve
    def add_columns(self, table, column_list=None):
        # type: (AnyStr, List) -> None
        if isinstance(column_list, list):
            sql = []
            for col in column_list:
                is_list = isinstance(col, (list, tuple))
                list_len = 0 if not is_list else len(col)
                column = col if not is_list else col[0]
                data_type = 'NUMERIC' if not is_list or 2 > list_len else col[1]
                default = 0 if not is_list or 3 > list_len else col[2]
                sql.append(['ALTER TABLE [%s] ADD %s %s%s' %
                            (table, column, data_type, '' if list_len < 3 else
                                ' DEFAULT %s' % ('""' if 'TEXT' == data_type and '' == default else default))])
                if 2 < list_len:
                    sql.append([f'UPDATE [{table}] SET {column} = ?', (default,)])
            if sql:
                self.connection.mass_action(sql)

    def drop_columns(self, table, column):
        # type: (AnyStr, Union[AnyStr, List[AnyStr]]) -> None
        # get old table columns and store the ones we want to keep
        result = self.connection.select(f'pragma table_info([{table}])')
        columns_list = ([column], column)[isinstance(column, list)]
        kept_columns = list(filter(lambda col: col['name'] not in columns_list, result))

        kept_columns_names = []
        final = []
        pk = []

        # copy the old table schema, column by column
        for column in kept_columns:

            kept_columns_names.append(column['name'])

            cl = [column['name'], column['type']]

            '''
            To be implemented if ever required
            if column['dflt_value']:
                cl.append(str(column['dflt_value']))

            if column['notnull']:
                cl.append(column['notnull'])
            '''

            if 0 != int(column['pk']):
                pk.append(column['name'])

            b = ' '.join(cl)
            final.append(b)

        # join all the table column creation fields
        final = ', '.join(final)
        kept_columns_names = ', '.join(kept_columns_names)

        # generate sql for the new table creation
        if 0 == len(pk):
            sql = f'CREATE TABLE [{table}_new] ({final})'
        else:
            pk = ', '.join(pk)
            sql = f'CREATE TABLE [{table}_new] ({final}, PRIMARY KEY({pk}))'

        # create new temporary table and copy the old table data across, barring the removed column
        self.connection.action(sql)
        # noinspection SqlResolve
        self.connection.action(f'INSERT INTO [{table}_new] SELECT {kept_columns_names} FROM [{table}]')

        # copy the old indexes from the old table
        result = self.connection.select("SELECT sql FROM sqlite_master WHERE tbl_name=? AND type='index'", [table])

        # remove the old table and rename the new table to take its place
        # noinspection SqlResolve
        self.connection.action(f'DROP TABLE [{table}]')
        # noinspection SqlResolve
        self.connection.action(f'ALTER TABLE [{table}_new] RENAME TO [{table}]')

        # write any indexes to the new table
        if 0 < len(result):
            for index in result:
                self.connection.action(index['sql'])

        # vacuum the db as we will have a lot of space to reclaim after dropping tables
        self.connection.action('VACUUM')

    def call_check_db_version(self):
        return self.connection.check_db_version()

    def inc_db_version(self):
        new_version = self.call_check_db_version() + 1
        # noinspection SqlConstantCondition
        self.connection.action('UPDATE db_version SET db_version = ? WHERE 1=1', [new_version])
        return new_version

    def set_db_version(self, new_version, check_db_version=True):
        # noinspection SqlConstantCondition
        self.connection.action('UPDATE db_version SET db_version = ? WHERE 1=1', [new_version])
        return check_db_version and self.call_check_db_version()

    def do_query(self, queries):
        if not isinstance(queries, list):
            queries = list(queries)
        elif isinstance(queries[0], list):
            queries = [item for sublist in queries for item in sublist]

        for query in queries:
            tbl_name = re.findall(r'(?i)DROP.*?TABLE.*?\[?([^\s\]]+)', query)
            if tbl_name and not self.has_table(tbl_name[0]):
                continue
            tbl_name = re.findall(r'(?i)CREATE.*?TABLE.*?\s([^\s(]+)\s*\(', query)
            if tbl_name and self.has_table(tbl_name[0]):
                continue
            self.connection.action(query)

    def finish(self, tbl_dropped=False):
        if tbl_dropped:
            self.connection.action('VACUUM')
        self.inc_db_version()

    def upgrade_log(self, *args, **kwargs):
        self.connection.upgrade_log(*args, **kwargs)


def migration_code(sg_db):
    schema = {
        0: sickgear.mainDB.InitialSchema,
        9: sickgear.mainDB.AddSizeAndSceneNameFields,
        10: sickgear.mainDB.RenameSeasonFolders,
        11: sickgear.mainDB.Add1080pAndRawHDQualities,
        12: sickgear.mainDB.AddShowidTvdbidIndex,
        13: sickgear.mainDB.AddLastUpdateTVDB,
        14: sickgear.mainDB.AddDBIncreaseTo15,
        15: sickgear.mainDB.AddIMDbInfo,
        16: sickgear.mainDB.AddProperNamingSupport,
        17: sickgear.mainDB.AddEmailSubscriptionTable,
        18: sickgear.mainDB.AddProperSearch,
        19: sickgear.mainDB.AddDvdOrderOption,
        20: sickgear.mainDB.AddSubtitlesSupport,
        21: sickgear.mainDB.ConvertTVShowsToIndexerScheme,
        22: sickgear.mainDB.ConvertTVEpisodesToIndexerScheme,
        23: sickgear.mainDB.ConvertIMDBInfoToIndexerScheme,
        24: sickgear.mainDB.ConvertInfoToIndexerScheme,
        25: sickgear.mainDB.AddArchiveFirstMatchOption,
        26: sickgear.mainDB.AddSceneNumbering,
        27: sickgear.mainDB.ConvertIndexerToInteger,
        28: sickgear.mainDB.AddRequireAndIgnoreWords,
        29: sickgear.mainDB.AddSportsOption,
        30: sickgear.mainDB.AddSceneNumberingToTvEpisodes,
        31: sickgear.mainDB.AddAnimeTVShow,
        32: sickgear.mainDB.AddAbsoluteNumbering,
        33: sickgear.mainDB.AddSceneAbsoluteNumbering,
        34: sickgear.mainDB.AddAnimeAllowlistBlocklist,
        35: sickgear.mainDB.AddSceneAbsoluteNumbering2,
        36: sickgear.mainDB.AddXemRefresh,
        37: sickgear.mainDB.AddSceneToTvShows,
        38: sickgear.mainDB.AddIndexerMapping,
        39: sickgear.mainDB.AddVersionToTvEpisodes,

        40: sickgear.mainDB.BumpDatabaseVersion,
        41: sickgear.mainDB.Migrate41,
        42: sickgear.mainDB.Migrate41,
        43: sickgear.mainDB.Migrate43,
        44: sickgear.mainDB.Migrate43,

        4301: sickgear.mainDB.Migrate4301,
        4302: sickgear.mainDB.Migrate4302,
        4400: sickgear.mainDB.Migrate4302,

        5816: sickgear.mainDB.MigrateUpstream,
        5817: sickgear.mainDB.MigrateUpstream,
        5818: sickgear.mainDB.MigrateUpstream,

        10000: sickgear.mainDB.SickGearDatabaseVersion,
        10001: sickgear.mainDB.RemoveDefaultEpStatusFromTvShows,
        10002: sickgear.mainDB.RemoveMinorDBVersion,
        10003: sickgear.mainDB.RemoveMetadataSub,

        20000: sickgear.mainDB.DBIncreaseTo20001,
        20001: sickgear.mainDB.AddTvShowOverview,
        20002: sickgear.mainDB.AddTvShowTags,
        20003: sickgear.mainDB.ChangeMapIndexer,
        20004: sickgear.mainDB.AddShowNotFoundCounter,
        20005: sickgear.mainDB.AddFlagTable,
        20006: sickgear.mainDB.DBIncreaseTo20007,
        20007: sickgear.mainDB.AddWebdlTypesTable,
        20008: sickgear.mainDB.AddWatched,
        20009: sickgear.mainDB.AddPrune,
        20010: sickgear.mainDB.AddIndexerToTables,
        20011: sickgear.mainDB.AddShowExludeGlobals,
        20012: sickgear.mainDB.RenameAllowBlockListTables,
        20013: sickgear.mainDB.AddHistoryHideColumn,
        20014: sickgear.mainDB.ChangeShowData,
        20015: sickgear.mainDB.ChangeTmdbID,
        # 20002: sickgear.mainDB.AddCoolSickGearFeature3,
    }

    db_version = sg_db.check_db_version()
    sg_db.new_db = 0 == db_version
    logger.debug(f'Detected database version: v{db_version}')

    if not (db_version in schema):
        if db_version == sickgear.mainDB.MAX_DB_VERSION:
            logger.log('Database schema is up-to-date, no upgrade required')
        elif 10000 > db_version:
            logger.log_error_and_exit('SickGear does not currently support upgrading from this database version')
        else:
            logger.log_error_and_exit('Invalid database version')

    else:

        sg_db.upgrade_log('Upgrading')
        while db_version < sickgear.mainDB.MAX_DB_VERSION:
            if None is schema[db_version]:  # skip placeholders used when multi PRs are updating DB
                db_version += 1
                continue
            try:
                update = schema[db_version](sg_db)
                db_version = update.execute()
                cleanup_old_db_backups(sg_db.filename)
            except (BaseException, Exception) as e:
                sg_db.close()
                logger.error(f'Failed to update database with error: {ex(e)} attempting recovery...')

                if _restore_database(sg_db.filename, db_version):
                    # initialize the main SB database
                    logger.log_error_and_exit(f'Successfully restored database version: {db_version}')
                else:
                    logger.log_error_and_exit(f'Failed to restore database version: {db_version}')
        sg_db.upgrade_log('Finished')


def cleanup_old_db_backups(filename):
    try:
        d, filename = os.path.split(filename)
        if not d:
            d = sickgear.DATA_DIR
        with scandir(d) as s_d:
            for f in filter(lambda fn: fn.is_file() and filename in fn.name and
                            re.search(r'\.db(\.v\d+)?\.r\d+$', fn.name), s_d):
                try:
                    os.unlink(f.path)
                except (BaseException, Exception):
                    pass
    except (BaseException, Exception):
        pass


def backup_database(db_connection, filename, version):

    if db_connection.new_db:
        logger.debug('new db, no backup required')
        return

    logger.log('Backing up database before upgrade')
    if not sickgear.helpers.backup_versioned_file(db_filename(filename), version):
        logger.log_error_and_exit('Database backup failed, abort upgrading database')
    else:
        logger.log('Proceeding with upgrade')


def get_rollback_module():
    import types
    from . import helpers

    module_urls = [
        'https://raw.githubusercontent.com/SickGear/sickgear.extdata/main/SickGear/Rollback/rollback_sg.py']

    try:
        hdr = '# SickGear Rollback Module'
        module = ''
        fetched = False

        for t in range(1, 4):
            for url in module_urls:
                try:
                    module = helpers.get_url(url)
                    if module and module.startswith(hdr):
                        fetched = True
                        break
                except (BaseException, Exception):
                    continue
            if fetched:
                break
            time.sleep(30)

        if fetched:
            loaded = types.ModuleType('DbRollback')
            exec(module, loaded.__dict__)
            return loaded

    except (BaseException, Exception):
        pass


def delete_old_db_backups(target):
    # type: (AnyStr) -> None
    """
    remove old db backups (> BACKUP_DB_MAX_COUNT)

    :param target: backup folder to check
    """
    use_count = (1, sickgear.BACKUP_DB_MAX_COUNT)[not sickgear.BACKUP_DB_ONEDAY]
    for include in ['sickbeard', 'cache', 'failed']:
        file_list = [f for f in scantree(target, include=include, filter_kind=False)]
        if use_count < len(file_list):
            file_list.sort(key=lambda _f: _f.stat(follow_symlinks=False).st_mtime, reverse=True)
            for direntry in file_list[use_count:]:
                remove_file_perm(direntry.path)


def backup_all_dbs(target, compress=True, prefer_7z=True):
    # type: (AnyStr, bool, bool) -> Tuple[bool, AnyStr]
    """
    backups all dbs to specified dir

    optional compress with zip or 7z (python 3 only, external lib py7zr required)
    7z falls back to zip if py7zr is not available

    :param target: target folder for backup db
    :param compress: compress db backups
    :param prefer_7z: prefer 7z compression if available
    :return: success, message
    """
    if not make_path(target):
        logger.error('Failed to create db backup dir')
        return False, 'Failed to create db backup dir'
    with DBConnection('cache.db') as sg_db:
        last_backup = sg_db.select('SELECT time FROM lastUpdate WHERE provider = ?', ['sickgear_db_backup'])
        if last_backup:
            now_stamp = SGDatetime.timestamp_near()
            the_time = int(last_backup[0]['time'])
            # only backup every 23 hours
            if now_stamp - the_time < 60 * 60 * 23:
                return False, 'Too early to backup db again'
        now = sgdatetime.SGDatetime.now()
        d = sgdatetime.SGDatetime.sbfdate(now, d_preset='%Y-%m-%d')
        t = sgdatetime.SGDatetime.sbftime(now, t_preset='%H-%M')
        ds = f'{d}_{t}'
        for cur_db in ['sickbeard', 'cache', 'failed']:
            with DBConnection(f'{cur_db}.db') as db_conn:
                name = f'{cur_db}_{ds}.db'
                success, msg = db_conn.backup_db(target=target, backup_filename=name)
                if not success:
                    return False, msg
                if compress:
                    full_path = os.path.join(target, name)
                    if not compress_file(full_path, f'{cur_db}.db', prefer_7z=prefer_7z):
                        return False, 'Failure to compress backup'
        delete_old_db_backups(target)
        sg_db.upsert('lastUpdate',
                     {'time': int(time.mktime(now.timetuple()))},
                     {'provider': 'sickgear_db_backup'})
        logger.log('successfully backed up all dbs')
    return True, 'successfully backed up all dbs'

def sg_db_select_helper(*args, **kwargs):
    """
    helper for Cheetah doesn't allow indentation for context manger

    :param args: select string
    :param kwargs: db connection arguments per keyword
    """
    with DBConnection(**kwargs) as sg_db:
        return sg_db.select(*args)
