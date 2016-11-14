# !/usr/bin/env python2
# encoding:utf-8
# author:dbr/Ben
# project:tvdb_api
# repository:http://github.com/dbr/tvdb_api
# license:unlicense (http://unlicense.org/)

import traceback
from functools import wraps

__author__ = 'dbr/Ben'
__version__ = '1.9'

import os
import time
import getpass
import StringIO
import tempfile
import warnings
import logging
import zipfile
import requests
import requests.exceptions

try:
    import gzip
except ImportError:
    gzip = None

from lib.dateutil.parser import parse
from lib.cachecontrol import CacheControl, caches

from lib.etreetodict import ConvertXmlToDict
from tvdb_ui import BaseUI, ConsoleUI
from tvdb_exceptions import (tvdb_error, tvdb_shownotfound,
                             tvdb_seasonnotfound, tvdb_episodenotfound, tvdb_attributenotfound)

from sickbeard import logger


def retry(ExceptionToCheck, tries=4, delay=3, backoff=2, logr=None):
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
    :param logr: logger to use. If None, print
    :type logr: logging.Logger instance
    """

    def deco_retry(f):

        @wraps(f)
        def f_retry(*args, **kwargs):
            mtries, mdelay = tries, delay
            while mtries > 1:
                try:
                    return f(*args, **kwargs)
                except ExceptionToCheck, e:
                    msg = 'TVDB_API :: %s, Retrying in %d seconds...' % (str(e), mdelay)
                    if logr:
                        logger.log(msg, logger.WARNING)
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

    def __init__(self):
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
        if isinstance(key, int) or key.isdigit():
            # Episode number x was not found
            raise tvdb_seasonnotfound('Could not find season %s' % (repr(key)))
        else:
            # If it's not numeric, it must be an attribute name, which
            # doesn't exist, so attribute error.
            raise tvdb_attributenotfound('Cannot find attribute %s' % (repr(key)))

    def airedOn(self, date):
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
    def __init__(self, show=None):
        """The show attribute points to the parent show
        """
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
    def __init__(self, season=None):
        """The season attribute points to the parent season
        """
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
        for cur_key, cur_value in self.items():
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
                 actors=False,
                 custom_ui=None,
                 language=None,
                 search_all_languages=False,
                 apikey=None,
                 forceConnect=False,
                 useZip=False,
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

        forceConnect (bool):
            If true it will always try to connect to theTVDB.com even if we
            recently timed out. By default it will wait one minute before
            trying again, and any requests within that one minute window will
            return an exception immediately.

        useZip (bool):
            Download the zip archive where possibale, instead of the xml.
            This is only used when all episodes are pulled.
            And only the main language xml is used, the actor and banner xml are lost.
        """

        self.shows = ShowContainer()  # Holds all Show classes
        self.corrections = {}  # Holds show-name to show_id mapping

        self.config = {}

        if None is not apikey:
            self.config['apikey'] = apikey
        else:
            self.config['apikey'] = '0629B785CE550C8D'  # tvdb_api's API key

        self.config['debug_enabled'] = debug  # show debugging messages

        self.config['custom_ui'] = custom_ui

        self.config['interactive'] = interactive  # prompt for correct series?

        self.config['select_first'] = select_first

        self.config['search_all_languages'] = search_all_languages

        self.config['useZip'] = useZip

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
        self.config['base_url'] = 'http://thetvdb.com'

        if self.config['search_all_languages']:
            self.config['url_get_series'] = u'%(base_url)s/api/GetSeries.php' % self.config
            self.config['params_get_series'] = {'seriesname': '', 'language': 'all'}
        else:
            self.config['url_get_series'] = u'%(base_url)s/api/GetSeries.php' % self.config
            self.config['params_get_series'] = {'seriesname': '', 'language': self.config['language']}

        self.config['url_epInfo'] = u'%(base_url)s/api/%(apikey)s/series/%%s/all/%%s.xml' % self.config
        self.config['url_epInfo_zip'] = u'%(base_url)s/api/%(apikey)s/series/%%s/all/%%s.zip' % self.config

        self.config['url_seriesInfo'] = u'%(base_url)s/api/%(apikey)s/series/%%s/%%s.xml' % self.config
        self.config['url_actorsInfo'] = u'%(base_url)s/api/%(apikey)s/series/%%s/actors.xml' % self.config

        self.config['url_seriesBanner'] = u'%(base_url)s/api/%(apikey)s/series/%%s/banners.xml' % self.config
        self.config['url_artworkPrefix'] = u'%(base_url)s/banners/%%s' % self.config

    def log(self, msg, log_level=logger.DEBUG):
        logger.log('TVDB_API :: %s' % (msg.replace(self.config['apikey'], '<apikey>')), log_level=log_level)

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
        self.log('Retrieving URL %s' % url)

        session = requests.session()

        if self.config['cache_enabled']:
            session = CacheControl(session, cache=caches.FileCache(self.config['cache_location']))

        if self.config['proxy']:
            self.log('Using proxy for URL: %s' % url)
            session.proxies = {'http': self.config['proxy'], 'https': self.config['proxy']}

        session.headers.update({'Accept-Encoding': 'gzip,deflate'})

        try:
            resp = session.get(url.strip(), params=params)
        except requests.exceptions.HTTPError, e:
            raise tvdb_error('HTTP error %s while loading URL %s' % (e.errno, url))
        except requests.exceptions.ConnectionError, e:
            raise tvdb_error('Connection error %s while loading URL %s' % (e.message, url))
        except requests.exceptions.Timeout, e:
            raise tvdb_error('Connection timed out %s while loading URL %s' % (e.message, url))
        except Exception:
            raise tvdb_error('Unknown exception while loading URL %s: %s' % (url, traceback.format_exc()))

        def process_data(data):
            te = ConvertXmlToDict(data)
            if isinstance(te, dict) and 'Data' in te and isinstance(te['Data'], dict) \
                    and 'Series' in te['Data'] and isinstance(te['Data']['Series'], dict) \
                    and 'FirstAired' in te['Data']['Series']:
                try:
                    value = parse(te['Data']['Series']['FirstAired'], fuzzy=True).strftime('%Y-%m-%d')
                except (StandardError, Exception):
                    value = None
                te['Data']['Series']['firstaired'] = value
            return te

        if resp.ok:
            if 'application/zip' in resp.headers.get('Content-Type', ''):
                try:
                    # TODO: The zip contains actors.xml and banners.xml, which are currently ignored [GH-20]
                    self.log('We received a zip file unpacking now ...')
                    zipdata = StringIO.StringIO()
                    zipdata.write(resp.content)
                    myzipfile = zipfile.ZipFile(zipdata)
                    return process_data(myzipfile.read('%s.xml' % language))
                except zipfile.BadZipfile:
                    raise tvdb_error('Bad zip file received from thetvdb.com, could not read it')
            else:
                try:
                    return process_data(resp.content.strip())
                except (StandardError, Exception):
                    return dict([(u'data', None)])

    def _getetsrc(self, url, params=None, language=None):
        """Loads a URL using caching, returns an ElementTree of the source
        """
        try:
            src = self._load_url(url, params=params, language=language).values()[0]
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

    def _set_show_data(self, sid, key, value):
        """Sets self.shows[sid] to a new Show instance, or sets the data
        """
        if sid not in self.shows:
            self.shows[sid] = Show()
        self.shows[sid].data[key] = value

    @staticmethod
    def _clean_data(data):
        """Cleans up strings returned by TheTVDB.com

        Issues corrected:
        - Replaces &amp; with &
        - Trailing whitespace
        """
        return data if not isinstance(data, basestring) else data.strip().replace(u'&amp;', u'&')

    def _get_url_artwork(self, image):
        return image and (self.config['url_artworkPrefix'] % image) or image

    def search(self, series):
        """This searches TheTVDB.com for the series name
        and returns the result list
        """
        series = series.encode('utf-8')
        self.log('Searching for show %s' % series)
        self.config['params_get_series']['seriesname'] = series

        try:
            series_found = self._getetsrc(self.config['url_get_series'], self.config['params_get_series'])
            if series_found:
                if not isinstance(series_found['Series'], list):
                    series_found['Series'] = [series_found['Series']]
                series_found['Series'] = [{k.lower(): v for k, v in s.iteritems()} for s in series_found['Series']]
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
            self.log('Series result returned zero')
            raise tvdb_shownotfound('Show-name search returned zero results (cannot find show on TVDB)')

        if None is not self.config['custom_ui']:
            self.log('Using custom UI %s' % (repr(self.config['custom_ui'])))
            custom_ui = self.config['custom_ui']
            ui = custom_ui(config=self.config)
        else:
            if not self.config['interactive']:
                self.log('Auto-selecting first search result using BaseUI')
                ui = BaseUI(config=self.config)
            else:
                self.log('Interactively selecting show using ConsoleUI')
                ui = ConsoleUI(config=self.config)

        return ui.selectSeries(all_series)

    def _parse_banners(self, sid):
        """Parses banners XML, from
        http://thetvdb.com/api/[APIKEY]/series/[SERIES ID]/banners.xml

        Banners are retrieved using t['show name]['_banners'], for example:

        >> t = Tvdb(banners = True)
        >> t['scrubs']['_banners'].keys()
        ['fanart', 'poster', 'series', 'season']
        >> t['scrubs']['_banners']['poster']['680x1000']['35308']['_bannerpath']
        u'http://thetvdb.com/banners/posters/76156-2.jpg'
        >>

        Any key starting with an underscore has been processed (not the raw
        data from the XML)

        This interface will be improved in future versions.
        """
        self.log('Getting season banners for %s' % sid)
        banners_et = self._getetsrc(self.config['url_seriesBanner'] % sid)
        banners = {}

        try:
            for cur_banner in banners_et['banner']:
                bid = cur_banner['id']
                btype = cur_banner['bannertype']
                btype2 = cur_banner['bannertype2']
                if None is btype or None is btype2:
                    continue
                if btype not in banners:
                    banners[btype] = {}
                if btype2 not in banners[btype]:
                    banners[btype][btype2] = {}
                if bid not in banners[btype][btype2]:
                    banners[btype][btype2][bid] = {}

                for k, v in cur_banner.items():
                    if None is k or None is v:
                        continue

                    k, v = k.lower(), v.lower()
                    banners[btype][btype2][bid][k] = v

                for k, v in banners[btype][btype2][bid].items():
                    if k.endswith('path'):
                        new_key = '_%s' % k
                        self.log('Transforming %s to %s' % (k, new_key))
                        new_url = self._get_url_artwork(v)
                        banners[btype][btype2][bid][new_key] = new_url
        except (StandardError, Exception):
            pass

        self._set_show_data(sid, '_banners', banners)

    def _parse_actors(self, sid):
        """Parsers actors XML, from
        http://thetvdb.com/api/[APIKEY]/series/[SERIES ID]/actors.xml

        Actors are retrieved using t['show name]['_actors'], for example:

        >> t = Tvdb(actors = True)
        >> actors = t['scrubs']['_actors']
        >> type(actors)
        <class 'tvdb_api.Actors'>
        >> type(actors[0])
        <class 'tvdb_api.Actor'>
        >> actors[0]
        <Actor "Zach Braff">
        >> sorted(actors[0].keys())
        ['id', 'image', 'name', 'role', 'sortorder']
        >> actors[0]['name']
        u'Zach Braff'
        >> actors[0]['image']
        u'http://thetvdb.com/banners/actors/43640.jpg'

        Any key starting with an underscore has been processed (not the raw
        data from the XML)
        """
        self.log('Getting actors for %s' % sid)
        actors_et = self._getetsrc(self.config['url_actorsInfo'] % sid)

        cur_actors = Actors()
        try:
            for curActorItem in actors_et['actor']:
                cur_actor = Actor()
                for k, v in curActorItem.items():
                    k = k.lower()
                    if None is not v:
                        if 'image' == k:
                            v = self._get_url_artwork(v)
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

        if None is self.config['language']:
            self.log('Config language is none, using show language')
            if None is language:
                raise tvdb_error('config[\'language\'] was None, this should not happen')
            get_show_in_language = language
        else:
            self.log('Configured language %s override show language of %s' % (self.config['language'], language))
            get_show_in_language = self.config['language']

        # Parse show information
        self.log('Getting all series data for %s' % sid)
        url = (self.config['url_seriesInfo'] % (sid, language), self.config['url_epInfo%s' % ('', '_zip')[self.config['useZip']]] % (sid, language))[get_ep_info]
        show_data = self._getetsrc(url, language=get_show_in_language)

        # check and make sure we have data to process and that it contains a series name
        if not len(show_data) or (isinstance(show_data, dict) and 'SeriesName' not in show_data['Series']):
            return False

        for k, v in show_data['Series'].iteritems():
            if None is not v:
                if k in ['banner', 'fanart', 'poster']:
                    v = self._get_url_artwork(v)
                else:
                    v = self._clean_data(v)

            self._set_show_data(sid, k.lower(), v)

        if get_ep_info:
            # Parse banners
            if self.config['banners_enabled']:
                self._parse_banners(sid)

            # Parse actors
            if self.config['actors_enabled']:
                self._parse_actors(sid)

            # Parse episode data
            self.log('Getting all episodes of %s' % sid)

            if 'Episode' not in show_data:
                return False

            episodes = show_data['Episode']
            if not isinstance(episodes, list):
                episodes = [episodes]

            dvd_order = {'dvd': [], 'network': []}
            for cur_ep in episodes:
                if self.config['dvdorder']:
                    use_dvd = cur_ep['DVD_season'] not in (None, '') and cur_ep['DVD_episodenumber'] not in (None, '')
                else:
                    use_dvd = False

                if use_dvd:
                    elem_seasnum, elem_epno = cur_ep['DVD_season'], cur_ep['DVD_episodenumber']
                else:
                    elem_seasnum, elem_epno = cur_ep['SeasonNumber'], cur_ep['EpisodeNumber']

                if None is elem_seasnum or None is elem_epno:
                    self.log('An episode has incomplete season/episode number (season: %r, episode: %r)' % (
                        elem_seasnum, elem_epno), logger.WARNING)
                    continue  # Skip to next episode

                # float() is because https://github.com/dbr/tvnamer/issues/95 - should probably be fixed in TVDB data
                seas_no = int(float(elem_seasnum))
                ep_no = int(float(elem_epno))

                if self.config['dvdorder']:
                    dvd_order[('network', 'dvd')[use_dvd]] += ['S%02dE%02d' % (seas_no, ep_no)]

                for k, v in cur_ep.items():
                    k = k.lower()

                    if None is not v:
                        if 'filename' == k:
                            v = self._get_url_artwork(v)
                        else:
                            v = self._clean_data(v)

                    self._set_item(sid, seas_no, ep_no, k, v)

            if self.config['dvdorder']:
                num_dvd, num_network = [len(dvd_order[x]) for x in 'dvd', 'network']
                num_all = num_dvd + num_network
                if num_all:
                    self.log('Of %s episodes, %s use the DVD order, and %s use the network aired order' % (
                        num_all, num_dvd, num_network))
                    for ep_numbers in [', '.join(dvd_order['dvd'][i:i + 5]) for i in xrange(0, num_dvd, 5)]:
                        self.log('Using DVD order: %s' % ep_numbers)

        return True

    def _name_to_sid(self, name):
        """Takes show name, returns the correct series ID (if the show has
        already been grabbed), or grabs all episodes and returns
        the correct SID.
        """
        if name in self.corrections:
            self.log('Correcting %s to %s' % (name, self.corrections[name]))
            return self.corrections[name]
        else:
            self.log('Getting show %s' % name)
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
        [[self._set_show_data(show['id'], k, v) for k, v in show.items()] for show in selected_series]
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
