# encoding:utf-8
# author:Prinz23
# project:tvdb_api_v4

__author__ = 'Prinz23'
__version__ = '1.0'
__api_version__ = '1.0.0'

import base64
import datetime
import logging
import os
import re

from bs4_parser import BS4Parser
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from .tvdb_exceptions import TvdbError, TvdbTokenFailure
from exceptions_helper import ex
from lib.dateutil.parser import parser
# noinspection PyProtectedMember
from lib.exceptions_helper import ConnectionSkipException
from lib.tvinfo_base import (
    CastList, CrewList, PersonGenders, RoleTypes,
    TVInfoBase, TVInfoCharacter, TVInfoEpisode, TVInfoIDs, TVInfoImage, TVInfoImageSize, TVInfoImageType, TVInfoNetwork,
    TVInfoPerson, TVInfoSeason, TVInfoSeasonTypes, TVInfoShow, TVInfoSocialIDs,
    TVINFO_FACEBOOK, TVINFO_FANSITE, TVINFO_IMDB, TVINFO_INSTAGRAM, TVINFO_LINKEDIN, TVINFO_OFFICIALSITE, TVINFO_REDDIT,
    TVINFO_MID_SEASON_FINALE, TVINFO_SEASON_FINALE, TVINFO_SERIES_FINALE, TVINFO_TIKTOK, TVINFO_TMDB, TVINFO_TVDB,
    TVINFO_TVDB_SLUG, TVINFO_TVMAZE, TVINFO_TWITTER, TVINFO_WIKIDATA, TVINFO_WIKIPEDIA, TVINFO_YOUTUBE)
from sg_helpers import clean_data, clean_str, enforce_type, get_url, try_date, try_int

from six import integer_types, iteritems, PY3, string_types
# noinspection PyUnreachableCode
if False:
    from typing import Any, AnyStr, Dict, List, Optional, Tuple, Union


ENV = os.environ

log = logging.getLogger('tvdb_v4.api')
log.addHandler(logging.NullHandler())

TVDB_API_CONFIG = {}

NoneType = type(None)


# always use https in cases of redirects
# noinspection PyUnusedLocal,HttpUrlsUsage
def _record_hook(r, *args, **kwargs):
    r.hook_called = True
    if r.status_code in (301, 302, 303, 307, 308) and \
            isinstance(r.headers.get('Location'), string_types) and r.headers.get('Location').startswith('http://'):
        r.headers['Location'] = r.headers['Location'].replace('http://', 'https://')
    return r


# noinspection PyUnresolvedReferences
class RequestsAuthBase(requests.auth.AuthBase):
    # inherit the Requests dynamic packaging here in order to isolate a pyc non-inspection directive
    pass


class TvdbAuth(RequestsAuthBase):
    _token = None

    def __init__(self):
        pass

    def reset_token(self):
        self._token = None

    @staticmethod
    def apikey():
        string = TVDB_API_CONFIG['api_params']['apikey_v4']
        key = TVDB_API_CONFIG['api_params']['apikey']
        string = base64.urlsafe_b64decode(string + b'===')
        string = string.decode('latin') if PY3 else string
        encoded_chars = []
        for i in range(len(string)):
            key_c = key[i % len(key)]
            encoded_c = chr((ord(string[i]) - ord(key_c) + 256) % 256)
            encoded_chars.append(encoded_c)
        encoded_string = ''.join(encoded_chars)
        return encoded_string

    def get_token(self):
        url = f'{TvdbAPIv4.base_url}{"login"}'
        params = {'apikey': self.apikey()}
        resp = get_url(url, post_json=params, parse_json=True, raise_skip_exception=True)
        if resp and isinstance(resp, dict):
            if 'status' in resp:
                if 'failure' == resp['status']:
                    raise TvdbTokenFailure(f'Failed to Authenticate. {resp.get("message", "")}')
                if 'success' == resp['status'] and 'data' in resp and isinstance(resp['data'], dict) \
                        and 'token' in resp['data']:
                    self._token = resp['data']['token']
                    return True
        else:
            raise TvdbTokenFailure('Failed to get Tvdb Token')

    @property
    def token(self):
        if not self._token:
            try:
                self.get_token()
            except TvdbTokenFailure as e:
                log.error(f'Tvdb Taken Failure: {e}')
        return self._token

    def handle_401(self, r, **kwargs):
        if 401 == r.status_code and not any(401 == _or.status_code for _or in r.history):
            self.reset_token()
            self.get_token()
            if self._token:
                prep = r.request.copy()
                prep.headers['Authorization'] = f'Bearer {self._token}'
                _r = r.connection.send(prep, **kwargs)
                _r.history.append(r)
                _r.request = prep
                return _r

        return r

    def __call__(self, r):
        r.headers["Authorization"] = f'Bearer {self.token}'
        r.register_hook('response', self.handle_401)
        return r


DEFAULT_TIMEOUT = 30  # seconds


class TimeoutHTTPAdapter(HTTPAdapter):
    def __init__(self, *args, **kwargs):
        self.timeout = DEFAULT_TIMEOUT
        if "timeout" in kwargs:
            self.timeout = kwargs["timeout"]
            del kwargs["timeout"]
        super(TimeoutHTTPAdapter, self).__init__(*args, **kwargs)

    def send(self, request, **kwargs):
        timeout = kwargs.get("timeout")
        if timeout is None:
            kwargs["timeout"] = self.timeout
        return super(TimeoutHTTPAdapter, self).send(request, **kwargs)


s = requests.Session()
retries = Retry(total=3,
                backoff_factor=1,
                status_forcelist=[429, 500, 502, 503, 504],
                allowed_methods=['HEAD', 'GET', 'PUT', 'DELETE', 'OPTIONS', 'TRACE', 'POST'])
# noinspection HttpUrlsUsage
s.mount('http://', HTTPAdapter(TimeoutHTTPAdapter(max_retries=retries)))
s.mount('https://', HTTPAdapter(TimeoutHTTPAdapter(max_retries=retries)))
base_request_para = dict(session=s, hooks={'response': _record_hook}, raise_skip_exception=True, auth=TvdbAuth())


# Query TVdb endpoints
def tvdb_endpoint_fetch(*args, **kwargs):
    kwargs.update(base_request_para)
    return get_url(*args, **kwargs)


img_type_map = {
    1: TVInfoImageType.banner,  # series
    2: TVInfoImageType.poster,  # series
    3: TVInfoImageType.fanart,  # series
    6: TVInfoImageType.season_banner,  # season
    7: TVInfoImageType.season_poster,  # season
    8: TVInfoImageType.season_fanart,  # season
    13: TVInfoImageType.person_poster,  # person
}

people_types = {
    1: RoleTypes.CrewDirector,  # 'Director',
    2: RoleTypes.CrewWriter,  # 'Writer'
    3: RoleTypes.ActorMain,  # 'Actor'
    4: RoleTypes.ActorGuest,  # 'Guest Star',
    5: RoleTypes.CrewOther,  # 'Crew',
    6: RoleTypes.CrewCreator,  # 'Creator',
    7: RoleTypes.CrewProducer,  # 'Producer',
    8: RoleTypes.CrewShowrunner,  # 'Showrunner',
    9: RoleTypes.MusicalGuest,  # 'Musical Guest',
    10: RoleTypes.Host,  # 'Host',
    11: RoleTypes.CrewExecutiveProducer,  # 'Executive Producer',
}

