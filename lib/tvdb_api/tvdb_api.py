# !/usr/bin/env python2
# encoding:utf-8
# author:dbr/Ben
# project:tvdb_api
# repository:http://github.com/dbr/tvdb_api
# license:unlicense (http://unlicense.org/)

from functools import wraps

__author__ = 'dbr/Ben'
__version__ = '2.0'
__api_version__ = '2.1.2'

import os
import time
import getpass
import tempfile
import warnings
import logging
import requests
import requests.exceptions
import datetime
from sickbeard.helpers import getURL

from lib.dateutil.parser import parse
from lib.cachecontrol import CacheControl, caches

from tvdb_ui import BaseUI, ConsoleUI
from tvdb_exceptions import (tvdb_error, tvdb_shownotfound,
                             tvdb_seasonnotfound, tvdb_episodenotfound, tvdb_attributenotfound)


def log():
    return logging.getLogger('tvdb_api')


def retry(ExceptionToCheck, tries=4, delay=3, backoff=2, logger=None):
    """Retry calling the decorated function using an exponential backoff.

    http://www.saltycrane.com/blog/2009/11/trying-out-retry-decorator-python/
    original from: http://wiki.python.org/moin/PythonDecoratorLibrary#Retry

    :param ExceptionToCheck: the exception to check. may be a tuple of
        exceptions to check
    :type ExceptionToCheck: Exception or tuple
    :param tries: number of times to try (not retry) before giving up
    :type tries: int
    :param delay: initial delay between retries in seconds
    :type delay: int
    :param backoff: backoff multiplier e.g. value of 2 will double the delay
        each retry
    :type backoff: int
    :param logger: logger to use. If None, print
    :type logger: logging.Logger instance
    """

    def deco_retry(f):

        @wraps(f)
        def f_retry(*args, **kwargs):
            mtries, mdelay = tries, delay
            while mtries > 1:
                try:
                    return f(*args, **kwargs)
                except ExceptionToCheck, e:
                    msg = '%s, Retrying in %d seconds...' % (str(e), mdelay)
                    if logger:
                        logger.warning(msg)
                    else:
                        print msg
                    time.sleep(mdelay)
                    mtries -= 1
                    mdelay *= backoff
            return f(*args, **kwargs)

        return f_retry  # true decorator

    return deco_retry


class ShowContainer(dict):
    """Simple dict that holds a series of Show instances
    """

    def __init__(self, **kwargs):
        super(ShowContainer, self).__init__(**kwargs)
        self._stack = []
        self._lastgc = time.time()

    def __set_item__(self, key, value):
        self._stack.append(key)

        # keep only the 100th latest results
        if time.time() - self._lastgc > 20:
            for o in self._stack[:-100]:
                del self[o]

            self._stack = self._stack[-100:]

            self._lastgc = time.time()

        super(ShowContainer, self).__set_item__(key, value)


class Show(dict):
    """Holds a dict of seasons, and show data.
    """

    def __init__(self):
        dict.__init__(self)
        self.data = {}

    def __repr__(self):
        return '<Show %r (containing %s seasons)>' % (self.data.get(u'seriesname', 'instance'), len(self))

    def __getattr__(self, key):
        if key in self:
            # Key is an episode, return it
            return self[key]

        if key in self.data:
            # Non-numeric request is for show-data
            return self.data[key]

        raise AttributeError

    def __getitem__(self, key):
        if key in self:
            # Key is an episode, return it
            return dict.__getitem__(self, key)

        if key in self.data:
            # Non-numeric request is for show-data
            return dict.__getitem__(self.data, key)

        # Data wasn't found, raise appropriate error
        if isinstance(key, (int, long)) or isinstance(key, basestring) and key.isdigit():
            # Episode number x was not found
            raise tvdb_seasonnotfound('Could not find season %s' % (repr(key)))
        else:
            # If it's not numeric, it must be an attribute name, which
            # doesn't exist, so attribute error.
            raise tvdb_attributenotfound('Cannot find attribute %s' % (repr(key)))

    def aired_on(self, date):
        ret = self.search(str(date), 'firstaired')
        if 0 == len(ret):
            raise tvdb_episodenotfound('Could not find any episodes that aired on %s' % date)
        return ret

    def search(self, term=None, key=None):
        """
        Search all episodes in show. Can search all data, or a specific key (for
        example, episodename)

        Always returns an array (can be empty). First index contains the first
        match, and so on.

        Each array index is an Episode() instance, so doing
        search_results[0]['episodename'] will retrieve the episode name of the
        first match.

        Search terms are converted to lower case (unicode) strings.

        # Examples
        
        These examples assume t is an instance of Tvdb():
        
        >> t = Tvdb()
        >>

        To search for all episodes of Scrubs with a bit of data
        containing "my first day":

        >> t['Scrubs'].search("my first day")
        [<Episode 01x01 - My First Day>]
        >>

        Search for "My Name Is Earl" episode named "Faked His Own Death":

        >> t['My Name Is Earl'].search('Faked His Own Death', key = 'episodename')
        [<Episode 01x04 - Faked His Own Death>]
        >>

        To search Scrubs for all episodes with "mentor" in the episode name:

        >> t['scrubs'].search('mentor', key = 'episodename')
        [<Episode 01x02 - My Mentor>, <Episode 03x15 - My Tormented Mentor>]
        >>

        # Using search results

        >> results = t['Scrubs'].search("my first")
        >> print results[0]['episodename']
        My First Day
        >> for x in results: print x['episodename']
        My First Day
        My First Step
        My First Kill
        >>
        """
        results = []
        for cur_season in self.values():
            searchresult = cur_season.search(term=term, key=key)
            if 0 != len(searchresult):
                results.extend(searchresult)

        return results


