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
import re
import datetime

import sickbeard
from lib.dateutil import parser
from sickbeard.common import Quality
from unidecode import unidecode

try:
    from collections import OrderedDict
except ImportError:
    from requests.compat import OrderedDict


class SearchResult:
    """
    Represents a search result from an indexer.
    """

    def __init__(self, episodes):
        self.provider = -1

        # release show object
        self.show = None

        # URL to the NZB/torrent file
        self.url = ''

        # used by some providers to store extra info associated with the result
        self.extraInfo = []

        # assign function to get the data for the download
        self.get_data_func = None

        # list of TVEpisode objects that this result is associated with
        self.episodes = episodes

        # quality of the release
        self.quality = Quality.UNKNOWN

        # release name
        self.name = ''

        # size of the release (-1 = n/a)
        self.size = -1

        # release group
        self.release_group = ''

        # version
        self.version = -1

    def __str__(self):

        if self.provider is None:
            return 'Invalid provider, unable to print self'

        myString = '%s @ %s\n' % (self.provider.name, self.url)
        myString += 'Extra Info:\n'
        for extra in self.extraInfo:
            myString += '  %s\n' % extra
        myString += 'Episode: %s\n' % self.episodes
        myString += 'Quality: %s\n' % Quality.qualityStrings[self.quality]
        myString += 'Name: %s\n' % self.name
        myString += 'Size: %s\n' % str(self.size)
        myString += 'Release Group: %s\n' % self.release_group

        return myString

    def fileName(self):
        return self.episodes[0].prettyName() + '.' + self.resultType

    def get_data(self):
        if None is not self.get_data_func:
            try:
                return self.get_data_func(self.url)
            except (StandardError, Exception):
                pass
        if self.extraInfo and 0 < len(self.extraInfo):
            return self.extraInfo[0]
        return None

class NZBSearchResult(SearchResult):
    """
    Regular NZB result with an URL to the NZB
    """
    resultType = 'nzb'


class NZBDataSearchResult(SearchResult):
    """
    NZB result where the actual NZB XML data is stored in the extraInfo
    """
    resultType = 'nzbdata'


class TorrentSearchResult(SearchResult):
    """
    Torrent result with an URL to the torrent
    """
    resultType = 'torrent'

    # torrent hash
    content = None
    hash = None


class AllShowsListUI:
    """
    This class is for indexer api. Instead of prompting with a UI to pick the
    desired result out of a list of shows it tries to be smart about it
    based on what shows are in SB.
    """

    def __init__(self, config, log=None):
        self.config = config
        self.log = log

    def selectSeries(self, allSeries):
        search_results = []

        # get all available shows
        if allSeries:
            search_term = self.config.get('searchterm', '').lower()
            if search_term:
                # try to pick a show that's in my show list
                for cur_show in allSeries:
                    if cur_show in search_results:
                        continue

                    seriesnames = []
                    if 'seriesname' in cur_show:
                        name = cur_show['seriesname'].lower()
                        seriesnames += [name, unidecode(name.encode('utf-8').decode('utf-8'))]
                    if 'aliasnames' in cur_show:
                        name = cur_show['aliasnames'].lower()
                        seriesnames += name.split('|') + unidecode(name.encode('utf-8').decode('utf-8')).split('|')

                    if search_term in set(seriesnames):
                        if 'firstaired' not in cur_show:
                            cur_show['firstaired'] = str(datetime.date.fromordinal(1))
                            cur_show['firstaired'] = re.sub('([-]0{2})+', '', cur_show['firstaired'])
                            fix_date = parser.parse(cur_show['firstaired'], fuzzy=True).date()
                            cur_show['firstaired'] = fix_date.strftime('%Y-%m-%d')

                        if cur_show not in search_results:
                            search_results += [cur_show]

        return search_results


class ShowListUI:
    """
    This class is for tvdb-api. Instead of prompting with a UI to pick the
    desired result out of a list of shows it tries to be smart about it
    based on what shows are in SB.
    """

    def __init__(self, config, log=None):
        self.config = config
        self.log = log

    def selectSeries(self, allSeries):
        try:
            # try to pick a show that's in my show list
            for curShow in allSeries:
                if filter(lambda x: int(x.indexerid) == int(curShow['id']), sickbeard.showList):
                    return curShow
        except:
            pass

        # if nothing matches then return first result
        return allSeries[0]


class Proper:
    def __init__(self, name, url, date, show, parsed_show=None):
        self.name = name
        self.url = url
        self.date = date
        self.provider = None
        self.quality = Quality.UNKNOWN
        self.release_group = None
        self.version = -1

        self.parsed_show = parsed_show
        self.show = show
        self.indexer = None
        self.indexerid = -1
        self.season = -1
        self.episode = -1
        self.scene_season = -1
        self.scene_episode = -1

    def __str__(self):
        return str(self.date) + ' ' + self.name + ' ' + str(self.season) + 'x' + str(self.episode) + ' of ' + str(
            self.indexerid) + ' from ' + str(sickbeard.indexerApi(self.indexer).name)


class ErrorViewer():
    """
    Keeps a static list of UIErrors to be displayed on the UI and allows
    the list to be cleared.
    """

    errors = []

    def __init__(self):
        ErrorViewer.errors = []

    @staticmethod
    def add(error):
        ErrorViewer.errors.append(error)

    @staticmethod
    def clear():
        ErrorViewer.errors = []


class UIError():
    """
    Represents an error to be displayed in the web UI.
    """

    def __init__(self, message):
        self.message = message
        self.time = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')


class OrderedDefaultdict(OrderedDict):
    def __init__(self, *args, **kwargs):
        if not args:
            self.default_factory = None
        else:
            if not (args[0] is None or callable(args[0])):
                raise TypeError('first argument must be callable or None')
            self.default_factory = args[0]
            args = args[1:]
        super(OrderedDefaultdict, self).__init__(*args, **kwargs)

    def __missing__ (self, key):
        if self.default_factory is None:
            raise KeyError(key)
        self[key] = default = self.default_factory()
        return default

    def __reduce__(self):  # optional, for pickle support
        args = (self.default_factory,) if self.default_factory else ()
        return self.__class__, args, None, None, self.iteritems()


class ImageUrlList(list):
    def __init__(self, iterable=None, max_age=30):
        super(ImageUrlList, self).__init__()
        self.max_age = max_age

    def add_url(self, url):
        self.remove_old()
        for x in self:
            if isinstance(x, (tuple, list)) and len(x) == 2 and url == x[0]:
                x = (x[0], datetime.datetime.now())
                return
        self.append((url, datetime.datetime.now()))

    def remove_old(self):
        age_limit = datetime.datetime.now() - datetime.timedelta(minutes=self.max_age)
        self[:] = [x for x in self if isinstance(x, (tuple, list)) and len(x) == 2 and x[1] > age_limit]

    def __repr__(self):
        return str([x[0] for x in self if isinstance(x, (tuple, list)) and len(x) == 2])

    def __contains__(self, y):
        for x in self:
            if isinstance(x, (tuple, list)) and len(x) == 2 and y == x[0]:
                return True
        return False

    def remove(self, x):
        for v in self:
            if isinstance(v, (tuple, list)) and len(v) == 2 and v[0] == x:
                super(ImageUrlList, self).remove(v)
                break