source_types = {
    2: TVINFO_IMDB,  # title
    # 3: TVINFO_ZAP2IT,
    4: TVINFO_OFFICIALSITE,
    5: TVINFO_FACEBOOK,
    6: TVINFO_TWITTER,
    7: TVINFO_REDDIT,
    8: TVINFO_FANSITE,
    9: TVINFO_INSTAGRAM,
    10: TVINFO_TMDB,  # movie
    11: TVINFO_YOUTUBE,
    12: TVINFO_TMDB,  # tv
    # 13: TVINFO_EIDR,  # content
    # 14: TVINFO_EIDR,  # party
    15: TVINFO_TMDB,  # person
    16: TVINFO_IMDB,  # person
    17: TVINFO_IMDB,  # company
    18: TVINFO_WIKIDATA,
    19: TVINFO_TVMAZE,  # title
    20: TVINFO_LINKEDIN,
    21: TVINFO_TVMAZE,  # person
    22: TVINFO_TVMAZE,  # season
    23: TVINFO_TVMAZE,  # episode
    24: TVINFO_WIKIPEDIA,
    25: TVINFO_TIKTOK,
    26: TVINFO_LINKEDIN,  # company
    27: TVINFO_TVMAZE,  # company
    28: TVINFO_TMDB,  # collection
    29: TVINFO_TMDB,  # collection
}

people_types_reverse = {_v: _k for _k, _v in iteritems(people_types)}

empty_ep = TVInfoEpisode()
tz_p = parser()
status_ids = {
    1: {'name': 'Continuing', 'recordType': 'series', 'keepUpdated': False},
    2: {'name': 'Ended', 'recordType': 'series', 'keepUpdated': False},
    3: {'name': 'Upcoming', 'recordType': 'series', 'keepUpdated': False}
    }
status_names = {
    'Continuing': {'id': 1, 'recordType': 'series', 'keepUpdated': False},
    'Ended': {'id': 2, 'recordType': 'series', 'keepUpdated': False},
    'Upcoming': {'id': 3, 'recordType': 'series', 'keepUpdated': False}
    }
tvdb_final_types = {
    'series': TVINFO_SERIES_FINALE,
    'season': TVINFO_SEASON_FINALE,
    'midseason': TVINFO_MID_SEASON_FINALE
}