class Season(dict):
    def __init__(self, show=None, **kwargs):
        """The show attribute points to the parent show
        """
        super(Season, self).__init__(**kwargs)
        self.show = show

    def __repr__(self):
        return '<Season instance (containing %s episodes)>' % (len(self.keys()))

    def __getattr__(self, episode_number):
        if episode_number in self:
            return self[episode_number]
        raise AttributeError

    def __getitem__(self, episode_number):
        if episode_number not in self:
            raise tvdb_episodenotfound('Could not find episode %s' % (repr(episode_number)))
        else:
            return dict.__getitem__(self, episode_number)

    def search(self, term=None, key=None):
        """Search all episodes in season, returns a list of matching Episode
        instances.

        >> t = Tvdb()
        >> t['scrubs'][1].search('first day')
        [<Episode 01x01 - My First Day>]
        >>

        See Show.search documentation for further information on search
        """
        results = []
        for ep in self.values():
            searchresult = ep.search(term=term, key=key)
            if None is not searchresult:
                results.append(searchresult)
        return results


class Episode(dict):
    def __init__(self, season=None, **kwargs):
        """The season attribute points to the parent season
        """
        super(Episode, self).__init__(**kwargs)
        self.season = season

    def __repr__(self):
        seasno, epno = int(self.get(u'seasonnumber', 0)), int(self.get(u'episodenumber', 0))
        epname = self.get(u'episodename')
        if None is not epname:
            return '<Episode %02dx%02d - %r>' % (seasno, epno, epname)
        else:
            return '<Episode %02dx%02d>' % (seasno, epno)

    def __getattr__(self, key):
        if key in self:
            return self[key]
        raise AttributeError

    def __getitem__(self, key):
        try:
            return dict.__getitem__(self, key)
        except KeyError:
            raise tvdb_attributenotfound('Cannot find attribute %s' % (repr(key)))

    def search(self, term=None, key=None):
        """Search episode data for term, if it matches, return the Episode (self).
        The key parameter can be used to limit the search to a specific element,
        for example, episodename.

        This primarily for use use by Show.search and Season.search. See
        Show.search for further information on search

        Simple example:

        >> e = Episode()
        >> e['episodename'] = "An Example"
        >> e.search("examp")
        <Episode 00x00 - An Example>
        >>

        Limiting by key:

        >> e.search("examp", key = "episodename")
        <Episode 00x00 - An Example>
        >>
        """
        if None is term:
            raise TypeError('must supply string to search for (contents)')

        term = unicode(term).lower()
        for cur_key, cur_value in self.iteritems():
            cur_key, cur_value = unicode(cur_key).lower(), unicode(cur_value).lower()
            if None is not key and cur_key != key:
                # Do not search this key
                continue
            if cur_value.find(unicode(term).lower()) > -1:
                return self


class Actors(list):
    """Holds all Actor instances for a show
    """
    pass


