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
from collections import OrderedDict

from sickbeard.common import Quality
from unidecode import unidecode

import datetime
import os
import re

import sickbeard


class SearchResult(object):
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

        # proper level
        self._properlevel = 0

        # is a repack
        self.is_repack = False

        # provider unique id
        self.puid = None

    @property
    def properlevel(self):
        return self._properlevel

    @properlevel.setter
    def properlevel(self, v):
        if isinstance(v, (int, long)):
            self._properlevel = v

    def __str__(self):

        if self.provider is None:
            return 'Invalid provider, unable to print self'

        return '\n'.join([
            '%s @ %s' % (self.provider.name, self.url),
            'Extra Info:',
            '\n'.join(['  %s' % x for x in self.extraInfo]),
            'Episode: %s' % self.episodes,
            'Quality: %s' % Quality.qualityStrings[self.quality],
            'Name: %s' % self.name,
            'Size: %s' % self.size,
            'Release Group: %s' % self.release_group])

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


class ShowFilter(object):
    def __init__(self, config, log=None):
        self.config = config
        self.log = log
        self.bad_names = [re.compile('(?i)%s' % r) for r in (
            '[*]+\s*(?:403:|do not add|dupli[^s]+\s*(?:\d+|<a\s|[*])|inval)',
            '(?:inval|not? allow(ed)?)(?:[,\s]*period)?\s*[*]',
            '[*]+\s*dupli[^\s*]+\s*[*]+\s*(?:\d+|<a\s)',
            '\s(?:dupli[^s]+\s*(?:\d+|<a\s|[*]))'
        )]

    def _is_bad_name(self, show):
        return isinstance(show, dict) and 'seriesname' in show and isinstance(show['seriesname'], (str, unicode)) \
               and any([x.search(show['seriesname']) for x in self.bad_names])

    @staticmethod
    def _fix_firstaired(show):
        if 'firstaired' not in show:
            show['firstaired'] = '1900-01-01'

    @staticmethod
    def _dict_prevent_none(d, key, default):
        v = None
        if isinstance(d, dict):
            v = d.get(key, default)
        return (v, default)[None is v]

    @staticmethod
    def _fix_seriesname(show):
        if isinstance(show, dict) and 'seriesname' in show and isinstance(show['seriesname'], (str, unicode)):
            show['seriesname'] = ShowFilter._dict_prevent_none(show, 'seriesname', '').strip()


class AllShowsNoFilterListUI(ShowFilter):
    """
    This class is for indexer api. Used for searching, no filter or smart select
    """

    def __init__(self, config, log=None):
        super(AllShowsNoFilterListUI, self).__init__(config, log)

    def select_series(self, all_series):
        search_results = []

        # get all available shows
        if all_series:
            for cur_show in all_series:
                self._fix_seriesname(cur_show)
                if cur_show in search_results or self._is_bad_name(cur_show):
                    continue

                self._fix_firstaired(cur_show)

                if cur_show not in search_results:
                    search_results += [cur_show]

        return search_results


class AllShowsListUI(ShowFilter):
    """
    This class is for indexer api. Instead of prompting with a UI to pick the
    desired result out of a list of shows it tries to be smart about it
    based on what shows are in SB.
    """

    def __init__(self, config, log=None):
        super(AllShowsListUI, self).__init__(config, log)

    def select_series(self, all_series):
        search_results = []

        # get all available shows
        if all_series:
            search_term = self.config.get('searchterm', '').strip().lower()
            if search_term:
                # try to pick a show that's in my show list
                for cur_show in all_series:
                    self._fix_seriesname(cur_show)
                    if cur_show in search_results or self._is_bad_name(cur_show):
                        continue

                    seriesnames = []
                    if 'seriesname' in cur_show:
                        name = cur_show['seriesname'].lower()
                        seriesnames += [name, unidecode(name.encode('utf-8').decode('utf-8'))]
                    if 'aliases' in cur_show:
                        if isinstance(cur_show['aliases'], list):
                            for a in cur_show['aliases']:
                                name = a.strip().lower()
                                seriesnames += [name, unidecode(name.encode('utf-8').decode('utf-8'))]
                        elif isinstance(cur_show['aliases'], (str, unicode)):
                            name = cur_show['aliases'].strip().lower()
                            seriesnames += name.split('|') + unidecode(name.encode('utf-8').decode('utf-8')).split('|')

                    if search_term in set(seriesnames):
                        self._fix_firstaired(cur_show)

                        if cur_show not in search_results:
                            search_results += [cur_show]

        return search_results


