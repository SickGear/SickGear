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

import copy
import datetime
import os
import re
import threading

import sickbeard
from ._legacy_classes import LegacySearchResult, LegacyProper
from .common import Quality

from six import integer_types, iteritems, PY2, string_types

# noinspection PyUnreachableCode
if False:
    from typing import Any, AnyStr, Callable, Dict, List, Optional


class SearchResult(LegacySearchResult):
    """
    Represents a search result from an indexer.
    """

    # type of result (overwritten in subclass)
    resultType = 'generic'

    def __init__(self, ep_obj_list):
        # type: (Optional[List[sickbeard.tv.TVEpisode]]) -> None
        """
        :param ep_obj_list: list of episode objs
        """
        # noinspection PyTypeChecker
        self.provider = -1  # type: sickbeard.providers.generic.GenericProvider

        # release show object
        self._show_obj = None

        # URL to the NZB/torrent file
        self.url = ''  # type: AnyStr

        # used by some providers to store extra info associated with the result
        self.extraInfo = []

        # assign function to get the data for the download
        self.get_data_func = None  # type: Callable or None

        # assign function for after getting the download data
        self.after_get_data_func = None  # type: Callable or None

        # list of TVEpisode objects that this result is associated with
        self.ep_obj_list = ep_obj_list  # type: Optional[List[sickbeard.tv.TVEpisode]]

        # quality of the release
        self.quality = Quality.UNKNOWN  # type: int

        # release name
        self.name = ''  # type: AnyStr

        # size of the release (-1 = n/a)
        self.size = -1  # type: int

        # release group
        self.release_group = ''  # type: AnyStr

        # version
        self.version = -1  # type: int

        # proper level
        self._properlevel = 0  # type: int

        # is a repack
        self.is_repack = False  # type: bool

        # provider unique id
        self.puid = None  # type: Any

        # path to cache file
        self.cache_filepath = ''  # type: AnyStr

        # priority of result
        # -1 = low, 0 = normal, 1 = high
        self.priority = 0  # type: int

    @property
    def show_obj(self):
        # type: (...) -> Optional[sickbeard.tv.TVShow]
        return self._show_obj

    @show_obj.setter
    def show_obj(self, val):
        # type: (sickbeard.tv.TVShow) -> None
        self._show_obj = val

    @property
    def properlevel(self):
        """
        :rtype: int or long
        """
        return self._properlevel

    @properlevel.setter
    def properlevel(self, v):
        """
        :param v: proper level
        :type v: int or long
        """
        if isinstance(v, integer_types):
            self._properlevel = v

    def __str__(self):

        if None is self.provider:
            return 'Invalid provider, unable to print self'

        return '\n'.join([
            '%s @ %s' % (self.provider.name, self.url),
            'Extra Info:',
            '\n'.join(['  %s' % x for x in self.extraInfo]),
            'Episode: %s' % self.ep_obj_list,
            'Quality: %s' % Quality.qualityStrings[self.quality],
            'Name: %s' % self.name,
            'Size: %s' % self.size,
            'Release Group: %s' % self.release_group])

    def get_data(self):
        """
        :return: None or data
        :rtype: Any
        """
        if None is not self.get_data_func:
            try:
                return self.get_data_func(self.url)
            except (BaseException, Exception):
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

    provider = None  # type: sickbeard.providers.generic.TorrentProvider


class ShowInfoFilter(object):
    def __init__(self, config, log=None):
        self.config = config
        self.log = log
        self.bad_names = [re.compile('(?i)%s' % r) for r in (
            r'[*]+\s*(?:403:|do not add|dupli[^s]+\s*(?:\d+|<a\s|[*])|inval)',
            r'(?:inval|not? allow(ed)?)(?:[,\s]*period)?\s*[*]',
            r'[*]+\s*dupli[^\s*]+\s*[*]+\s*(?:\d+|<a\s)',
            r'\s(?:dupli[^s]+\s*(?:\d+|<a\s|[*]))'
        )]

    def _is_bad_name(self, show_info):
        return isinstance(show_info, dict) \
               and 'seriesname' in show_info \
               and isinstance(show_info['seriesname'], string_types) \
               and any([x.search(show_info['seriesname']) for x in self.bad_names])

    @staticmethod
    def _fix_firstaired(show_info):
        if 'firstaired' not in show_info:
            show_info['firstaired'] = '1900-01-01'

    @staticmethod
    def _dict_prevent_none(d, key, default):
        v = None
        if isinstance(d, dict):
            v = d.get(key, default)
        return (v, default)[None is v]

    @staticmethod
    def _fix_seriesname(show_info):
        if isinstance(show_info, dict) \
                and 'seriesname' in show_info \
                and isinstance(show_info['seriesname'], string_types):
            show_info['seriesname'] = ShowInfoFilter._dict_prevent_none(show_info, 'seriesname', '').strip()


