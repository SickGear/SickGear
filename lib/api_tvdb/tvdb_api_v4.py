# encoding:utf-8
# author:Prinz23
# project:tvdb_api_v4

__author__ = 'Prinz23'
__version__ = '1.0'
__api_version__ = '1.0.0'

import base64
import datetime
import logging
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
from sickgear import ENV

from six import integer_types, iterkeys, iteritems, PY3, string_types
# noinspection PyUnreachableCode
if False:
    from typing import Any, AnyStr, Dict, List, Optional, Tuple, Union

log = logging.getLogger('tvdb_v4.api')
log.addHandler(logging.NullHandler())

TVDB_API_CONFIG = {}


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
        url = '%s%s' % (TvdbAPIv4.base_url, 'login')
        params = {'apikey': self.apikey()}
        resp = get_url(url, post_json=params, parse_json=True, raise_skip_exception=True)
        if resp and isinstance(resp, dict):
            if 'status' in resp:
                if 'failure' == resp['status']:
                    raise TvdbTokenFailure('Failed to Authenticate. %s' % resp.get('message', ''))
                if 'success' == resp['status'] and 'data' in resp and isinstance(resp['data'], dict) \
                        and 'token' in resp['data']:
                    self._token = resp['data']['token']
                    return True
        else:
            raise TvdbTokenFailure('Failed to get Tvdb Token')

    @property
    def token(self):
        if not self._token:
            self.get_token()
        return self._token

    def handle_401(self, r, **kwargs):
        if 401 == r.status_code and not any(401 == _or.status_code for _or in r.history):
            self.reset_token()
            self.get_token()
            if self._token:
                prep = r.request.copy()
                prep.headers['Authorization'] = "Bearer %s" % self._token
                _r = r.connection.send(prep, **kwargs)
                _r.history.append(r)
                _r.request = prep
                return _r

        return r

    def __call__(self, r):
        r.headers["Authorization"] = "Bearer %s" % self.token
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
                method_whitelist=['HEAD', 'GET', 'PUT', 'DELETE', 'OPTIONS', 'TRACE', 'POST'])
# noinspection HttpUrlsUsage
s.mount('http://', HTTPAdapter(TimeoutHTTPAdapter(max_retries=retries)))
s.mount('https://', HTTPAdapter(TimeoutHTTPAdapter(max_retries=retries)))
base_request_para = dict(session=s, hooks={'response': _record_hook}, raise_skip_exception=True, auth=TvdbAuth())


