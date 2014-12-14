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

import os.path
import re
import sqlite3
import time
import threading

import sickbeard

from sickbeard import encodingKludge as ek
from sickbeard import logger
from sickbeard.exceptions import ex

db_lock = threading.Lock()


def dbFilename(filename="sickbeard.db", suffix=None):
    """
    @param filename: The sqlite database filename to use. If not specified,
                     will be made to be sickbeard.db
    @param suffix: The suffix to append to the filename. A '.' will be added
                   automatically, i.e. suffix='v0' will make dbfile.db.v0
    @return: the correct location of the database file.
    """
    if suffix:
        filename = "%s.%s" % (filename, suffix)
    return ek.ek(os.path.join, sickbeard.DATA_DIR, filename)


class DBConnection(object):
    def __init__(self, filename="sickbeard.db", suffix=None, row_type=None):

        self.filename = filename
        self.suffix = suffix
        self.row_type = row_type
        self.connection = None

        try:
            self.reconnect()
        except Exception as e:
            logger.log(u"DB error: " + ex(e), logger.ERROR)
            raise

    def reconnect(self):
        """Closes the existing database connection and re-opens it."""
        self.close()
        self.connection = sqlite3.connect(dbFilename(self.filename, self.suffix), 20, check_same_thread=False)
        self.connection.isolation_level = None

        if self.row_type == "dict":
            self.connection.row_factory = self._dict_factory
        else:
            self.connection.row_factory = sqlite3.Row

    def __del__(self):
        self.close()

    def _cursor(self):
        """Returns the cursor; reconnects if disconnected."""
        if self.connection is None: self.reconnect()
        return self.connection.cursor()

    def execute(self, query, args=None, fetchall=False, fetchone=False):
        """Executes the given query, returning the lastrowid from the query."""
        cursor = self._cursor()

        try:
            if fetchall:
                return self._execute(cursor, query, args).fetchall()
            elif fetchone:
                return self._execute(cursor, query, args).fetchone()
            else:
                return self._execute(cursor, query, args)
        finally:
            cursor.close()

    def _execute(self, cursor, query, args):
        try:
            if args == None:
                return cursor.execute(query)
            return cursor.execute(query, args)
        except sqlite3.OperationalError as e:
            logger.log(u"DB error: " + ex(e), logger.ERROR)
            self.close()
            raise

    def checkDBVersion(self):

        result = None

        try:
            if self.hasTable('db_version'):
                result = self.select("SELECT db_version FROM db_version")
        except:
            return 0

        if result:
            return int(result[0]["db_version"])
        else:
            return 0

    def mass_action(self, querylist, logTransaction=False, fetchall=False):

        with db_lock:
            # remove None types
            querylist = [i for i in querylist if i != None]

            if querylist == None:
                return

            sqlResult = []
            attempt = 0

            while attempt < 5:
                try:
                    for qu in querylist:
                        if len(qu) == 1:
                            if logTransaction:
                                logger.log(qu[0], logger.DEBUG)
                            sqlResult.append(self.execute(qu[0], fetchall=fetchall))
                        elif len(qu) > 1:
                            if logTransaction:
                                logger.log(qu[0] + " with args " + str(qu[1]), logger.DEBUG)
                            sqlResult.append(self.execute(qu[0], qu[1], fetchall=fetchall))

                    logger.log(u"Transaction with " + str(len(querylist)) + u" queries executed", logger.DEBUG)

                    # finished
                    break
                except sqlite3.OperationalError, e:
                    sqlResult = []
                    if self.connection:
                        self.connection.rollback()
                    if "unable to open database file" in e.args[0] or "database is locked" in e.args[0]:
                        logger.log(u"DB error: " + ex(e), logger.WARNING)
                        attempt += 1
                        time.sleep(1)
                    else:
                        logger.log(u"DB error: " + ex(e), logger.ERROR)
                        raise
                except sqlite3.DatabaseError, e:
                    sqlResult = []
                    if self.connection:
                        self.connection.rollback()
                    logger.log(u"Fatal error executing query: " + ex(e), logger.ERROR)
                    raise

            #time.sleep(0.02)

            return sqlResult

    def action(self, query, args=None, fetchall=False, fetchone=False):

        with db_lock:

            if query == None:
                return

            sqlResult = None
            attempt = 0

            while attempt < 5:
                try:
                    if args == None:
                        logger.log(self.filename + ": " + query, logger.DB)
                    else:
                        logger.log(self.filename + ": " + query + " with args " + str(args), logger.DB)

                    sqlResult = self.execute(query, args, fetchall=fetchall, fetchone=fetchone)

                    # get out of the connection attempt loop since we were successful
                    break
                except sqlite3.OperationalError, e:
                    if "unable to open database file" in e.args[0] or "database is locked" in e.args[0]:
                        logger.log(u"DB error: " + ex(e), logger.WARNING)
                        attempt += 1
                        time.sleep(1)
                    else:
                        logger.log(u"DB error: " + ex(e), logger.ERROR)
                        raise
                except sqlite3.DatabaseError, e:
                    logger.log(u"Fatal error executing query: " + ex(e), logger.ERROR)
                    raise

            #time.sleep(0.02)

            return sqlResult

    def select(self, query, args=None):

        sqlResults = self.action(query, args, fetchall=True)

        if sqlResults == None:
            return []

        return sqlResults

    def selectOne(self, query, args=None):

        sqlResults = self.action(query, args, fetchone=True)

        if sqlResults == None:
            return []

        return sqlResults

    def upsert(self, tableName, valueDict, keyDict):

        changesBefore = self.connection.total_changes

        genParams = lambda myDict: [x + " = ?" for x in myDict.keys()]

        query = "UPDATE [" + tableName + "] SET " + ", ".join(genParams(valueDict)) + " WHERE " + " AND ".join(
            genParams(keyDict))

        self.action(query, valueDict.values() + keyDict.values())

        if self.connection.total_changes == changesBefore:
            query = "INSERT INTO [" + tableName + "] (" + ", ".join(valueDict.keys() + keyDict.keys()) + ")" + \
                    " VALUES (" + ", ".join(["?"] * len(valueDict.keys() + keyDict.keys())) + ")"
            self.action(query, valueDict.values() + keyDict.values())

    def tableInfo(self, tableName):

        # FIXME ? binding is not supported here, but I cannot find a way to escape a string manually
        sqlResult = self.select("PRAGMA table_info([%s])" % tableName)
        columns = {}
        for column in sqlResult:
            columns[column['name']] = {'type': column['type']}
        return columns

    # http://stackoverflow.com/questions/3300464/how-can-i-get-dict-from-sqlite-query
    def _dict_factory(self, cursor, row):
        d = {}
        for idx, col in enumerate(cursor.description):
            d[col[0]] = row[idx]
        return d

    def hasTable(self, tableName):
        return len(self.select("SELECT 1 FROM sqlite_master WHERE name = ?;", (tableName, ))) > 0

    def hasColumn(self, tableName, column):
        return column in self.tableInfo(tableName)

    def hasIndex(self, tableName, index):
        sqlResults = self.select('PRAGMA index_list([%s])' % tableName)
        for result in sqlResults:
            if result['name'] == index:
                return True
        return False


    def addColumn(self, table, column, type="NUMERIC", default=0):
        self.action("ALTER TABLE [%s] ADD %s %s" % (table, column, type))
        self.action("UPDATE [%s] SET %s = ?" % (table, column), (default,))

    def close(self):
        """Close database connection"""
        if getattr(self, "connection", None) is not None:
            self.connection.close()
        self.connection = None

