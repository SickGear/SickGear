# Author: Tyler Fenby <tylerfenby@gmail.com>
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

from .. import db
from ..common import Quality

from six import iteritems

MIN_DB_VERSION = 1
MAX_DB_VERSION = 2
TEST_BASE_VERSION = None  # the base production db version, only needed for TEST db versions (>=100000)


# Add new migrations at the bottom of the list; subclass the previous migration.
class InitialSchema(db.SchemaUpgrade):
    def test(self):
        return self.hasTable('failed')

    def execute(self):
        queries = [
            ('CREATE TABLE failed (`release` TEXT);',),
            ('CREATE TABLE db_version (db_version INTEGER);',),
            ('INSERT INTO db_version (db_version) VALUES (?)', 1),
        ]
        for query in queries:
            if 1 == len(query):
                self.connection.action(query[0])
            else:
                self.connection.action(query[0], query[1:])


class SizeAndProvider(InitialSchema):
    def test(self):
        return self.hasColumn('failed', 'size') and self.hasColumn('failed', 'provider')

    def execute(self):
        self.addColumn('failed', 'size')
        self.addColumn('failed', 'provider', 'TEXT', '')


class History(SizeAndProvider):
    """Snatch history that can't be modified by the user"""

    def test(self):
        return self.hasTable('history')

    def execute(self):
        self.connection.action('CREATE TABLE history (date NUMERIC, ' +
                               'size NUMERIC, release TEXT, provider TEXT);')


class HistoryStatus(History):
    """Store episode status before snatch to revert to if necessary"""

    def test(self):
        return self.hasColumn('history', 'old_status')

    def execute(self):
        self.addColumn('history', 'old_status', 'NUMERIC', Quality.NONE)
        self.addColumn('history', 'showid', 'NUMERIC', '-1')
        self.addColumn('history', 'season', 'NUMERIC', '-1')
        self.addColumn('history', 'episode', 'NUMERIC', '-1')


class AddIndexerToTables(HistoryStatus):
    def test(self):
        return self.hasColumn('history', 'indexer')

    def execute(self):
        self.addColumn('history', 'indexer', 'NUMERIC')

        main_db = db.DBConnection('sickbeard.db')
        show_ids = {s['prod_id']: s['tv_id'] for s in
                    main_db.select('SELECT indexer AS tv_id, indexer_id AS prod_id FROM tv_shows')}
        cl = []
        for s_id, i in iteritems(show_ids):
            cl.append(['UPDATE history SET indexer = ? WHERE showid = ?', [i, s_id]])
        self.connection.mass_action(cl)

        if self.connection.hasTable('backup_history'):
            self.connection.action(
                'REPLACE INTO history '
                '(date, size, `release`, provider, old_status, showid, season, episode, indexer)'
                ' SELECT'
                ' date, size, `release`, provider, old_status, showid, season, episode, indexer'
                ' FROM backup_history')
            self.connection.removeTable('backup_history')

        self.connection.action('VACUUM')

        self.setDBVersion(2)
