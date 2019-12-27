# Author: Nic Wolfe <nic@wolfeden.ca>
# URL: http://code.google.com/p/sickbeard/
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

from __future__ import with_statement

import itertools
import os.path
import re
import sqlite3
import threading
import time

# noinspection PyPep8Naming
import encodingKludge as ek
from exceptions_helper import ex

import sickbeard
from . import logger

from _23 import filter_iter, list_values, scandir
from six import iterkeys, iteritems, itervalues

# noinspection PyUnreachableCode
if False:
    from typing import Any, AnyStr, Dict, List, Optional, Tuple, Union


db_lock = threading.Lock()


def dbFilename(filename='sickbeard.db', suffix=None):
    # type: (AnyStr, Optional[AnyStr]) -> AnyStr
    """
    @param filename: The sqlite database filename to use. If not specified,
                     will be made to be sickbeard.db
    @param suffix: The suffix to append to the filename. A '.' will be added
                   automatically, i.e. suffix='v0' will make dbfile.db.v0
    @return: the correct location of the database file.
    """
    if suffix:
        filename = '%s.%s' % (filename, suffix)
    return ek.ek(os.path.join, sickbeard.DATA_DIR, filename)


def mass_upsert_sql(table_name, value_dict, key_dict, sanitise=True):
    # type: (AnyStr, Dict, Dict, bool) -> List[List[AnyStr]]
    """
    use with cl.extend(mass_upsert_sql(tableName, valueDict, keyDict))

    :param table_name: table name
    :param value_dict: dict of values to be set {'table_fieldname': value}
    :param key_dict: dict of restrains for update {'table_fieldname': value}
    :param sanitise: True to remove k, v pairs in keyDict from valueDict as they must not exist in both.
    This option has a performance hit so it's best to remove key_dict keys from value_dict and set this False instead.
    :type sanitise: Boolean
    :return: list of 2 sql command
    """
    cl = []

    gen_params = (lambda my_dict: [x + ' = ?' for x in iterkeys(my_dict)])

    # sanity: remove k, v pairs in keyDict from valueDict
    if sanitise:
        value_dict = dict(filter_iter(lambda k: k[0] not in key_dict, iteritems(value_dict)))

    # noinspection SqlResolve
    cl.append(['UPDATE [%s] SET %s WHERE %s' %
               (table_name, ', '.join(gen_params(value_dict)), ' AND '.join(gen_params(key_dict))),
               list_values(value_dict) + list_values(key_dict)])

    # noinspection SqlResolve
    cl.append(['INSERT INTO [' + table_name + '] (' +
               ', '.join(["'%s'" % ('%s' % v).replace("'", "''") for v in
                          itertools.chain(iterkeys(value_dict), iterkeys(key_dict))]) + ')' +
               ' SELECT ' +
               ', '.join(["'%s'" % ('%s' % v).replace("'", "''") for v in
                          itertools.chain(itervalues(value_dict), itervalues(key_dict))]) +
               ' WHERE changes() = 0'])
    return cl