def sanityCheckDatabase(connection, sanity_check):
    sanity_check(connection).check()


class DBSanityCheck(object):
    def __init__(self, connection):
        self.connection = connection

    def check(self):
        pass


# ===============
# = Upgrade API =
# ===============

def upgradeDatabase(connection, schema):
    logger.log(u"Checking database structure...", logger.MESSAGE)
    _processUpgrade(connection, schema)


def prettyName(class_name):
    return ' '.join([x.group() for x in re.finditer("([A-Z])([a-z0-9]+)", class_name)])


def restoreDatabase(version):
    logger.log(u"Restoring database before trying upgrade again")
    if not sickbeard.helpers.restoreVersionedFile(dbFilename(suffix='v' + str(version)), version):
        logger.log_error_and_exit(u"Database restore failed, abort upgrading database")
        return False
    else:
        return True


def _processUpgrade(connection, upgradeClass):
    instance = upgradeClass(connection)
    logger.log(u"Checking " + prettyName(upgradeClass.__name__) + " database upgrade", logger.DEBUG)
    if not instance.test():
        logger.log(u"Database upgrade required: " + prettyName(upgradeClass.__name__), logger.MESSAGE)
        try:
            instance.execute()
        except sqlite3.DatabaseError, e:
            # attemping to restore previous DB backup and perform upgrade
            try:
                instance.execute()
            except:
                restored = False
                result = connection.select("SELECT db_version FROM db_version")
                if result:
                    version = int(result[0]["db_version"])

                    # close db before attempting restore
                    connection.close()

                    if restoreDatabase(version):
                        # initialize the main SB database
                        upgradeDatabase(DBConnection(), sickbeard.mainDB.InitialSchema)
                        restored = True

                if not restored:
                    print "Error in " + str(upgradeClass.__name__) + ": " + ex(e)
                    raise
        logger.log(upgradeClass.__name__ + " upgrade completed", logger.DEBUG)
    else:
        logger.log(upgradeClass.__name__ + " upgrade not required", logger.DEBUG)

    for upgradeSubClass in upgradeClass.__subclasses__():
        _processUpgrade(connection, upgradeSubClass)


