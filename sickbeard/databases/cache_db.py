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

# Add new migrations at the bottom of the list; subclass the previous migration.
class InitialSchema(db.SchemaUpgrade):
    def test(self):
        return self.hasTable("lastUpdate")

    def execute(self):

        queries = [
            ("CREATE TABLE lastUpdate (provider TEXT, time NUMERIC);",),
            ("CREATE TABLE lastSearch (provider TEXT, time NUMERIC);",),
            ("CREATE TABLE db_version (db_version INTEGER);",),
            ("INSERT INTO db_version (db_version) VALUES (?)", 1),
        ]
        for query in queries:
            if len(query) == 1:
                self.connection.action(query[0])
            else:
                self.connection.action(query[0], query[1:])


class AddSceneExceptions(InitialSchema):
    def test(self):
        return self.hasTable("scene_exceptions")

    def execute(self):
        self.connection.action(
            "CREATE TABLE scene_exceptions (exception_id INTEGER PRIMARY KEY, indexer_id INTEGER KEY, show_name TEXT)")

class AddSceneNameCache(AddSceneExceptions):
    def test(self):
        return self.hasTable("scene_names")

    def execute(self):
        self.connection.action("CREATE TABLE scene_names (indexer_id INTEGER, name TEXT)")


class AddNetworkTimezones(AddSceneNameCache):
    def test(self):
        return self.hasTable("network_timezones")

    def execute(self):
        self.connection.action("CREATE TABLE network_timezones (network_name TEXT PRIMARY KEY, timezone TEXT)")

class AddLastSearch(AddNetworkTimezones):
    def test(self):
        return self.hasTable("lastSearch")

    def execute(self):
        self.connection.action("CREATE TABLE lastSearch (provider TEXT, time NUMERIC)")

class AddSceneExceptionsSeasons(AddSceneNameCache):
    def test(self):
        return self.hasColumn("scene_exceptions", "season")

    def execute(self):
        self.addColumn("scene_exceptions", "season", "NUMERIC", -1)

class AddSceneExceptionsCustom(AddSceneExceptionsSeasons):
    def test(self):
        return self.hasColumn("scene_exceptions", "custom")

    def execute(self):
        self.addColumn("scene_exceptions", "custom", "NUMERIC", 0)

class AddSceneExceptionsRefresh(AddSceneExceptionsCustom):
    def test(self):
        return self.hasTable("scene_exceptions_refresh")

    def execute(self):
        self.connection.action(
            "CREATE TABLE scene_exceptions_refresh (list TEXT PRIMARY KEY, last_refreshed INTEGER)")


class AddNetworkConversions(AddSceneExceptionsRefresh):
    def test(self):
        return self.hasTable('network_conversions')

    def execute(self):
        self.connection.action('CREATE TABLE network_conversions (tvdb_network TEXT PRIMARY KEY, tvrage_network TEXT,'
                               ' tvrage_country TEXT)')
        
        self.connection.action('CREATE INDEX tvrage_idx on network_conversions (tvrage_network, tvrage_country)')


class ConsolidateProviders(AddNetworkConversions):
    def test(self):
        return self.checkDBVersion() > 1

    def execute(self):

        db.backup_database('cache.db', self.checkDBVersion())
        if self.hasTable('provider_cache'):
            self.connection.action('DROP TABLE provider_cache')

        self.connection.action('CREATE TABLE provider_cache (provider TEXT ,name TEXT, season NUMERIC, episodes TEXT,'
                               ' indexerid NUMERIC, url TEXT UNIQUE, time NUMERIC, quality TEXT, release_group TEXT, '
                               'version NUMERIC)')

        keep_tables = set(['lastUpdate', 'lastSearch', 'db_version', 'scene_exceptions', 'scene_names',
                           'network_timezones', 'scene_exceptions_refresh', 'network_conversions', 'provider_cache'])
        current_tables = set(self.listTables())
        remove_tables = list(current_tables - keep_tables)
        for table in remove_tables:
            self.connection.action('DROP TABLE [%s]' % table)

        self.incDBVersion()