class DBConnection(object):
    def __init__(self, filename='sickbeard.db', row_type=None, **kwargs):
        # type: (AnyStr, Optional[AnyStr], Dict) -> None

        from . import helpers
        db_src = dbFilename(filename)
        if not os.path.isfile(db_src):
            db_alt = dbFilename('sickrage.db')
            if os.path.isfile(db_alt):
                helpers.copy_file(db_alt, db_src)

        self.filename = filename
        self.connection = sqlite3.connect(db_src, 20)

        if 'dict' == row_type:
            self.connection.row_factory = self._dict_factory
        else:
            self.connection.row_factory = sqlite3.Row

    def checkDBVersion(self):
        # type: (...) -> int

        try:
            if self.hasTable('db_version'):
                result = self.select('SELECT db_version FROM db_version')
            else:
                version = self.select('PRAGMA user_version')[0]['user_version']
                if version:
                    self.action('PRAGMA user_version = 0')
                    self.action('CREATE TABLE db_version (db_version INTEGER);')
                    self.action('INSERT INTO db_version (db_version) VALUES (%s);' % version)
                return version
        except (BaseException, Exception):
            return 0

        if result:
            version = int(result[0]['db_version'])
            if 10000 > version and self.hasColumn('db_version', 'db_minor_version'):
                # noinspection SqlResolve
                minor = self.select('SELECT db_minor_version FROM db_version')
                return version * 100 + int(minor[0]['db_minor_version'])
            return version
        return 0

    def mass_action(self, querylist, log_transaction=False):
        # type: (List[Union[List[AnyStr], Tuple[AnyStr, List], Tuple[AnyStr]]], bool) -> Optional[List, sqlite3.Cursor]

        from . import helpers
        with db_lock:

            if None is querylist:
                return

            sqlResult = []
            attempt = 0

            while 5 > attempt:
                try:
                    affected = 0
                    for qu in querylist:
                        cursor = self.connection.cursor()
                        if 1 == len(qu):
                            if log_transaction:
                                logger.log(qu[0], logger.DB)

                            sqlResult.append(cursor.execute(qu[0]).fetchall())
                        elif 1 < len(qu):
                            if log_transaction:
                                logger.log(qu[0] + ' with args ' + str(qu[1]), logger.DB)
                            sqlResult.append(cursor.execute(qu[0], qu[1]).fetchall())
                        affected += cursor.rowcount
                    self.connection.commit()
                    if 0 < affected:
                        logger.log(u'Transaction with %s queries executed affected %i row%s' % (
                            len(querylist), affected, helpers.maybe_plural(affected)), logger.DEBUG)
                    return sqlResult
                except sqlite3.OperationalError as e:
                    sqlResult = []
                    if self.connection:
                        self.connection.rollback()
                    if not self.action_error(e):
                        raise
                    attempt += 1
                except sqlite3.DatabaseError as e:
                    if self.connection:
                        self.connection.rollback()
                    logger.log(u'Fatal error executing query: ' + ex(e), logger.ERROR)
                    raise

            return sqlResult

    @staticmethod
    def action_error(e):

        if 'unable to open database file' in e.args[0] or 'database is locked' in e.args[0]:
            logger.log(u'DB error: ' + ex(e), logger.WARNING)
            time.sleep(1)
            return True
        logger.log(u'DB error: ' + ex(e), logger.ERROR)

    def action(self, query, args=None):
        # type: (AnyStr, Optional[List, Tuple]) -> Optional[Union[List, sqlite3.Cursor]]

        with db_lock:

            if None is query:
                return

            sqlResult = None
            attempt = 0

            while 5 > attempt:
                try:
                    if None is args:
                        logger.log(self.filename + ': ' + query, logger.DB)
                        sqlResult = self.connection.execute(query)
                    else:
                        logger.log(self.filename + ': ' + query + ' with args ' + str(args), logger.DB)
                        sqlResult = self.connection.execute(query, args)
                    self.connection.commit()
                    # get out of the connection attempt loop since we were successful
                    break
                except sqlite3.OperationalError as e:
                    if not self.action_error(e):
                        raise
                    attempt += 1
                except sqlite3.DatabaseError as e:
                    logger.log(u'Fatal error executing query: ' + ex(e), logger.ERROR)
                    raise

            return sqlResult

    def select(self, query, args=None):
        # type: (AnyStr, Optional[List, Tuple]) -> List

        sqlResults = self.action(query, args).fetchall()

        if None is sqlResults:
            return []

        return sqlResults

    def upsert(self, table_name, value_dict, key_dict):
        # type: (AnyStr, Dict, Dict) -> None

        changes_before = self.connection.total_changes

        gen_params = (lambda my_dict: [x + ' = ?' for x in iterkeys(my_dict)])

        # noinspection SqlResolve
        query = 'UPDATE [%s] SET %s WHERE %s' % (
            table_name, ', '.join(gen_params(value_dict)), ' AND '.join(gen_params(key_dict)))

        self.action(query, list_values(value_dict) + list_values(key_dict))

        if self.connection.total_changes == changes_before:
            # noinspection SqlResolve
            query = 'INSERT INTO [' + table_name + ']' \
                    + ' (%s)' % ', '.join(itertools.chain(iterkeys(value_dict), iterkeys(key_dict))) \
                    + ' VALUES (%s)' % ', '.join(['?'] * (len(value_dict) + len(key_dict)))
            self.action(query, list_values(value_dict) + list_values(key_dict))

    def tableInfo(self, table_name):
        # type: (AnyStr) -> Dict[AnyStr, Dict[AnyStr, AnyStr]]

        # FIXME ? binding is not supported here, but I cannot find a way to escape a string manually
        sqlResult = self.select('PRAGMA table_info([%s])' % table_name)
        columns = {}
        for column in sqlResult:
            columns[column['name']] = {'type': column['type']}
        return columns

    # http://stackoverflow.com/questions/3300464/how-can-i-get-dict-from-sqlite-query
    @staticmethod
    def _dict_factory(cursor, row):
        d = {}
        for idx, col in enumerate(cursor.description):
            d[col[0]] = row[idx]
        return d

    def hasTable(self, table_name):
        # type: (AnyStr) -> bool
        return 0 < len(self.select('SELECT 1 FROM sqlite_master WHERE name = ?;', (table_name,)))

    def hasColumn(self, table_name, column):
        # type: (AnyStr, AnyStr) -> bool
        return column in self.tableInfo(table_name)

    def hasIndex(self, table_name, index):
        # type: (AnyStr, AnyStr) -> bool
        sqlResults = self.select('PRAGMA index_list([%s])' % table_name)
        for result in sqlResults:
            if result['name'] == index:
                return True
        return False

    def removeIndex(self, table, name):
        # type: (AnyStr, AnyStr) -> None
        if self.hasIndex(table, name):
            self.action('DROP INDEX' + ' [%s]' % name)

    def removeTable(self, name):
        # type: (AnyStr) -> None
        if self.hasTable(name):
            self.action('DROP TABLE' + ' [%s]' % name)

    # noinspection SqlResolve
    def addColumn(self, table, column, data_type='NUMERIC', default=0):
        # type: (AnyStr, AnyStr, AnyStr, Any) -> None
        self.action('ALTER TABLE [%s] ADD %s %s' % (table, column, data_type))
        self.action('UPDATE [%s] SET %s = ?' % (table, column), (default,))

    def has_flag(self, flag_name):
        # type: (AnyStr) -> bool
        sql_result = self.select('SELECT flag FROM flags WHERE flag = ?', [flag_name])
        if 0 < len(sql_result):
            return True
        return False

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
        logger.load_log('Upgrading %s' % self.filename, to_log, log_level)


