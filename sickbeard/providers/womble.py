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

import generic

from sickbeard import logger, tvcache


class WombleProvider(generic.NZBProvider):

    def __init__(self):
        generic.NZBProvider.__init__(self, 'Womble\'s Index', supports_backlog=False)

        self.url = 'https://newshost.co.za/'
        self.cache = WombleCache(self)


class WombleCache(tvcache.TVCache):

    def __init__(self, this_provider):
        tvcache.TVCache.__init__(self, this_provider)

        self.minTime = 15  # cache update frequency

    def updateCache(self):

        # delete anything older then 7 days
        self._clearCache()

        if not self.shouldUpdate():
            return

        cl = []
        data = None
        for url in [self.provider.url + 'rss/?sec=tv-x264&fr=false',
                    self.provider.url + 'rss/?sec=tv-sd&fr=false',
                    self.provider.url + 'rss/?sec=tv-dvd&fr=false',
                    self.provider.url + 'rss/?sec=tv-hd&fr=false']:
            logger.log(u'Womble\'s Index cache update URL: ' + url, logger.DEBUG)
            data = self.getRSSFeed(url)

            # As long as we got something from the provider we count it as an update
            if not data:
                return []

            # By now we know we've got data and no auth errors, all we need to do is put it in the database
            for item in data.entries:
                title, url = self._get_title_and_url(item)
                ci = self._parseItem(title, url)
                if None is not ci:
                    cl.append(ci)

        if 0 < len(cl):
            my_db = self._getDB()
            my_db.mass_action(cl)

        # set last updated
        if data:
            self.setLastUpdate()

    def _checkAuth(self, *data):
        return 'Invalid Link' != data[0]


provider = WombleProvider()