class TvdbAPIv4(TVInfoBase):
    supported_id_searches = [TVINFO_TVDB, TVINFO_TVDB_SLUG, TVINFO_IMDB, TVINFO_TMDB, TVINFO_TVMAZE]
    supported_person_id_searches = [TVINFO_TVDB, TVINFO_IMDB, TVINFO_TMDB, TVINFO_TVMAZE]
    base_url = 'https://api4.thetvdb.com/v4/'
    art_url = 'https://artworks.thetvdb.com/'
    season_types = {1: 'official', 2: 'dvd', 3: 'absolute', 4: 'alternate', 5: 'regional', 6: 'altdvd'}
    season_type_map = {season_types[1]: TVInfoSeasonTypes.official, season_types[2]: TVInfoSeasonTypes.dvd}

    def __init__(self, banners=False, posters=False, seasons=False, seasonwides=False, fanart=False, actors=False,
                 dvdorder=False, *args, **kwargs):
        super(TvdbAPIv4, self).__init__(banners, posters, seasons, seasonwides, fanart, actors, dvdorder, *args,
                                        **kwargs)

    def _fetch_data(self, endpoint, **kwargs):
        # type: (string_types, Any) -> Any
        if is_series_info := endpoint.startswith('/series/'):
            self.show_not_found = False
        try:
            return tvdb_endpoint_fetch(url=f'{self.base_url}{endpoint}', params=kwargs, parse_json=True,
                                       raise_status_code=True, raise_exceptions=True)
        except ConnectionSkipException as e:
            raise e
        except requests.exceptions.HTTPError as e:
            if 401 == e.response.status_code:
                raise TvdbTokenFailure('Failed to get new Token')
            elif 404 == e.response.status_code:
                if is_series_info:
                    self.show_not_found = True
                self.not_found = True
            elif 404 != e.response.status_code:
                raise TvdbError(ex(e))
        except (BaseException, Exception) as e:
            raise TvdbError(ex(e))

    @staticmethod
    def _check_resp(type_chk=list, data=None):
        return isinstance(data, dict) and all(_k in data for _k in ('data', 'status')) \
            and 'success' == data['status'] and isinstance(data['data'], type_chk) and bool(data['data'])

    @staticmethod
    def _next_page(resp, page):
        page += 1
        if f'?page={page}' in ((resp.get('links') or {}).get('next') or ''):
            return page

    def _convert_person(self, p, ids=None, include_guests=False):
        # type: (Dict, Dict, bool) -> List[TVInfoPerson]
        ch, ids = [], ids or {}
        p_types = ([3], [3, 4])[include_guests]
        dedupe = {}
        for cur_c in sorted(filter(
                lambda a: (a['type'] in p_types or 'Actor' == a['peopleType'])
                and a['seriesId'] and ((not a.get('episodeId') and a['name']) or include_guests),
                p.get('characters') or []),
                key=lambda a: (not a['isFeatured'], a['sort'])):
            role_name = clean_data(cur_c['name'] or '')
            role_name_lc = role_name.lower()
            sid = cur_c.get('seriesId')
            if sid and sid == dedupe.get(role_name_lc):
                continue
            if role_name:  # skip dedupe of records that are name ''
                dedupe[role_name_lc] = sid

            ti_show = TVInfoShow()
            ti_show.id = clean_data(cur_c['seriesId'])
            ti_show.ids = TVInfoIDs(ids={TVINFO_TVDB: ti_show.id})
            ti_show.seriesname = clean_data(('series' in cur_c and cur_c['series'] and cur_c['series']['name']))
            ti_show.poster = self._sanitise_image_uri(('series' in cur_c and cur_c['series']
                                                       and cur_c['series']['image']))
            ti_show.firstaired = self._get_first_aired(('series' in cur_c and cur_c['series']))
            ch.append(TVInfoCharacter(
                id=cur_c['id'], ids=TVInfoIDs(ids={TVINFO_TVDB: cur_c['id']}),
                name=role_name,
                image=self._sanitise_image_uri(cur_c.get('image')),
                regular=cur_c['isFeatured'],
                ti_show=ti_show
            ))
        try:
            b_date = clean_data(p.get('birth'))
            birthdate = (b_date and '0000-00-00' != b_date and tz_p.parse(b_date).date()) or None
        except (BaseException, Exception):
            birthdate = None
        try:
            d_date = clean_data(p.get('death'))
            deathdate = (d_date and '0000-00-00' != d_date and tz_p.parse(d_date).date()) or None
        except (BaseException, Exception):
            deathdate = None

        p_tvdb_id = self._get_tvdb_id(p)
        ids.update({TVINFO_TVDB: p_tvdb_id})
        social_ids, official_site = {}, None

        if 'remoteIds' in p and isinstance(p['remoteIds'], list):
            for cur_rid in p['remoteIds']:
                if not (src_value := clean_data(cur_rid['id'])):
                    continue
                src_name = cur_rid['sourceName'].lower()
                src_type = source_types.get(cur_rid['type'])
                if TVINFO_IMDB == src_type or 'imdb' in src_name:
                    try:
                        imdb_id = try_int(f'{src_value}'.replace('nm', ''), None)
                        ids[TVINFO_IMDB] = imdb_id
                    except (BaseException, Exception):
                        pass
                elif TVINFO_TMDB == src_type or 'themoviedb' in src_name:
                    ids[TVINFO_TMDB] = try_int(src_value, None)
                elif TVINFO_TVMAZE == src_type or 'tv maze' in src_name:
                    ids[TVINFO_TVMAZE] = try_int(src_value, None)
                elif TVINFO_OFFICIALSITE == src_type or 'official website' in src_name:
                    official_site = src_value
                elif TVINFO_FACEBOOK == src_type or 'facebook' in src_name:
                    social_ids[TVINFO_FACEBOOK] = src_value
                elif TVINFO_TWITTER == src_type or 'twitter' in src_name:
                    social_ids[TVINFO_TWITTER] = src_value
                elif TVINFO_INSTAGRAM == src_type or 'instagram' in src_name:
                    social_ids[TVINFO_INSTAGRAM] = src_value
                elif TVINFO_REDDIT == src_type or 'reddit' in src_name:
                    social_ids[TVINFO_REDDIT] = src_value
                elif TVINFO_YOUTUBE == src_type or 'youtube' in src_name:
                    social_ids[TVINFO_YOUTUBE] = src_value
                elif TVINFO_WIKIPEDIA == src_type or 'wikipedia' in src_name:
                    social_ids[TVINFO_WIKIPEDIA] = src_value
                elif TVINFO_WIKIDATA == src_type or 'wikidata' in src_name:
                    social_ids[TVINFO_WIKIDATA] = src_value
                elif TVINFO_TIKTOK == src_type or 'tiktok' in src_name:
                    social_ids[TVINFO_TIKTOK] = src_value
                elif TVINFO_LINKEDIN == src_type:
                    social_ids[TVINFO_LINKEDIN] = src_value
                elif TVINFO_FANSITE == src_type:
                    social_ids[TVINFO_FANSITE] = src_value

        bio = clean_data(
            next((_cp.get('biography') for _cp in p.get('biographies') or [] if 'eng' == _cp.get('language')), None)) \
            or None

        return [TVInfoPerson(
            p_id=p_tvdb_id, name=clean_data(p['name'] or ''),
            image=self._sanitise_image_uri(p.get('image') or p.get('image_url')),
            gender=PersonGenders.tvdb_map.get(p.get('gender'), PersonGenders.unknown), birthdate=birthdate,
            deathdate=deathdate, birthplace=clean_data(p.get('birthPlace')),
            akas=set(clean_data((isinstance(_a, dict) and _a['name']) or _a) for _a in p.get('aliases') or []),
            bio=bio, ids=TVInfoIDs(ids=ids), social_ids=TVInfoSocialIDs(ids=social_ids), homepage=official_site,
            characters=ch
        )]

    def get_cached_or_url(self, url, cache_key, try_cache=False, expire=None, **kwargs):
        # type: (AnyStr, AnyStr, Optional[bool], Optional[int], ...) -> Union[Dict, List, NoneType]
        """
        get cached or new data from url

        :param url: url
        :param cache_key: cache key
        :param try_cache: Nonetype to ignore the cache, True to use cache, otherwise False to check cache config
        :param expire: expire time for caching
        :param kwargs: extra parameter for fetching data
        """
        is_none, resp = False, None
        if use_cache := False if None is try_cache else try_cache or bool(self.config.get('cache_search')):
            is_none, resp = self._get_cache_entry(cache_key)
        if not use_cache or (None is resp and not is_none):
            try:
                resp = self._fetch_data(url, **kwargs)
                self._set_cache_entry(cache_key, resp, expire=expire)
            except (BaseException, Exception):
                resp = None
        return resp

    def get_person(self, p_id, get_show_credits=False, get_images=False, try_cache=True, include_guests=False, **kwargs):
        # type: (integer_types, bool, bool, bool, bool, ...) -> Optional[TVInfoPerson]
        """
        get person's data for id or list of matching persons for name

        :param p_id: persons id
        :param get_show_credits: get show credits
        :param get_images: get person images
        :param try_cache: use cached data if available
        :param include_guests: include guest roles
        :return: person object or None
        """
        if bool(p_id) and self._check_resp(dict, resp := self.get_cached_or_url(
                f'/people/{p_id}/extended',
                f'p-v4-{p_id}', try_cache=try_cache)):
            return self._convert_person(resp['data'], include_guests=include_guests)[0]

    def _search_person(self, name=None, ids=None):
        # type: (AnyStr, Dict[integer_types, integer_types]) -> List[TVInfoPerson]
        """
        search for person by name
        :param name: text to search for
        :param ids: dict of ids to search
        :return: list of found person's
        """
        urls, result, ids = [], [], ids or {}
        for cur_tvinfo in self.supported_person_id_searches:
            if cur_tvinfo in ids:
                if TVINFO_TVDB == cur_tvinfo and (resp := self.get_person(ids[cur_tvinfo])):
                    result.append(resp)
                elif cur_tvinfo in (TVINFO_IMDB, TVINFO_TMDB, TVINFO_TVMAZE):
                    if TVINFO_IMDB == cur_tvinfo:
                        url = f'search/remoteid/nm{ids.get(TVINFO_IMDB):07d}'
                    elif cur_tvinfo in (TVINFO_TMDB, TVINFO_TVMAZE):
                        url = f'search/remoteid/{ids.get(cur_tvinfo)}'
                    else:
                        continue

                    if self._check_resp(list, resp := self.get_cached_or_url(
                            url, f'p-v4-id-{cur_tvinfo}-{ids[cur_tvinfo]}', expire=self.search_cache_expire)):
                        for cur_resp in resp['data']:
                            if isinstance(cur_resp, dict) and 'people' in cur_resp:
                                if p_d := None if 1 != len(cur_resp) else self.get_person(cur_resp['people']['id']):
                                    result.append(p_d)
                                else:
                                    result.extend(self._convert_person(cur_resp['people'], ids))
                                break

        if name and self._check_resp(list, resp := self.get_cached_or_url(
                '/search',
                f'p-v4-src-text-{name}', expire=self.search_cache_expire,
                query=name, type='people')):
            for cur_resp in resp['data']:
                result.extend(self._convert_person(cur_resp))

        seen = set()
        result = [seen.add(_r.id) or _r for _r in result if _r.id not in seen]
        return result

    def search_tvs(self, terms, language=None):
        # type: (Union[int, AnyStr], Optional[AnyStr]) -> Optional[dict]
        from random import choice

        sg_lang = next(filter(lambda x: language == x['id'], self.get_languages()), {}).get('sg_lang')
        headers = {'Accept-Encoding': 'gzip,deflate'}
        if None is not sg_lang:  # and sg_lang in self.config['valid_languages']:
            headers.update({'Accept-Language': sg_lang})

        try:
            src = get_url(
                'https://tvshow''time-%s.algo''lia.net/1/'
                'indexes/*/queries' % choice([1, 2, 3, 'dsn']),
                params={'x-algo''lia-agent': 'Alg''olia for vani''lla JavaScript (lite) 3.3''2.0;'
                                             'instant''search.js (3.5''.3);JS Helper (2.2''8.0)',
                        'x-algo''lia''-app''lication-id': 'tvshow''time',
                        'x-algo''lia''-ap''i-key': '3d''978dd96c457390f21cec6131ce5d''9c'[::-1]},
                post_json={'requests': [
                    {'indexName': 'TVDB',
                     'params': '&'.join(
                         [f'query={terms}', 'maxValuesPerFacet=10', 'page=0',
                          'facetFilters=[["type:series", "type:person"]]',
                          'tagFilters=', 'analytics=false', 'advancedSyntax=true',
                          'highlightPreTag=__ais-highlight__', 'highlightPostTag=__/ais-highlight__'
                          ])
                     }]},
                session=requests.session(), headers=headers, parse_json=True, failure_monitor=False)
            return src
        except (KeyError, IndexError, Exception):
            pass

    @staticmethod
    def _get_overview(show_data, language='eng'):
        # type: (Dict, AnyStr) -> AnyStr
        """
        internal helper to get english overview
        :param show_data:
        :param language:
        """
        result = ''
        if isinstance(show_data.get('translations'), dict) and 'overviewTranslations' in show_data['translations']:
            try:
                if trans := next(filter(
                        lambda _s: language == _s['language'], show_data['translations']['overviewTranslations']),
                    next(filter(
                        lambda _s: 'eng' == _s['language'], show_data['translations']['overviewTranslations']), None)):

                    result = trans['overview']
            except (BaseException, Exception):
                pass
        elif isinstance(show_data, dict) and 'overviews' in show_data:
            result = show_data['overviews'].get(language, show_data.get('overview'))

        return clean_str(result)

    def _get_series_name(self, show_data, language=None):
        # type: (Dict, AnyStr) -> Tuple[Optional[AnyStr], List]
        if 'nameTranslations' in show_data.get('translations', {}):
            series_name = clean_data(
                next(filter(lambda l: language and language == l['language'],
                            show_data.get('translations', {}).get('nameTranslations', [])),
                     {'name': show_data['name']})['name'])
        else:
            series_name = clean_data(show_data.get('translations', {}).get(language, show_data['name']))
        series_aliases = self._get_aliases(show_data)
        if not series_name and isinstance(series_aliases, list) and 0 < len(series_aliases):
            series_name = series_aliases.pop(0)
        return series_name, series_aliases

    def _get_show_data(
            self,
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
    ):
        # type: (...) -> Optional[bool, dict]
        """
        internal function that should be overwritten in class to get data for given show id
        :param sid: show id
        :param language: language
        :param get_ep_info: get episodes
        :param banners: load banners
        :param posters: load posters
        :param seasons: load seasons
        :param seasonwides: load seasonwides
        :param fanart: load fanard
        :param actors: load actors
        :param direct_data: return pure data
        """
        if not sid:
            return False

        resp = self._fetch_data(f'/series/{sid}/extended?meta=translations')
        if direct_data:
            return resp

        if self._check_resp(dict, resp):
            show_data = resp['data']
            series_name, series_aliases = self._get_series_name(show_data, language)
            if not series_name:
                return False

            ti_show = self.ti_shows[sid]  # type: TVInfoShow
            ti_show.banner_loaded = ti_show.poster_loaded = ti_show.fanart_loaded = True
            ti_show.id = show_data['id']
            ti_show.seriesname = series_name
            ti_show.slug = clean_data(show_data.get('slug'))
            ti_show.poster = clean_data(show_data.get('image'))
            ti_show.firstaired = clean_data(show_data.get('firstAired'))
            ti_show.rating = show_data.get('score')
            ti_show.contentrating = ('contentRatings' in show_data and show_data['contentRatings']
                                     and next((_r['name'] for _r in show_data['contentRatings'] or []
                                               if 'usa' == _r['country']), None)) or None
            ti_show.aliases = series_aliases
            ti_show.status = clean_data(show_data['status']['name'])
            ti_show.network_country = clean_data(show_data.get('originalCountry'))
            ti_show.lastupdated = clean_data(show_data.get('lastUpdated'))
            existing_networks = []
            if 'latestNetwork' in show_data \
                    and isinstance(show_data['latestNetwork'].get('primaryCompanyType'), integer_types) \
                    and 1 == show_data['latestNetwork']['primaryCompanyType'] \
                    and show_data['latestNetwork']['country']:
                ti_show.networks = [TVInfoNetwork(
                    name=clean_data(show_data['latestNetwork']['name']),
                    country=clean_data(show_data['latestNetwork']['country']),
                    active_date=clean_data(show_data['latestNetwork']['activeDate']),
                    inactive_date=clean_data(show_data['latestNetwork']['inactiveDate']))]
                ti_show.network = clean_data(show_data['latestNetwork']['name'])
                existing_networks.extend([ti_show.network])
                ti_show.network_country = clean_data(show_data['latestNetwork']['country'])
            if 'companies' in show_data and isinstance(show_data['companies'], list):
                # filter networks
                networks = sorted([_n for _n in show_data['companies'] if 1 == _n['companyType']['companyTypeId']
                                   and _n['country']], key=lambda a: a['activeDate'] or '0000-00-00')
                if networks:
                    ti_show.networks.extend([TVInfoNetwork(
                        name=clean_data(_n['name']), country=clean_data(_n['country']),
                        active_date=clean_data(_n['activeDate']), inactive_date=clean_data(_n['inactiveDate']))
                        for _n in networks if clean_data(_n['name']) not in existing_networks])
                    if not ti_show.network:
                        ti_show.network = clean_data(networks[-1]['name'])
                        ti_show.network_country = clean_data(networks[-1]['country'])
            ti_show.language = clean_data(show_data.get('originalLanguage'))
            ti_show.runtime = show_data.get('averageRuntime')
            ti_show.airs_time = clean_data(show_data.get('airsTime'))
            ti_show.airs_dayofweek = ', '.join([_k.capitalize()
                                                for _k, _v in iteritems(show_data.get('airsDays')) if _v])
            ti_show.genre_list = ('genres' in show_data and show_data['genres']
                                  and [clean_data(_g['name']) for _g in show_data['genres']]) or []
            ti_show.genre = '|'.join(ti_show.genre_list)

            ids, social_ids = {}, {}
            if 'remoteIds' in show_data and isinstance(show_data['remoteIds'], list):
                for cur_rid in show_data['remoteIds']:
                    src_name = cur_rid['sourceName'].lower()
                    src_value = clean_data(cur_rid['id'])
                    src_type = source_types.get(cur_rid['type'])
                    if TVINFO_IMDB == src_type or 'imdb' in src_name:
                        try:
                            imdb_id = try_int(src_value.replace('tt', ''), None)
                            ids['imdb'] = imdb_id
                        except (BaseException, Exception):
                            pass
                        ti_show.imdb_id = src_value
                    elif TVINFO_TMDB == src_type or 'themoviedb' in src_name:
                        ids['tmdb'] = try_int(src_value, None)
                    elif TVINFO_TVMAZE == src_type or 'tv maze' in src_name:
                        ids['tvmaze'] = try_int(src_value, None)
                    elif TVINFO_OFFICIALSITE == src_type or 'official website' in src_name:
                        ti_show.official_site = src_value
                    elif TVINFO_FACEBOOK == src_type or 'facebook' in src_name:
                        social_ids['facebook'] = src_value
                    elif TVINFO_TWITTER == src_type or 'twitter' in src_name:
                        social_ids['twitter'] = src_value
                    elif TVINFO_INSTAGRAM == src_type or 'instagram' in src_name:
                        social_ids['instagram'] = src_value
                    elif TVINFO_REDDIT == src_type or 'reddit' in src_name:
                        social_ids['reddit'] = src_value
                    elif TVINFO_YOUTUBE == src_type or 'youtube' in src_name:
                        social_ids['youtube'] = src_value
                    elif TVINFO_WIKIPEDIA == src_type or 'wikipedia' in src_name:
                        social_ids['wikipedia'] = src_value
                    elif TVINFO_WIKIDATA == src_type or 'wikidata' in src_name:
                        social_ids['wikidata'] = src_value
                    elif TVINFO_TIKTOK == src_type or 'tiktok' in src_name:
                        social_ids['tiktok'] = src_value
                    elif TVINFO_LINKEDIN == src_type:
                        social_ids['linkedin'] = src_value
                    elif TVINFO_FANSITE == src_type:
                        social_ids['fansite'] = src_value

            ti_show.ids = TVInfoIDs(tvdb=show_data['id'], **ids)
            if social_ids:
                ti_show.social_ids = TVInfoSocialIDs(**social_ids)

            ti_show.overview = self._get_overview(show_data, language=language)

            if 'artworks' in show_data and isinstance(show_data['artworks'], list):
                poster = banner = fanart_url = False
                for cur_art in sorted(show_data['artworks'], key=lambda a: a['score'], reverse=True):
                    img_type = img_type_map.get(cur_art['type'], TVInfoImageType.other)
                    if False is poster and img_type == TVInfoImageType.poster:
                        ti_show.poster, ti_show.poster_thumb, poster = cur_art['image'], cur_art['thumbnail'], True
                    elif False is banner and img_type == TVInfoImageType.banner:
                        ti_show.banner, ti_show.banner_thumb, banner = cur_art['image'], cur_art['thumbnail'], True
                    elif False is fanart_url and img_type == TVInfoImageType.fanart:
                        ti_show.fanart, fanart_url = cur_art['image'], True
                    ti_show['images'].setdefault(img_type, []).append(TVInfoImage(
                        image_type=img_type,
                        sizes={
                            TVInfoImageSize.original: cur_art['image'],
                            TVInfoImageSize.small: cur_art['thumbnail']
                        },
                        img_id=cur_art['id'],
                        has_text=enforce_type(cur_art.get('includesText'), (bool, NoneType), None),
                        lang=cur_art['language'],
                        rating=cur_art['score'],
                        updated_at=cur_art['updatedAt'] or None
                    ))

            if (actors or self.config['actors_enabled']) \
                    and not getattr(self.ti_shows.get(sid), 'actors_loaded', False):
                cast, crew, ti_show.actors_loaded = CastList(), CrewList(), True
                if isinstance(show_data.get('characters'), list):
                    for cur_char in sorted(show_data.get('characters') or [],
                                           key=lambda c: (not c['isFeatured'], c['sort'])):
                        if (people_type := people_types.get(cur_char['type'])) not in (
                                RoleTypes.ActorMain, RoleTypes.ActorGuest, RoleTypes.ActorSpecialGuest,
                                RoleTypes.ActorRecurring) \
                                and isinstance(cur_char['name'], string_types):
                            if 'presenter' in (low_name := cur_char['name'].lower()):
                                people_type = RoleTypes.Presenter
                            elif 'interviewer' in low_name:
                                people_type = RoleTypes.Interviewer
                            elif 'host' in low_name:
                                people_type = RoleTypes.Host
                        if cur_char['episodeId']:
                            if RoleTypes.ActorMain == people_type:
                                people_type = RoleTypes.ActorGuest
                            elif RoleTypes.Presenter == people_type:
                                people_type = RoleTypes.PresenterGuest
                            elif RoleTypes.Interviewer == people_type:
                                people_type = RoleTypes.InterviewerGuest
                            elif RoleTypes.Host == people_type:
                                people_type = RoleTypes.HostGuest
                        if people_type in (RoleTypes.Presenter, RoleTypes.Interviewer, RoleTypes.Host) \
                                and not cur_char['name']:
                            cur_char['name'] = {RoleTypes.Presenter: 'Presenter', RoleTypes.Interviewer: 'Interviewer',
                                                RoleTypes.Host: 'Host'}.get(people_type) or cur_char['name']
                        if None is people_type:
                            continue
                        if RoleTypes.crew_limit > people_type:
                            cast[people_type].append(TVInfoCharacter(
                                p_id=cur_char['id'], name=clean_data(cur_char['name'] or ''),
                                ids=TVInfoIDs(ids={TVINFO_TVDB: cur_char['id']}),
                                image=self._sanitise_image_uri(cur_char['image']),
                                regular=cur_char['isFeatured'],
                                person=[TVInfoPerson(
                                    p_id=cur_char['peopleId'], name=clean_data(cur_char['personName'] or ''),
                                    image=self._sanitise_image_uri(cur_char.get('personImgURL')),
                                    ids=TVInfoIDs(ids={TVINFO_TVDB: cur_char['peopleId']})
                                )]
                            ))
                        else:
                            crew[people_type].append(TVInfoPerson(
                                p_id=cur_char['peopleId'], name=clean_data(cur_char['personName'] or ''),
                                ids=TVInfoIDs(ids={TVINFO_TVDB: cur_char['peopleId']}),
                                image=self._sanitise_image_uri(cur_char.get('personImgURL'))
                            ))

                if not cast[RoleTypes.ActorMain]:
                    html = get_url(f'https://www.thetvdb.com/series/{ti_show.slug}/people')
                    if html:
                        try:
                            with BS4Parser(html) as soup:
                                rc_role = re.compile(r'/series/(?P<show_slug>[^/]+)/people/(?P<role_id>\d+)/?$')
                                rc_img = re.compile(r'/(?P<url>person/(?P<person_id>\d+)/(?P<img_id>[^/]+)\..*)')
                                rc_img_v3 = re.compile(r'/(?P<url>actors/(?P<img_id>[^/]+)\..*)')
                                max_people = 5
                                rc_clean = re.compile(r'[^a-z\d]')
                                for cur_role in soup.find_all('a', href=rc_role) or []:
                                    try:
                                        image, person_id = 2 * [None]
                                        for cur_rc in (rc_img, rc_img_v3):
                                            img_tag = cur_role.find('img', src=cur_rc)
                                            if img_tag:
                                                img_parsed = cur_rc.search(img_tag.get('src'))
                                                image, person_id = [
                                                    _x in img_parsed.groupdict() and img_parsed.group(_x)
                                                    for _x in ('url', 'person_id')]
                                                break
                                        lines = [_x.strip() for _x in cur_role.get_text().split('\n')
                                                 if _x.strip()][0:2]
                                        name = role = ''
                                        if len(lines):
                                            name = lines[0]
                                            for cur_line in lines[1:]:
                                                if cur_line.lower().startswith('as '):
                                                    role = cur_line[3:]
                                                    break
                                        if not person_id and max_people:
                                            max_people -= 1
                                            results = self.search_tvs(name)
                                            try:
                                                for cur_result in (
                                                        isinstance(results, dict) and results.get('results') or []):
                                                    # sorts 'banners/images/missing/' to last before filter
                                                    people_filter = (
                                                        lambda r: 'person' == r['type'] and
                                                                  rc_clean.sub(name, '') == rc_clean.sub(r['name'], ''),
                                                        cur_result.get('nbHits')
                                                        and sorted(cur_result.get('hits'),
                                                                   key=lambda x: len(x['image']), reverse=True) or [])
                                                    if ENV.get('SG_DEV_MODE'):
                                                        for cur_person in filter(*people_filter):
                                                            new_keys = set(list(cur_person)).difference({
                                                                '_highlightResult', 'banner', 'id', 'image',
                                                                'is_tvdb_searchable', 'is_tvt_searchable', 'name',
                                                                'objectID', 'people_birthdate', 'people_died',
                                                                'poster', 'type', 'url'
                                                            })
                                                            if new_keys:
                                                                log.warning(
                                                                    f'DEV_MODE: New _parse_actors tvdb attrs for'
                                                                    f' {cur_person["id"]} {new_keys!r}')

                                                    person_ok = False
                                                    for cur_person in filter(*people_filter):
                                                        if image:
                                                            people_data = get_url(cur_person['url'])
                                                            person_ok = re.search(re.escape(image), people_data)
                                                        if not image or person_ok:
                                                            person_id = cur_person['id']
                                                            raise ValueError('value okay, id found')
                                            except (BaseException, Exception):
                                                pass

                                        rid = int(rc_role.search(cur_role.get('href')).group('role_id'))
                                        person_id = try_int(person_id, None)
                                        image = image and f'https://artworks.thetvdb.com/banners/{image}' or None
                                        # noinspection PyTypeChecker
                                        cast[RoleTypes.ActorMain].append(TVInfoCharacter(
                                            p_id=rid, name=clean_data(role),
                                            ids={TVINFO_TVDB: rid},
                                            image=image,
                                            person=[TVInfoPerson(
                                                p_id=person_id, name=clean_data(name), ids={TVINFO_TVDB: person_id}
                                            )]
                                        ))
                                    except(BaseException, Exception):
                                        pass
                        except(BaseException, Exception):
                            pass

                ti_show.cast = cast
                ti_show.crew = crew
                ti_show.actors = [dict(
                    character=dict(
                        id=_ch.id, name=_ch.name,
                        url=f'https://www.thetvdb.com/series/{show_data["slug"]}/people/{_ch.id}',
                        image=_ch.image
                    ),
                    person=dict(
                        id=_ch.person and _ch.person[0].id, name=_ch.person and _ch.person[0].name,
                        url=_ch.person and f'https://www.thetvdb.com/people/{_ch.person[0].id}',
                        image=_ch.person and _ch.person[0].image,
                        birthday=try_date(_ch.birthdate), deathday=try_date(_ch.deathdate),
                        gender=None,
                        country=None
                    )
                ) for _ch in cast[RoleTypes.ActorMain]]

            if get_ep_info and not getattr(self.ti_shows.get(sid), 'ep_loaded', False):
                # fetch absolute numbers
                abs_ep_nums = {}
                if any(1 for _s in show_data.get('seasons', []) or [] if 'absolute' == _s.get('type', {}).get('type')):
                    page = 0
                    while 100 >= page:
                        resp = self._fetch_data(f'/series/{sid}/episodes/absolute?page={page:d}')
                        if isinstance(resp, dict) and isinstance((resp.get('data') or {}).get('episodes'), list):
                            abs_ep_nums.update({_e['id']: _e['number'] for _e in resp['data']['episodes']
                                                if None is _e['seasons'] and _e['number']})
                            if None is not (page := self._next_page(resp, page)):
                                continue
                        break

                # fetch alt numbers
                alt_ep_nums, alt_ep_types, default_season_type = \
                    {}, {}, self.season_types.get(show_data.get('defaultSeasonType'))
                for cur_alt_type in {_a.get('type', {}).get('type') for _a in show_data.get('seasons', []) or []
                                     if _a.get('type', {}).get('type') not in ('absolute', default_season_type)}:
                    if any(1 for _s in show_data.get('seasons', []) or []
                           if cur_alt_type == _s.get('type', {}).get('type')):
                        page = 0
                        while 100 >= page:
                            resp = self._fetch_data(f'/series/{sid}/episodes/{cur_alt_type}?page={page:d}')
                            if isinstance(resp, dict) and isinstance((resp.get('data') or {}).get('episodes'), list):
                                for cur_ep in resp['data']['episodes']:
                                    alt_ep_types.setdefault(
                                        self.season_types.get(cur_alt_type, cur_alt_type),
                                        {}).setdefault(cur_ep['id'], {}).update({
                                            'season': cur_ep['seasonNumber'], 'episode': cur_ep['number'],
                                            'name': cur_ep['name']})
                                    alt_ep_nums.setdefault(cur_ep['id'], {}).update({
                                        self.season_type_map.get(cur_alt_type, cur_alt_type):
                                            {'season': cur_ep['seasonNumber'], 'episode': cur_ep['number']}})
                                if None is not (page := self._next_page(resp, page)):
                                    continue
                            break

                ep_lang = (language in (show_data.get('overviewTranslations') or []) and language) or 'eng'
                page, ti_show.ep_loaded, eps_count = 0, True, 0
                while 100 >= page:
                    resp = self._fetch_data(f'/series/{sid}/episodes/default/{ep_lang}?page={page:d}')
                    if isinstance(resp, dict) and isinstance((resp.get('data') or {}).get('episodes'), list):
                        links = 'next' in (resp.get('links') or '')
                        total_items = (links and resp.get('links', {}).get('total_items')) or None
                        page_size = (links and resp.get('links', {}).get('page_size')) or 500
                        eps_count += (len(resp['data']['episodes'])) or 0
                        full_page = page_size <= len(resp['data']['episodes'])
                        more = (links and None is not (page := self._next_page(resp, page))) or (
                                links and isinstance(total_items, integer_types) and eps_count < total_items)
                        alt_page = (full_page and not links)
                        if not alt_page:
                            self._set_episodes(ti_show, resp, abs_ep_nums, alt_ep_nums, alt_ep_types)

                        if not alt_page and more:
                            continue

                        if alt_page:
                            html = get_url(f'https://www.thetvdb.com/series/{ti_show.slug}/'
                                           f'allseasons/{default_season_type}')
                            if not html:
                                raise TvdbError('Failed to get episodes for show')

                            api_sxe = [f's{_e["seasonNumber"]}e{_e["number"]}'
                                       for _e in resp['data']['episodes']]
                            template_ep = resp['data']['episodes'][-1].copy()
                            try:
                                with BS4Parser(html) as soup:
                                    for cur_ep in soup.find_all('li', class_='list-group-item'):
                                        try:
                                            heading = cur_ep.h4
                                            sxe = [try_int(_n, None) for _n in
                                                   re.findall(r'(?i)s(?:pecial\s+)?(\d+)[ex](\d+)', clean_data(
                                                       heading.find('span', class_='episode-label').get_text()))[0]]
                                            if None in sxe or 's{}e{}'.format(*sxe) in api_sxe:
                                                continue
                                            ep_season, ep_number = sxe
                                        except(BaseException, Exception):
                                            continue

                                        try:
                                            ep_name = clean_data(heading.a.get_text())
                                            ep_link = heading.a['href']  # check link contains 'series'
                                            ep_id = try_int(re.findall(r'episodes/(\d+$)', ep_link)[0], None)
                                        except(BaseException, Exception):
                                            ep_id = None
                                        if None is ep_id:
                                            continue

                                        list_items = cur_ep.find('ul', class_='list-inline')
                                        aired = try_date(list_items.find_all('li')[0].get_text())

                                        row_items = cur_ep.find('div', class_='row')
                                        try:
                                            overview = clean_str(row_items.p.get_text())
                                        except(BaseException, Exception):
                                            overview = ''

                                        try:
                                            image = row_items.find('div', class_='col-xs-3').img['src']
                                        except(BaseException, Exception):
                                            image = None

                                        new_ep = template_ep.copy()
                                        new_ep.update(dict(
                                            id=ep_id, name=ep_name, aired=aired, overview=overview,
                                            image=image, imageType=11 if image and '/banner' in image else None,
                                            number=ep_number, seasonNumber=ep_season
                                        ))
                                        resp['data']['episodes'] += [new_ep]
                            except (BaseException, Exception):
                                pass
                            self._set_episodes(ti_show, resp, abs_ep_nums, alt_ep_nums, alt_ep_types)
                    break

            return True

        return False

    def _sanitise_image_uri(self, image):
        return isinstance(image, string_types) and 'http' != image[0:4] and \
            f'{self.art_url}{image.lstrip("/")}' or image

    def _set_episodes(self, ti_show, ep_data, abs_ep_nums, alt_ep_nums, alt_ep_types):
        # type: (TVInfoShow, Dict, Dict, Dict, Dict) -> None
        """
        populate a show with episode objects
        """
        for cur_ep_data in ep_data['data']['episodes']:
            for cur_key, cur_data in (
                    ('seasonnumber', 'seasonNumber'), ('episodenumber', 'number'),
                    ('episodename', 'name'), ('firstaired', 'aired'), ('runtime', 'runtime'),
                    ('seriesid', 'seriesId'), ('id', 'id'), ('filename', 'image'), ('overview', 'overview'),
                    ('absolute_number', 'abs'), ('finale_type', 'finaleType')):
                season_num, ep_num = cur_ep_data['seasonNumber'], cur_ep_data['number']

                if 'absolute_number' == cur_key:
                    value = abs_ep_nums.get(cur_ep_data['id'])
                else:
                    value = clean_data(cur_ep_data.get(cur_data, getattr(empty_ep, cur_key)))

                if 'finale_type' == cur_key:
                    value = tvdb_final_types.get(cur_ep_data.get(cur_data), None)

                if 'image' == cur_data:
                    value = self._sanitise_image_uri(value)

                if season_num not in ti_show:
                    ti_show[season_num] = TVInfoSeason(show=ti_show)
                    ti_show[season_num].number = season_num
                if ep_num not in ti_show[season_num]:
                    ti_show[season_num][ep_num] = TVInfoEpisode(season=ti_show[season_num])

                ti_show[season_num][ep_num][cur_key] = value
                ti_show[season_num][ep_num].__dict__[cur_key] = value
            ti_show[season_num][ep_num].alt_num = alt_ep_nums.get(cur_ep_data['id'], {})
            for cur_et in alt_ep_types:
                try:
                    ep = alt_ep_types[cur_et][cur_ep_data['id']]
                    if ep:
                        ti_show.alt_ep_numbering.setdefault(cur_et, {}).setdefault(ep['season'], {})[ep['episode']] = \
                            ti_show[season_num][ep_num]
                except (BaseException, Exception):
                    continue

    @staticmethod
    def _get_network(show_data):
        # type: (Dict) -> Optional[AnyStr]
        if 'network' in show_data:
            return clean_data(show_data['network'])
        if show_data.get('companies'):
            if isinstance(show_data['companies'][0], dict):
                return clean_data(next(
                    filter(lambda a: 1 == a['companyType']['companyTypeId'], show_data['companies']),
                    {}).get('name'))

            return clean_data(show_data['companies'][0])

    @staticmethod
    def _get_aliases(show_data):
        if show_data.get('aliases') and isinstance(show_data['aliases'][0], dict):
            return [clean_data(_a['name']) for _a in show_data['aliases']]
        return clean_data(show_data.get('aliases', []))

    @staticmethod
    def _get_tvdb_id(dct):
        try:
            return try_int(dct.get('tvdb_id'), None) or try_int(re.sub(r'^.+-(\d+)$', r'\1', f'{dct["id"]}'), None)
        except (BaseException, Exception):
            return

    @staticmethod
    def _get_first_aired(show_data):
        if isinstance(show_data, dict):
            first_aired = clean_data(show_data.get('first_air_time') or show_data.get('firstAired') or
                                     ('0000' != show_data.get('year') and show_data.get('year')) or None)
            if isinstance(first_aired, string_types) and re.search(r'(19|20)\d\d', first_aired):
                return first_aired

    @staticmethod
    def _get_remote_ids(show_data, tvdb_id):
        ids = {}
        if 'remote_ids' in show_data and isinstance(show_data['remote_ids'], list):
            for cur_rid in show_data['remote_ids']:
                src_name = cur_rid['sourceName'].lower()
                src_value = clean_data(cur_rid['id'])
                if 'imdb' in src_name:
                    try:
                        imdb_id = try_int(src_value.replace('tt', ''), None)
                        ids['imdb'] = imdb_id
                    except (BaseException, Exception):
                        pass
                elif 'themoviedb' in src_name:
                    ids['tmdb'] = try_int(src_value, None)
                elif 'tv maze' in src_name:
                    ids['tvmaze'] = try_int(src_value, None)
        return TVInfoIDs(tvdb=tvdb_id, **ids)

    def _search_show(
            self,
            name=None,  # type: Union[AnyStr, List[AnyStr]]
            ids=None,  # type: Dict[integer_types, integer_types]
            lang=None,  # type: Optional[string_types]
            **kwargs):
        # type: (...) -> List[Dict]
        """
        internal search function to find shows, should be overwritten in class
        :param name: name to search for
        :param ids: dict of ids {tvid: prodid} to search for
        """
        def _make_result_dict(show_data):
            tvdb_id = self._get_tvdb_id(show_data)
            series_name, series_aliases = self._get_series_name(show_data, language=lang)
            if not series_name:
                return []

            ti_show = TVInfoShow()
            if country := clean_data(show_data.get('country')) or []:
                country = [country]
            ti_show.seriesname, ti_show.id, ti_show.ids, \
                ti_show.firstaired, ti_show.network, \
                ti_show.overview, \
                ti_show.poster, \
                ti_show.status, \
                ti_show.language, ti_show.origin_countries, \
                ti_show.aliases, ti_show.slug, \
                ti_show.genre_list \
                = series_name, tvdb_id, self._get_remote_ids(show_data, tvdb_id), \
                self._get_first_aired(show_data), self._get_network(show_data), \
                self._get_overview(show_data, language=lang) or clean_str(show_data.get('overview')), \
                show_data.get('image_url') or show_data.get('image'), \
                clean_data(isinstance(show_data.get('status'), dict) and show_data.get('status', {}).get('name')
                           or show_data['status']), \
                clean_data(show_data.get('primary_language')), country, \
                series_aliases, clean_data(show_data.get('slug')), \
                [clean_data(_g.get('name')) for _g in (show_data.get('genres') or [])]

            ti_show.genre = '|'.join(ti_show.genre_list or [])
            return [ti_show]

        results = []
        if ids:
            for cur_tvinfo, cur_arg, cur_name in ((TVINFO_TVDB, lang, None), (TVINFO_IMDB, 'tt%07d', 'imdb'),
                                                  (TVINFO_TMDB, '%s', 'themoviedb'), (TVINFO_TVMAZE, '%s', 'tv maze')):
                if not ids.get(cur_tvinfo):
                    continue

                type_chk, query = list, None
                if TVINFO_TVDB == cur_tvinfo:
                    resp = self._get_show_data(ids[cur_tvinfo], cur_arg, direct_data=True)
                    type_chk = dict
                else:
                    query = cur_arg % ids[cur_tvinfo]
                    resp = self.get_cached_or_url(
                        'search?meta=translations',
                        f's-v4-id-{cur_tvinfo}-{ids[cur_tvinfo]}', expire=self.search_cache_expire,
                        remote_id=query, query=query, type='series')

                if self._check_resp(type_chk, resp):
                    if TVINFO_TVDB == cur_tvinfo:
                        results.extend(_make_result_dict(resp['data']))
                        continue

                    for cur_item in resp['data']:
                        try:
                            if query == next(filter(lambda b: cur_name in b['sourceName'].lower(),
                                                    cur_item.get('remote_ids', []) or []), {}).get('id'):
                                results.extend(_make_result_dict(cur_item))
                                break
                        except (BaseException, Exception):
                            pass

            if ids.get(TVINFO_TVDB_SLUG) and isinstance(ids.get(TVINFO_TVDB_SLUG), string_types) \
                and self._check_resp(dict, resp := self.get_cached_or_url(
                            f'/series/slug/{ids.get(TVINFO_TVDB_SLUG)}?meta=translations',
                            f's-id-{TVINFO_TVDB}-{ids[TVINFO_TVDB_SLUG]}', expire=self.search_cache_expire)):
                if ids.get(TVINFO_TVDB_SLUG).lower() == resp['data']['slug'].lower():
                    results.extend(_make_result_dict(resp['data']))

        if name:
            for cur_name in ([name], name)[isinstance(name, list)]:
                if self._check_resp(list, resp := self.get_cached_or_url(
                            'search?meta=translations',
                            f's-v4-name-{cur_name}', expire=self.search_cache_expire,
                            query=cur_name, type='series')):
                    for cur_item in resp['data']:
                        results.extend(_make_result_dict(cur_item))

        seen = set()
        results = [seen.add(_r['id']) or _r for _r in results if _r['id'] not in seen]
        return results

    def _get_languages(self):
        # type: (...) -> None
        if self._check_resp(list, resp := self._fetch_data('/languages')):
            TvdbAPIv4._supported_languages = [{
                'id': clean_data(_r['id']), 'name': clean_data(_r['name']),
                'nativeName': clean_data(_r['nativeName']),
                'shortCode': clean_data(_r['shortCode']),
                'sg_lang': self.reverse_map_languages.get(_r['id'], _r['id'])} for _r in resp['data']]
        else:
            TvdbAPIv4._supported_languages = []

    def _get_filtered_series(self, result_count=100, **kwargs):
        # type: (...) -> List[TVInfoShow]
        result = []
        page, cc = 0, 0
        while 100 > page and cc < result_count:
            if self._check_resp(list, resp := self._fetch_data('/series/filter', page=page, **kwargs)):
                for cur_item in resp['data']:
                    cc += 1
                    if cc > result_count:
                        break
                    _ti = TVInfoShow()
                    _ti.id, _ti.seriesname, _ti.firstaired, \
                        _ti.overview, _ti.ids, \
                        _ti.poster, _ti.language, \
                        _ti.origin_countries, _ti.rating, _ti.slug \
                        = cur_item['id'], clean_data(cur_item['name']), self._get_first_aired(cur_item), \
                        clean_str(cur_item['overview']), TVInfoIDs(tvdb=cur_item['id']), \
                        self._sanitise_image_uri(cur_item['image']), clean_data(cur_item['originalLanguage']), \
                        clean_data([cur_item['originalCountry']]), cur_item['score'], clean_data(cur_item['slug'])
                    result.append(_ti)
                if None is not (page := self._next_page(resp, page)):
                    continue
            break
        return result

    def discover(self, result_count=100, get_extra_images=False, **kwargs):
        # type: (integer_types, bool, Optional[Any]) -> List[TVInfoShow]
        return self._get_filtered_series(result_count=result_count, status=status_names['Upcoming']['id'],
                                         sort='firstAired', sortType='asc', lang='eng')

    def get_top_rated(self, result_count=100, year=None, in_last_year=False, **kwargs):
        # type: (integer_types, integer_types, bool, Optional[Any]) -> List[TVInfoShow]
        kw = dict(sort='score', sortType='desc', lang='eng')
        if in_last_year:
            ly = ((t := datetime.date.today()) - datetime.timedelta(days=365)).strftime('%Y-%m-%d')
            this_year = self._get_filtered_series(result_count=result_count, year=(y := t.year), **kw)
            last_year = [_l for _l in self._get_filtered_series(result_count=result_count, year=y-1, **kw)
                         if 10 == len(_l.firstaired or '') and _l.firstaired > ly]
            return sorted(this_year + last_year, key=lambda a: a.rating, reverse=True)[:result_count]
        elif isinstance(year, int):
            kw['year'] = year
        return self._get_filtered_series(result_count=result_count, **kw)