def sanityCheckDatabase(connection, sanity_check):
    sanity_check(connection).check()


class DBSanityCheck(object):
    def __init__(self, connection):
        self.connection = connection

    def check(self):
        pass


def upgradeDatabase(connection, schema):
    logger.log(u'Checking database structure...', logger.MESSAGE)
    connection.is_upgrading = False
    _processUpgrade(connection, schema)
    if connection.is_upgrading:
        connection.upgrade_log('Finished')


def prettyName(class_name):
    # type: (AnyStr) -> AnyStr
    return ' '.join([x.group() for x in re.finditer('([A-Z])([a-z0-9]+)', class_name)])


def restoreDatabase(filename, version):
    logger.log(u'Restoring database before trying upgrade again')
    if not sickbeard.helpers.restore_versioned_file(dbFilename(filename=filename, suffix='v%s' % version), version):
        logger.log_error_and_exit(u'Database restore failed, abort upgrading database')
        return False
    return True


def _processUpgrade(connection, upgrade_class):
    instance = upgrade_class(connection)
    logger.log('Checking %s database upgrade' % prettyName(upgrade_class.__name__), logger.DEBUG)
    if not instance.test():
        connection.is_upgrading = True
        connection.upgrade_log(getattr(upgrade_class, 'pretty_name', None) or prettyName(upgrade_class.__name__))
        logger.log('Database upgrade required: %s' % prettyName(upgrade_class.__name__), logger.MESSAGE)
        db_version = connection.checkDBVersion()
        try:
            # only do backup if it's not a new db
            0 < db_version and backup_database(connection.filename, db_version)
            instance.execute()
            cleanup_old_db_backups(connection.filename)
        except (BaseException, Exception):
            # attempting to restore previous DB backup and perform upgrade
            if db_version:
                # close db before attempting restore
                connection.close()

                if restoreDatabase(connection.filename, db_version):
                    logger.log_error_and_exit('Successfully restored database version: %s' % db_version)
                else:
                    logger.log_error_and_exit('Failed to restore database version: %s' % db_version)
            else:
                logger.log_error_and_exit('Database upgrade failed, can\'t determine old db version, not restoring.')

        logger.log('%s upgrade completed' % upgrade_class.__name__, logger.DEBUG)
    else:
        logger.log('%s upgrade not required' % upgrade_class.__name__, logger.DEBUG)

    for upgradeSubClass in upgrade_class.__subclasses__():
        _processUpgrade(connection, upgradeSubClass)