class AllShowInfosNoFilterListUI(ShowInfoFilter):
    """
    This class is for indexer api. Used for searching.
    """

    def __init__(self, config, log=None):
        super(AllShowInfosNoFilterListUI, self).__init__(config, log)

    def select_series(self, all_series):
        search_results = []

        # get all available shows
        if all_series:
            for cur_show_info in all_series:
                self._fix_seriesname(cur_show_info)
                if cur_show_info in search_results or self._is_bad_name(cur_show_info):
                    continue

                self._fix_firstaired(cur_show_info)

                if cur_show_info not in search_results:
                    search_results += [cur_show_info]

        return search_results


class Proper(LegacyProper):
    def __init__(self, name, url, date, show_obj, parsed_show_obj=None, size=-1, puid=None, **kwargs):
        """

        :param name: release name
        :type name: AnyStr
        :param url: url
        :type url: AnyStr
        :param date: date
        :type date:
        :param show_obj: show object or None
        :type show_obj: sickbeard.tv.TVShow or None
        :param parsed_show_obj: parsed show object
        :type parsed_show_obj: sickbread.tv.TVShow
        :param size: size
        :type size: int or long
        :param puid: puid
        :type puid: AnyStr
        :param kwargs:
        """
        self.name = name
        self.url = url
        self.date = date
        self.size = size
        self.puid = puid
        self.provider = None
        self.quality = Quality.UNKNOWN
        self.release_group = None  # type: Optional[AnyStr]
        self.version = -1  # type: int

        self.parsed_show_obj = parsed_show_obj
        self.show_obj = show_obj
        self.tvid = None  # type: Optional[int]
        self.prodid = -1  # type: int
        self.season = -1  # type: int
        self.episode = -1  # type: int
        self.scene_season = -1  # type: int
        self.scene_episode = -1  # type: int

        super(Proper, self).__init__(**kwargs)

    @property
    def show_obj(self):
        # type: (...) -> Optional[sickbeard.tv.TVShow]
        return self._show_obj

    @show_obj.setter
    def show_obj(self, val):
        # type: (sickbeard.tv.TVShow) -> None
        self._show_obj = val

    def __str__(self):
        if self.show_obj:
            prodid = self.show_obj.prodid
            tvid = self.show_obj.tvid
        elif self.parsed_show_obj:
            prodid = self.parsed_show_obj.prodid
            tvid = self.parsed_show_obj.tvid
        else:
            prodid = self.prodid
            tvid = self.tvid
        return '%s %s %sx%s of %s from %s' % (self.date, self.name, self.season, self.episode, prodid,
                                              sickbeard.TVInfoAPI(tvid).name)


class ErrorViewer(object):
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


class UIError(object):
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
            if not (None is args[0] or callable(args[0])):
                raise TypeError('first argument must be callable or None')
            self.default_factory = args[0]
            args = args[1:]
        super(OrderedDefaultdict, self).__init__(*args, **kwargs)

    def __missing__(self, key):
        if None is self.default_factory:
            raise KeyError(key)
        self[key] = default = self.default_factory()
        return default

    def __reduce__(self):  # optional, for pickle support
        args = (self.default_factory,) if self.default_factory else ()
        return self.__class__, args, None, None, iteritems(self)

    if PY2:
        # backport from python 3
        def move_to_end(self, key, last=True):
            """Move an existing element to the end (or beginning if last==False).

            Raises KeyError if the element does not exist.
            When last=True, acts like a fast version of self[key]=self.pop(key).

            """
            link_prev, link_next, key = link = getattr(self, '_OrderedDict__map')[key]
            link_prev[1] = link_next
            link_next[0] = link_prev
            root = getattr(self, '_OrderedDict__root')
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
            return getattr(self, '_OrderedDict__root')[1][2]

        def last_key(self):
            return getattr(self, '_OrderedDict__root')[0][2]
    else:
        def first_key(self):
            return next(iter(self))

        def last_key(self):
            return next(reversed(self))


