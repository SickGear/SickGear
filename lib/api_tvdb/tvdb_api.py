# !/usr/bin/env python2
# encoding:utf-8
# author:dbr/Ben
# project:tvdb_api
# repository:http://github.com/dbr/tvdb_api
# license:un license (http://unlicense.org/)

from __future__ import absolute_import
from functools import wraps

__author__ = 'dbr/Ben'
__version__ = '2.0'
__api_version__ = '3.0.0'

import copy
import datetime
import getpass
import logging
import os
import random
import re
import requests
import requests.exceptions
import tempfile
import time
import warnings

from bs4_parser import BS4Parser
from collections import OrderedDict
from sg_helpers import clean_data, get_url, try_int
from sickbeard import ENV

from lib.cachecontrol import CacheControl, caches
from lib.dateutil.parser import parse
from lib.exceptions_helper import ConnectionSkipException
from lib.tvinfo_base import CastList, Character, CrewList, Person, RoleTypes, \
    TVINFO_TVDB, TVINFO_TVDB_SLUG, TVInfoBase, TVInfoIDs

from .tvdb_exceptions import TvdbError, TvdbShownotfound, TvdbTokenexpired
from .tvdb_ui import BaseUI, ConsoleUI

from _23 import filter_list, list_keys, list_values, map_list
from six import integer_types, iteritems, PY2, string_types

# noinspection PyUnreachableCode
if False:
    # noinspection PyUnresolvedReferences
    from typing import Any, AnyStr, Dict, List, Optional, Union
    from lib.tvinfo_base import TVInfoShow


THETVDB_V2_API_TOKEN = {'token': None, 'datetime': datetime.datetime.fromordinal(1)}
log = logging.getLogger('tvdb.api')
log.addHandler(logging.NullHandler())


# noinspection PyUnusedLocal
def _record_hook(r, *args, **kwargs):
    r.hook_called = True
    if 301 == r.status_code and isinstance(r.headers.get('Location'), string_types) \
            and r.headers.get('Location').startswith('http://api.thetvdb.com/'):
        r.headers['Location'] = r.headers['Location'].replace('http://', 'https://')
    return r


def retry(exception_to_check, tries=4, delay=3, backoff=2):
    """Retry calling the decorated function using an exponential backoff.

    http://www.saltycrane.com/blog/2009/11/trying-out-retry-decorator-python/
    original from: http://wiki.python.org/moin/PythonDecoratorLibrary#Retry

    :param exception_to_check: the exception to check. may be a tuple of
        exceptions to check
    :type exception_to_check: Exception or tuple
    :param tries: number of times to try (not retry) before giving up
    :type tries: int
    :param delay: initial delay between retries in seconds
    :type delay: int
    :param backoff: backoff multiplier e.g. value of 2 will double the delay
        each retry
    :type backoff: int
    """

    def deco_retry(f):

        @wraps(f)
        def f_retry(*args, **kwargs):
            mtries, mdelay = tries, delay
            auth_error = 0
            while 1 < mtries:
                try:
                    return f(*args, **kwargs)
                except exception_to_check as e:
                    msg = '%s, Retrying in %d seconds...' % (str(e), mdelay)
                    log.warning(msg)
                    time.sleep(mdelay)
                    if isinstance(e, TvdbTokenexpired) and not auth_error:
                        auth_error += 1
                    else:
                        mtries -= 1
                        mdelay *= backoff
                except ConnectionSkipException as e:
                    raise e
            try:
                return f(*args, **kwargs)
            except TvdbTokenexpired:
                if not auth_error:
                    return f(*args, **kwargs)
                raise TvdbTokenexpired
            except ConnectionSkipException as e:
                raise e

        return f_retry  # true decorator

    return deco_retry


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