# Base migration class. All future DB changes should be subclassed from this class
class SchemaUpgrade(object):
    def __init__(self, connection, **kwargs):
        self.connection = connection

    def hasTable(self, table_name):
        return 0 < len(self.connection.select('SELECT 1 FROM sqlite_master WHERE name = ?;', (table_name,)))

    def hasColumn(self, table_name, column):
        return column in self.connection.tableInfo(table_name)

    # noinspection SqlResolve
    def addColumn(self, table, column, data_type='NUMERIC', default=0):
        self.connection.action('ALTER TABLE [%s] ADD %s %s' % (table, column, data_type))
        self.connection.action('UPDATE [%s] SET %s = ?' % (table, column), (default,))

    def dropColumn(self, table, column):
        # get old table columns and store the ones we want to keep
        result = self.connection.select('pragma table_info([%s])' % table)
        keptColumns = [c for c in result if c['name'] != column]

        keptColumnsNames = []
        final = []
        pk = []

        # copy the old table schema, column by column
        for column in keptColumns:

            keptColumnsNames.append(column['name'])

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
        keptColumnsNames = ', '.join(keptColumnsNames)

        # generate sql for the new table creation
        if 0 == len(pk):
            sql = 'CREATE TABLE [%s_new] (%s)' % (table, final)
        else:
            pk = ', '.join(pk)
            sql = 'CREATE TABLE [%s_new] (%s, PRIMARY KEY(%s))' % (table, final, pk)

        # create new temporary table and copy the old table data across, barring the removed column
        self.connection.action(sql)
        # noinspection SqlResolve
        self.connection.action('INSERT INTO [%s_new] SELECT %s FROM [%s]' % (table, keptColumnsNames, table))

        # copy the old indexes from the old table
        result = self.connection.select("SELECT sql FROM sqlite_master WHERE tbl_name=? AND type='index'", [table])

        # remove the old table and rename the new table to take it's place
        # noinspection SqlResolve
        self.connection.action('DROP TABLE [%s]' % table)
        # noinspection SqlResolve
        self.connection.action('ALTER TABLE [%s_new] RENAME TO [%s]' % (table, table))

        # write any indexes to the new table
        if 0 < len(result):
            for index in result:
                self.connection.action(index['sql'])

        # vacuum the db as we will have a lot of space to reclaim after dropping tables
        self.connection.action('VACUUM')

    def checkDBVersion(self):
        return self.connection.checkDBVersion()

    def incDBVersion(self):
        new_version = self.checkDBVersion() + 1
        # noinspection SqlConstantCondition
        self.connection.action('UPDATE db_version SET db_version = ? WHERE 1=1', [new_version])
        return new_version

    def setDBVersion(self, new_version):
        # noinspection SqlConstantCondition
        self.connection.action('UPDATE db_version SET db_version = ? WHERE 1=1', [new_version])
        return new_version

    def listTables(self):
        tables = []
        # noinspection SqlResolve
        sql_result = self.connection.select('SELECT name FROM [sqlite_master] WHERE type = "table"')
        for table in sql_result:
            tables.append(table[0])
        return tables

    def do_query(self, queries):
        if not isinstance(queries, list):
            queries = list(queries)
        elif isinstance(queries[0], list):
            queries = [item for sublist in queries for item in sublist]

        for query in queries:
            tbl_name = re.findall(r'(?i)DROP.*?TABLE.*?\[?([^\s\]]+)', query)
            if tbl_name and not self.hasTable(tbl_name[0]):
                continue
            tbl_name = re.findall(r'(?i)CREATE.*?TABLE.*?\s([^\s(]+)\s*\(', query)
            if tbl_name and self.hasTable(tbl_name[0]):
                continue
            self.connection.action(query)

    def finish(self, tbl_dropped=False):
        if tbl_dropped:
            self.connection.action('VACUUM')
        self.incDBVersion()

    def upgrade_log(self, *args, **kwargs):
        self.connection.upgrade_log(*args, **kwargs)