# Query TVdb endpoints
def tvdb_endpoint_get(*args, **kwargs):
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

    def _get_data(self, endpoint, **kwargs):
        # type: (string_types, Any) -> Any
        is_series_info, retry = endpoint.startswith('/series/'), kwargs.pop('token_retry', 1)
        if retry > 3:
            raise TvdbTokenFailure('Failed to get new token')
        if is_series_info:
            self.show_not_found = False
        try:
            return tvdb_endpoint_get(url='%s%s' % (self.base_url, endpoint), params=kwargs, parse_json=True,
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

    def _convert_person(self, p, ids=None):
        # type: (Dict, Dict) -> List[TVInfoPerson]
        ch, ids = [], ids or {}
        for c in sorted(filter(
                lambda a: (3 == a['type'] or 'Actor' == a['peopleType'])
                and a['name'] and a['seriesId'] and not a.get('episodeId'),
                p.get('characters') or []),
                key=lambda a: (not a['isFeatured'], a['sort'])):
            ti_show = TVInfoShow()
            ti_show.id = clean_data(c['seriesId'])
            ti_show.ids = TVInfoIDs(ids={TVINFO_TVDB: ti_show.id})
            ti_show.seriesname = clean_data(('series' in c and c['series'] and c['series']['name']))
            ti_show.poster = self._sanitise_image_uri(('series' in c and c['series'] and c['series']['image']))
            ti_show.firstaired = self._get_first_aired(('series' in c and c['series']))
            ch.append(TVInfoCharacter(id=c['id'], name=clean_data(c['name'] or ''), regular=c['isFeatured'],
                                      ids=TVInfoIDs(ids={TVINFO_TVDB: c['id']}),
                                      image=self._sanitise_image_uri(c.get('image')), ti_show=ti_show))
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
            for r_id in p['remoteIds']:
                src_name = r_id['sourceName'].lower()
                src_value = clean_data(r_id['id'])
                src_type = source_types.get(r_id['type'])
                if not src_value:
                    continue
                if TVINFO_IMDB == src_type or 'imdb' in src_name:
                    try:
                        imdb_id = try_int(('%s' % src_value).replace('nm', ''), None)
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
            akas=set(clean_data((isinstance(a, dict) and a['name']) or a) for a in p.get('aliases') or []),
            bio=bio, ids=TVInfoIDs(ids=ids), social_ids=TVInfoSocialIDs(ids=social_ids), homepage=official_site,
            characters=ch
        )]

    def get_person(self, p_id, get_show_credits=False, get_images=False, **kwargs):
        # type: (integer_types, bool, bool, Any) -> Optional[TVInfoPerson]
        """
        get person's data for id or list of matching persons for name

        :param p_id: persons id
        :param get_show_credits: get show credits
        :param get_images: get images for person
        :return: person object
        """
        if not p_id:
            return
        cache_key_name = 'p-v4-%s' % p_id
        is_none, people_obj = self._get_cache_entry(cache_key_name)
        if None is people_obj and not is_none:
            resp = self._get_data('/people/%s/extended' % p_id)
            self._set_cache_entry(cache_key_name, resp)
        else:
            resp = people_obj
        if isinstance(resp, dict) and all(t in resp for t in ('data', 'status')) and 'success' == resp['status'] \
                and isinstance(resp['data'], dict):
            return self._convert_person(resp['data'])[0]

    def _search_person(self, name=None, ids=None):
        # type: (AnyStr, Dict[integer_types, integer_types]) -> List[TVInfoPerson]
        """
        search for person by name
        :param name: name to search for
        :param ids: dict of ids to search
        :return: list of found person's
        """
        urls, result, ids = [], [], ids or {}
        for tv_src in self.supported_person_id_searches:
            if tv_src in ids:
                if TVINFO_TVDB == tv_src:
                    r = self.get_person(ids[tv_src])
                    if r:
                        result.append(r)
                if tv_src in (TVINFO_IMDB, TVINFO_TMDB, TVINFO_TVMAZE):
                    _src = tv_src
                    cache_id_key = 'p-v4-id-%s-%s' % (_src, ids[_src])
                    is_none, shows = self._get_cache_entry(cache_id_key)
                    d_m = None
                    if not self.config.get('cache_search') or (None is shows and not is_none):
                        try:
                            if TVINFO_IMDB == tv_src:
                                d_m = self._get_data('search/remoteid/%s' % ('nm%07d' % ids.get(TVINFO_IMDB)))
                            elif TVINFO_TMDB == tv_src:
                                d_m = self._get_data('search/remoteid/%s' % ids.get(TVINFO_TMDB))
                            elif TVINFO_TVMAZE == tv_src:
                                d_m = self._get_data('search/remoteid/%s' % ids.get(TVINFO_TVMAZE))
                            self._set_cache_entry(cache_id_key, d_m, expire=self.search_cache_expire)
                        except (BaseException, Exception):
                            d_m = None
                    else:
                        d_m = shows
                    if isinstance(d_m, dict) and all(t in d_m for t in ('data', 'status')) \
                            and 'success' == d_m['status'] and isinstance(d_m['data'], list):
                        for r in d_m['data']:
                            if isinstance(r, dict) and 'people' in r:
                                if 1 == len(r):
                                    p_d = self.get_person(r['people']['id'])
                                else:
                                    p_d = None
                                if p_d:
                                    result.append(p_d)
                                else:
                                    result.extend(self._convert_person(r['people'], ids))
                                break
        if name:
            cache_key_name = 'p-v4-src-text-%s' % name
            is_none, people_objs = self._get_cache_entry(cache_key_name)
            if None is people_objs and not is_none:
                resp = self._get_data('/search', query=name, type='people')
                self._set_cache_entry(cache_key_name, resp)
            else:
                resp = people_objs
            if isinstance(resp, dict) and all(t in resp for t in ('data', 'status')) and 'success' == resp['status'] \
                    and isinstance(resp['data'], list):
                for r in resp['data']:
                    result.extend(self._convert_person(r))
        seen = set()
        result = [seen.add(r.id) or r for r in result if r.id not in seen]
        return result

    def search_tvs(self, terms, language=None):
        # type: (Union[int, str], Optional[str]) -> Optional[dict]
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
                         ['query=%s' % terms, 'maxValuesPerFacet=10', 'page=0',
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
        if isinstance(show_data.get('translations'), dict) and 'overviewTranslations' in show_data['translations']:
            try:
                trans = next(filter(
                    lambda _s: language == _s['language'], show_data['translations']['overviewTranslations']),
                    next(filter(
                        lambda _s: 'eng' == _s['language'], show_data['translations']['overviewTranslations']), None))
                if trans:
                    return clean_str(trans['overview'])
            except (BaseException, Exception):
                pass
        elif isinstance(show_data, dict) and 'overviews' in show_data:
            return clean_str(show_data['overviews'].get(language, show_data.get('overview')))
        return ''

    def _get_series_name(self, show_data, language=None):
        # type: (Dict, AnyStr) -> Tuple[Optional[AnyStr], List]
        series_name = clean_data(
            next(filter(lambda l: language and language == l['language'],
                        show_data.get('translations', {}).get('nameTranslations', [])),
                 {'name': show_data['name']})['name'])
        series_aliases = self._get_aliases(show_data)
        if not series_name:
            if isinstance(series_aliases, list) and 0 < len(series_aliases):
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
        resp = self._get_data('/series/%s/extended?meta=translations' % sid)
        if direct_data:
            return resp
        if isinstance(resp, dict) and all(f in resp for f in ('status', 'data')) and 'success' == resp['status'] \
                and isinstance(resp['data'], dict):
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
                                     and next((r['name'] for r in show_data['contentRatings'] or []
                                               if 'usa' == r['country']), None)) or None
            ti_show.aliases = series_aliases
            ti_show.status = clean_data(show_data['status']['name'])
            ti_show.network_country = clean_data(show_data.get('originalCountry'))
            ti_show.lastupdated = clean_data(show_data.get('lastUpdated'))
            existing_networks = []
            if 'latestNetwork' in show_data:
                if isinstance(show_data['latestNetwork'].get('primaryCompanyType'), integer_types) \
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
                networks = sorted([n for n in show_data['companies'] if 1 == n['companyType']['companyTypeId']
                                   and n['country']], key=lambda a: a['activeDate'] or '0000-00-00')
                if networks:
                    ti_show.networks.extend([TVInfoNetwork(
                        name=clean_data(n['name']), country=clean_data(n['country']),
                        active_date=clean_data(n['activeDate']), inactive_date=clean_data(n['inactiveDate']))
                                             for n in networks if clean_data(n['name']) not in existing_networks])
                    if not ti_show.network:
                        ti_show.network = clean_data(networks[-1]['name'])
                        ti_show.network_country = clean_data(networks[-1]['country'])
            ti_show.language = clean_data(show_data.get('originalLanguage'))
            ti_show.runtime = show_data.get('averageRuntime')
            ti_show.airs_time = clean_data(show_data.get('airsTime'))
            ti_show.airs_dayofweek = ', '.join([k.capitalize() for k, v in iteritems(show_data.get('airsDays')) if v])
            ti_show.genre_list = ('genres' in show_data and show_data['genres']
                                  and [clean_data(g['name']) for g in show_data['genres']]) or []
            ti_show.genre = '|'.join(ti_show.genre_list)

            ids, social_ids = {}, {}
            if 'remoteIds' in show_data and isinstance(show_data['remoteIds'], list):
                for r_id in show_data['remoteIds']:
                    src_name = r_id['sourceName'].lower()
                    src_value = clean_data(r_id['id'])
                    src_type = source_types.get(r_id['type'])
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
                        social_ids[TVINFO_TIKTOK] = src_value
                    elif TVINFO_LINKEDIN == src_type:
                        social_ids[TVINFO_LINKEDIN] = src_value
                    elif TVINFO_FANSITE == src_type:
                        social_ids[TVINFO_FANSITE] = src_value

            ti_show.ids = TVInfoIDs(tvdb=show_data['id'], **ids)
            if social_ids:
                ti_show.social_ids = TVInfoSocialIDs(**social_ids)

            ti_show.overview = self._get_overview(show_data, language=language)

            if 'artworks' in show_data and isinstance(show_data['artworks'], list):
                poster = banner = fanart_url = False
                for artwork in sorted(show_data['artworks'], key=lambda a: a['score'], reverse=True):
                    img_type = img_type_map.get(artwork['type'], TVInfoImageType.other)
                    if False is poster and img_type == TVInfoImageType.poster:
                        ti_show.poster, ti_show.poster_thumb, poster = artwork['image'], artwork['thumbnail'], True
                    elif False is banner and img_type == TVInfoImageType.banner:
                        ti_show.banner, ti_show.banner_thumb, banner = artwork['image'], artwork['thumbnail'], True
                    elif False is fanart_url and img_type == TVInfoImageType.fanart:
                        ti_show.fanart, fanart_url = artwork['image'], True
                    ti_show['images'].setdefault(img_type, []).append(
                        TVInfoImage(
                            image_type=img_type,
                            sizes={TVInfoImageSize.original: artwork['image'],
                                   TVInfoImageSize.small: artwork['thumbnail']},
                            img_id=artwork['id'],
                            lang=artwork['language'],
                            rating=artwork['score'],
                            updated_at=artwork['updatedAt'] or None
                        )
                    )

            if (actors or self.config['actors_enabled']) \
                    and not getattr(self.ti_shows.get(sid), 'actors_loaded', False):
                cast, crew, ti_show.actors_loaded = CastList(), CrewList(), True
                if isinstance(show_data.get('characters'), list):
                    for character in sorted(show_data.get('characters') or [],
                                            key=lambda c: (not c['isFeatured'], c['sort'])):
                        people_type = people_types.get(character['type'])
                        if people_type not in (RoleTypes.ActorMain, RoleTypes.ActorGuest, RoleTypes.ActorSpecialGuest,
                                               RoleTypes.ActorRecurring) \
                                and isinstance(character['name'], string_types):
                            low_name = character['name'].lower()
                            if 'presenter' in low_name:
                                people_type = RoleTypes.Presenter
                            elif 'interviewer' in low_name:
                                people_type = RoleTypes.Interviewer
                            elif 'host' in low_name:
                                people_type = RoleTypes.Host
                        if character['episodeId']:
                            if RoleTypes.ActorMain == people_type:
                                people_type = RoleTypes.ActorGuest
                            elif RoleTypes.Presenter == people_type:
                                people_type = RoleTypes.PresenterGuest
                            elif RoleTypes.Interviewer == people_type:
                                people_type = RoleTypes.InterviewerGuest
                            elif RoleTypes.Host == people_type:
                                people_type = RoleTypes.HostGuest
                        if people_type in (RoleTypes.Presenter, RoleTypes.Interviewer, RoleTypes.Host) \
                                and not character['name']:
                            character['name'] = {RoleTypes.Presenter: 'Presenter', RoleTypes.Interviewer: 'Interviewer',
                                                 RoleTypes.Host: 'Host'}.get(people_type) or character['name']
                        if None is people_type:
                            continue
                        if RoleTypes.crew_limit > people_type:
                            cast[people_type].append(
                                TVInfoCharacter(p_id=character['id'], name=clean_data(character['name'] or ''),
                                                regular=character['isFeatured'],
                                                ids=TVInfoIDs(ids={TVINFO_TVDB: character['id']}),
                                                person=[
                                                    TVInfoPerson(
                                                        p_id=character['peopleId'],
                                                        name=clean_data(character['personName'] or ''),
                                                        image=self._sanitise_image_uri(character.get('personImgURL')),
                                                        ids=TVInfoIDs(ids={TVINFO_TVDB: character['peopleId']}))],
                                                image=self._sanitise_image_uri(character['image'])))
                        else:
                            crew[people_type].append(
                                TVInfoPerson(p_id=character['peopleId'], name=clean_data(character['personName'] or ''),
                                             image=self._sanitise_image_uri(character.get('personImgURL')),
                                             ids=TVInfoIDs(ids={TVINFO_TVDB: character['peopleId']})))

                if not cast[RoleTypes.ActorMain]:
                    html = get_url('https://www.thetvdb.com/series/%s/people' % ti_show.slug)
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
                                                        for person in filter(*people_filter):
                                                            new_keys = set(list(person)).difference({
                                                                '_highlightResult', 'banner', 'id', 'image',
                                                                'is_tvdb_searchable', 'is_tvt_searchable', 'name',
                                                                'objectID', 'people_birthdate', 'people_died',
                                                                'poster', 'type', 'url'
                                                            })
                                                            if new_keys:
                                                                log.warning(
                                                                    'DEV_MODE: New _parse_actors tvdb attrs for %s %r'
                                                                    % (person['id'], new_keys))

                                                    person_ok = False
                                                    for person in filter(*people_filter):
                                                        if image:
                                                            people_data = get_url(person['url'])
                                                            person_ok = re.search(re.escape(image), people_data)
                                                        if not image or person_ok:
                                                            person_id = person['id']
                                                            raise ValueError('value okay, id found')
                                            except (BaseException, Exception):
                                                pass

                                        rid = int(rc_role.search(cur_role.get('href')).group('role_id'))
                                        person_id = try_int(person_id, None)
                                        image = image and 'https://artworks.thetvdb.com/banners/%s' % image or None
                                        # noinspection PyTypeChecker
                                        cast[RoleTypes.ActorMain].append(
                                            TVInfoCharacter(p_id=rid, name=clean_data(role), ids={TVINFO_TVDB: rid},
                                                            image=image,
                                                            person=[TVInfoPerson(p_id=person_id, name=clean_data(name),
                                                                                 ids={TVINFO_TVDB: person_id})]
                                                            ))
                                    except(BaseException, Exception):
                                        pass
                        except(BaseException, Exception):
                            pass

                ti_show.cast = cast
                ti_show.crew = crew
                ti_show.actors = [
                    {'character': {'id': ch.id,
                                   'name': ch.name,
                                   'url': 'https://www.thetvdb.com/series/%s/people/%s' % (show_data['slug'], ch.id),
                                   'image': ch.image,
                                   },
                     'person': {'id': ch.person and ch.person[0].id,
                                'name': ch.person and ch.person[0].name,
                                'url': ch.person and 'https://www.thetvdb.com/people/%s' % ch.person[0].id,
                                'image': ch.person and ch.person[0].image,
                                'birthday': try_date(ch.birthdate),
                                'deathday': try_date(ch.deathdate),
                                'gender': None,
                                'country': None,
                                },
                     } for ch in cast[RoleTypes.ActorMain]]

            if get_ep_info and not getattr(self.ti_shows.get(sid), 'ep_loaded', False):
                # fetch absolute numbers
                abs_ep_nums = {}
                if any(1 for _s in show_data.get('seasons', []) or [] if 'absolute' == _s.get('type', {}).get('type')):
                    page = 0
                    while 100 >= page:
                        abs_ep_data = self._get_data('/series/%s/episodes/absolute?page=%d' % (sid, page))
                        page += 1
                        if isinstance(abs_ep_data, dict):
                            valid_data = 'data' in abs_ep_data and isinstance(abs_ep_data['data'], dict) \
                                         and 'episodes' in abs_ep_data['data'] \
                                         and isinstance(abs_ep_data['data']['episodes'], list)
                            if not valid_data:
                                break
                            links = 'links' in abs_ep_data and isinstance(abs_ep_data['links'], dict) \
                                    and 'next' in abs_ep_data['links']
                            more = (links and isinstance(abs_ep_data['links']['next'], string_types)
                                    and '?page=%d' % page in abs_ep_data['links']['next'])
                            if valid_data:
                                abs_ep_nums.update({_e['id']: _e['number'] for _e in abs_ep_data['data']['episodes']
                                                    if None is _e['seasons'] and _e['number']})
                            if more:
                                continue
                        break

                # fetch alt numbers
                alt_ep_nums, alt_ep_types, default_season_type = \
                    {}, {}, self.season_types.get(show_data.get('defaultSeasonType'))
                for alt_type in {_a.get('type', {}).get('type') for _a in show_data.get('seasons', []) or []
                                 if _a.get('type', {}).get('type') not in ('absolute', default_season_type)}:
                    if any(1 for _s in show_data.get('seasons', []) or []
                           if alt_type == _s.get('type', {}).get('type')):
                        page = 0
                        while 100 >= page:
                            alt_ep_data = self._get_data('/series/%s/episodes/%s?page=%d' % (sid, alt_type, page))
                            page += 1
                            if isinstance(alt_ep_data, dict):
                                valid_data = 'data' in alt_ep_data and isinstance(alt_ep_data['data'], dict) \
                                             and 'episodes' in alt_ep_data['data'] \
                                             and isinstance(alt_ep_data['data']['episodes'], list)
                                if not valid_data:
                                    break
                                links = 'links' in alt_ep_data and isinstance(alt_ep_data['links'], dict) \
                                        and 'next' in alt_ep_data['links']
                                more = (links and isinstance(alt_ep_data['links']['next'], string_types)
                                        and '?page=%d' % page in alt_ep_data['links']['next'])
                                if valid_data:
                                    for _e in alt_ep_data['data']['episodes']:
                                        alt_ep_types.setdefault(
                                            self.season_types.get(alt_type, alt_type),
                                            {}).setdefault(_e['id'], {}).update(
                                            {'season': _e['seasonNumber'], 'episode': _e['number'], 'name': _e['name']})
                                        alt_ep_nums.setdefault(_e['id'], {}).update(
                                            {self.season_type_map.get(alt_type, alt_type):
                                             {'season': _e['seasonNumber'], 'episode': _e['number']}})
                                if more:
                                    continue
                            break

                ep_lang = (language in (show_data.get('overviewTranslations', []) or []) and language) or 'eng'
                page, ti_show.ep_loaded, eps_count = 0, True, 0
                while 100 >= page:
                    ep_data = self._get_data('/series/%s/episodes/default/%s?page=%d' % (sid, ep_lang, page))
                    page += 1
                    if isinstance(ep_data, dict):
                        valid_data = 'data' in ep_data and isinstance(ep_data['data'], dict) \
                                and 'episodes' in ep_data['data'] and isinstance(ep_data['data']['episodes'], list)
                        if not valid_data:
                            break
                        links = 'links' in ep_data and isinstance(ep_data['links'], dict) \
                                and 'next' in ep_data['links']
                        total_items = (links and 'total_items' in ep_data['links'] and ep_data['links']['total_items']
                                       ) or None
                        page_size = (links and 'page_size' in ep_data['links'] and ep_data['links']['page_size']
                                     ) or 500
                        eps_count += (valid_data and len(ep_data['data']['episodes'])) or 0
                        full_page = valid_data and page_size <= len(ep_data['data']['episodes'])
                        more = (links and isinstance(ep_data['links']['next'], string_types)
                                and '?page=%d' % page in ep_data['links']['next']) or (
                                links and isinstance(total_items, integer_types) and eps_count < total_items)
                        alt_page = (full_page and not links)
                        if not alt_page and valid_data:
                            self._set_episodes(ti_show, ep_data, abs_ep_nums, alt_ep_nums, alt_ep_types)

                        if not alt_page and more:
                            continue

                        if alt_page:
                            html = get_url('https://www.thetvdb.com/series/%s/allseasons/%s' %
                                           (ti_show.slug, default_season_type))
                            if not html:
                                raise TvdbError('Failed to get episodes for show')
                            else:
                                api_sxe = ['s%se%s' % (_e['seasonNumber'], _e['number'])
                                           for _e in ep_data['data']['episodes']]
                                template_ep = ep_data['data']['episodes'][-1].copy()
                                try:
                                    with BS4Parser(html) as soup:
                                        for cur_ep in soup.find_all('li', class_='list-group-item'):
                                            try:
                                                heading = cur_ep.h4
                                                sxe = [try_int(n, None) for n in
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
                                            ep_data['data']['episodes'] += [new_ep]
                                except (BaseException, Exception):
                                    pass
                            self._set_episodes(ti_show, ep_data, abs_ep_nums, alt_ep_nums, alt_ep_types)
                    break

            return True

        return False

    def _sanitise_image_uri(self, image):
        return isinstance(image, string_types) and 'http' != image[0:4] and \
               '%s%s' % (self.art_url, image.lstrip('/')) or image

    def _set_episodes(self, ti_show, ep_data, abs_ep_nums, alt_ep_nums, alt_ep_types):
        # type: (TVInfoShow, Dict, Dict, Dict, Dict) -> None
        """
        populates the show with episode objects
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
            for s_t in iterkeys(alt_ep_types):
                try:
                    m_e = alt_ep_types.get(s_t, {}).get(cur_ep_data['id'], {})
                    if m_e:
                        ti_show.alt_ep_numbering.setdefault(s_t, {}).setdefault(m_e['season'], {})[m_e['episode']] = \
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
                return clean_data(next(filter(
                    lambda a: 1 == a['companyType']['companyTypeId'], show_data['companies']), {}).get('name'))
            else:
                return clean_data(show_data['companies'][0])

    @staticmethod
    def _get_aliases(show_data):
        if show_data.get('aliases') and isinstance(show_data['aliases'][0], dict):
            return [clean_data(a['name']) for a in show_data['aliases']]
        return clean_data(show_data.get('aliases', []))

    @staticmethod
    def _get_tvdb_id(dct):
        try:
            tvdb_id = try_int(dct.get('tvdb_id'), None) or try_int(re.sub(r'^.+-(\d+)$', r'\1', '%s' % dct['id']), None)
        except (BaseException, Exception):
            tvdb_id = None

        return tvdb_id

    @staticmethod
    def _get_first_aired(show_data):
        if isinstance(show_data, dict):
            _f_a = clean_data(show_data.get('first_air_time') or show_data.get('firstAired') or
                              ('0000' != show_data.get('year') and show_data.get('year')) or None)
            if isinstance(_f_a, string_types) and re.search(r'(19|20)\d\d', _f_a):
                return _f_a

    @staticmethod
    def _get_remote_ids(show_data, tvdb_id):
        ids = {}
        if 'remote_ids' in show_data and isinstance(show_data['remote_ids'], list):
            for r_id in show_data['remote_ids']:
                src_name = r_id['sourceName'].lower()
                src_value = clean_data(r_id['id'])
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

    def _search_show(self, name=None, ids=None, lang=None, **kwargs):
        # type: (Union[AnyStr, List[AnyStr]], Dict[integer_types, integer_types], Optional[string_types], Optional[Any]) -> List[Dict]
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
            country = clean_data(show_data.get('country'))
            if country:
                country = [country]
            else:
                country = []
            ti_show.seriesname, ti_show.id, ti_show.ids, ti_show.firstaired, ti_show.network, ti_show.overview, \
                ti_show.poster, ti_show.status, ti_show.language, ti_show.origin_countries, ti_show.aliases, \
                ti_show.slug, ti_show.genre_list = series_name, tvdb_id, self._get_remote_ids(show_data, tvdb_id), \
                self._get_first_aired(show_data), self._get_network(show_data), \
                self._get_overview(show_data, language=lang) or clean_str(show_data.get('overview')), \
                show_data.get('image_url') or show_data.get('image'), \
                clean_data(isinstance(show_data['status'], dict) and show_data['status']['name']
                           or show_data['status']), clean_data(show_data.get('primary_language')), \
                country, series_aliases, clean_data(show_data.get('slug')), \
                ('genres' in show_data and show_data['genres'] and [clean_data(g['name'])
                                                                    for g in show_data['genres']]) or []
            ti_show.genre = '|'.join(ti_show.genre_list or [])
            return [ti_show]

        results = []
        if ids:
            if ids.get(TVINFO_TVDB):
                cache_id_key = 's-v4-id-%s-%s' % (TVINFO_TVDB, ids[TVINFO_TVDB])
                is_none, shows = self._get_cache_entry(cache_id_key)
                # noinspection DuplicatedCode
                if not self.config.get('cache_search') or (None is shows and not is_none):
                    try:
                        d_m = self._get_show_data(ids.get(TVINFO_TVDB), self.config['language'], direct_data=True)
                        self._set_cache_entry(cache_id_key, d_m, expire=self.search_cache_expire)
                    except (BaseException, Exception):
                        d_m = None
                else:
                    d_m = shows
                if isinstance(d_m, dict) and all(t in d_m for t in ('data', 'status')) and 'success' == d_m['status'] \
                        and isinstance(d_m['data'], dict):
                    results.extend(_make_result_dict(d_m['data']))

            if ids.get(TVINFO_IMDB):
                cache_id_key = 's-v4-id-%s-%s' % (TVINFO_IMDB, ids[TVINFO_IMDB])
                is_none, shows = self._get_cache_entry(cache_id_key)
                if not self.config.get('cache_search') or (None is shows and not is_none):
                    try:
                        d_m = self._get_data('search', remote_id='tt%07d' % ids.get(TVINFO_IMDB),
                                             query='tt%07d' % ids.get(TVINFO_IMDB), type='series')
                        self._set_cache_entry(cache_id_key, d_m, expire=self.search_cache_expire)
                    except (BaseException, Exception):
                        d_m = None
                else:
                    d_m = shows
                if isinstance(d_m, dict) and all(t in d_m for t in ('data', 'status')) and 'success' == d_m['status'] \
                        and isinstance(d_m['data'], list):
                    for r in d_m['data']:
                        try:
                            if 'tt%07d' % ids[TVINFO_IMDB] == \
                                    next(filter(lambda b: 'imdb' in b['sourceName'].lower(),
                                                r.get('remote_ids', []) or []), {}).get('id'):
                                results.extend(_make_result_dict(r))
                                break
                        except (BaseException, Exception):
                            pass

            if ids.get(TVINFO_TMDB):
                cache_id_key = 's-v4-id-%s-%s' % (TVINFO_TMDB, ids[TVINFO_TMDB])
                is_none, shows = self._get_cache_entry(cache_id_key)
                if not self.config.get('cache_search') or (None is shows and not is_none):
                    try:
                        d_m = self._get_data('search', remote_id='%s' % ids.get(TVINFO_TMDB),
                                             query='%s' % ids.get(TVINFO_TMDB), type='series')
                        self._set_cache_entry(cache_id_key, d_m, expire=self.search_cache_expire)
                    except (BaseException, Exception):
                        d_m = None
                else:
                    d_m = shows
                if isinstance(d_m, dict) and all(t in d_m for t in ('data', 'status')) and 'success' == d_m['status'] \
                        and isinstance(d_m['data'], list):
                    for r in d_m['data']:
                        try:
                            if '%s' % ids[TVINFO_TMDB] == \
                                    next(filter(lambda b: 'themoviedb' in b['sourceName'].lower(),
                                                r.get('remote_ids', []) or []), {}).get('id'):
                                results.extend(_make_result_dict(r))
                                break
                        except (BaseException, Exception):
                            pass

            if ids.get(TVINFO_TVMAZE):
                cache_id_key = 's-v4-id-%s-%s' % (TVINFO_TVMAZE, ids[TVINFO_TVMAZE])
                is_none, shows = self._get_cache_entry(cache_id_key)
                if not self.config.get('cache_search') or (None is shows and not is_none):
                    try:
                        d_m = self._get_data('search', remote_id='%s' % ids.get(TVINFO_TVMAZE),
                                             query='%s' % ids.get(TVINFO_TVMAZE), type='series')
                        self._set_cache_entry(cache_id_key, d_m, expire=self.search_cache_expire)
                    except (BaseException, Exception):
                        d_m = None
                else:
                    d_m = shows
                if isinstance(d_m, dict) and all(t in d_m for t in ('data', 'status')) and 'success' == d_m['status'] \
                        and isinstance(d_m['data'], list):
                    for r in d_m['data']:
                        try:
                            if '%s' % ids[TVINFO_TVMAZE] == \
                                    next(filter(lambda b: 'tv maze' in b['sourceName'].lower(),
                                                r.get('remote_ids', []) or []), {}).get('id'):
                                results.extend(_make_result_dict(r))
                                break
                        except (BaseException, Exception):
                            pass

            if ids.get(TVINFO_TVDB_SLUG) and isinstance(ids.get(TVINFO_TVDB_SLUG), string_types):
                cache_id_key = 's-id-%s-%s' % (TVINFO_TVDB, ids[TVINFO_TVDB_SLUG])
                is_none, shows = self._get_cache_entry(cache_id_key)
                if not self.config.get('cache_search') or (None is shows and not is_none):
                    try:
                        d_m = self._get_data('/series/slug/%s' % ids.get(TVINFO_TVDB_SLUG))
                        self._set_cache_entry(cache_id_key, d_m, expire=self.search_cache_expire)
                    except (BaseException, Exception):
                        d_m = None
                else:
                    d_m = shows
                if d_m and isinstance(d_m, dict) and 'data' in d_m and 'success' == d_m.get('status') and \
                        ids.get(TVINFO_TVDB_SLUG).lower() == d_m['data']['slug'].lower():
                    results.extend(_make_result_dict(d_m['data']))

        if name:
            for n in ([name], name)[isinstance(name, list)]:
                cache_name_key = 's-v4-name-%s' % n
                is_none, shows = self._get_cache_entry(cache_name_key)
                if not self.config.get('cache_search') or (None is shows and not is_none):
                    resp = self._get_data('search', query=n, type='series')
                    self._set_cache_entry(cache_name_key, resp, expire=self.search_cache_expire)
                else:
                    resp = shows

                if resp and isinstance(resp, dict) and 'data' in resp and 'success' == resp.get('status') \
                        and isinstance(resp['data'], list):
                    for show in resp['data']:
                        results.extend(_make_result_dict(show))

        seen = set()
        results = [seen.add(r['id']) or r for r in results if r['id'] not in seen]
        return results

    def _get_languages(self):
        # type: (...) -> None
        langs = self._get_data('/languages')
        if isinstance(langs, dict) and 'status' in langs and 'success' == langs['status'] \
                and isinstance(langs.get('data'), list):
            TvdbAPIv4._supported_languages = [{'id': clean_data(a['id']), 'name': clean_data(a['name']),
                                               'nativeName': clean_data(a['nativeName']),
                                               'shortCode': clean_data(a['shortCode']),
                                               'sg_lang': self.reverse_map_languages.get(a['id'], a['id'])}
                                                for a in langs['data']]
        else:
            TvdbAPIv4._supported_languages = []

    def _get_filtered_series(self, result_count=100, **kwargs):
        # type: (...) -> List[TVInfoShow]
        r = []
        page, cc = 0, 0
        while 100 > page and cc < result_count:
            d = self._get_data('/series/filter', page=page, **kwargs)
            page += 1
            valid_data = isinstance(d, dict) and 'data' in d and isinstance(d['data'], list) and len(d['data'])
            if not valid_data:
                break
            links = 'links' in d and isinstance(d['links'], dict) and 'next' in d['links']
            more = (links and isinstance(d['links']['next'], string_types) and 'page=%d' % page in d['links']['next'])
            if isinstance(d, dict) and 'status' in d and 'success' == d['status'] \
                    and isinstance(d.get('data'), list):
                for _s in d['data']:
                    cc += 1
                    if cc > result_count:
                        break
                    _ti = TVInfoShow()
                    _ti.id, _ti.seriesname, _ti.firstaired, _ti.overview, _ti.ids, _ti.poster, _ti.language, \
                        _ti.origin_countries, _ti.rating, _ti.slug = _s['id'], clean_data(_s['name']), \
                        self._get_first_aired(_s), clean_str(_s['overview']), \
                        TVInfoIDs(tvdb=_s['id']), self._sanitise_image_uri(_s['image']), \
                        clean_data(_s['originalLanguage']), clean_data([_s['originalCountry']]), \
                        _s['score'], clean_data(_s['slug'])
                    r.append(_ti)
            if not more:
                break
        return r

    def discover(self, result_count=100, get_extra_images=False, **kwargs):
        # type: (integer_types, bool, Optional[Any]) -> List[TVInfoShow]
        return self._get_filtered_series(result_count=result_count, status=status_names['Upcoming']['id'],
                                         sort='firstAired', sortType='asc', lang='eng')

    def get_top_rated(self, result_count=100, year=None, in_last_year=False, **kwargs):
        # type: (integer_types, integer_types, bool, Optional[Any]) -> List[TVInfoShow]
        kw = dict(sort='score', sortType='desc', lang='eng')
        if in_last_year:
            t = datetime.date.today()
            y = t.year
            ly = (t - datetime.timedelta(days=365)).strftime('%Y-%m-%d')
            this_year = self._get_filtered_series(result_count=result_count, year=y, **kw)
            last_year = [_l for _l in self._get_filtered_series(result_count=result_count, year=y-1, **kw)
                         if 10 == len(_l.firstaired or '') and _l.firstaired > ly]
            return sorted(this_year + last_year, key=lambda a: a.rating, reverse=True)[:result_count]
        elif isinstance(year, int):
            kw['year'] = year
        return self._get_filtered_series(result_count=result_count, **kw)

