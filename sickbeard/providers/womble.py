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

from . import generic
from sickbeard import tvcache
import time


class WombleProvider(generic.NZBProvider):

    def __init__(self):
        generic.NZBProvider.__init__(self, 'Womble\'s Index', supports_backlog=False)

        self.url = 'https://newshost.co.za/'
        self.cache = WombleCache(self)


class WombleCache(tvcache.TVCache):

    def __init__(self, this_provider):
        tvcache.TVCache.__init__(self, this_provider)

        self.update_freq = 6  # cache update frequency

    def _cache_data(self):

        result = []
        for section in ['sd', 'hd', 'x264', 'dvd']:
            url = '%srss/?sec=tv-%s&fr=false' % (self.provider.url, section)
            data = self.getRSSFeed(url)
            time.sleep(1.1)
            cnt = len(result)
            for entry in (data and data.get('entries', []) or []):
                if entry.get('title') and entry.get('link', '').startswith('http'):
                    result.append((entry['title'], entry['link'], None, None))

            self.provider.log_result(count=len(result) - cnt, url=url)

        return result


provider = WombleProvider()