def MigrationCode(my_db):
    schema = {
        0: sickbeard.mainDB.InitialSchema,
        9: sickbeard.mainDB.AddSizeAndSceneNameFields,
        10: sickbeard.mainDB.RenameSeasonFolders,
        11: sickbeard.mainDB.Add1080pAndRawHDQualities,
        12: sickbeard.mainDB.AddShowidTvdbidIndex,
        13: sickbeard.mainDB.AddLastUpdateTVDB,
        14: sickbeard.mainDB.AddDBIncreaseTo15,
        15: sickbeard.mainDB.AddIMDbInfo,
        16: sickbeard.mainDB.AddProperNamingSupport,
        17: sickbeard.mainDB.AddEmailSubscriptionTable,
        18: sickbeard.mainDB.AddProperSearch,
        19: sickbeard.mainDB.AddDvdOrderOption,
        20: sickbeard.mainDB.AddSubtitlesSupport,
        21: sickbeard.mainDB.ConvertTVShowsToIndexerScheme,
        22: sickbeard.mainDB.ConvertTVEpisodesToIndexerScheme,
        23: sickbeard.mainDB.ConvertIMDBInfoToIndexerScheme,
        24: sickbeard.mainDB.ConvertInfoToIndexerScheme,
        25: sickbeard.mainDB.AddArchiveFirstMatchOption,
        26: sickbeard.mainDB.AddSceneNumbering,
        27: sickbeard.mainDB.ConvertIndexerToInteger,
        28: sickbeard.mainDB.AddRequireAndIgnoreWords,
        29: sickbeard.mainDB.AddSportsOption,
        30: sickbeard.mainDB.AddSceneNumberingToTvEpisodes,
        31: sickbeard.mainDB.AddAnimeTVShow,
        32: sickbeard.mainDB.AddAbsoluteNumbering,
        33: sickbeard.mainDB.AddSceneAbsoluteNumbering,
        34: sickbeard.mainDB.AddAnimeBlacklistWhitelist,
        35: sickbeard.mainDB.AddSceneAbsoluteNumbering2,
        36: sickbeard.mainDB.AddXemRefresh,
        37: sickbeard.mainDB.AddSceneToTvShows,
        38: sickbeard.mainDB.AddIndexerMapping,
        39: sickbeard.mainDB.AddVersionToTvEpisodes,

        40: sickbeard.mainDB.BumpDatabaseVersion,
        41: sickbeard.mainDB.Migrate41,
        42: sickbeard.mainDB.Migrate41,
        43: sickbeard.mainDB.Migrate43,
        44: sickbeard.mainDB.Migrate43,

        4301: sickbeard.mainDB.Migrate4301,
        4302: sickbeard.mainDB.Migrate4302,
        4400: sickbeard.mainDB.Migrate4302,

        5816: sickbeard.mainDB.MigrateUpstream,
        5817: sickbeard.mainDB.MigrateUpstream,
        5818: sickbeard.mainDB.MigrateUpstream,

        10000: sickbeard.mainDB.SickGearDatabaseVersion,
        10001: sickbeard.mainDB.RemoveDefaultEpStatusFromTvShows,
        10002: sickbeard.mainDB.RemoveMinorDBVersion,
        10003: sickbeard.mainDB.RemoveMetadataSub,

        20000: sickbeard.mainDB.DBIncreaseTo20001,
        20001: sickbeard.mainDB.AddTvShowOverview,
        20002: sickbeard.mainDB.AddTvShowTags,
        20003: sickbeard.mainDB.ChangeMapIndexer,
        20004: sickbeard.mainDB.AddShowNotFoundCounter,
        20005: sickbeard.mainDB.AddFlagTable,
        20006: sickbeard.mainDB.DBIncreaseTo20007,
        20007: sickbeard.mainDB.AddWebdlTypesTable,
        20008: sickbeard.mainDB.AddWatched,
        20009: sickbeard.mainDB.AddPrune,
        20010: sickbeard.mainDB.AddIndexerToTables,
        # 20002: sickbeard.mainDB.AddCoolSickGearFeature3,
    }

    db_version = my_db.checkDBVersion()
    logger.log(u'Detected database version: v%s' % db_version, logger.DEBUG)

    if not (db_version in schema):
        if db_version == sickbeard.mainDB.MAX_DB_VERSION:
            logger.log(u'Database schema is up-to-date, no upgrade required')
        elif 10000 > db_version:
            logger.log_error_and_exit(u'SickGear does not currently support upgrading from this database version')
        else:
            logger.log_error_and_exit(u'Invalid database version')

    else:

        my_db.upgrade_log('Upgrading')
        while db_version < sickbeard.mainDB.MAX_DB_VERSION:
            if None is schema[db_version]:  # skip placeholders used when multi PRs are updating DB
                db_version += 1
                continue
            try:
                update = schema[db_version](my_db)
                db_version = update.execute()
                cleanup_old_db_backups(my_db.filename)
            except (BaseException, Exception) as e:
                my_db.close()
                logger.log(u'Failed to update database with error: %s attempting recovery...' % ex(e), logger.ERROR)

                if restoreDatabase(my_db.filename, db_version):
                    # initialize the main SB database
                    logger.log_error_and_exit(u'Successfully restored database version: %s' % db_version)
                else:
                    logger.log_error_and_exit(u'Failed to restore database version: %s' % db_version)
        my_db.upgrade_log('Finished')


def cleanup_old_db_backups(filename):
    try:
        d, filename = ek.ek(os.path.split, filename)
        if not d:
            d = sickbeard.DATA_DIR
        for f in filter_iter(lambda fn: fn.is_file() and filename in fn.name and
                             re.search(r'\.db(\.v\d+)?\.r\d+$', fn.name),
                             ek.ek(scandir, d)):
            try:
                ek.ek(os.unlink, f.path)
            except (BaseException, Exception):
                pass
    except (BaseException, Exception):
        pass


def backup_database(filename, version):
    logger.log(u'Backing up database before upgrade')
    if not sickbeard.helpers.backup_versioned_file(dbFilename(filename), version):
        logger.log_error_and_exit(u'Database backup failed, abort upgrading database')
    else:
        logger.log(u'Proceeding with upgrade')


def get_rollback_module():
    import types
    from . import helpers

    module_urls = [
        'https://raw.githubusercontent.com/SickGear/sickgear.extdata/master/SickGear/Rollback/rollback.py']

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

    return None
