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

import requests
from urllib3.util.retry import Retry
from requests.adapters import HTTPAdapter

from _23 import filter_iter
from exceptions_helper import ex
from six import integer_types, iteritems, PY3, string_types
from sg_helpers import clean_data, get_url, try_int
from lib.dateutil.parser import parser
# noinspection PyProtectedMember
from lib.exceptions_helper import ConnectionSkipException, ex
from lib.tvinfo_base import TVInfoBase, TVInfoImage, TVInfoImageSize, TVInfoImageType, Character, \
    Person, RoleTypes, TVInfoShow, TVInfoEpisode, TVInfoIDs, TVInfoSeason, PersonGenders, \
    TVINFO_FACEBOOK, TVINFO_TWITTER, TVINFO_INSTAGRAM, TVINFO_REDDIT, TVINFO_YOUTUBE, \
    TVINFO_TVDB, TVInfoNetwork, TVInfoSocialIDs, CastList, TVINFO_TVDB_SLUG
from .tvdb_exceptions import TvdbTokenFailre, TvdbError

# noinspection PyUnreachableCode
if False:
    from typing import Any, AnyStr, Dict, List, Optional, Tuple, Union

log = logging.getLogger('tvdb_v4.api')
log.addHandler(logging.NullHandler())

TVDB_API_CONFIG = {}


# always use https in cases of redirects
def _record_hook(r, *args, **kwargs):
    r.hook_called = True
    if r.status_code in (301, 302, 303, 307, 308) and isinstance(r.headers.get('Location'), string_types) \
            and r.headers.get('Location').startswith('http://'):
        r.headers['Location'] = r.headers['Location'].replace('http://', 'https://')
    return r


class TvdbAuth(requests.auth.AuthBase):
    _token = None
    _auth_time = None

    def __init__(self):
        pass

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
        url = '%s%s' % (Tvdb_API_V4.base_url, 'login')
        params = {'apikey': self.apikey()}
        resp = get_url(url, post_json=params, parse_json=True, raise_skip_exception=True)
        if resp and isinstance(resp, dict):
            if 'status' in resp:
                if 'failure' == resp['status']:
                    raise TvdbTokenFailre('Failed to Authenticate. %s' % resp.get('message', ''))
                if 'success' == resp['status'] and 'data' in resp and isinstance(resp['data'], dict) \
                        and 'token' in resp['data']:
                    self._token = resp['data']['token']
                    self._auth_time = datetime.datetime.now()
                    return True
        else:
            raise TvdbTokenFailre('Failed to get Tvdb Token')

    @property
    def token(self):
        if not self._token or not self._auth_time:
            self.get_token()
        return self._token

    def __call__(self, r):
        r.headers["Authorization"] = "Bearer %s" % self.token
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

empty_ep = TVInfoEpisode()
tz_p = parser()