class Tvdb(TVInfoBase):
    """Create easy-to-use interface to name of season/episode name
    >> t = Tvdb()
    >> t['Scrubs'][1][24]['episodename']
    u'My Last Day'
    """
    supported_id_searches = [TVINFO_TVDB, TVINFO_TVDB_SLUG]

    # noinspection PyUnusedLocal
    def __init__(self,
                 interactive=False,
                 select_first=False,
                 debug=False,
                 cache=True,
                 banners=False,
                 fanart=False,
                 posters=False,
                 seasons=False,
                 seasonwides=False,
                 actors=False,
                 custom_ui=None,
                 language=None,
                 search_all_languages=False,
                 apikey=None,
                 dvdorder=False,
                 proxy=None,
                 *args,
                 **kwargs):

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
            via the banners key of a Show(), for example:

            >> Tvdb(banners=True)['scrubs']['banners'].keys()
            ['fanart', 'poster', 'series', 'season']

        actors (True/False):
            Retrieves a list of the actors for a show. These are accessed
            via the actors key of a Show(), for example:

            >> t = Tvdb(actors=True)
            >> t['scrubs']['actors'][0]['name']
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

        super(Tvdb, self).__init__(*args, **kwargs)
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

        self.config['dvdorder'] = dvdorder

        self.config['proxy'] = proxy

        if cache is True:
            self.config['cache_enabled'] = True
            self.config['cache_location'] = self._get_temp_dir()
        elif cache is False:
            self.config['cache_enabled'] = False
        elif isinstance(cache, string_types):
            self.config['cache_enabled'] = True
            self.config['cache_location'] = cache
        else:
            raise ValueError('Invalid value for Cache %r (type was %s)' % (cache, type(cache)))

        self.config['banners_enabled'] = banners
        self.config['posters_enabled'] = posters
        self.config['seasons_enabled'] = seasons
        self.config['seasonwides_enabled'] = seasonwides
        self.config['fanart_enabled'] = fanart
        self.config['actors_enabled'] = actors

        if self.config['debug_enabled']:
            warnings.warn('The debug argument to tvdb_api.__init__ will be removed in the next version. ' +
                          'To enable debug messages, use the following code before importing: ' +
                          'import logging; logging.basicConfig(level=logging.DEBUG)')
            logging.basicConfig(level=logging.DEBUG)

        # List of language from http://thetvdb.com/api/0629B785CE550C8D/languages.xml
        # Hard-coded here as it is relatively static, and saves another HTTP request, as
        # recommended on http://thetvdb.com/wiki/index.php/API:languages.xml
        self.config['valid_languages'] = [
            'cs', 'da', 'de', 'el', 'en', 'es', 'fi', 'fr',
            'he', 'hr', 'hu', 'it', 'ja', 'ko', 'nl', 'no',
            'pl', 'pt', 'ru', 'sl', 'sv', 'tr', 'zh'
        ]

        # not mapped: el, sl, tr. added as guess: fin, pol. unknown: _1
        self.config['langabbv_23'] = {
            'cs': 'ces', 'da': 'dan', 'de': 'deu', 'en': 'eng', 'es': 'spa', 'fi': 'fin', 'fr': 'fra',
            'he': 'heb', 'hr': 'hrv', 'hu': 'hun', 'it': 'ita', 'ja': 'jpn', 'ko': 'kor', 'nb': 'nor',
            'nl': 'nld', 'no': 'nor',
            'pl': 'pol', 'pt': 'pot', 'ru': 'rus', 'sk': 'slv', 'sv': 'swe', 'zh': 'zho', '_1': 'srp',
        }
        self.config['valid_languages_3'] = list_values(self.config['langabbv_23'])

        # TheTvdb.com should be based around numeric language codes,
        # but to link to a series like http://thetvdb.com/?tab=series&id=79349&lid=16
        # requires the language ID, thus this mapping is required (mainly
        # for usage in tvdb_ui - internally tvdb_api will use the language abbreviations)
        self.config['langabbv_to_id'] = {
            'cs': 28, 'da': 10, 'de': 14, 'el': 20, 'en':  7, 'es': 16, 'fi': 11, 'fr': 17,
            'he': 24, 'hr': 31, 'hu': 19, 'it': 15, 'ja': 25, 'ko': 32, 'nl': 13, 'no':  9,
            'pl': 18, 'pt': 26, 'ru': 22, 'sl': 30, 'sv':  8, 'tr': 21, 'zh': 27
        }

        if not language:
            self.config['language'] = 'en'
        else:
            if language not in self.config['valid_languages']:
                raise ValueError('Invalid language %s, options are: %s' % (language, self.config['valid_languages']))
            else:
                self.config['language'] = language

        # The following url_ configs are based of the
        # http://thetvdb.com/wiki/index.php/Programmers_API
        self.config['base_url'] = 'https://thetvdb.com/'
        self.config['api3_url'] = 'https://api.thetvdb.com/'

        self.config['url_search_series'] = '%(api3_url)ssearch/series' % self.config
        self.config['params_search_series'] = {'name': ''}

        self.config['url_series_episodes_info'] = '%(api3_url)sseries/%%s/episodes?page=%%s' % self.config

        self.config['url_series_info'] = '%(api3_url)sseries/%%s' % self.config
        self.config['url_episodes_info'] = '%(api3_url)sepisodes/%%s' % self.config
        self.config['url_actors_info'] = '%(api3_url)sseries/%%s/actors' % self.config

        self.config['url_series_images'] = '%(api3_url)sseries/%%s/images/query?keyType=%%s' % self.config
        self.config['url_artworks'] = 'https://artworks.thetvdb.com/banners/%s'

        self.config['url_people'] = '%(base_url)speople/%%s' % self.config
        self.config['url_series_people'] = '%(base_url)sseries/%%s/people' % self.config
        self.config['url_series_all'] = '%(base_url)sseries/%%s/allseasons/official' % self.config
        self.config['url_series_dvd'] = '%(base_url)sseries/%%s/allseasons/dvd' % self.config
        self.config['url_series_abs'] = '%(base_url)sseries/%%s/seasons/absolute/1' % self.config

    def _search_show(self, name=None, ids=None, **kwargs):
        # type: (AnyStr, Dict[integer_types, integer_types], Optional[Any]) -> List[TVInfoShow]
        def map_data(data):
            data['poster'] = data.get('image')
            data['ids'] = TVInfoIDs(
                tvdb=data.get('id'),
                imdb=data.get('imdb_id') and try_int(data.get('imdb_id', '').replace('tt', ''), None))
            return data

        results = []
        if ids:
            if ids.get(TVINFO_TVDB):
                cache_id_key = 's-id-%s-%s' % (TVINFO_TVDB, ids[TVINFO_TVDB])
                is_none, shows = self._get_cache_entry(cache_id_key)
                if not self.config.get('cache_search') or (None is shows and not is_none):
                    try:
                        d_m = self._get_show_data(ids.get(TVINFO_TVDB), self.config['language'], direct_data=True)
                        self._set_cache_entry(cache_id_key, d_m, expire=self.search_cache_expire)
                    except (BaseException, Exception):
                        d_m = None
                else:
                    d_m = shows
                if d_m:
                    results = map_list(map_data, [d_m['data']])
            if ids.get(TVINFO_TVDB_SLUG):
                cache_id_key = 's-id-%s-%s' % (TVINFO_TVDB, ids[TVINFO_TVDB_SLUG])
                is_none, shows = self._get_cache_entry(cache_id_key)
                if not self.config.get('cache_search') or (None is shows and not is_none):
                    try:
                        d_m = self.get_series(ids.get(TVINFO_TVDB_SLUG).replace('-', ' '))
                        self._set_cache_entry(cache_id_key, d_m, expire=self.search_cache_expire)
                    except (BaseException, Exception):
                        d_m = None
                else:
                    d_m = shows
                if d_m:
                    for r in d_m:
                        if ids.get(TVINFO_TVDB_SLUG) == r['slug']:
                            results = map_list(map_data, [r])
                            break
        if name:
            for n in ([name], name)[isinstance(name, list)]:
                cache_name_key = 's-name-%s' % n
                is_none, shows = self._get_cache_entry(cache_name_key)
                if not self.config.get('cache_search') or (None is shows and not is_none):
                    try:
                        r = self.get_series(n)
                        self._set_cache_entry(cache_name_key, r, expire=self.search_cache_expire)
                    except (BaseException, Exception):
                        r = None
                else:
                    r = shows
                if r:
                    results.extend(map_list(map_data, r))

        seen = set()
        results = [seen.add(r['id']) or r for r in results if r['id'] not in seen]
        return results

    def get_new_token(self):
        global THETVDB_V2_API_TOKEN
        token = THETVDB_V2_API_TOKEN.get('token', None)
        dt = THETVDB_V2_API_TOKEN.get('datetime', datetime.datetime.fromordinal(1))
        url = '%s%s' % (self.config['api3_url'], 'login')
        params = {'apikey': self.config['apikey']}
        resp = get_url(url.strip(), post_json=params, parse_json=True, raise_skip_exception=True)
        if resp:
            if 'token' in resp:
                token = resp['token']
                dt = datetime.datetime.now()

        return {'token': token, 'datetime': dt}

    def get_token(self):
        global THETVDB_V2_API_TOKEN
        if None is THETVDB_V2_API_TOKEN.get(
                'token') or datetime.datetime.now() - THETVDB_V2_API_TOKEN.get(
                'datetime', datetime.datetime.fromordinal(1)) > datetime.timedelta(hours=23):
            THETVDB_V2_API_TOKEN = self.get_new_token()
        if not THETVDB_V2_API_TOKEN.get('token'):
            raise TvdbError('Could not get Authentification Token')
        return THETVDB_V2_API_TOKEN.get('token')

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

    def _match_url_pattern(self, pattern, url):
        if pattern in self.config:
            try:
                if PY2:
                    return None is not re.search('^%s$' % re.escape(self.config[pattern]).replace('\\%s', '[^/]+'), url)
                else:
                    return None is not re.search('^%s$' % re.escape(self.config[pattern]).replace(r'%s', '[^/]+'), url)
            except (BaseException, Exception):
                pass
        return False

    def is_apikey(self, check_url=None):
        return bool(self.config['apikey']) and (None is check_url or '://api' in check_url)

    @retry((TvdbError, TvdbTokenexpired))
    def _load_url(self, url, params=None, language=None, parse_json=False, **kwargs):
        log.debug('Retrieving URL %s' % url)

        parse_json = parse_json or self.is_apikey(url)
        session = requests.session()

        if self.config['cache_enabled']:
            session = CacheControl(session, cache=caches.FileCache(self.config['cache_location']))

        if self.config['proxy']:
            log.debug('Using proxy for URL: %s' % url)
            session.proxies = {'http': self.config['proxy'], 'https': self.config['proxy']}

        headers = {'Accept-Encoding': 'gzip,deflate'}
        if self.is_apikey(url):
            headers.update({'Authorization': 'Bearer %s' % self.get_token(),
                            'Accept': 'application/vnd.thetvdb.v%s' % __api_version__})

        if None is not language and language in self.config['valid_languages']:
            headers.update({'Accept-Language': language})

        resp = None
        is_series_info = self._match_url_pattern('url_series_info', url)
        if is_series_info:
            self.show_not_found = False
        self.not_found = False
        try:
            resp = get_url(url.strip(), params=params, session=session, headers=headers, parse_json=parse_json,
                           raise_status_code=True, raise_exceptions=True, raise_skip_exception=True, **kwargs)
        except ConnectionSkipException as e:
            raise e
        except requests.exceptions.HTTPError as e:
            if 401 == e.response.status_code:
                if self.is_apikey(url):
                    # token expired, get new token, raise error to retry
                    global THETVDB_V2_API_TOKEN
                    THETVDB_V2_API_TOKEN = self.get_new_token()
                    raise TvdbTokenexpired
            elif 404 == e.response.status_code:
                if is_series_info:
                    self.show_not_found = True
                elif self._match_url_pattern('url_series_episodes_info', url):
                    resp = {'data': []}
                self.not_found = True
            elif 404 != e.response.status_code:
                raise TvdbError
        except (BaseException, Exception):
            raise TvdbError

        if is_series_info and isinstance(resp, dict) and isinstance(resp.get('data'), dict) and \
                isinstance(resp['data'].get('seriesName'), string_types) and \
                re.search(r'^[*]\s*[*]\s*[*]', resp['data'].get('seriesName', ''), flags=re.I):
            self.show_not_found = True
            self.not_found = True

        map_show = {'airstime': 'airs_time', 'airsdayofweek': 'airs_dayofweek', 'imdbid': 'imdb_id',
                    'writers': 'writer', 'siterating': 'rating'}

        def map_show_keys(data):
            keep_data = {}
            del_keys = []
            new_data = {}
            for k, v in iteritems(data):
                k_org = k
                k = k.lower()
                if None is not v:
                    if k in ['banner', 'fanart', 'poster'] and v:
                        v = self.config['url_artworks'] % v
                    elif 'genre' == k:
                        keep_data['genre_list'] = v
                        v = '|%s|' % '|'.join([clean_data(c) for c in v if isinstance(c, string_types)])
                    elif 'gueststars' == k:
                        keep_data['gueststars_list'] = v
                        v = '|%s|' % '|'.join([clean_data(c) for c in v if isinstance(c, string_types)])
                    elif 'writers' == k:
                        keep_data[k] = v
                        v = '|%s|' % '|'.join([clean_data(c) for c in v if isinstance(c, string_types)])
                    elif 'rating' == k:
                        new_data['contentrating'] = v
                    elif 'firstaired' == k:
                        if v:
                            try:
                                v = parse(v, fuzzy=True).strftime('%Y-%m-%d')
                            except (BaseException, Exception):
                                v = None
                        else:
                            v = None
                    elif 'imdbid' == k:
                        if v:
                            if re.search(r'^(tt)?\d{1,9}$', v, flags=re.I):
                                v = clean_data(v)
                            else:
                                v = ''
                    else:
                        v = clean_data(v)

                if not v and 'seriesname' == k:
                    if isinstance(data.get('aliases'), list) and 0 < len(data.get('aliases')):
                        v = data['aliases'].pop(0)
                    # this is a invalid show, it has no Name
                    if not v:
                        return None

                if k in map_show:
                    k = map_show[k]
                if k_org is not k:
                    del_keys.append(k_org)
                    new_data[k] = v
                else:
                    data[k] = v
            for d in del_keys:
                del (data[d])
            if isinstance(data, dict):
                data.update(new_data)
                data.update(keep_data)
            return data

        if resp and isinstance(resp, dict):
            if isinstance(resp.get('data'), dict):
                resp['data'] = map_show_keys(resp['data'])
            elif isinstance(resp.get('data'), list):
                data_list = []
                for idx, row in enumerate(resp['data']):
                    if isinstance(row, dict):
                        cr = map_show_keys(row)
                        if None is not cr:
                            data_list.append(cr)
                resp['data'] = data_list
            return resp
        return dict([(u'data', (None, resp)[isinstance(resp, string_types)])])

    def _getetsrc(self, url, params=None, language=None, parse_json=False):
        """Loads a URL using caching
        """
        try:
            src = self._load_url(url, params=params, language=language, parse_json=parse_json)
            if isinstance(src, dict):
                if None is not src['data']:
                    data = src['data']
                else:
                    data = {}
                # data = src['data'] or {}
                if isinstance(data, list):
                    if 0 < len(data):
                        data = data[0]
                    # data = data[0] or {}
                if None is data or (isinstance(data, dict) and 1 > len(data.keys())):
                    raise ValueError
                return src
        except (KeyError, IndexError, Exception):
            pass

    @staticmethod
    def clean_overview(text):
        """replace newlines with period and space, remove multiple spaces"""
        return ' '.join(['%s.' % re.sub(r'[\s][\s]+', r' ', x).strip().rstrip('.') for x in text.split('\r\n')])

    def get_show_info(self, sid, language=None):
        # type: (int, Optional[str]) -> Optional[dict]
        results = self.search_tvs(sid, language=language)
        for cur_result in (isinstance(results, dict) and results.get('results') or []):
            result = filter_list(lambda r: 'series' == r['type'] and sid == r['id'],
                                 cur_result.get('nbHits') and cur_result.get('hits') or [])
            if 1 == len(result):
                result[0]['overview'] = self.clean_overview(
                    result[0]['overviews'][self.config['langabbv_23'].get(language) or 'eng'])
                # remap
                for from_key, to_key in iteritems({
                    'name': 'seriesname', 'first_air_date': 'firstaired'
                }):
                    result[0][to_key] = result[0][from_key]
                    del result[0][from_key]  # delete also prevents false +ve with the following new key notifier

                # notify of new keys
                if ENV.get('SG_DEV_MODE'):
                    new_keys = set(list_keys(result[0])).difference({
                        '_highlightResult', 'aliases', 'banner',
                        'fanart', 'firstaired', 'follower_count',
                        'id', 'image', 'is_tvdb_searchable', 'is_tvt_searchable',
                        'seriesname', 'network',
                        'objectID', 'overviews', 'poster', 'release_year',
                        'slug', 'status',
                        'translations', 'type',
                        'url', 'uuid'
                    })
                    if new_keys:
                        log.warning('DEV_MODE: New get_show_info tvdb attrs for %s %r' % (sid, new_keys))

                return result[0]

        # fallback : e.g. https://thetvdb.com/?tab=series&id=349309&lid=7
        response = self._load_url(self.config['base_url'], params={
            'tab': 'series', 'id': sid, 'lid': self.config['langabbv_to_id'].get(language, 7)})
        series = {}

        def get_value(tag, contains):
            try:
                rc_contains = re.compile(r'(?i)%s' % contains)
                parent = copy.copy(tag.find(string=rc_contains, recursive=True).find_parent(class_=re.compile('item')))
                return ', '.join(re.sub(r'(?i)(\s)([\s]+)', r'\1', i.get_text(strip=True))
                                 for i in parent.find_all('span'))
            except(BaseException, Exception):
                pass

        with BS4Parser(response.get('data', '')) as soup:
            basic_info = soup.find(id='series_basic_info')
            series_id = try_int(get_value(basic_info, r'series\sid'), None)
            if None is not series_id:
                series['id'] = series_id
                series['firstaired'] = None  # fill from ep listings page
                series['genrelist'] = get_value(basic_info, 'genres').split(', ')  # extra field
                series['genre'] = '|%s|' % '|'.join(series['genrelist'])
                series['language'] = language
                series['seriesname'] = soup.find(id='series_title').get_text(strip=True)
                series['networklist'] = get_value(basic_info, 'network').split(', ')  # extra field
                series['network'] = '|%s|' % '|'.join(series['networklist'])  # e.g. '|network|network n|network 10|'
                series['status'] = get_value(basic_info, 'status')
                series['type'] = 'series'  # extra field

                airs_at = get_value(basic_info, 'airs')
                airs = airs_at and airs_at.split(', ') or []
                if 0 < len(airs):
                    series['airs_time'] = 'at ' in airs[-1] \
                                          and re.sub(r'(?i)\s+([ap]m)', r'\1', airs[-1]).split()[-1] or ''
                    series['airs_dayofweek'] = ', '.join(airs[0:-1])
                else:
                    series['airs_time'] = airs_at
                    series['airs_dayofweek'] = ''

                # alias list
                series['aliases'] = []
                try:
                    lang_tag = soup.find(id='translations').select('.change_translation_text[data-language="%s"]' % (
                            self.config['langabbv_23'].get(language) or 'eng'))[0]
                    series['aliases'] = [t.get_text(strip=True) for t in lang_tag
                                         .find(string=re.compile('(?i)alias'), recursive=True).find_parent()
                                         .find_next_sibling('ul').find_all('li')]
                except(BaseException, Exception):
                    pass

                # images
                series['image'] = series['poster'] = (soup.find(rel=re.compile('artwork_posters')) or {}).get('href')
                series['banner'] = (soup.find(rel=re.compile('artwork_banners')) or {}).get('href')
                series['fanart'] = (soup.find(rel=re.compile('artwork_backgrounds')) or {}).get('href')

                series['imdb_id'] = re.sub(r'.*(tt\d+)', r'\1',
                                           (soup.find(href=re.compile(r'imdb\.com')) or {}).get('href', ''))

                # {lang: overview}
                series.setdefault('overviews', {})
                for cur_tag in soup.find_all(class_='change_translation_text'):
                    try:
                        lang = cur_tag.attrs.get('data-language')
                        if None is not lang:
                            text = cur_tag.p.get_text(strip=True)
                            if text:
                                text = self.clean_overview(text)
                                series['overviews'].setdefault(lang, text)  # extra field
                                if lang == self.config['langabbv_23'].get(language):
                                    series['overview'] = text
                    except(BaseException, Exception):
                        pass

                runtime = get_value(basic_info, 'runtime')
                runtime_often = None
                if ', ' in runtime:
                    try:
                        # sort runtimes by most number of episodes (e.g. '25 minutes (700 episodes)')
                        runtime_often = sorted([re.findall(r'([^(]+)\((\d+).*', i)[0] for i in runtime.split(', ')],
                                               key=lambda x: try_int(x[1]), reverse=True)
                        runtime_often = next(iter(runtime_often))[0].strip()  # first item is most frequent runtime
                    except(BaseException, Exception):
                        runtime_often = None
                series['runtime'] = runtime_often and re.sub('^([0-9]+).*', r'\1', runtime_often) or runtime

                series['season'] = None
                try:
                    last_season = sorted([x.get('href')
                                          for x in soup.find_all(href=re.compile(r'/seasons/official/(\d+)'))])[-1]
                    series['season'] = re.findall(r'(\d+)$', last_season)[0]
                except(BaseException, Exception):
                    pass

                series['slug'] = series['url'] = ''
                try:
                    rc_slug = re.compile('(?i)/series/(?P<slug>[^/]+)/(?:episode|season)')
                    series['slug'] = rc_slug.search(soup.find(href=rc_slug).get('href')).group('slug')
                    series['url'] = '%sseries/%s' % (self.config['base_url'], series['slug'])  # extra field
                except(BaseException, Exception):
                    pass

                # {lang: show title in lang}  # extra field
                series['translations'] = {t.attrs.get('data-language'): t.attrs.get('data-title')
                                          for t in soup.find_all(class_='change_translation_text')
                                          if all(t.attrs.get(a) for a in ('data-title', 'data-language'))}

        return series

    def search_tvs(self, terms, language=None):
        # type: (Union[int, str], Optional[str]) -> Optional[dict]
        try:
            src = self._load_url(
                'https://tvshow''time-%s.algo''lia.net/1/'
                'indexes/*/queries' % random.choice([1, 2, 3, 'dsn']),
                params={'x-algo''lia-agent': 'Alg''olia for vani''lla JavaScript (lite) 3.3''2.0;'
                                             'instant''search.js (3.5''.3);JS Helper (2.2''8.0)',
                        'x-algo''lia''-app''lication-id': 'tvshow''time',
                        'x-algo''lia''-ap''i-key': '3d''978dd96c457390f21cec6131ce5d''9c'[::-1]},
                post_json={'requests': [
                    {'indexName': 'TVDB',
                     'params': '&'.join(
                         ['query=%s' % terms, 'maxValuesPerFacet=10', 'page=0',
                          'facetFilters=[["type:series", "type:person"]]',
                          'tagFilters=', 'analytics=false', 'advancedSyntax=true',
                          'highlightPreTag=__ais-highlight__', 'highlightPostTag=__/ais-highlight__'
                          ])
                     }]},
                language=language, parse_json=True)
            return src
        except (KeyError, IndexError, Exception):
            pass

    def search(self, series):
        # type: (AnyStr) -> List
        """This searches TheTVDB.com for the series name
        and returns the result list
        """
        if PY2:
            series = series.encode('utf-8')
        self.config['params_search_series']['name'] = series
        log.debug('Searching for show %s' % series)

        try:
            series_found = self._getetsrc(self.config['url_search_series'], params=self.config['params_search_series'],
                                          language=self.config['language'])
            if series_found:
                return list_values(series_found)[0]
        except (BaseException, Exception):
            pass

        return []

    def get_series(self, series):
        """This searches TheTVDB.com for the series name,
        If a custom_ui UI is configured, it uses this to select the correct
        series. If not, and interactive == True, ConsoleUI is used, if not
        BaseUI is used to select the first result.
        """
        all_series = self.search(series)
        if not isinstance(all_series, list):
            all_series = [all_series]

        if 0 == len(all_series):
            log.debug('Series result returned zero')
            raise TvdbShownotfound('Show-name search returned zero results (cannot find show on TVDB)')

        if None is not self.config['custom_ui']:
            log.debug('Using custom UI %s' % self.config['custom_ui'].__name__)
            custom_ui = self.config['custom_ui']
            ui = custom_ui(config=self.config)
        else:
            if not self.config['interactive']:
                log.debug('Auto-selecting first search result using BaseUI')
                ui = BaseUI(config=self.config)
            else:
                log.debug('Interactively selecting show using ConsoleUI')
                ui = ConsoleUI(config=self.config)

        return ui.select_series(all_series)

    def _parse_banners(self, sid, img_list):
        banners = {}

        try:
            for cur_banner in img_list:
                bid = cur_banner['id']
                btype = (cur_banner['keytype'], 'banner')['series' == cur_banner['keytype']]
                btype2 = (cur_banner['resolution'], try_int(cur_banner['subkey'], cur_banner['subkey']))[
                    btype in ('season', 'seasonwide')]
                if None is btype or None is btype2:
                    continue

                for k, v in iteritems(cur_banner):
                    if None is k or None is v:
                        continue

                    k, v = k.lower(), v.lower() if isinstance(v, string_types) else v
                    if 'filename' == k:
                        k = 'bannerpath'
                        v = self.config['url_artworks'] % v
                    elif 'thumbnail' == k:
                        k = 'thumbnailpath'
                        v = self.config['url_artworks'] % v
                    elif 'keytype' == k:
                        k = 'bannertype'
                    banners.setdefault(btype, OrderedDict()).setdefault(btype2, OrderedDict()).setdefault(bid, {})[
                        k] = v

        except (BaseException, Exception):
            pass

        self._set_show_data(sid, '_banners', banners, add=True)

    def _parse_actors(self, sid, actor_list, actor_list_alt):

        a = []
        cast = CastList()
        try:
            alts = {}
            if actor_list_alt:
                with BS4Parser(actor_list_alt) as soup:
                    rc_role = re.compile(r'/series/(?P<show_slug>[^/]+)/people/(?P<role_id>\d+)/?$')
                    rc_img = re.compile(r'/(?P<url>person/(?P<person_id>[0-9]+)/(?P<img_id>[^/]+)\..*)')
                    rc_img_v3 = re.compile(r'/(?P<url>actors/(?P<img_id>[^/]+)\..*)')
                    max_people = 5
                    rc_clean = re.compile(r'[^a-z0-9]')
                    for cur_enum, cur_role in enumerate(soup.find_all('a', href=rc_role) or []):
                        try:
                            image = person_id = None
                            for cur_rc in (rc_img, rc_img_v3):
                                img_tag = cur_role.find('img', src=cur_rc)
                                if img_tag:
                                    img_parsed = cur_rc.search(img_tag.get('src'))
                                    image, person_id = [x in img_parsed.groupdict() and img_parsed.group(x)
                                                        for x in ('url', 'person_id')]
                                    break
                            lines = [x.strip() for x in cur_role.get_text().split('\n') if x.strip()][0:2]
                            name = role = ''
                            if len(lines):
                                name = lines[0]
                                for line in lines[1:]:
                                    if line.lower().startswith('as '):
                                        role = line[3:]
                                        break
                            if not person_id and max_people:
                                max_people -= 1
                                results = self.search_tvs(name)
                                try:
                                    for cur_result in (isinstance(results, dict) and results.get('results') or []):
                                        # sorts 'banners/images/missing/' to last before filter
                                        people = filter_list(
                                            lambda r: 'person' == r['type']
                                                      and rc_clean.sub(name, '') == rc_clean.sub(r['name'], ''),
                                            cur_result.get('nbHits')
                                            and sorted(cur_result.get('hits'),
                                                       key=lambda x: len(x['image']), reverse=True) or [])
                                        if ENV.get('SG_DEV_MODE'):
                                            for person in people:
                                                new_keys = set(list_keys(person)).difference({
                                                    '_highlightResult', 'banner', 'id', 'image',
                                                    'is_tvdb_searchable', 'is_tvt_searchable', 'name',
                                                    'objectID', 'people_birthdate', 'people_died',
                                                    'poster', 'type', 'url'
                                                })
                                                if new_keys:
                                                    log.warning('DEV_MODE: New _parse_actors tvdb attrs for %s %r'
                                                                % (person['id'], new_keys))

                                        person_ok = False
                                        for person in people:
                                            if image:
                                                people_data = self._load_url(person['url'])['data']
                                                person_ok = re.search(re.escape(image), people_data)
                                            if not image or person_ok:
                                                person_id = person['id']
                                                raise ValueError('value okay, id found')
                                except (BaseException, Exception):
                                    pass

                            rid = int(rc_role.search(cur_role.get('href')).group('role_id'))
                            alts.setdefault(rid, {'id': rid, 'person_id': person_id or None, 'name': name, 'role': role,
                                                  'image': image, 'sortorder': cur_enum, 'lastupdated': 0})
                        except(BaseException, Exception):
                            pass
                    if not self.is_apikey():  # for the future when apikey == ''
                        actor_list = sorted([d for _, d in iteritems(alts)], key=lambda x: x.get('sortorder'))

            unique_c_p, c_p_list, new_actor_list = set(), [], []
            for actor in sorted(actor_list, key=lambda x: x.get('lastupdated'), reverse=True):
                c_p_list.append((actor['name'], actor['role']))
                if (actor['name'], actor['role']) not in unique_c_p:
                    unique_c_p.add((actor['name'], actor['role']))
                    new_actor_list.append(actor)
            for n in sorted(new_actor_list, key=lambda x: x['sortorder']):
                role_image = (alts.get(n['id'], {}).get('image'), n.get('image'))[
                    any([n.get('image')]) and 1 == c_p_list.count((n['name'], n['role']))]
                if role_image:
                    role_image = self.config['url_artworks'] % role_image
                character_name = n.get('role', '').strip() or alts.get(n['id'], {}).get('role', '')
                person_name = n.get('name', '').strip() or alts.get(n['id'], {}).get('name', '')
                try:
                    person_id = try_int(re.search(r'^person/(\d+)/', n.get('image', '')).group(1), None)
                except (BaseException, Exception):
                    person_id = None
                person_id = person_id or alts.get(n['id'], {}).get('person_id')
                character_id = n.get('id', None) or alts.get(n['id'], {}).get('rid')
                a.append({'character': {'id': character_id,
                                        'name': character_name,
                                        'url': None,  # not supported by tvdb
                                        'image': role_image,
                                        },
                          'person': {'id': person_id,
                                     'name': person_name,
                                     'url': person_id and (self.config['url_people'] % person_id) or None,
                                     'image': None,  # not supported by tvdb
                                     'birthday': None,  # not supported by tvdb
                                     'deathday': None,  # not supported by tvdb
                                     'gender': None,  # not supported by tvdb
                                     'country': None,  # not supported by tvdb
                                     },
                          })
                cast[RoleTypes.ActorMain].append(
                    Character(p_id=character_id, name=character_name,
                              person=[Person(p_id=person_id, name=person_name)], image=role_image))
        except (BaseException, Exception):
            pass
        self._set_show_data(sid, 'actors', a)
        self._set_show_data(sid, 'cast', cast)
        self.shows[sid].actors_loaded = True

    def get_episode_data(self, epid):
        # Parse episode information
        data = None
        log.debug('Getting all episode data for %s' % epid)
        url = self.config['url_episodes_info'] % epid
        episode_data = self._getetsrc(url, language=self.config['language'])

        if episode_data and 'data' in episode_data:
            data = episode_data['data']
            if isinstance(data, dict):
                for k, v in iteritems(data):
                    k = k.lower()

                    if None is not v:
                        if 'filename' == k and v:
                            v = self.config['url_artworks'] % v
                        else:
                            v = clean_data(v)
                    data[k] = v

        return data

    def _parse_images(self, sid, language, show_data, image_type, enabled_type, type_bool):
        mapped_img_types = {'banner': 'series'}
        excluded_main_data = enabled_type in ['seasons_enabled', 'seasonwides_enabled']
        loaded_name = '%s_loaded' % image_type
        if (type_bool or self.config[enabled_type]) and not getattr(self.shows.get(sid), loaded_name, False):
            image_data = self._getetsrc(self.config['url_series_images'] %
                                        (sid, mapped_img_types.get(image_type, image_type)), language=language)
            if image_data and 0 < len(image_data.get('data', '') or ''):
                image_data['data'] = sorted(image_data['data'], reverse=True,
                                            key=lambda x: (x['ratingsinfo']['average'], x['ratingsinfo']['count']))
                if not excluded_main_data:
                    url_image = self.config['url_artworks'] % image_data['data'][0]['filename']
                    url_thumb = self.config['url_artworks'] % image_data['data'][0]['thumbnail']
                    self._set_show_data(sid, image_type, url_image)
                    self._set_show_data(sid, u'%s_thumb' % image_type, url_thumb)
                    excluded_main_data = True  # artwork found so prevent fallback
                self._parse_banners(sid, image_data['data'])
                self.shows[sid].__dict__[loaded_name] = True

        # fallback image thumbnail for none excluded_main_data if artwork is not found
        if not excluded_main_data and show_data['data'].get(image_type):
            self._set_show_data(sid, u'%s_thumb' % image_type,
                                re.sub(r'\.jpg$', '_t.jpg', show_data['data'][image_type], flags=re.I))

    def _get_show_data(self,
                       sid,  # type: integer_types
                       language,  # type: AnyStr
                       get_ep_info=False,  # type: bool
                       banners=False,  # type: bool
                       posters=False,  # type: bool
                       seasons=False,  # type: bool
                       seasonwides=False,  # type: bool
                       fanart=False,  # type: bool
                       actors=False,  # type: bool
                       direct_data=False,  # type: bool
                       **kwargs  # type: Optional[Any]
                       ):  # type: (...) -> Optional[bool, dict]
        """Takes a series ID, gets the epInfo URL and parses the TVDB
        XML file into the shows dict in layout:
        shows[series_id][season_number][episode_number]
        """

        # Parse show information
        url = self.config['url_series_info'] % sid
        if direct_data or sid not in self.shows or None is self.shows[sid].id:
            log.debug('Getting all series data for %s' % sid)
            show_data = self._getetsrc(url, language=language)
            if not show_data or not show_data.get('data'):
                show_data = {'data': self.get_show_info(sid, language=language)}
            if direct_data:
                return show_data

            # check and make sure we have data to process and that it contains a series name
            if not (show_data and 'seriesname' in show_data.get('data', {}) or {}):
                return False

            for k, v in iteritems(show_data['data']):
                self._set_show_data(sid, k, v)
            self._set_show_data(sid, 'ids',
                                TVInfoIDs(
                                    tvdb=show_data['data'].get('id'),
                                    imdb=show_data['data'].get('imdb_id')
                                    and try_int(show_data['data'].get('imdb_id', '').replace('tt', ''), None)))
        else:
            show_data = {'data': {}}

        for img_type, en_type, p_type in [(u'poster', 'posters_enabled', posters),
                                          (u'banner', 'banners_enabled', banners),
                                          (u'fanart', 'fanart_enabled', fanart),
                                          (u'season', 'seasons_enabled', seasons),
                                          (u'seasonwide', 'seasonwides_enabled', seasonwides)]:
            self._parse_images(sid, language, show_data, img_type, en_type, p_type)

        if (actors or self.config['actors_enabled']) and not getattr(self.shows.get(sid), 'actors_loaded', False):
            actor_data = self._getetsrc(self.config['url_actors_info'] % sid, language=language)
            actor_data_alt = self._getetsrc(self.config['url_series_people'] % sid, language=language)
            if actor_data and 0 < len(actor_data.get('data', '') or '') or actor_data_alt and actor_data_alt['data']:
                self._parse_actors(sid, actor_data['data'], actor_data_alt and actor_data_alt['data'])

        if get_ep_info and not getattr(self.shows.get(sid), 'ep_loaded', False):
            # Parse episode data
            log.debug('Getting all episodes of %s' % sid)

            page = 1
            episodes = []
            while page <= 400:
                episode_data = {}
                if self.is_apikey():
                    episode_data = self._getetsrc(
                        self.config['url_series_episodes_info'] % (sid, page), language=language)

                if not episode_data:
                    response = {'data': None}
                    items_found = False
                    # fallback to page 'all' if dvd is enabled and response has no items
                    for page_type in ('url_series_dvd', 'url_series_all'):
                        if 'dvd' not in page_type or self.config['dvdorder']:
                            response = self._load_url(self.config[page_type] % show_data.get('data').get('slug'))
                            with BS4Parser(response.get('data') or '') as soup:
                                items_found = bool(soup.find_all(class_='list-group-item'))
                                if items_found:
                                    break
                    if not items_found:
                        break

                    episode_data = {'data': []}
                    with BS4Parser(response.get('data')) as soup:
                        items = soup.find_all(class_='list-group-item')
                        rc_sxe = re.compile(r'(?i)s(?:pecial\s*)?(\d+)\s*[xe]\s*(\d+)')  # Special nxn or SnnEnn
                        rc_episode = re.compile(r'(?i)/series/%s/episodes?/(?P<ep_id>\d+)' % show_data['data']['slug'])
                        rc_date = re.compile(r'\s\d{4}\s*$')
                        season_type, episode_type = ['%s%s' % (('aired', 'dvd')['dvd' in page_type], x)
                                                     for x in ('season', 'episodenumber')]
                        for cur_item in items:
                            try:
                                heading_tag = cur_item.find(class_='list-group-item-heading')
                                sxe = heading_tag.find(class_='episode-label').get_text(strip=True)
                                ep_season, ep_episode = [try_int(x) for x in rc_sxe.findall(sxe)[0]]
                                link_ep_tag = heading_tag.find(href=rc_episode) or {}
                                link_match = rc_episode.search(link_ep_tag.get('href', ''))
                                ep_id = link_match and try_int(link_match.group('ep_id'), None)
                                ep_name = link_ep_tag.get_text(strip=True)
                                # ep_network = None  # extra field
                                ep_aired = None
                                for cur_tag in cur_item.find('ul').find_all('li'):
                                    text = cur_tag.get_text(strip=True)
                                    if rc_date.search(text):
                                        ep_aired = parse(text).strftime('%Y-%m-%d')
                                    # elif text in show_data['data']['network']:  # unreliable data
                                    #     ep_network = text
                                ep_overview = None
                                item_tag = cur_item.find(class_='list-group-item-text')
                                if item_tag:
                                    ep_overview = self.clean_overview(item_tag.get_text() or '')
                                ep_filename = None
                                link_ep_tag = item_tag.find(href=rc_episode) or None
                                if link_ep_tag:
                                    ep_filename = (link_ep_tag.find('img') or {}).get('src', '')

                                episode_data['data'].append({
                                    'id': ep_id, season_type: ep_season, episode_type: ep_episode,
                                    'episodename': ep_name, 'firstaired': ep_aired, 'overview': ep_overview,
                                    'filename': ep_filename,  # 'network': ep_network
                                })

                                if not show_data['data']['firstaired'] and ep_aired \
                                        and (1, 1) == (ep_season, ep_episode):
                                    show_data['data']['firstaired'] = ep_aired

                                episode_data['fallback'] = True
                            except (BaseException, Exception):
                                continue

                if None is episode_data:
                    raise TvdbError('Exception retrieving episodes for show')
                if isinstance(episode_data, dict) and not episode_data.get('data', []):
                    if 1 != page:
                        self.not_found = False
                    break
                if not getattr(self, 'not_found', False) and None is not episode_data.get('data'):
                    episodes.extend(episode_data['data'])
                next_link = episode_data.get('links', {}).get('next', None)
                # check if page is a valid following page
                if not isinstance(next_link, integer_types) or next_link <= page:
                    next_link = None
                if not next_link and isinstance(episode_data, dict) \
                        and isinstance(episode_data.get('data', []), list) and \
                        (100 > len(episode_data.get('data', [])) or episode_data.get('fallback')):
                    break
                if next_link:
                    page = next_link
                else:
                    page += 1

            ep_map_keys = {'absolutenumber': u'absolute_number', 'airedepisodenumber': u'episodenumber',
                           'airedseason': u'seasonnumber', 'airedseasonid': u'seasonid',
                           'dvdepisodenumber': u'dvd_episodenumber', 'dvdseason': u'dvd_season'}

            for cur_ep in episodes:
                if self.config['dvdorder']:
                    log.debug('Using DVD ordering.')
                    use_dvd = None is not cur_ep.get('dvdseason') and None is not cur_ep.get('dvdepisodenumber')
                else:
                    use_dvd = False

                if use_dvd:
                    elem_seasnum, elem_epno = cur_ep.get('dvdseason'), cur_ep.get('dvdepisodenumber')
                else:
                    elem_seasnum, elem_epno = cur_ep.get('airedseason'), cur_ep.get('airedepisodenumber')

                if None is elem_seasnum or None is elem_epno:
                    log.warning('An episode has incomplete season/episode number (season: %r, episode: %r)' % (
                        elem_seasnum, elem_epno))
                    continue  # Skip to next episode

                # float() is because https://github.com/dbr/tvnamer/issues/95 - should probably be fixed in TVDB data
                seas_no = int(float(elem_seasnum))
                ep_no = int(float(elem_epno))

                if not cur_ep.get('network'):
                    cur_ep['network'] = self.shows[sid].network
                for k, v in iteritems(cur_ep):
                    k = k.lower()

                    if None is not v:
                        if 'filename' == k and v:
                            if '://' not in v:
                                v = self.config['url_artworks'] % v
                        else:
                            v = clean_data(v)

                    if k in ep_map_keys:
                        k = ep_map_keys[k]
                    self._set_item(sid, seas_no, ep_no, k, v)

                crew = CrewList()
                cast = CastList()
                try:
                    for director in cur_ep.get('directors', []):
                        crew[RoleTypes.CrewDirector].append(Person(name=director))
                except (BaseException, Exception):
                    pass
                try:
                    for guest in cur_ep.get('gueststars_list', []):
                        cast[RoleTypes.ActorGuest].append(Character(person=[Person(name=guest)]))
                except (BaseException, Exception):
                    pass
                try:
                    for writers in cur_ep.get('writers', []):
                        crew[RoleTypes.CrewWriter].append(Person(name=writers))
                except (BaseException, Exception):
                    pass
                self._set_item(sid, seas_no, ep_no, 'crew', crew)
                self._set_item(sid, seas_no, ep_no, 'cast', cast)

            self.shows[sid].ep_loaded = True

        return True

    def _name_to_sid(self, name):
        """Takes show name, returns the correct series ID (if the show has
        already been grabbed), or grabs all episodes and returns
        the correct SID.
        """
        if name in self.corrections:
            log.debug('Correcting %s to %s' % (name, self.corrections[name]))
            return self.corrections[name]
        else:
            log.debug('Getting show %s' % name)
            selected_series = self.get_series(name)
            if isinstance(selected_series, dict):
                selected_series = [selected_series]
            sids = [int(x['id']) for x in selected_series if
                    self._get_show_data(int(x['id']), self.config['language'])]
            self.corrections.update(dict([(x['seriesname'], int(x['id'])) for x in selected_series]))
            return sids


def main():
    """Simple example of using tvdb_api - it just
    grabs an episode name interactively.
    """
    import logging

    logging.basicConfig(level=logging.DEBUG)

    tvdb_instance = Tvdb(interactive=True, cache=False)
    print(tvdb_instance['Lost']['seriesname'])
    print(tvdb_instance['Lost'][1][4]['episodename'])


if '__main__' == __name__:
    main()