# Base migration class. All future DB changes should be subclassed from this class
class SchemaUpgrade(object):
    def __init__(self, connection):
        self.connection = connection

    def hasTable(self, tableName):
        return len(self.connection.select("SELECT 1 FROM sqlite_master WHERE name = ?;", (tableName, ))) > 0

    def hasColumn(self, tableName, column):
        return column in self.connection.tableInfo(tableName)

    def addColumn(self, table, column, type="NUMERIC", default=0):
        self.connection.action("ALTER TABLE [%s] ADD %s %s" % (table, column, type))
        self.connection.action("UPDATE [%s] SET %s = ?" % (table, column), (default,))

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

            cl = []
            cl.append(column['name'])
            cl.append(column['type'])

            '''
            To be implemented if ever required
            if column['dflt_value']:
                cl.append(str(column['dflt_value']))

            if column['notnull']:
                cl.append(column['notnull'])
            '''

            if int(column['pk']) != 0:
                pk.append(column['name'])

            b = ' '.join(cl)
            final.append(b)

        # join all the table column creation fields
        final = ', '.join(final)
        keptColumnsNames = ', '.join(keptColumnsNames)

        # generate sql for the new table creation
        if len(pk) == 0:
            sql = 'CREATE TABLE [%s_new] (%s)' % (table, final)
        else:
            pk = ', '.join(pk)
            sql = 'CREATE TABLE [%s_new] (%s, PRIMARY KEY(%s))' % (table, final, pk)

        # create new temporary table and copy the old table data across, barring the removed column
        self.connection.action(sql)
        self.connection.action('INSERT INTO [%s_new] SELECT %s FROM [%s]' % (table, keptColumnsNames, table))

        # copy the old indexes from the old table
        result = self.connection.select('SELECT sql FROM sqlite_master WHERE tbl_name=? and type="index"', [table])

        # remove the old table and rename the new table to take it's place
        self.connection.action('DROP TABLE [%s]' % table)
        self.connection.action('ALTER TABLE [%s_new] RENAME TO [%s]' % (table, table))

        # write any indexes to the new table
        if len(result) > 0:
            for index in result:
                self.connection.action(index['sql'])

        # vacuum the db as we will have a lot of space to reclaim after dropping tables
        self.connection.action("VACUUM")

    def checkDBVersion(self):
        return self.connection.checkDBVersion()

    def incDBVersion(self):
        new_version = self.checkDBVersion() + 1
        self.connection.action("UPDATE db_version SET db_version = ?", [new_version])
        return new_version

    def setDBVersion(self, new_version):
        self.connection.action("UPDATE db_version SET db_version = ?", [new_version])
        return new_version


def MigrationCode(myDB):

    schema = {
        0: sickbeard.mainDB.InitialSchema,  # 0->20000
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

        10000: sickbeard.mainDB.SickGearDatabaseVersion,
        10001: sickbeard.mainDB.RemoveDefaultEpStatusFromTvShows

        #20000: sickbeard.mainDB.AddCoolSickGearFeature1,
        #20001: sickbeard.mainDB.AddCoolSickGearFeature2,
        #20002: sickbeard.mainDB.AddCoolSickGearFeature3,
    }

    db_version = myDB.checkDBVersion()
    logger.log(u'Detected database version: v' + str(db_version), logger.DEBUG)

    if not (db_version in schema):
        if db_version == sickbeard.mainDB.MAX_DB_VERSION:
            logger.log(u'Database schema is up-to-date, no upgrade required')
        elif db_version < 10000:
            logger.log_error_and_exit(u'SickGear does not currently support upgrading from this database version')
        else:
            logger.log_error_and_exit(u'Invalid database version')

    else:

        while db_version < sickbeard.mainDB.MAX_DB_VERSION:
            try:
                update = schema[db_version](myDB)
                db_version = update.execute()
            except Exception, e:
                myDB.close()
                logger.log(u'Failed to update database with error: ' + ex(e) + ' attempting recovery...', logger.ERROR)

                if restoreDatabase(db_version):
                    # initialize the main SB database
                    logger.log_error_and_exit(u'Successfully restored database version:' + str(db_version))
                else:
                    logger.log_error_and_exit(u'Failed to restore database version:' + str(db_version))