class Tvdb_API_V4(TVInfoBase):
    supported_id_searches = [TVINFO_TVDB, TVINFO_TVDB_SLUG, TVINFO_IMDB, TVINFO_TMDB]
    supported_person_id_searches = [TVINFO_TVDB, TVINFO_IMDB]
    base_url = 'https://api4.thetvdb.com/v4/'

    def __init__(self, banners=False, posters=False, seasons=False, seasonwides=False, fanart=False, actors=False,
                 *args, **kwargs):
        super(Tvdb_API_V4, self).__init__(banners, posters, seasons, seasonwides, fanart, actors, *args, **kwargs)

    def _get_data(self, endpoint, **kwargs):
        # type: (string_types, Any) -> Any
        is_series_info, retry = endpoint.startswith('/series/'), kwargs.pop('token_retry', 1)
        if retry > 3:
            raise TvdbTokenFailre('Failed to get new token')
        if is_series_info:
            self.show_not_found = False
        try:
            return tvdb_endpoint_get(url='%s%s' % (self.base_url, endpoint), params=kwargs, parse_json=True,
                                     raise_status_code=True, raise_exceptions=True)
        except ConnectionSkipException as e:
            raise e
        except requests.exceptions.HTTPError as e:
            if 401 == e.response.status_code:
                # get new token
                try:
                    if base_request_para['auth'].get_token():
                        retry += 1
                        kwargs['token_retry'] = retry
                        return self._get_data(endpoint, **kwargs)
                except (BaseException, Exception):
                    pass
                raise e
            elif 404 == e.response.status_code:
                if is_series_info:
                    self.show_not_found = True
                self.not_found = True
            elif 404 != e.response.status_code:
                raise TvdbError(ex(e))
        except (BaseException, Exception) as e:
            raise TvdbError(ex(e))

    @staticmethod
    def _convert_person(p):
        # type: (Dict) -> List[Person]
        ch = []
        for c in sorted(filter_iter(lambda a: (3 == a['type'] or 'Actor' == a['peopleType']) and a['name']
                                    and a['seriesId'],
                                    p.get('characters') or []), key=lambda a: (not a['isFeatured'], a['sort'])):
            show = TVInfoShow()
            show.id = clean_data(c['seriesId'])
            show.ids = TVInfoIDs(ids={TVINFO_TVDB: show.id})
            ch.append(Character(id=c['id'], name=clean_data(c['name']), regular=c['isFeatured'],
                                ids={TVINFO_TVDB: c['id']}, image=c.get('image'), show=show))
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
        try:
            p_tvdb_id = try_int(p.get('tvdb_id'), None) or try_int(re.sub(r'^.+-(\d+)$', r'\1', p['id']), None)
        except (BaseException, Exception):
            p_tvdb_id = None

        ids, social_ids, official_site = {TVINFO_TVDB: p_tvdb_id}, {}, None

        if 'remote_ids' in p and isinstance(p['remote_ids'], list):
            for r_id in p['remote_ids']:
                src_name = r_id['sourceName'].lower()
                src_value = clean_data(r_id['id'])
                if not src_value:
                    continue
                if 'imdb' in src_name:
                    try:
                        imdb_id = try_int(('%s' % src_value).replace('nm', ''), None)
                        ids[TVINFO_IMDB] = imdb_id
                    except (BaseException, Exception):
                        pass
                elif 'themoviedb' in src_name:
                    ids[TVINFO_TMDB] = try_int(src_value, None)
                elif 'official website' in src_name:
                    official_site = src_value
                elif 'facebook' in src_name:
                    social_ids[TVINFO_FACEBOOK] = src_value
                elif 'twitter' in src_name:
                    social_ids[TVINFO_TWITTER] = src_value
                elif 'instagram' in src_name:
                    social_ids[TVINFO_INSTAGRAM] = src_value
                elif 'reddit' in src_name:
                    social_ids[TVINFO_REDDIT] = src_value
                elif 'youtube' in src_name:
                    social_ids[TVINFO_YOUTUBE] = src_value

        return [Person(p_id=p_tvdb_id, name=clean_data(p['name']),
                       image=p.get('image') or p.get('image_url'),
                       gender=PersonGenders.tvdb_map.get(p.get('gender'), PersonGenders.unknown),
                       birthdate=birthdate, deathdate=deathdate, birthplace=clean_data(p.get('birthPlace')),
                       akas=set(clean_data(a['name']) for a in p.get('aliases') or []),
                       ids=ids, social_ids=social_ids, homepage=official_site, characters=ch
                       )]

    def get_person(self, p_id, get_show_credits=False, get_images=False, **kwargs):
        # type: (integer_types, bool, bool, Any) -> Optional[Person]
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
        # type: (AnyStr, Dict[integer_types, integer_types]) -> List[Person]
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
                if TVINFO_IMDB == tv_src:
                    cache_id_key = 'p-v4-id-%s-%s' % (TVINFO_IMDB, ids[TVINFO_IMDB])
                    is_none, shows = self._get_cache_entry(cache_id_key)
                    if not self.config.get('cache_search') or (None is shows and not is_none):
                        try:
                            d_m = self._get_data('search', remote_id='nm%07d' % ids.get(TVINFO_IMDB),
                                                 q='nm%07d' % ids.get(TVINFO_IMDB), type='people')
                            self._set_cache_entry(cache_id_key, d_m, expire=self.search_cache_expire)
                        except (BaseException, Exception):
                            d_m = None
                    else:
                        d_m = shows
                    if isinstance(d_m, dict) and all(t in d_m for t in ('data', 'status')) and 'success' == d_m[
                        'status'] \
                            and isinstance(d_m['data'], list):
                        for r in d_m['data']:
                            try:
                                if 'nm%07d' % ids[TVINFO_IMDB] == \
                                        next(filter_iter(lambda b: 'imdb' in b['sourceName'].lower(),
                                                         r.get('remote_ids', []) or []), {}).get('id'):
                                    result.extend(self._convert_person(r))
                                    break
                            except (BaseException, Exception):
                                pass
        if name:
            cache_key_name = 'p-v4-src-text-%s' % name
            is_none, people_objs = self._get_cache_entry(cache_key_name)
            if None is people_objs and not is_none:
                resp = self._get_data('/search', q=name, type='people')
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

    @staticmethod
    def _get_overview(show_data, language='eng'):
        # type: (Dict, AnyStr) -> Optional[AnyStr]
        """
        internal helper to get english overview
        :param show_data:
        :param language:
        """
        if isinstance(show_data.get('translations'), dict) and 'overviewTranslations' in show_data['translations']:
            try:
                trans = next(filter_iter(lambda show: language == show['language'],
                                         show_data['translations']['overviewTranslations']),
                             next(filter_iter(lambda show: 'eng' == show['language'],
                                              show_data['translations']['overviewTranslations']), None)
                             )
                if trans:
                    return clean_data(trans['overview'])
            except (BaseException, Exception):
                pass

    def _get_series_name(self, show_data, language=None):
        # type: (Dict, AnyStr) -> Tuple[Optional[AnyStr], List]
        series_name = clean_data(
            next(filter_iter(lambda l: language and language == l['language'],
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
        resp = self._get_data('/series/%s/extended' % sid)
        if direct_data:
            return resp
        if isinstance(resp, dict) and all(f in resp for f in ('status', 'data')) and 'success' == resp['status'] \
                and isinstance(resp['data'], dict):
            show_data = resp['data']
            series_name, series_aliases = self._get_series_name(show_data, language)
            if not series_name:
                return False
            show_obj = self.shows[sid]  # type: TVInfoShow
            show_obj.banner_loaded = show_obj.poster_loaded = show_obj.fanart_loaded = True
            show_obj.id = show_data['id']
            show_obj.seriesname = series_name
            show_obj.slug = clean_data(show_data.get('slug'))
            show_obj.poster = clean_data(show_data.get('image'))
            show_obj.firstaired = clean_data(show_data.get('firstAired'))
            show_obj.rating = show_data.get('score')
            show_obj.aliases = series_aliases
            show_obj.status = clean_data(show_data['status']['name'])
            show_obj.network_country = clean_data(show_data.get('originalCountry'))
            show_obj.lastupdated = clean_data(show_data.get('lastUpdated'))
            if 'companies' in show_data and isinstance(show_data['companies'], list):
                # filter networks
                networks = sorted([n for n in show_data['companies'] if 1 == n['companyType']['companyTypeId']],
                                  key=lambda a: a['activeDate'] or '0000-00-00')
                if networks:
                    show_obj.networks = [TVInfoNetwork(name=clean_data(n['name']), country=clean_data(n['country']))
                                         for n in networks]
                    show_obj.network = clean_data(networks[-1]['name'])
                    show_obj.network_country = clean_data(networks[-1]['country'])
            show_obj.language = clean_data(show_data.get('originalLanguage'))
            show_obj.runtime = show_data.get('averageRuntime')
            show_obj.airs_time = clean_data(show_data.get('airsTime'))
            show_obj.airs_dayofweek = ', '.join([k.capitalize() for k, v in iteritems(show_data.get('airsDays')) if v])
            show_obj.genre_list = 'genres' in show_data and show_data['genres'] \
                                  and [clean_data(g['name']) for g in show_data['genres']]
            if show_obj.genre_list:
                show_obj.genre = '|'.join(show_obj.genre_list)

            ids, social_ids = {}, {}
            if 'remoteIds' in show_data and isinstance(show_data['remoteIds'], list):
                for r_id in show_data['remoteIds']:
                    src_name = r_id['sourceName'].lower()
                    src_value = clean_data(r_id['id'])
                    if 'imdb' in src_name:
                        try:
                            imdb_id = try_int(src_value.replace('tt', ''), None)
                            ids['imdb'] = imdb_id
                        except (BaseException, Exception):
                            pass
                        show_obj.imdb_id = src_value
                    elif 'themoviedb' in src_name:
                        ids['tmdb'] = try_int(src_value, None)
                    elif 'official website' in src_name:
                        show_obj.official_site = src_value
                    elif 'facebook' in src_name:
                        social_ids['facebook'] = src_value
                    elif 'twitter' in src_name:
                        social_ids['twitter'] = src_value
                    elif 'instagram' in src_name:
                        social_ids['instagram'] = src_value
                    elif 'reddit' in src_name:
                        social_ids['reddit'] = src_value
                    elif 'youtube' in src_name:
                        social_ids['youtube'] = src_value

            show_obj.ids = TVInfoIDs(tvdb=show_data['id'], **ids)
            if social_ids:
                show_obj.social_ids = TVInfoSocialIDs(**social_ids)

            show_obj.overview = self._get_overview(show_data)

            if 'artworks' in show_data and isinstance(show_data['artworks'], list):
                poster = banner = fanart_url = False
                for artwork in sorted(show_data['artworks'], key=lambda a: a['score'], reverse=True):
                    img_type = img_type_map.get(artwork['type'], TVInfoImageType.other)
                    if False is poster and img_type == TVInfoImageType.poster:
                        show_obj.poster, show_obj.poster_thumb, poster = artwork['image'], artwork['thumbnail'], True
                    elif False is banner and img_type == TVInfoImageType.banner:
                        show_obj.banner, show_obj.banner_thumb, banner = artwork['image'], artwork['thumbnail'], True
                    elif False is fanart_url and img_type == TVInfoImageType.fanart:
                        show_obj.fanart, fanart_url = artwork['image'], True
                    show_obj['images'].setdefault(img_type, []).append(
                        TVInfoImage(
                            image_type=img_type,
                            sizes={TVInfoImageSize.original: artwork['image'],
                                   TVInfoImageSize.small: artwork['thumbnail']},
                            img_id=artwork['id'],
                            lang=artwork['language'],
                            rating=artwork['score']
                        )
                    )

            if (actors or self.config['actors_enabled']) and not getattr(self.shows.get(sid), 'actors_loaded', False):
                cast, show_obj.actors_loaded = CastList(), True
                if isinstance(show_data.get('characters'), list):
                    for character in sorted(filter_iter(lambda a: (3 == a['type'] or 'Actor' == a['peopleType'])
                                                        and not a['episodeId'],
                                                        show_data.get('characters')) or [],
                                            key=lambda c: (not c['isFeatured'], c['sort'])):
                        cast[RoleTypes.ActorMain].append(
                            Character(p_id=character['id'], name=clean_data(character['name']),
                                      regular=character['isFeatured'], ids={TVINFO_TVDB: character['id']},
                                      person=[Person(p_id=character['peopleId'],
                                                     name=clean_data(character['personName']),
                                                     ids={TVINFO_TVDB: character['peopleId']})],
                                      image=character['image']))
                show_obj.cast = cast
                show_obj.actors = [
                    {'character': {'id': ch.id,
                                   'name': ch.name,
                                   'url': 'https://www.thetvdb.com/series/%s/people/%s' % (show_data['slug'], ch.id),
                                   'image': ch.image,
                                   },
                     'person': {'id': ch.person and ch.person[0].id,
                                'name': ch.person and ch.person[0].name,
                                'url': ch.person and 'https://www.thetvdb.com/people/%s' % ch.person[0].id,
                                'image': ch.person and ch.person[0].image,
                                'birthday': None,  # not sure about format
                                'deathday': None,  # not sure about format
                                'gender': None,
                                'country': None,
                                },
                     } for ch in cast[RoleTypes.ActorMain]]

            if get_ep_info and not getattr(self.shows.get(sid), 'ep_loaded', False):
                # fetch absolute numbers
                eps_abs_nums = {}
                if any(1 for s in show_data.get('seasons', []) or [] if 'absolute' == s.get('type', {}).get('type')):
                    page = 0
                    while 100 >= page:
                        abs_ep_data = self._get_data('/series/%s/episodes/absolute?page=%d' % (sid, page))
                        page += 1
                        if isinstance(abs_ep_data, dict):
                            valid_data = 'data' in abs_ep_data and isinstance(abs_ep_data['data'], dict) \
                                         and 'episodes' in abs_ep_data['data'] \
                                         and isinstance(abs_ep_data['data']['episodes'], list)
                            links = 'links' in abs_ep_data and isinstance(abs_ep_data['links'], dict) \
                                    and 'next' in abs_ep_data['links']
                            more = (links and isinstance(abs_ep_data['links']['next'], string_types)
                                    and '?page=%d' % page in abs_ep_data['links']['next'])
                            if valid_data:
                                eps_abs_nums.update({_e['id']: _e['number'] for _e in abs_ep_data['data']['episodes']
                                                     if None is _e['seasons'] and _e['number']})
                            if more:
                                continue
                        break

                ep_lang = (language in (show_data.get('overviewTranslations', []) or []) and language) or 'eng'
                page, more_eps, show_obj.ep_loaded = 0, True, True
                while more_eps and 100 >= page:
                    ep_data = self._get_data('/series/%s/episodes/default/%s?page=%d' % (sid, ep_lang, page))
                    page += 1
                    if isinstance(ep_data, dict):
                        valid_data = 'data' in ep_data and isinstance(ep_data['data'], dict) \
                                and 'episodes' in ep_data['data'] and isinstance(ep_data['data']['episodes'], list)
                        full_page = valid_data and 500 <= len(ep_data['data']['episodes'])
                        links = 'links' in ep_data and isinstance(ep_data['links'], dict) \
                                and 'next' in ep_data['links']
                        more = links and isinstance(ep_data['links']['next'], string_types) \
                               and '?page=%d' % page in ep_data['links']['next']
                        alt_page = (full_page and not links)
                        if not alt_page and valid_data:
                            self._set_episodes(show_obj, ep_data, eps_abs_nums)
                        if 'links' in ep_data and isinstance(ep_data['links'], dict) and 'next' in ep_data['links'] \
                                and isinstance(ep_data['links']['next'], string_types):
                            if '?page=%d' % page in ep_data['links']['next']:
                                continue
                    break

            return True

        return False

    @staticmethod
    def _set_episodes(s_ref, ep_data, eps_abs_nums):
        # type: (TVInfoShow, Dict, Dict) -> None
        """
        populates the show with episode objects
        """
        for ep_obj in ep_data['data']['episodes']:
            for _k, _s in (
                    ('seasonnumber', 'seasonNumber'), ('episodenumber', 'number'),
                    ('episodename', 'name'), ('firstaired', 'aired'), ('runtime', 'runtime'),
                    ('seriesid', 'seriesId'), ('id', 'id'), ('filename', 'image'), ('overview', 'overview'),
                    ('absolute_number', 'abs')):
                seas, ep = ep_obj['seasonNumber'], ep_obj['number']
                if 'abs' == _s:
                    value = eps_abs_nums.get(ep_obj['id'])
                else:
                    value = clean_data(ep_obj.get(_s, getattr(empty_ep, _k)))

                if seas not in s_ref:
                    s_ref[seas] = TVInfoSeason(show=s_ref)
                    s_ref[seas].number = seas
                if ep not in s_ref[seas]:
                    s_ref[seas][ep] = TVInfoEpisode(season=s_ref[seas])
                if _k not in ('cast', 'crew'):
                    s_ref[seas][ep][_k] = value
                s_ref[seas][ep].__dict__[_k] = value

    @staticmethod
    def _get_network(show):
        # type: (Dict) -> Optional[AnyStr]
        if show.get('companies'):
            if isinstance(show['companies'][0], dict):
                return clean_data(next(filter_iter(lambda a: 1 == a['companyType']['companyTypeId'], show['companies']),
                                       {}).get('name'))
            else:
                return clean_data(show['companies'][0])

    @staticmethod
    def _get_aliases(show):
        if show.get('aliases') and isinstance(show['aliases'][0], dict):
            return [clean_data(a['name']) for a in show['aliases']]
        return clean_data(show.get('aliases', []))

    def _search_show(self, name=None, ids=None, **kwargs):
        # type: (Union[AnyStr, List[AnyStr]], Dict[integer_types, integer_types], Optional[Any]) -> List[Dict]
        """
        internal search function to find shows, should be overwritten in class
        :param name: name to search for
        :param ids: dict of ids {tvid: prodid} to search for
        """
        def _make_result_dict(show_data):
            tvdb_id = self._get_tvdb_id(show_data)
            series_name, series_aliases = self._get_series_name(show_data)
            if not series_name:
                return []

            return [{'seriesname': series_name, 'id': tvdb_id,
                     'firstaired': clean_data(show_data.get('year') or show_data.get('firstAired')),
                     'network': self._get_network(show_data),
                     'overview': clean_data(show_data.get('overview')) or self._get_overview(show_data),
                     'poster': show_data.get('image_url') or show_data.get('image'),
                     'status': clean_data(isinstance(show_data['status'], dict) and
                                          show_data['status']['name'] or show_data['status']),
                     'language': clean_data(show_data.get('primary_language')), 'country':
                         clean_data(show_data.get('country')),
                     'aliases': series_aliases, 'slug': clean_data(show_data.get('slug')),
                     'ids': TVInfoIDs(tvdb=tvdb_id)}]
        results = []
        if ids:
            if ids.get(TVINFO_TVDB):
                cache_id_key = 's-v4-id-%s-%s' % (TVINFO_TVDB, ids[TVINFO_TVDB])
                is_none, shows = self._get_cache_entry(cache_id_key)
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
                                             q='tt%07d' % ids.get(TVINFO_IMDB), type='series')
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
                                    next(filter_iter(lambda b: 'imdb' in b['sourceName'].lower(),
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
                                             q='%s' % ids.get(TVINFO_TMDB), type='series')
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
                                    next(filter_iter(lambda b: 'themoviedb' in b['sourceName'].lower(),
                                                     r.get('remote_ids', []) or []), {}).get('id'):
                                results.extend(_make_result_dict(r))
                                break
                        except (BaseException, Exception):
                            pass

            if ids.get(TVINFO_TVDB_SLUG):
                cache_id_key = 's-id-%s-%s' % (TVINFO_TVDB, ids[TVINFO_TVDB_SLUG])
                is_none, shows = self._get_cache_entry(cache_id_key)
                if not self.config.get('cache_search') or (None is shows and not is_none):
                    try:
                        d_m = self._get_data('search', q=ids.get(TVINFO_TVDB_SLUG).replace('-', ' '), type='series')
                        self._set_cache_entry(cache_id_key, d_m, expire=self.search_cache_expire)
                    except (BaseException, Exception):
                        d_m = None
                else:
                    d_m = shows
                if d_m and isinstance(d_m, dict) and 'data' in d_m and 'success' == d_m.get('status') \
                        and isinstance(d_m['data'], list):
                    for r in d_m['data']:
                        if ids.get(TVINFO_TVDB_SLUG) == r['slug']:
                            results.extend(_make_result_dict(r))
                            break

        if name:
            for n in ([name], name)[isinstance(name, list)]:
                cache_name_key = 's-v4-name-%s' % n
                is_none, shows = self._get_cache_entry(cache_name_key)
                if not self.config.get('cache_search') or (None is shows and not is_none):
                    resp = self._get_data('search', q=n, type='series')
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
            self._supported_languages = [{'id': clean_data(a['id']), 'name': clean_data(a['name']),
                                          'nativeName': clean_data(a['nativeName']),
                                          'shortCode': clean_data(a['shortCode']),
                                          'sg_lang': self.reverse_map_languages.get(a['id'], a['id'])}
                                         for a in langs['data']]
        else:
            self._supported_languages = []
