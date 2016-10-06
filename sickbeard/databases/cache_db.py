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
#  GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with SickGear.  If not, see <http://www.gnu.org/licenses/>.

from sickbeard import db

MIN_DB_VERSION = 1
MAX_DB_VERSION = 3


# Add new migrations at the bottom of the list; subclass the previous migration.
class InitialSchema(db.SchemaUpgrade):
    def test(self):
        return self.hasTable('lastUpdate')

    def execute(self):
        queries = [
            'CREATE TABLE lastUpdate (provider TEXT, time NUMERIC)',
            'CREATE TABLE lastSearch (provider TEXT, time NUMERIC)',
            'CREATE TABLE db_version (db_version INTEGER)',
            'INSERT INTO db_version (db_version) VALUES (1)',
            'CREATE TABLE network_timezones (network_name TEXT PRIMARY KEY, timezone TEXT)',
            'CREATE TABLE network_conversions ('
                'tvdb_network TEXT PRIMARY KEY, tvrage_network TEXT, tvrage_country TEXT)',
            'CREATE INDEX tvrage_idx on network_conversions (tvrage_network, tvrage_country)',
            'CREATE TABLE provider_cache (provider TEXT ,name TEXT, season NUMERIC, episodes TEXT,'
            ' indexerid NUMERIC, url TEXT UNIQUE, time NUMERIC, quality TEXT, release_group TEXT, '
            'version NUMERIC)',
            'CREATE  TABLE  IF NOT EXISTS "backlogparts" ("part" NUMERIC NOT NULL ,'
            ' "indexer" NUMERIC NOT NULL , "indexerid" NUMERIC NOT NULL )',
            'CREATE  TABLE  IF NOT EXISTS "lastrecentsearch" ("name" TEXT PRIMARY KEY  NOT NULL'
            ' , "datetime" NUMERIC NOT NULL )',
        ]
        for query in queries:
            self.connection.action(query)
        self.setDBVersion(3)


class ConsolidateProviders(InitialSchema):
    def test(self):
        return self.checkDBVersion() > 1

    def execute(self):

        db.backup_database('cache.db', self.checkDBVersion())
        if self.hasTable('provider_cache'):
            self.connection.action('DROP TABLE provider_cache')

        self.connection.action('CREATE TABLE provider_cache (provider TEXT, name TEXT, season NUMERIC, episodes TEXT, '
                               'indexerid NUMERIC, url TEXT UNIQUE, time NUMERIC, quality TEXT, release_group TEXT, '
                               'version NUMERIC)')

        if not self.hasTable('network_conversions'):
            self.connection.action('CREATE TABLE network_conversions ' +
                                   '(tvdb_network TEXT PRIMARY KEY, tvrage_network TEXT, tvrage_country TEXT)')
            self.connection.action('CREATE INDEX tvrage_idx ' +
                                   'on network_conversions (tvrage_network, tvrage_country)')

        keep_tables = set(['lastUpdate', 'lastSearch', 'db_version',
                           'network_timezones', 'network_conversions', 'provider_cache'])
        current_tables = set(self.listTables())
        remove_tables = list(current_tables - keep_tables)
        for table in remove_tables:
            self.connection.action('DROP TABLE [%s]' % table)

        self.incDBVersion()


class AddBacklogParts(ConsolidateProviders):
    def test(self):
        return self.checkDBVersion() > 2

    def execute(self):

        db.backup_database('cache.db', self.checkDBVersion())
        if self.hasTable('scene_names'):
            self.connection.action('DROP TABLE scene_names')

        if not self.hasTable('backlogparts'):
            self.connection.action('CREATE  TABLE  IF NOT EXISTS "backlogparts" ("part" NUMERIC NOT NULL ,'
                                   ' "indexer" NUMERIC NOT NULL , "indexerid" NUMERIC NOT NULL )')

        if not self.hasTable('lastrecentsearch'):
            self.connection.action('CREATE  TABLE  IF NOT EXISTS "lastrecentsearch" ("name" TEXT PRIMARY KEY  NOT NULL'
                                   ' , "datetime" NUMERIC NOT NULL )')

        if self.hasTable('scene_exceptions_refresh'):
            self.connection.action('DROP TABLE scene_exceptions_refresh')
        if self.hasTable('scene_exceptions'):
            self.connection.action('DROP TABLE scene_exceptions')
        self.connection.action('VACUUM')

        self.incDBVersion()