class ShowListUI(ShowFilter):
    """
    This class is for tvdb-api. Instead of prompting with a UI to pick the
    desired result out of a list of shows it tries to be smart about it
    based on what shows are in SB.
    """

    def __init__(self, config, log=None):
        super(ShowListUI, self).__init__(config, log)

    def select_series(self, all_series):
        try:
            # try to pick a show that's in my show list
            for curShow in all_series:
                self._fix_seriesname(curShow)
                if self._is_bad_name(curShow):
                    continue
                if filter(lambda x: int(x.indexerid) == int(curShow['id']), sickbeard.showList):
                    return curShow
        except (StandardError, Exception):
            pass

        # if nothing matches then return first result
        return all_series[0]


class Proper:
    def __init__(self, name, url, date, show, parsed_show=None, size=-1, puid=None):
        self.name = name
        self.url = url
        self.date = date
        self.size = size
        self.puid = puid
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


class ErrorViewer:
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


class UIError:
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

    def __missing__(self, key):
        if self.default_factory is None:
            raise KeyError(key)
        self[key] = default = self.default_factory()
        return default

    def __reduce__(self):  # optional, for pickle support
        args = (self.default_factory,) if self.default_factory else ()
        return self.__class__, args, None, None, self.iteritems()

    # backport from python 3
    def move_to_end(self, key, last=True):
        """Move an existing element to the end (or beginning if last==False).

        Raises KeyError if the element does not exist.
        When last=True, acts like a fast version of self[key]=self.pop(key).

        """
        link_prev, link_next, key = link = self._OrderedDict__map[key]
        link_prev[1] = link_next
        link_next[0] = link_prev
        root = self._OrderedDict__root
        if last:
            last = root[0]
            link[0] = last
            link[1] = root
            last[1] = root[0] = link
        else:
            first = root[1]
            link[0] = root
            link[1] = first
            root[1] = first[0] = link

    def first_key(self):
        return self._OrderedDict__root[1][2]

    def last_key(self):
        return self._OrderedDict__root[0][2]


class ImageUrlList(list):
    def __init__(self, max_age=30):
        super(ImageUrlList, self).__init__()
        self.max_age = max_age

    def add_url(self, url):
        self.remove_old()
        cache_item = (url, datetime.datetime.now())
        for n, x in enumerate(self):
            if self._is_cache_item(x) and url == x[0]:
                self[n] = cache_item
                return
        self.append(cache_item)

    @staticmethod
    def _is_cache_item(item):
        return isinstance(item, (tuple, list)) and 2 == len(item)

    def remove_old(self):
        age_limit = datetime.datetime.now() - datetime.timedelta(minutes=self.max_age)
        self[:] = [x for x in self if self._is_cache_item(x) and age_limit < x[1]]

    def __repr__(self):
        return str([x[0] for x in self if self._is_cache_item(x)])

    def __contains__(self, url):
        for x in self:
            if self._is_cache_item(x) and url == x[0]:
                return True
        return False

    def remove(self, url):
        for x in self:
            if self._is_cache_item(x) and url == x[0]:
                super(ImageUrlList, self).remove(x)
                break


if 'nt' == os.name:
    import ctypes

    class WinEnv:
        def __init__(self):
            pass

        @staticmethod
        def get_environment_variable(name):
            name = unicode(name)  # ensures string argument is unicode
            n = ctypes.windll.kernel32.GetEnvironmentVariableW(name, None, 0)
            result = None
            if n:
                buf = ctypes.create_unicode_buffer(u'\0'*n)
                ctypes.windll.kernel32.GetEnvironmentVariableW(name, buf, n)
                result = buf.value
            return result

        def __getitem__(self, key):
            return self.get_environment_variable(key)

        def get(self, key, default=None):
            r = self.get_environment_variable(key)
            return r if r is not None else default

    sickbeard.ENV = WinEnv()
else:
    class LinuxEnv(object):
        def __init__(self, environ):
            self.environ = environ

        def __getitem__(self, key):
            v = self.environ.get(key)
            try:
                return v.decode(SYS_ENCODING) if isinstance(v, str) else v
            except (UnicodeDecodeError, UnicodeEncodeError):
                return v

        def get(self, key, default=None):
            v = self[key]
            return v if v is not None else default

    sickbeard.ENV = LinuxEnv(os.environ)


# backport from python 3
class SimpleNamespace:
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)

    def __repr__(self):
        keys = sorted(self.__dict__)
        items = ("{}={!r}".format(k, self.__dict__[k]) for k in keys)
        return "{}({})".format(type(self).__name__, ", ".join(items))

    def __eq__(self, other):
        return self.__dict__ == other.__dict__
