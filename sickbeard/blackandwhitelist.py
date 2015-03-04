# Author: Dennis Lutter <lad1337@gmail.com>
# URL: http://code.google.com/p/sickbeard/
#
# This file is part of Sick Beard.
#
# Sick Beard is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# Sick Beard is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with Sick Beard.  If not, see <http://www.gnu.org/licenses/>.

import sickbeard
from sickbeard import db, logger, helpers
import urllib

class BlackAndWhiteList(object):
    blacklist = []
    whitelist = []

    def __init__(self, show_id):
        if not show_id:
            raise BlackWhitelistNoShowIDException()
        self.show_id = show_id
        self.load()

    def load(self):
        logger.log(u'Building black and white list for ' + str(self.show_id), logger.DEBUG)
        self.blacklist = self._load_list('blacklist')
        self.whitelist = self._load_list('whitelist')

    def _add_keywords(self, table, values):
        myDB = db.DBConnection()
        for value in values:
            myDB.action('INSERT INTO [' + table + '] (show_id, keyword) VALUES (?,?)', [self.show_id, value])

    def set_black_keywords(self, values):
        self._del_all_keywords('blacklist')
        self._add_keywords('blacklist', values)
        self.blacklist = values
        logger.log('Blacklist set to: %s' % self.blacklist, logger.DEBUG)

    def set_white_keywords(self, values):
        self._del_all_keywords('whitelist')
        self._add_keywords('whitelist', values)
        self.whitelist = values
        logger.log('Whitelist set to: %s' % self.whitelist, logger.DEBUG)

    def _del_all_keywords(self, table):
        myDB = db.DBConnection()
        myDB.action('DELETE FROM [' + table + '] WHERE show_id = ?', [self.show_id])

    def _load_list(self, table):
        myDB = db.DBConnection()
        sqlResults = myDB.select('SELECT keyword FROM [' + table + '] WHERE show_id = ?', [self.show_id])
        if not sqlResults or not len(sqlResults):
            return []

        groups = []
        for result in sqlResults:
            groups.append(result['keyword'])

        logger.log('BWL: ' + str(self.show_id) + ' loaded keywords from ' + table + ': ' + str(groups), logger.DEBUG)

        return groups

    def is_valid(self, result):

        if not result.release_group:
            logger.log('Failed to detect release group, invalid result', logger.DEBUG)
            return False

        if result.release_group.lower() in [x.lower() for x in self.whitelist] or not self.whitelist:
            white_result = True
        else:
            white_result = False

        if result.release_group.lower() in [x.lower() for x in self.blacklist]:
            black_result = False
        else:
            black_result = True

        logger.log('Whitelist check passed: %s. Blacklist check passed: %s' % (white_result, black_result), logger.DEBUG)

        if white_result and black_result:
            return True
        else:
            return False


class BlackWhitelistNoShowIDException(Exception):
    """
    No show_id was given
    """


def short_group_names(groups):
    group_list = groups.split(',')
    short_group_list = []
    if helpers.set_up_anidb_connection():
        for group_name in group_list:
            adba_result = sickbeard.ADBA_CONNECTION.group(gname=group_name)  # no such group is returned for utf8 groups like interrobang
            for line in adba_result.datalines:
                if line['shortname']:
                    short_group_list.append(line['shortname'])
                else:
                    if group_name not in short_group_list:
                        short_group_list.append(group_name)
    else:
        short_group_list = group_list
    return short_group_list