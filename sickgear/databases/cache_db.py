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

from collections import OrderedDict

from .. import db

MIN_DB_VERSION = 1
MAX_DB_VERSION = 7
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
            ]),
            ('connection_fails', [
                'CREATE TABLE connection_fails(domain_url TEXT, fail_type INTEGER, fail_code INTEGER,'
                ' fail_time NUMERIC)',
                'CREATE INDEX idx_conn_error ON connection_fails (domain_url)',
                'CREATE UNIQUE INDEX idx_conn_errors ON connection_fails (domain_url, fail_time)',
                'CREATE TABLE connection_fails_count(domain_url TEXT PRIMARY KEY,'
                ' failure_count NUMERIC, failure_time NUMERIC,'
                ' tmr_limit_count NUMERIC, tmr_limit_time NUMERIC, tmr_limit_wait NUMERIC)'
            ]),
            ('save_queues', [
                'CREATE TABLE people_queue(indexer NUMERIC NOT NULL, indexer_id NUMERIC NOT NULL,'
                ' action_id NUMERIC NOT NULL, forced INTEGER DEFAULT 0, scheduled INTEGER DEFAULT 0,'
                ' uid NUMERIC NOT NULL)',
                'CREATE UNIQUE INDEX idx_people_queue ON people_queue (indexer,indexer_id,action_id)',
                'CREATE UNIQUE INDEX idx_people_queue_uid ON people_queue (uid)',
                'CREATE TABLE search_queue(indexer NUMERIC NOT NULL, indexer_id NUMERIC NOT NULL,'
                ' segment TEXT NOT NULL, standard_backlog INTEGER DEFAULT 0, limited_backlog INTEGER DEFAULT 0,'
                ' forced INTEGER DEFAULT 0, torrent_only INTEGER DEFAULT 0, action_id INTEGER NOT NULL,'
                ' uid NUMERIC NOT NULL )',
                'CREATE UNIQUE INDEX idx_search_queue ON search_queue'
                ' (indexer, indexer_id, segment, standard_backlog, limited_backlog, forced, torrent_only, action_id)',
                'CREATE UNIQUE INDEX idx_search_queue_uid ON search_queue (uid)',
                'CREATE TABLE show_queue(tvid NUMERIC NOT NULL, prodid NUMERIC NOT NULL, priority INTEGER DEFAULT 20,'
                ' force INTEGER DEFAULT 0, scheduled_update INTEGER DEFAULT 0, after_update INTEGER DEFAULT 0,'
                ' force_image_cache INTEGER DEFAULT 0, show_dir TEXT, default_status NUMERIC, quality NUMERIC,'
                ' flatten_folders INTEGER, lang TEXT, subtitles INTEGER DEFAULT 0, anime INTEGER,'
                ' scene INTEGER, paused INTEGER, blocklist TEXT, allowlist TEXT,'
                ' wanted_begin NUMERIC, wanted_latest NUMERIC, prune NUMERIC DEFAULT 0, tag TEXT,'
                ' new_show INTEGER DEFAULT 0, show_name TEXT, upgrade_once INTEGER DEFAULT 0,'
                ' pausestatus_after INTEGER, skip_refresh INTEGER DEFAULT 0, action_id INTEGER NOT NULL,'
                ' uid NUMERIC NOT NULL)',
                'CREATE UNIQUE INDEX idx_show_queue_uid ON show_queue(uid)',
                'CREATE UNIQUE INDEX idx_show_queue ON show_queue(tvid, prodid, action_id)'
            ])
        ])

    def test(self):
        return self.has_table('lastUpdate')

    def execute(self):
        self.do_query(self.queries[next(iter(self.queries))])
        self.set_db_version(MIN_DB_VERSION, check_db_version=False)


class ConsolidateProviders(InitialSchema):
    def test(self):
        return 1 < self.call_check_db_version()

    def execute(self):
        keep_tables = {'lastUpdate', 'lastSearch', 'db_version',
                       'network_timezones', 'network_conversions', 'provider_cache'}
        # old provider_cache is dropped before re-creation
        # noinspection SqlResolve
        self.do_query(['DROP TABLE [provider_cache]'] + self.queries['consolidate_providers'] +
                      ['DROP TABLE [%s]' % t for t in (set(self.list_tables()) - keep_tables)])
        self.finish(True)


class AddBacklogParts(ConsolidateProviders):
    def test(self):
        return 2 < self.call_check_db_version()

    def execute(self):
        # noinspection SqlResolve
        self.do_query(self.queries['add_backlogparts'] +
                      ['DROP TABLE [%s]' % t for t in ('scene_names', 'scene_exceptions_refresh', 'scene_exceptions')])
        self.finish(True)


class AddProviderFailureHandling(AddBacklogParts):
    def test(self):
        return 3 < self.call_check_db_version()

    def execute(self):
        self.do_query(self.queries['add_provider_fails'])
        self.finish()


class AddIndexerToTables(AddProviderFailureHandling):
    def test(self):
        return 4 < self.call_check_db_version()

    def execute(self):
        self.do_query(self.queries['add_indexer_to_tables'])
        self.add_column('provider_cache', 'indexer', 'NUMERIC')
        self.finish()


class AddGenericFailureHandling(AddBacklogParts):
    def test(self):
        return 5 < self.call_check_db_version()

    def execute(self):
        self.do_query(self.queries['connection_fails'])
        self.finish()


class AddSaveQueues(AddGenericFailureHandling):
    def test(self):
        return 6 < self.call_check_db_version()

    def execute(self):
        self.do_query(self.queries['save_queues'])
        self.finish()
