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

from collections import OrderedDict

from .. import db

MIN_DB_VERSION = 1
MAX_DB_VERSION = 5
TEST_BASE_VERSION = None  # the base production db version, only needed for TEST db versions (>=100000)


# Add new migrations at the bottom of the list; subclass the previous migration.
class InitialSchema(db.SchemaUpgrade):
    def __init__(self, connection):
        super(InitialSchema, self).__init__(connection)

        self.queries = OrderedDict([
            ('base', [
                'CREATE TABLE lastUpdate(provider TEXT, time NUMERIC)',
                'CREATE TABLE lastSearch(provider TEXT, time NUMERIC)',
                'CREATE TABLE db_version(db_version INTEGER)',
                'INSERT INTO db_version(db_version) VALUES (1)',
                'CREATE TABLE network_timezones(network_name TEXT PRIMARY KEY, timezone TEXT)'
            ]),
            ('consolidate_providers', [
                'CREATE TABLE provider_cache(provider TEXT, name TEXT, season NUMERIC, episodes TEXT,'
                ' indexerid NUMERIC, url TEXT UNIQUE, time NUMERIC, quality TEXT, release_group TEXT, version NUMERIC)',
                'CREATE TABLE network_conversions('
                'tvdb_network TEXT PRIMARY KEY, tvrage_network TEXT, tvrage_country TEXT)',
                'CREATE INDEX tvrage_idx ON network_conversions(tvrage_network, tvrage_country)'
            ]),
            ('add_backlogparts', [
                'CREATE TABLE backlogparts('
                'part NUMERIC NOT NULL, indexer NUMERIC NOT NULL, indexerid NUMERIC NOT NULL)',
                'CREATE TABLE lastrecentsearch(name TEXT PRIMARY KEY NOT NULL, datetime NUMERIC NOT NULL)'
            ]),
            ('add_provider_fails', [
                'CREATE TABLE provider_fails(prov_name TEXT, fail_type INTEGER, fail_code INTEGER, fail_time NUMERIC)',
                'CREATE INDEX idx_prov_name_error ON provider_fails (prov_name)',
                'CREATE UNIQUE INDEX idx_prov_errors ON provider_fails (prov_name, fail_time)',
                'CREATE TABLE provider_fails_count(prov_name TEXT PRIMARY KEY,'
                ' failure_count NUMERIC, failure_time NUMERIC,'
                ' tmr_limit_count NUMERIC, tmr_limit_time NUMERIC, tmr_limit_wait NUMERIC)'
            ]),
            ('add_indexer_to_tables', [
                'DELETE FROM provider_cache WHERE 1=1'
            ])
        ])

    def test(self):
        return self.hasTable('lastUpdate')

    def execute(self):
        self.do_query(self.queries[next(iter(self.queries))])
        self.setDBVersion(MIN_DB_VERSION)


class ConsolidateProviders(InitialSchema):
    def test(self):
        return 1 < self.checkDBVersion()

    def execute(self):
        keep_tables = {'lastUpdate', 'lastSearch', 'db_version',
                       'network_timezones', 'network_conversions', 'provider_cache'}
        # old provider_cache is dropped before re-creation
        # noinspection SqlResolve
        self.do_query(['DROP TABLE [provider_cache]'] + self.queries['consolidate_providers'] +
                      ['DROP TABLE [%s]' % t for t in (set(self.listTables()) - keep_tables)])
        self.finish(True)


class AddBacklogParts(ConsolidateProviders):
    def test(self):
        return 2 < self.checkDBVersion()

    def execute(self):
        # noinspection SqlResolve
        self.do_query(self.queries['add_backlogparts'] +
                      ['DROP TABLE [%s]' % t for t in ('scene_names', 'scene_exceptions_refresh', 'scene_exceptions')])
        self.finish(True)


class AddProviderFailureHandling(AddBacklogParts):
    def test(self):
        return 3 < self.checkDBVersion()

    def execute(self):
        self.do_query(self.queries['add_provider_fails'])
        self.finish()


class AddIndexerToTables(AddProviderFailureHandling):
    def test(self):
        return 4 < self.checkDBVersion()

    def execute(self):
        self.do_query(self.queries['add_indexer_to_tables'])
        self.addColumn('provider_cache', 'indexer', 'NUMERIC')
        self.finish()