class ImageUrlList(list):
    def __init__(self, max_age=30):
        """
        :param max_age: max age in days
        :type max_age: int
        """
        super(ImageUrlList, self).__init__()
        self.max_age = max_age

    def add_url(self, url):
        """
        adds url to list

        :param url: url
        :type url: AnyStr
        """
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
        """
        removes url from list

        :param url: url
        :type url: AnyStr
        """
        for x in self:
            if self._is_cache_item(x) and url == x[0]:
                super(ImageUrlList, self).remove(x)
                break


class EnvVar(object):
    def __init__(self):
        pass

    def __getitem__(self, key):
        return os.environ(key)

    @staticmethod
    def get(key, default=None):
        return os.environ.get(key, default)


if not PY2:
    sickbeard.ENV = EnvVar()

elif 'nt' == os.name:
    from ctypes import windll, create_unicode_buffer

    # noinspection PyCompatibility
    class WinEnvVar(EnvVar):

        @staticmethod
        def get_environment_variable(name):
            # noinspection PyUnresolvedReferences
            name = unicode(name)  # ensures string argument is unicode
            n = windll.kernel32.GetEnvironmentVariableW(name, None, 0)
            env_value = None
            if n:
                buf = create_unicode_buffer(u'\0' * n)
                windll.kernel32.GetEnvironmentVariableW(name, buf, n)
                env_value = buf.value
            return env_value

        def __getitem__(self, key):
            return self.get_environment_variable(key)

        def get(self, key, default=None):
            r = self.get_environment_variable(key)
            return r if None is not r else default

    sickbeard.ENV = WinEnvVar()
else:
    # noinspection PyCompatibility
    class LinuxEnvVar(EnvVar):
        # noinspection PyMissingConstructor
        def __init__(self, environ):
            self.environ = environ

        def __getitem__(self, key):
            v = self.environ.get(key)
            try:
                return v if not isinstance(v, str) else v.decode(sickbeard.SYS_ENCODING)
            except (UnicodeDecodeError, UnicodeEncodeError):
                return v

        def get(self, key, default=None):
            v = self[key]
            return v if None is not v else default

    sickbeard.ENV = LinuxEnvVar(os.environ)


# backport from python 3
class SimpleNamespace(object):
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)

    def __repr__(self):
        keys = sorted(self.__dict__)
        items = ["{}={!r}".format(k, self.__dict__[k]) for k in keys]
        return "{}({})".format(type(self).__name__, ", ".join(items))

    def __eq__(self, other):
        return self.__dict__ == other.__dict__


class LoadingMessage(object):
    def __init__(self):
        self.lock = threading.Lock()
        self._message = [{'msg': 'Loading', 'progress': -1}]

    @property
    def message(self):
        """
        :return: list of messages
        :rtype: List[Dict[AnyStr, int]]
        """
        with self.lock:
            return copy.deepcopy(self._message)

    @message.setter
    def message(self, msg):
        """
        add message to list

        :param msg: message
        :type msg: AnyStr
        """
        with self.lock:
            if 0 != len(self._message) and msg != self._message[-1:][0]['msg']:
                self._message.append({'msg': msg, 'progress': -1})

    def set_msg_progress(self, msg, progress):
        """
        add message with progress

        :param msg: message
        :type msg: AnyStr
        :param progress: progress message
        :type progress: Any
        """
        with self.lock:
            for m in self._message:
                if msg == m.get('msg'):
                    m['progress'] = progress
                    return
            self._message.append({'msg': msg, 'progress': progress})

    def reset(self, msg=None):
        """
        resets message list

        :param msg: optional message dict to reset to
        :type msg: Dict[AnyStr, int] or None
        """
        msg = msg or {'msg': 'Loading', 'progress': -1}
        with self.lock:
            self._message = [msg]


loading_msg = LoadingMessage()