class Actor(dict):
    """Represents a single actor. Should contain..

    id,
    image,
    name,
    role,
    sortorder
    """

    def __repr__(self):
        return '<Actor "%r">' % self.get('name')


class Tvdb:
    """Create easy-to-use interface to name of season/episode name
    >> t = Tvdb()
    >> t['Scrubs'][1][24]['episodename']
    u'My Last Day'
    """

    def __init__(self,
                 interactive=False,
                 select_first=False,
                 debug=False,
                 cache=True,
                 banners=False,
                 fanart=False,
                 actors=False,
                 custom_ui=None,
                 language=None,
                 search_all_languages=False,
                 apikey=None,
                 dvdorder=False,
                 proxy=None):

        """interactive (True/False):
            When True, uses built-in console UI is used to select the correct show.
            When False, the first search result is used.

        select_first (True/False):
            Automatically selects the first series search result (rather
            than showing the user a list of more than one series).
            Is overridden by interactive = False, or specifying a custom_ui

        debug (True/False) DEPRECATED:
             Replaced with proper use of logging module. To show debug messages:

                 >> import logging
                 >> logging.basicConfig(level = logging.DEBUG)

        cache (True/False/str/unicode/urllib2 opener):
            Retrieved XML are persisted to to disc. If true, stores in
            tvdb_api folder under your systems TEMP_DIR, if set to
            str/unicode instance it will use this as the cache
            location. If False, disables caching.  Can also be passed
            an arbitrary Python object, which is used as a urllib2
            opener, which should be created by urllib2.build_opener

        banners (True/False):
            Retrieves the banners for a show. These are accessed
            via the _banners key of a Show(), for example:

            >> Tvdb(banners=True)['scrubs']['_banners'].keys()
            ['fanart', 'poster', 'series', 'season']

        actors (True/False):
            Retrieves a list of the actors for a show. These are accessed
            via the _actors key of a Show(), for example:

            >> t = Tvdb(actors=True)
            >> t['scrubs']['_actors'][0]['name']
            u'Zach Braff'

        custom_ui (tvdb_ui.BaseUI subclass):
            A callable subclass of tvdb_ui.BaseUI (overrides interactive option)

        language (2 character language abbreviation):
            The language of the returned data. Is also the language search
            uses. Default is "en" (English). For full list, run..

            >> Tvdb().config['valid_languages'] #doctest: +ELLIPSIS
            ['da', 'fi', 'nl', ...]

        search_all_languages (True/False):
            By default, Tvdb will only search in the language specified using
            the language option. When this is True, it will search for the
            show in and language

        apikey (str/unicode):
            Override the default thetvdb.com API key. By default it will use
            tvdb_api's own key (fine for small scripts), but you can use your
            own key if desired - this is recommended if you are embedding
            tvdb_api in a larger application)
            See http://thetvdb.com/?tab=apiregister to get your own key

        """

        self.shows = ShowContainer()  # Holds all Show classes
        self.corrections = {}  # Holds show-name to show_id mapping

        self.config = {}

        if None is not apikey:
            self.config['apikey'] = apikey
        else:
            self.config['apikey'] = '0629B785CE550C8D'  # tvdb_api's API key

        self.token = {'token': None, 'datetime': datetime.datetime.fromordinal(1)}

        self.config['debug_enabled'] = debug  # show debugging messages

        self.config['custom_ui'] = custom_ui

        self.config['interactive'] = interactive  # prompt for correct series?

        self.config['select_first'] = select_first

        self.config['search_all_languages'] = search_all_languages

        self.config['dvdorder'] = dvdorder

        self.config['proxy'] = proxy

        if cache is True:
            self.config['cache_enabled'] = True
            self.config['cache_location'] = self._get_temp_dir()
        elif cache is False:
            self.config['cache_enabled'] = False
        elif isinstance(cache, basestring):
            self.config['cache_enabled'] = True
            self.config['cache_location'] = cache
        else:
            raise ValueError('Invalid value for Cache %r (type was %s)' % (cache, type(cache)))

        self.config['banners_enabled'] = banners
        self.config['fanart_enabled'] = fanart
        self.config['actors_enabled'] = actors

        if self.config['debug_enabled']:
            warnings.warn('The debug argument to tvdb_api.__init__ will be removed in the next version. ' +
                          'To enable debug messages, use the following code before importing: ' +
                          'import logging; logging.basicConfig(level=logging.DEBUG)')
            logging.basicConfig(level=logging.DEBUG)

        # List of language from http://thetvdb.com/api/0629B785CE550C8D/languages.xml
        # Hard-coded here as it is realtively static, and saves another HTTP request, as
        # recommended on http://thetvdb.com/wiki/index.php/API:languages.xml
        self.config['valid_languages'] = [
            'da', 'fi', 'nl', 'de', 'it', 'es', 'fr', 'pl', 'hu', 'el', 'tr',
            'ru', 'he', 'ja', 'pt', 'zh', 'cs', 'sl', 'hr', 'ko', 'en', 'sv', 'no'
        ]

        # thetvdb.com should be based around numeric language codes,
        # but to link to a series like http://thetvdb.com/?tab=series&id=79349&lid=16
        # requires the language ID, thus this mapping is required (mainly
        # for usage in tvdb_ui - internally tvdb_api will use the language abbreviations)
        self.config['langabbv_to_id'] = {'el': 20, 'en': 7, 'zh': 27,
                                         'it': 15, 'cs': 28, 'es': 16, 'ru': 22, 'nl': 13, 'pt': 26, 'no': 9,
                                         'tr': 21, 'pl': 18, 'fr': 17, 'hr': 31, 'de': 14, 'da': 10, 'fi': 11,
                                         'hu': 19, 'ja': 25, 'he': 24, 'ko': 32, 'sv': 8, 'sl': 30}

        if None is language:
            self.config['language'] = 'en'
        else:
            if language not in self.config['valid_languages']:
                raise ValueError('Invalid language %s, options are: %s' % (language, self.config['valid_languages']))
            else:
                self.config['language'] = language

        # The following url_ configs are based of the
        # http://thetvdb.com/wiki/index.php/Programmers_API
        self.config['base_url'] = 'https://api.thetvdb.com/'

        self.config['url_get_series'] = '%(base_url)s/search/series' % self.config
        self.config['params_get_series'] = {'name': ''}

        self.config['url_epInfo'] = '%(base_url)sseries/%%s/episodes?page=%%s' % self.config

        self.config['url_seriesInfo'] = '%(base_url)sseries/%%s' % self.config
        self.config['url_actorsInfo'] = '%(base_url)sseries/%%s/actors' % self.config

        self.config['url_seriesBanner'] = '%(base_url)sseries/%%s/images/query?keyType=%%s' % self.config
        self.config['url_artworkPrefix'] = 'https://thetvdb.com/banners/%s'

    def get_new_token(self):
        token = None
        url = '%s%s' % (self.config['base_url'], 'login')
        params = {'apikey': self.config['apikey']}
        resp = getURL(url.strip(), post_json=params, json=True)
        if resp:
            if 'token' in resp:
                token = resp['token']

        return {'token': token, 'datetime': datetime.datetime.now()}

    def get_token(self):
        if self.token.get('token') is None or datetime.datetime.now() - self.token.get(
                'datetime', datetime.datetime.fromordinal(1)) > datetime.timedelta(hours=23):
            self.token = self.get_new_token()
        if not self.token.get('token'):
            raise tvdb_error('Could not get Authentification Token')
        return self.token.get('token')

    @staticmethod
    def _get_temp_dir():
        """Returns the [system temp dir]/tvdb_api-u501 (or
        tvdb_api-myuser)
        """
        if hasattr(os, 'getuid'):
            uid = 'u%d' % (os.getuid())
        else:
            # For Windows
            try:
                uid = getpass.getuser()
            except ImportError:
                return os.path.join(tempfile.gettempdir(), 'tvdb_api')

        return os.path.join(tempfile.gettempdir(), 'tvdb_api-%s' % uid)

    @retry(tvdb_error)
    def _load_url(self, url, params=None, language=None):
        log().debug('Retrieving URL %s' % url)

        session = requests.session()

        if self.config['cache_enabled']:
            session = CacheControl(session, cache=caches.FileCache(self.config['cache_location']))

        if self.config['proxy']:
            log().debug('Using proxy for URL: %s' % url)
            session.proxies = {'http': self.config['proxy'], 'https': self.config['proxy']}

        session.headers.update({'Accept-Encoding': 'gzip,deflate', 'Authorization': 'Bearer %s' % self.get_token(),
                                'Accept': 'application/vnd.thetvdb.v%s' % __api_version__})

        if None is not language and language in self.config['valid_languages']:
            session.headers.update({'Accept-Language': language})

        resp = getURL(url.strip(), params=params, session=session, json=True)

        map_show = {'airstime': 'airs_time', 'airsdayofweek': 'airs_dayofweek', 'imdbid': 'imdb_id'}

        def map_show_keys(data):
            for k, v in data.iteritems():
                k_org = k
                k = k.lower()
                if None is not v:
                    if k in ['banner', 'fanart', 'poster']:
                        v = self.config['url_artworkPrefix'] % v
                    elif 'genre' == k:
                        v = '|%s|' % '|'.join([self._clean_data(c) for c in v if isinstance(c, basestring)])
                    elif 'firstaired' == k:
                        if v:
                            try:
                                v = parse(v, fuzzy=True).strftime('%Y-%m-%d')
                            except (StandardError, Exception):
                                v = None
                        else:
                            v = None
                    else:
                        v = self._clean_data(v)
                if k in map_show:
                    k = map_show[k]
                if k_org is not k:
                    del(data[k_org])
                data[k] = v
            return data

        if resp:
            if isinstance(resp['data'], dict):
                resp['data'] = map_show_keys(resp['data'])
            elif isinstance(resp['data'], list):
                for idx, row in enumerate(resp['data']):
                    if isinstance(row, dict):
                        resp['data'][idx] = map_show_keys(row)
            return resp
        return dict([(u'data', None)])

    def _getetsrc(self, url, params=None, language=None):
        """Loads a URL using caching
        """
        try:
            src = self._load_url(url, params=params, language=language)
            return src
        except (StandardError, Exception):
            return []

    def _set_item(self, sid, seas, ep, attrib, value):
        """Creates a new episode, creating Show(), Season() and
        Episode()s as required. Called by _get_show_data to populate show

        Since the nice-to-use tvdb[1][24]['name] interface
        makes it impossible to do tvdb[1][24]['name] = "name"
        and still be capable of checking if an episode exists
        so we can raise tvdb_shownotfound, we have a slightly
        less pretty method of setting items.. but since the API
        is supposed to be read-only, this is the best way to
        do it!
        The problem is that calling tvdb[1][24]['episodename'] = "name"
        calls __getitem__ on tvdb[1], there is no way to check if
        tvdb.__dict__ should have a key "1" before we auto-create it
        """
        if sid not in self.shows:
            self.shows[sid] = Show()
        if seas not in self.shows[sid]:
            self.shows[sid][seas] = Season(show=self.shows[sid])
        if ep not in self.shows[sid][seas]:
            self.shows[sid][seas][ep] = Episode(season=self.shows[sid][seas])
        self.shows[sid][seas][ep][attrib] = value

    def _set_show_data(self, sid, key, value, add=False):
        """Sets self.shows[sid] to a new Show instance, or sets the data
        """
        if sid not in self.shows:
            self.shows[sid] = Show()
        if add and isinstance(self.shows[sid].data, dict) and key in self.shows[sid].data:
            self.shows[sid].data[key].update(value)
        else:
            self.shows[sid].data[key] = value

    @staticmethod
    def _clean_data(data):
        """Cleans up strings returned by TheTVDB.com

        Issues corrected:
        - Replaces &amp; with &
        - Trailing whitespace
        """
        return data if not isinstance(data, basestring) else data.strip().replace(u'&amp;', u'&')

    def search(self, series):
        """This searches TheTVDB.com for the series name
        and returns the result list
        """
        series = series.encode('utf-8')
        self.config['params_get_series']['name'] = series
        log().debug('Searching for show %s' % series)

        try:
            series_found = self._getetsrc(self.config['url_get_series'], params=self.config['params_get_series'],
                                          language=self.config['language'])
            if series_found:
                return series_found.values()[0]
        except (StandardError, Exception):
            pass

        return []

    def _get_series(self, series):
        """This searches TheTVDB.com for the series name,
        If a custom_ui UI is configured, it uses this to select the correct
        series. If not, and interactive == True, ConsoleUI is used, if not
        BaseUI is used to select the first result.
        """
        all_series = self.search(series)
        if not isinstance(all_series, list):
            all_series = [all_series]

        if 0 == len(all_series):
            log().debug('Series result returned zero')
            raise tvdb_shownotfound('Show-name search returned zero results (cannot find show on TVDB)')

        if None is not self.config['custom_ui']:
            log().debug('Using custom UI %s' % (repr(self.config['custom_ui'])))
            custom_ui = self.config['custom_ui']
            ui = custom_ui(config=self.config)
        else:
            if not self.config['interactive']:
                log().debug('Auto-selecting first search result using BaseUI')
                ui = BaseUI(config=self.config)
            else:
                log().debug('Interactively selecting show using ConsoleUI')
                ui = ConsoleUI(config=self.config)

        return ui.selectSeries(all_series)

    def _parse_banners(self, sid, img_list):
        banners = {}

        try:
            for cur_banner in img_list:
                bid = cur_banner['id']
                btype = cur_banner['keytype']
                btype2 = cur_banner['resolution']
                if None is btype or None is btype2:
                    continue
                if btype not in banners:
                    banners[btype] = {}
                if btype2 not in banners[btype]:
                    banners[btype][btype2] = {}
                if bid not in banners[btype][btype2]:
                    banners[btype][btype2][bid] = {}

                for k, v in cur_banner.iteritems():
                    if None is k or None is v:
                        continue

                    k, v = k.lower(), v.lower() if isinstance(v, (str, unicode)) else v
                    if k == 'filename':
                        k = 'bannerpath'
                        banners[btype][btype2][bid]['_bannerpath'] = self.config['url_artworkPrefix'] % v
                    elif k == 'thumbnail':
                        k = 'thumbnailpath'
                        banners[btype][btype2][bid]['_thumbnailpath'] = self.config['url_artworkPrefix'] % v
                    elif k == 'keytype':
                        k = 'bannertype'
                    banners[btype][btype2][bid][k] = v

        except (StandardError, Exception):
            pass

        self._set_show_data(sid, '_banners', banners, add=True)

    def _parse_actors(self, sid, actor_list):

        cur_actors = Actors()
        try:
            for curActorItem in actor_list:
                cur_actor = Actor()
                for k, v in curActorItem.iteritems():
                    k = k.lower()
                    if None is not v:
                        if 'image' == k:
                            v = self.config['url_artworkPrefix'] % v
                        else:
                            v = self._clean_data(v)
                    cur_actor[k] = v
                cur_actors.append(cur_actor)
        except (StandardError, Exception):
            pass

        self._set_show_data(sid, '_actors', cur_actors)

    def _get_show_data(self, sid, language, get_ep_info=False):
        """Takes a series ID, gets the epInfo URL and parses the TVDB
        XML file into the shows dict in layout:
        shows[series_id][season_number][episode_number]
        """

        # Parse show information
        log().debug('Getting all series data for %s' % sid)
        url = self.config['url_seriesInfo'] % sid
        show_data = self._getetsrc(url, language=language)

        # check and make sure we have data to process and that it contains a series name
        if not isinstance(show_data, dict) or 'data' not in show_data or not isinstance(show_data['data'], dict) or 'seriesname' not in show_data['data']:
            return False

        for k, v in show_data['data'].iteritems():
            self._set_show_data(sid, k, v)

        if self.config['banners_enabled']:
            poster_data = self._getetsrc(self.config['url_seriesBanner'] % (sid, 'poster'), language=language)
            if poster_data and 'data' in poster_data and poster_data['data'] and len(poster_data['data']) > 1:
                b = self.config['url_artworkPrefix'] % poster_data['data'][0]['filename']
                self._parse_banners(sid, poster_data['data'])
            else:
                b = ''
            self._set_show_data(sid, u'poster', b)

        if self.config['fanart_enabled']:
            fanart_data = self._getetsrc(self.config['url_seriesBanner'] % (sid, 'fanart'), language=language)
            if fanart_data and 'data' in fanart_data and fanart_data['data'] and len(fanart_data['data']) > 1:
                f = self.config['url_artworkPrefix'] % fanart_data['data'][0]['filename']
                self._parse_banners(sid, fanart_data['data'])
            else:
                f = ''
            self._set_show_data(sid, u'fanart', f)

        if self.config['actors_enabled']:
            actor_data = self._getetsrc(self.config['url_actorsInfo'] % sid, language=language)
            if actor_data and 'data' in actor_data and actor_data['data'] and len(actor_data['data']) > 0:
                a = '|%s|' % '|'.join([n.get('name', '') for n in sorted(
                                        actor_data['data'], key=lambda x: x['sortorder'])])
                self._parse_actors(sid, actor_data['data'])
            else:
                a = '||'
            self._set_show_data(sid, u'actors', a)

        if get_ep_info:
            # Parse episode data
            log().debug('Getting all episodes of %s' % sid)

            page = 1
            episodes = []
            while page is not None:
                episode_data = self._getetsrc(self.config['url_epInfo'] % (sid, page), language=language)
                if isinstance(episode_data, dict) and episode_data['data'] is not None:
                    episodes.extend(episode_data['data'])
                page = episode_data['links']['next'] if isinstance(episode_data, dict) \
                    and 'links' in episode_data and 'next' in episode_data['links'] else None

            ep_map_keys = {'absolutenumber': u'absolute_number', 'airedepisodenumber': u'episodenumber',
                           'airedseason': u'seasonnumber', 'airedseasonid': u'seasonid',
                           'dvdepisodenumber': u'dvd_episodenumber', 'dvdseason': u'dvd_season'}

            for cur_ep in episodes:
                if self.config['dvdorder']:
                    log().debug('Using DVD ordering.')
                    use_dvd = None is not cur_ep.get('dvdseason') and None is not cur_ep.get('dvdepisodenumber')
                else:
                    use_dvd = False

                if use_dvd:
                    elem_seasnum, elem_epno = cur_ep.get('dvdseason'), cur_ep.get('dvdepisodenumber')
                else:
                    elem_seasnum, elem_epno = cur_ep.get('airedseason'), cur_ep.get('airedepisodenumber')

                if None is elem_seasnum or None is elem_epno:
                    log().warning('An episode has incomplete season/episode number (season: %r, episode: %r)' % (
                        elem_seasnum, elem_epno))
                    continue  # Skip to next episode

                # float() is because https://github.com/dbr/tvnamer/issues/95 - should probably be fixed in TVDB data
                seas_no = int(float(elem_seasnum))
                ep_no = int(float(elem_epno))

                for k, v in cur_ep.iteritems():
                    k = k.lower()

                    if None is not v:
                        if 'filename' == k:
                            v = self.config['url_artworkPrefix'] % v
                        else:
                            v = self._clean_data(v)

                    if k in ep_map_keys:
                        k = ep_map_keys[k]
                    self._set_item(sid, seas_no, ep_no, k, v)

        return True

    def _name_to_sid(self, name):
        """Takes show name, returns the correct series ID (if the show has
        already been grabbed), or grabs all episodes and returns
        the correct SID.
        """
        if name in self.corrections:
            log().debug('Correcting %s to %s' % (name, self.corrections[name]))
            return self.corrections[name]
        else:
            log().debug('Getting show %s' % name)
            selected_series = self._get_series(name)
            if isinstance(selected_series, dict):
                selected_series = [selected_series]
            sids = list(int(x['id']) for x in selected_series if
                        self._get_show_data(int(x['id']), self.config['language']))
            self.corrections.update(dict((x['seriesname'], int(x['id'])) for x in selected_series))
            return sids

    def __getitem__(self, key):
        """Handles tvdb_instance['seriesname'] calls.
        The dict index should be the show id
        """
        arg = None
        if isinstance(key, tuple) and 2 == len(key):
            key, arg = key
            if not isinstance(arg, bool):
                arg = None

        if isinstance(key, (int, long)):
            # Item is integer, treat as show id
            if key not in self.shows:
                self._get_show_data(key, self.config['language'], (True, arg)[arg is not None])
            return None if key not in self.shows else self.shows[key]

        key = str(key).lower()
        self.config['searchterm'] = key
        selected_series = self._get_series(key)
        if isinstance(selected_series, dict):
            selected_series = [selected_series]
        [[self._set_show_data(show['id'], k, v) for k, v in show.iteritems()] for show in selected_series]
        return selected_series

    def __repr__(self):
        return str(self.shows)


def main():
    """Simple example of using tvdb_api - it just
    grabs an episode name interactively.
    """
    import logging

    logging.basicConfig(level=logging.DEBUG)

    tvdb_instance = Tvdb(interactive=True, cache=False)
    print tvdb_instance['Lost']['seriesname']
    print tvdb_instance['Lost'][1][4]['episodename']


if '__main__' == __name__:
    main()
