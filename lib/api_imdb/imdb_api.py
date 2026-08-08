# author:Prinz23
# project:imdb_api

__author__ = 'Prinz23'
__version__ = '1.0'
__api_version__ = '1.0.0'

import datetime
import hashlib
import logging
import re
import requests
import time
import traceback

from .imdb_exceptions import *
# from bs4_parser import BS4Parser
from exceptions_helper import ex
from lib import imdbpie, imdbgql
from lib.dateutil.parser import parser
# from lib.tvinfo_base.exceptions import BaseTVinfoShownotfound
from lib.tvinfo_base import (
    TVInfoCharacter, TVInfoPerson, PersonGenders, TVINFO_IMDB,
    # TVINFO_FACEBOOK, TVINFO_INSTAGRAM, TVINFO_TMDB, TVINFO_TRAKT,
    # TVINFO_TVDB, TVINFO_TVRAGE, TVINFO_X, TVINFO_WIKIPEDIA,
    TVInfoBase, TVInfoIDs, TVInfoShow, TVInfoSeason, TVInfoEpisode, TVInfoImage, TVInfoImageType, TVInfoImageSize,
    BaseTVinfoError, CastList, RoleTypes)
from sg_helpers import clean_data, enforce_type, get_url, try_int, ConnectionSkipException
from json_helper import json_loads, json_dumps, is_orjson, JSONEncoder, JSON_INDENT

from six import iteritems
from six.moves import http_client as httplib
from six.moves.urllib.parse import urlencode, urljoin, quote, unquote


# noinspection PyUnreachableCode
if False:
    from typing import Any, AnyStr, Callable, Dict, List, Optional, Tuple, Union
    u_date = Union[int, str, datetime.date, datetime.date]
    from six import integer_types

tz_p = parser()
log = logging.getLogger('imdb.api')
log.addHandler(logging.NullHandler())
id_regex = re.compile(r'(?:tt|nm)(\d{7,10})', flags=re.I)
img_uri_regex = re.compile(r'(?im)(.*V1_?)(\..*?)$', flags=re.I)

if is_orjson:
    from json_helper import OPT_SORT_KEYS
    json_enc_kw = {'option': OPT_SORT_KEYS}

else:

    class PythonObjectEncoder(JSONEncoder):
        def default(self, obj):
            if isinstance(obj, set):
                return list(obj)
            elif isinstance(obj, datetime.datetime):
                return obj.strftime('%Y-%m-%d %H:%M %z')
            elif isinstance(obj, datetime.date):
                return obj.strftime('%Y-%m-%d')
            return JSONEncoder.default(self, obj)

    json_enc_kw = {'cls': PythonObjectEncoder, 'indent': JSON_INDENT, 'sort_keys': True}


def _get_response_imdb(payload):
    imdbgql.graphql.compact_payload(payload)
    try_count = 1
    while 3 >= try_count:
        try:
            return get_url(imdbgql.graphql.BASE_URL, headers=imdbgql.graphql.HEADERS, post_json=payload, json=True,
                           raise_exceptions=True, raise_skip_exception=True)
        except ConnectionSkipException:
            return
        except requests.exceptions.ConnectionError:
            pass
        except (BaseException, Exception):
            return

        try_count += 1
        if 3 >= try_count:
            logging.debug('Retrying imdb api call')
            time.sleep(30)


def _get_imdb(self, url, query=None, params=None):
    headers = {'Accept-Language': self.locale}
    if params:
        full_url = '{0}?{1}'.format(url, urlencode(params))
    else:
        full_url = url
    headers.update(self.get_auth_headers(full_url))
    resp = get_url(url, headers=headers, params=params, return_response=True)

    if not resp.ok:
        if resp.status_code == httplib.NOT_FOUND:
            raise LookupError('Resource {0} not found'.format(url))
        else:
            msg = '{0} {1}'.format(resp.status_code, resp.text)
            raise imdbpie.ImdbAPIError(msg)
    resp_data = resp.content.decode('utf-8')
    try:
        resp_dict = json_loads(resp_data)
    except ValueError:
        resp_dict = self._parse_dirty_json(
            data=resp_data, query=query
        )

    if resp_dict.get('error'):
        return None
    return resp_dict


imdbpie.Imdb._get = _get_imdb
imdbgql.graphql._get_response = _get_response_imdb


class IMDbIndexer(TVInfoBase):
    # supported_id_searches = [TVINFO_IMDB]
    supported_person_id_searches = [TVINFO_IMDB]
    supported_id_searches = [TVINFO_IMDB]

    # noinspection PyUnusedLocal
    # noinspection PyDefaultArgument
    def __init__(self, *args, **kwargs):
        super(IMDbIndexer, self).__init__(*args, **kwargs)

    def search(self, series):
        # type: (AnyStr) -> List
        """This searches for the series name
        and returns the result list
        """
        result = []
        cache_name_key = 's-title-%s' % series
        is_none, shows = self._get_cache_entry(cache_name_key)
        if not self.config.get('cache_search') or (None is shows and not is_none):
            try:
                result = imdbpie.Imdb().search_for_title(series)
            except (BaseException, Exception):
                pass
            self._set_cache_entry(cache_name_key, result, expire=self.search_cache_expire)
        else:
            result = shows
        return result

    def _search_show(self, name=None, ids=None, **kwargs):
        # type: (AnyStr, Dict[integer_types, integer_types], Optional[Any]) -> List[TVInfoShow]
        """This searches IMDB for the series name,
        """
        def _make_result_dict(s):
            imdb_id = try_int(re.search(r'tt(\d+)', s.get('id') or s.get('imdb_id')).group(1), None)
            ti_show = TVInfoShow()
            ti_show.seriesname, ti_show.id, ti_show.firstaired, ti_show.genre_list, ti_show.overview, \
                ti_show.poster, ti_show.ids = \
                clean_data(s['title']), imdb_id, s.get('releaseDetails', {}).get('date') or s.get('year'), \
                s.get('genres'), enforce_type(clean_data(s.get('plot', {}).get('outline', {}).get('text')), str, ''), \
                s.get('image') and s['image'].get('url'), TVInfoIDs(imdb=imdb_id)
            return ti_show

        results = []
        if ids:
            for t, p in iteritems(ids):
                if t in self.supported_id_searches:
                    if t == TVINFO_IMDB:
                        cache_id_key = 's-id-%s-%s' % (TVINFO_IMDB, p)
                        is_none, shows = self._get_cache_entry(cache_id_key)
                        if not self.config.get('cache_search') or (None is shows and not is_none):
                            try:
                                show = imdbpie.Imdb().get_title_auxiliary('tt%07d' % p)
                            except (BaseException, Exception):
                                continue
                            self._set_cache_entry(cache_id_key, show, expire=self.search_cache_expire)
                        else:
                            show = shows
                        if show:
                            results.extend([_make_result_dict(show)])
        if name:
            for n in ([name], name)[isinstance(name, list)]:
                try:
                    shows = self.search(n)
                    results.extend([_make_result_dict(s) for s in shows])
                except (BaseException, Exception) as e:
                    log.debug('Error searching for show: %s' % ex(e))
        seen = set()
        results = [seen.add(r.id) or r for r in results if r.id not in seen]
        return results

    @staticmethod
    def _convert_person(person_obj, filmography=None, bio=None):
        if isinstance(person_obj, dict) and 'imdb_id' in person_obj:
            imdb_id = try_int(re.search(r'(\d+)', person_obj['imdb_id']).group(1))
            return TVInfoPerson(p_id=imdb_id, name=person_obj['name'], ids=TVInfoIDs(ids={TVINFO_IMDB: imdb_id}))
        characters = []
        for known_for in (filmography and filmography['filmography']) or []:
            if known_for['titleType'] not in ('tvSeries', 'tvMiniSeries'):
                continue
            for character in known_for.get('characters') or ['unknown name']:
                ti_show = TVInfoShow()
                ti_show.id = try_int(re.search(r'(\d+)', known_for.get('id')).group(1))
                ti_show.ids.imdb = ti_show.id
                ti_show.seriesname = known_for.get('title')
                ti_show.firstaired = known_for.get('year')
                characters.append(
                    TVInfoCharacter(name=character, ti_show=ti_show, start_year=known_for.get('startYear'),
                                    end_year=known_for.get('endYear'))
                )
        try:
            birthdate = person_obj['base']['birthDate'] and tz_p.parse(person_obj['base']['birthDate']).date()
        except (BaseException, Exception):
            birthdate = None
        try:
            deathdate = person_obj['base']['deathDate'] and tz_p.parse(person_obj['base']['deathDate']).date()
        except (BaseException, Exception):
            deathdate = None
        imdb_id = try_int(re.search(r'(\d+)', person_obj['id']).group(1))
        return TVInfoPerson(
            p_id=imdb_id, ids=TVInfoIDs(ids={TVINFO_IMDB: imdb_id}), characters=characters,
            name=person_obj['base'].get('name'), real_name=person_obj['base'].get('realName'),
            nicknames=set((person_obj['base'].get('nicknames') and person_obj['base'].get('nicknames')) or []),
            akas=set((person_obj['base'].get('akas') and person_obj['base'].get('akas')) or []),
            bio=bio, gender=PersonGenders.imdb_map.get(person_obj['base'].get('gender'), PersonGenders.unknown),
            image=person_obj['base'].get('image', {}).get('url'),
            birthdate=birthdate, birthplace=person_obj['base'].get('birthPlace'),
            deathdate=deathdate, deathplace=person_obj['base'].get('deathPlace'),
            height=person_obj['base'].get('heightCentimeters')
        )

    def _search_person(self, name=None, ids=None):
        # type: (AnyStr, Dict[integer_types, integer_types]) -> List[TVInfoPerson]
        """
        search for person by name
        :param name: name to search for
        :param ids: dict of ids to search
        :return: list of found person's
        """
        results, ids = [], ids or {}
        for tv_src in self.supported_person_id_searches:
            if tv_src in ids:
                if TVINFO_IMDB == tv_src:
                    try:
                        p = self.get_person(ids[tv_src])
                    except (BaseException, Exception):
                        p = None
                    if p:
                        results.append(p)
        if name:
            cache_name_key = 'p-name-%s' % name
            is_none, ps = self._get_cache_entry(cache_name_key)
            if None is ps and not is_none:
                try:
                    ps = imdbpie.Imdb().search_for_name(name)
                except (BaseException, Exception):
                    ps = None
                self._set_cache_entry(cache_name_key, ps)
            if ps:
                for cp in ps:
                    if not any(1 for c in results if cp['imdb_id'] == 'nm%07d' % c.id):
                        results.append(self._convert_person(cp))
        return results

    @staticmethod
    def _get_bio(p_id):
        try:
            return imdbpie.Imdb().get_name_biography(f'nm{p_id:07d}')
            # bio = get_url('https://www.imdb.com/name/nm%07d/bio' % p_id, headers={'Accept-Language': 'en'})
            # bio = get_url(f'https://realimdb.netlify.app/api/',
            #               post_json={"query":"query GetPersonDetails($id: ID!) {\nname(id: $id) {\nid\nnameText "
            #                                  "{\ntext\n}\nprimaryImage {\nurl\nwidth\nheight\n}\nprimaryProfessions "
            #                                  "{\ncategory {\ntext\nid\n}\n}\nknownFor(first: 10) {\nedges {\nnode "
            #                                  "{\ntitle {\nid\ntitleText {\ntext\n}\nreleaseYear {\nyear\n}\ntitleType "
            #                                  "{\ntext\n}\nratingsSummary {\naggregateRating\nvoteCount\n}\nprimaryImage"
            #                                  " {\nurl\n}\n}\n}\n}\n}\nbirthDate {\ndateComponents "
            #                                  "{\nday\nmonth\nyear\n}\n}\ndeathDate {\ndateComponents "
            #                                  "{\nday\nmonth\nyear\n}\n}\nbirthLocation {\ntext\n}\nmeterRanking "
            #                                  "{\ncurrentRank\nrankChange {\nchangeDirection\ndifference\n}\n}\nheight "
            #                                  "{\ndisplayableProperty {\nvalue {\nplainText\n}\n}\n}\nbio "
            #                                  "{\ntext {\nplainText\n}\n}\nakas(first: 5) {\nedges {\nnode "
            #                                  "{\ntext\n}\n}\n}\n}\n}","operationName":"GetPersonDetails",
            #                          "variables":{"id": f"nm{p_id:07d}"}},
            #               headers={'Accept-Language': 'en'}, json=True)
            # if not bio:
            #     return
            # return bio['data']['name']['bio']['text']['plainText']
            # with BS4Parser(bio) as bio_item:
            #     bv = bio_item.find('div', attrs={'data-testid': re.compile('mini_bio$')}, recursive=True)
            #     for a in bv.findAll('a'):
            #         a.replaceWithChildren()
            #     for b in bv.findAll('br'):
            #         b.replaceWith('\n')
            #     return bv.get_text().strip()
        except (BaseException, Exception):
            return

    def get_person(self, p_id, get_show_credits=False, get_images=False, **kwargs):
        # type: (integer_types, bool, bool, Any) -> Optional[TVInfoPerson]
        if not p_id:
            return
        cache_main_key, cache_bio_key, cache_credits_key = 'p-main-%s' % p_id, 'p-bio-%s' % p_id, 'p-credits-%s' % p_id
        is_none, p = self._get_cache_entry(cache_main_key)
        if None is p and not is_none:
            try:
                p = imdbpie.Imdb().get_name(imdb_id='nm%07d' % p_id)
            except (BaseException, Exception):
                p = None
            self._set_cache_entry(cache_main_key, p)
        is_none, bio = self._get_cache_entry(cache_bio_key)
        if None is bio and not is_none:
            bio = self._get_bio(p_id)
            self._set_cache_entry(cache_bio_key, bio)
        fg = None
        if get_show_credits:
            is_none, fg = self._get_cache_entry(cache_credits_key)
            if None is fg and not is_none:
                try:
                    fg = imdbpie.Imdb().get_name_filmography(imdb_id='nm%07d' % p_id)
                except (BaseException, Exception):
                    fg = None
                self._set_cache_entry(cache_credits_key, fg)
        if p:
            return self._convert_person(p, filmography=fg, bio=bio)

    def imdb_image_resize(self, img_uri, height, width, target_height=450):
        # type: (str, int, int, int) -> str
        if img_uri and 'tv_series.gif' not in img_uri and 'nopicture' not in img_uri:
            scale = (lambda low1, high1: int((float(target_height) / high1) * low1))
            dims = [width, height]
            s = [scale(x, int(max(dims))) for x in dims]
            img_uri = img_uri_regex.sub(r'\1UX%s_CR0,0,%s,%s_AL_\2' % (s[0], s[0], s[1]), img_uri)
        return img_uri

    def _parse_graphql_data(self, show_data):
        t_id = int(id_regex.search(show_data['id']).group(1))
        title = None
        akas = []
        if _t := show_data.get('originalTitleText'):
            title = clean_data(_t['text'])
        if not title:
            title = clean_data(show_data.get('originalTitleText', {}).get('text'))
        elif title != (_t := clean_data(show_data.get('originalTitleText', {}).get('text'))):
            akas = _t
        runtime = None
        if rt := show_data.get('runtime'):
            runtime = rt['seconds'] // 60
        status = None
        if _ps := show_data.get('productionStatus'):
            status = _ps['currentProductionStage']['text']
        genres = None
        if _g := show_data.get('genres') or show_data.get('titleGenres', {}):
            genres = [_i.get('text') or _i.get('genre', {}).get('text') for _i in _g['genres']]
        spoken_languages = []
        if _l := show_data.get('spokenLanguages'):
            spoken_languages = [_i['id'] for _i in _l['spokenLanguages']]
        vote_count = None
        vote_avg = None
        if _v := show_data.get('ratingsSummary'):
            vote_count = _v['voteCount']
            vote_avg = _v['aggregateRating']
        certification = None
        if _c := show_data.get('certificate'):
            certification = _c['rating']
        origin_countries = []
        if _c := show_data.get('countriesOfOrigin'):
            origin_countries = [_i['id'] for _i in _c['countries']]
        image = None
        images = {}
        img_thumb = None
        if _i := show_data.get('primaryImage'):
            image = _i['url']
            img_height = show_data['primaryImage']['height']
            img_width = show_data['primaryImage']['width']
            img_thumb = self.imdb_image_resize(image, img_height, img_width, target_height=450)
            images.setdefault(TVInfoImageType.poster, []).append(
                TVInfoImage(
                    image_type=TVInfoImageType.poster,
                    sizes={
                        TVInfoImageSize.original: image,
                        TVInfoImageSize.medium: self.imdb_image_resize(image, img_height, img_width, target_height=900),
                        TVInfoImageSize.small: img_thumb
                    },
                    main_image=True,
                    height=img_height,
                    width=img_width,
                    aspect_ratio=img_width / img_height,
                    description=show_data['primaryImage']['caption']['plainText']
                )
            )
        plot = ''
        if (_p := show_data.get('plot')) and _p.get('plotText'):
            plot = enforce_type(_p['plotText']['plainText'], str, '')
        release_date = rel_year = None
        if (_d := show_data.get('releaseDate')) and all(_d.get(_k) for _k in ('year', 'month', 'day')):
            release_date = f'{_d["year"]:04d}-{_d["month"]:02d}-{_d["day"]:02d}'
            rel_year = _d["year"]
        if (_y := show_data['releaseYear']) and (None is release_date or _y['year'] < rel_year):
            release_date = str(_y['year'])
        return t_id, title, akas, runtime, status, genres, spoken_languages, vote_count, vote_avg, certification, \
            origin_countries, image, plot, release_date, images, img_thumb

    def _convert_graphql_show(self, full_data):
        # type: (dict) -> TVInfoShow
        try:
            if 'tvepisode' == full_data['titleType']['id'].lower():
                show_data = full_data['series']['series']
                ep_data = [full_data]
            else:
                show_data = full_data
                ep_data = []
            t_id, title, akas, runtime, status, genres, spoken_languages, vote_count, vote_avg, certification, \
                origin_countries, image, plot, release_date, images, img_thumb = self._parse_graphql_data(show_data)
            ti_show = TVInfoShow()
            ti_show.seriesname, ti_show.id, ti_show.imdb_id, ti_show.firstaired, ti_show.overview, ti_show.runtime, \
                ti_show.status, ti_show.genre_list, ti_show.spoken_languages, \
                ti_show.vote_count, \
                ti_show.vote_average, ti_show.rating, ti_show.contentrating, ti_show.origin_countries, \
                ti_show.poster, ti_show.aliases, ti_show.images, ti_show.poster_thumb = \
                title, t_id, f'tt{t_id:07d}', release_date, plot, runtime, status, genres, spoken_languages, \
                vote_count, vote_avg, vote_avg, certification, origin_countries, image, akas, images, img_thumb
            ti_show.ids = TVInfoIDs(ids={TVINFO_IMDB: t_id})
            ti_show.genre = '|'.join(ti_show.genre_list or [])
            for _ep in ep_data:
                t_id, title, akas, runtime, status, genres, spoken_languages, vote_count, vote_avg, certification, \
                    origin_countries, image, plot, release_date, images, img_thumb = self._parse_graphql_data(_ep)
                ep_nb = ('episodeNumber' in _ep['series'] and _ep['series']['episodeNumber']['episodeNumber']) \
                        or ('displayableEpisodeNumber' in _ep['series'] and
                            int(_ep['series']['displayableEpisodeNumber']['episodeNumber']['text']))
                season_nb = ('episodeNumber' in _ep['series'] and _ep['series']['episodeNumber']['seasonNumber']) \
                            or ('displayableEpisodeNumber' in _ep['series'] and
                                int(_ep['series']['displayableEpisodeNumber']['displayableSeason']['text']))
                ti_ep = TVInfoEpisode()
                ti_ep.episodename, ti_ep.id, ti_ep.imdb_id, ti_ep.firstaired, ti_ep.overview, ti_ep.runtime, \
                    ti_ep.status, ti_ep.genre_list, ti_ep.spoken_languages, \
                    ti_ep.vote_count, \
                    ti_ep.vote_average, ti_ep.rating, ti_ep.contentrating, ti_ep.origin_countries, \
                    ti_ep.poster, ti_ep.filename, ti_ep.aliases, ti_ep.episodenumber, ti_ep.seasonnumber, ti_ep.show, \
                    ti_ep.images = \
                    title, t_id, f'tt{t_id:07d}', release_date, plot, runtime, status, genres, spoken_languages, \
                        vote_count, vote_avg, vote_avg, certification, origin_countries, image, image, akas, ep_nb, \
                        season_nb, ti_show, images
                if ti_ep.seasonnumber not in ti_show:
                    season = TVInfoSeason(show=ti_show, number=ti_ep.seasonnumber)
                    ti_show[ti_ep.seasonnumber] = season
                    ti_ep.season = season
                ti_show[season_nb][ep_nb] = ti_ep
            return ti_show
        except (BaseException, Exception) as e:
            log.error(f'Error creating TVInfoShow: {e}')
            log.debug(traceback.format_exc())

    def _get_graphql_data(self, endpoint, *args, **kwargs):
        # type:(Callable, ..., ...) -> Any
        """
        helper method to cache graphql responses

        :param endpoint: endpoint to call
        :param args: args for endpoint
        :param kwargs: kwargs for endpoint
        :return: data from cache or endpoint
        """
        data = [endpoint.__name__, args, kwargs]
        data_md5 = hashlib.md5(json_dumps(data, **json_enc_kw).encode('utf-8')).hexdigest()
        cache_graphql_key = f'graphql-{data_md5}'
        is_none, d = self._get_cache_entry(cache_graphql_key)
        if None is d and not is_none:
            if any(_ep in endpoint.__name__.lower() for _ep in ('watchlist', 'get_favorite_people')):
                expire = 60 * 15
            else:
                expire = 60 * 60 * 18
            try:
                d = endpoint(*args, **kwargs)
            except imdbgql.IMDbGQLPersonNotFound:
                raise IMDbPersonNotFound(f'Person id {kwargs.get("name_id", "")} not found')
            except (BaseException, Exception):
                d = None
            if isinstance(d, tuple) and d[0]:
                self._set_cache_entry(cache_graphql_key, d, expire=expire)
        return d

    def _check_params(self, start_date, end_date):
        if not isinstance(start_date, (int, type(None), str, datetime.date, datetime.datetime)):
            msg = f'start_date has to be (int, str, datetime, date, None) and is {type(start_date)}'
            log.error(msg)
            raise BaseTVinfoError(msg)
        if not isinstance(end_date, (int, type(None), str, datetime.date, datetime.datetime)):
            msg = f'end_date has to be (int, str, datetime, date, None) and is {type(end_date)}'
            log.error(msg)
            raise BaseTVinfoError(msg)

    def _convert_graphql_person(self, p_data, show_data, ep_list=None):
        # type: (dict, dict, dict) -> TVInfoPerson
        p_naem = p_data['nameText']['text']
        p_id = int(id_regex.search(p_data['id']).group(1))
        if p_data['primaryImage']:
            image = p_data['primaryImage']['url']
            img_height = p_data['primaryImage']['height']
            img_width = p_data['primaryImage']['width']
            thumb_url = self.imdb_image_resize(image, img_height, img_width, 450)
            images = [
                TVInfoImage(
                    image_type=TVInfoImageType.person_poster,
                    sizes={
                        TVInfoImageSize.original: image,
                        TVInfoImageSize.medium: self.imdb_image_resize(image, img_height, img_width, 900),
                        TVInfoImageSize.small: thumb_url
                    }
                )
            ]
        else:
            image = None
            thumb_url = None
            images = []
        bio = (p_data['bio'] and p_data['bio']['text']['plainText']) or None
        if p_data.get('birthDate') and (bd := p_data['birthDate'].get('dateComponents')) \
                and all(bd.get(_f) for _f in ('year', 'month', 'day')):
            birthdate = datetime.date(bd['year'], bd['month'], bd['day'])
        else:
            birthdate = None
        if p_data.get('deathDate') and (bd := p_data['deathDate'].get('dateComponents')) \
                and all(bd.get(_f) for _f in ('year', 'month', 'day')):
            deathdate = datetime.date(bd['year'], bd['month'], bd['day'])
        else:
            deathdate = None
        if p_data.get('birthLocation'):
            birthplace = p_data['birthLocation']['text']
        else:
            birthplace = None
        ids = TVInfoIDs(imdb=p_id)
        if p_data.get('height'):
            value = p_data['height']['measurement']['value']
            unit = p_data['height']['measurement']['unit']
            if 'centimeter' == (unit or '').lower():
                height = f'{value / 100:.2f} m'
            else:
                height = p_data['height']['displayableProperty']['value']['plainText']
        else:
            height = None
        akas = set()
        if p_data.get('akas'):
            akas = {_a['node']['text'] for _a in p_data['akas']['edges']}
        person_obj = TVInfoPerson(
            p_id=p_id, name=p_naem, image=image, thumb_url=thumb_url, images=images, bio=bio, birthdate=birthdate,
            deathdate=deathdate, ids=ids, birthplace=birthplace, height=height, akas=akas)
        ep_data_dict = {}
        if isinstance(ep_list, list):
            ep_list =  [e['episodeCredits']['edges'] for e in ep_list]
            for s in ep_list:
                for e in s:
                    ep_data_dict.setdefault(e['node']['title']['series']['series']['id'], []).append(e['node'])

        for _s in show_data:
            show_obj = self._convert_graphql_show(_s['title'])  # type: TVInfoShow
            cast = CastList()
            if _s:
                char_ep = {}
                for _ep in ep_data_dict.get(show_obj.imdb_id) or []:
                    for ep_c in _ep['creditedRoles']['edges']:
                        try:
                            _ep_num = _ep['title']['series']['episodeNumber']
                            char_ep.setdefault(ep_c['node']['text'], []).append(
                                {'ep_id': _ep['title']['id'],
                                 # 'series_id': _ep['title']['series']['series']['id'],
                                 'title': _ep['title']['titleText']['text'],
                                 'releaseDate': _ep['title']['releaseDate'],
                                 'episode': (None is not _ep_num and _ep_num['episodeNumber']) or None,
                                 'season': (None is not _ep_num and _ep_num['seasonNumber']) or None})
                        except (BaseException, Exception) as e:
                            log.error(f'Error parsing character ep list: {ex(e)}')
                            log.debug(traceback.format_exc())

                for _r in _s['creditedRoles']['edges']:
                    _cd = _r['node']
                    # {'ADDITIONAL_APPEARANCES_TRAIT', 'CAST_TRAIT', 'CREW_TRAIT', 'MAJOR_CREATIVE_INPUT_TRAIT',
                    # 'SELF_TRAIT', 'UNCATEGORIZED_TRAIT'}
                    if any(_t in ('CAST_TRAIT', 'SELF_TRAIT') for _t in _r['node']['category']['traits']):
                        c_name = _cd['text']
                        start_year = end_year = None
                        if _s['episodeCredits']['yearRange']:
                            start_year = _s['episodeCredits']['yearRange']['year']
                            end_year = _s['episodeCredits']['yearRange']['endYear']
                        for _c in _r['node']['characters']['edges']:
                            c_name = _c['node']['name']
                            ep_count = _s['episodeCredits']['total']
                            char_ep_list = char_ep.get(c_name) or\
                                           next((v for k, v in char_ep.items() if c_name in k), None) or []
                            ep_count = (None, len(char_ep_list))[ep_count <= 250] or ep_count
                            play_self = any('SELF_TRAIT' == _t for _t in _r['node']['category']['traits'])
                            archive_footage = (_r['node'] and 'attributes' in _r['node'] and _r['node']['attributes']
                                               and any('archive footage' in _a['text']
                                                       for _a in _r['node']['attributes'])) or False
                            char_obj = TVInfoCharacter(
                                name=c_name, ti_show=show_obj, episode_count=ep_count or None, person=[person_obj],
                                start_year=start_year, end_year=end_year, plays_self=play_self,
                                episode_list=char_ep_list, incl_archive_footage=archive_footage)
                            cast[RoleTypes.ActorMain].append(char_obj)
                            person_obj.characters.append(char_obj)
            show_obj.cast = cast
            show_obj.actors = [
                {'character': {'id': ch.id,
                               'name': ch.name,
                               'image': ch.image,
                               },
                 'person': {'id': ch.person and ch.person[0].id,
                            'name': ch.person and ch.person[0].name,
                            'url': ch.person and 'https://www.themoviedb.org/person/%s' % ch.person[0].id,
                            'image': ch.person and ch.person[0].image,
                            'birthday': None,  # not sure about format
                            'deathday': None,  # not sure about format
                            'gender': None,
                            'country': None,
                            },
                 } for ch in cast[RoleTypes.ActorMain]]
        return person_obj

    def get_person_tvshow_filmography(self, p_id, get_ep_list=False):
        # type: (str, bool) -> TVInfoPerson
        """
        get all tv shows with actor/actress credit

        :param p_id:
        :param get_ep_list: get ep list
        :return: List of TVInfoShow
        """
        if isinstance(p_id, int):
            p_id = f'nm{p_id:07d}'
        elif isinstance(p_id, str) and not p_id.startswith('nm'):
            raise BaseTVinfoError(f'Invalid name id: {p_id}')
        result = None
        try:
            imdb_obj = imdbgql.IMDb()
            res = self._get_graphql_data(
                imdb_obj.get_full_filmography,
                name_id=p_id, type_categories=['tv'], tv_limit=9999, credits_limit=9999)
            tv_shows = [_s for _s in res[1]
                        if _s['title']['titleType']['id'] in ["tvSeries", "tvMiniSeries", "tvEpisode"]]

            ep_data = None
            if get_ep_list:
                ep_data = self._get_graphql_data(
                    imdb_obj.get_person_episodes,
                    name_id=p_id, tv_limit=9999, credits_limit=9999, episode_limit=9999, credited_roles=9999)
                if isinstance(ep_data, tuple):
                    ep_data = ep_data[1]

            result = self._convert_graphql_person(res[0], tv_shows, ep_data)
        except IMDbPersonNotFound as e:
            raise e
        except (BaseException, Exception) as e:
            log.error(f'Person full filmography error: {e}')
            log.debug(traceback.format_exc())
        return result

    def get_popular(self, result_count=100, start_date=None, end_date=None, after_cursor=None, **kwargs):
        # type: (int, u_date, u_date, str, ...) -> Tuple[List[TVInfoShow],str,int]
        """
        get all popular shows

        :param result_count: max results to return
        :param start_date: start year or date: 2030}-12-31 or datetime.date object
        :param end_date: end year or date 2030}-12-31 or datetime.date object
        :param after_cursor: for pagination: end_cursor of previous call
        :return: Tuple of List of TVInfoShow, end_cursor, total count of results
        """
        self._check_params(start_date, end_date)
        res = ([], None, 0)
        result = []
        try:
            imdb_obj = imdbgql.IMDb()
            res = self._get_graphql_data(
                imdb_obj.search_by_filters,
                languages='en', limit=result_count, title_type=["tvSeries", "tvMiniSeries"], min_date=start_date,
                max_date=end_date, sort_by='POPULARITY', sort_order='ASC', after_cursor=after_cursor)
            for _s_d in res[0]:
                ti_show = self._convert_graphql_show(_s_d)
                if ti_show:
                    result.append(ti_show)
        except (BaseException, Exception) as e:
            log.error(f'Trending error: {e}')
            res = ([], None, 0)
        return result, res[1], res[2]

    def get_top_rated(self, result_count=100, start_date=None, end_date=None, score='USER', after_cursor=None,
                      **kwargs):
        # type: (int, u_date, u_date, str, str, ...) -> Tuple[List[TVInfoShow],str,int]
        """
        get top-rated shows

        :param result_count: how many results to return (optional)
        :param start_date: start year or date: 2030}-12-31 or datetime.date object
        :param end_date: end year or date 2030}-12-31 or datetime.date object
        :param score: rating score source: METACRITIC, USER (default)
        :param after_cursor: for pagination: end_cursor of previous call
        :return: Tuple of List of TVInfoShow, end_cursor, total count of results
        """
        self._check_params(start_date, end_date)
        score_sources = {'METACRITIC': 'METACRITIC_SCORE', 'USER': 'USER_RATING'}
        if score not in score_sources:
            msg = f'score has invalid value of: {score}, available values: {list(score_sources.keys())}'
            log.error(msg)
            raise BaseTVinfoError(msg)

        res = ([], None, 0)
        result = []
        try:
            imdb_obj = imdbgql.IMDb()
            res = self._get_graphql_data(
                imdb_obj.search_by_filters,
                languages='en', limit=result_count, title_type=["tvSeries", "tvMiniSeries"], min_date=start_date,
                max_date=end_date, sort_by=score_sources[score], sort_order='DESC', after_cursor=after_cursor)
            for _s_d in res[0]:
                ti_show = self._convert_graphql_show(_s_d)
                if ti_show:
                    result.append(ti_show)
        except (BaseException, Exception) as e:
            log.error(f'Trending error: {e}')
            res = ([], None, 0)
        return result, res[1], res[2]

    def _get_new_shows(self, result_count=100, start_date=None, end_date=None, episodicConstraint=None,
                       seasonsConstraint=None, seasonsExlcudeConstraint=None, after_cursor=None, **kwargs):
        # type: (int, u_date, u_date, Union[int,str], Union[int,str], Union[int,str], str, ...) -> Tuple[List[TVInfoShow], str, int]
        """
        internal get new shows

        :param result_count: how many results to return (opitnal)
        :param start_date: start year or date: 2030}-12-31 or datetime.date object
        :param end_date: end year or date 2030}-12-31 or datetime.date object
        :param episodicConstraint: only include listed episode numbers
        :param seasonsConstraint: only include listed season numbers
        :param seasonsExlcudeConstraint: exclude listed season numbers
        :param after_cursor: for pagination: end_cursor of previous call
        :return: Tuple of List of TVInfoShow, end_cursor, total count of results
        """
        self._check_params(start_date, end_date)
        if not start_date:
            start_date = (datetime.date.today() - datetime.timedelta(days=180)).strftime('%Y-%m-%d')

        result = []
        res = [], None, 0
        try:
            imdb_obj = imdbgql.IMDb()
            de_dupe = []
            res = self._get_graphql_data(
                imdb_obj.search_by_filters,
                languages='en', limit=result_count, title_type=["tvEpisode"], min_date=start_date,
                max_date=end_date, sort_by='RELEASE_DATE', sort_order='DESC', episodicConstraint=episodicConstraint,
                seasonsConstraint=seasonsConstraint, seasonsExlcudeConstraint=seasonsExlcudeConstraint,
                after_cursor=after_cursor)
            for _s_d in res[0]:
                if (_s := _s_d.get('series')) and \
                        (not episodicConstraint or
                         int(episodicConstraint) == _s['episodeNumber']['episodeNumber']) \
                        and (not seasonsConstraint or
                             int(seasonsConstraint) == _s['episodeNumber']['seasonNumber']) \
                        and (_id := _s['series']['id']) not in de_dupe:
                    de_dupe.append(_id)
                    ti_show = self._convert_graphql_show(_s_d)
                    if ti_show:
                        result.append(ti_show)
        except (BaseException, Exception) as e:
            log.error(f'Trending error: {e}')
            res = ([], None, 0)
        return result, res[1], res[2]

    def get_new_shows(self, result_count=300, start_date=None, end_date=None, after_cursor=None, **kwargs):
        # type: (int, u_date, u_date, str, ...) -> Tuple[List[TVInfoShow], str, int]
        """
        get new shows

        :param result_count: how many results to return (optional)
        :param start_date: start year or date: 2030}-12-31 or datetime.date object
        :param end_date: end year or date 2030}-12-31 or datetime.date object
        :param after_cursor: for pagination: end_cursor of previous call
        :return: Tuple of List of TVInfoShow, end_cursor, total count of results
        """
        return self._get_new_shows(result_count=result_count, start_date=start_date, end_date=end_date,
                                   episodicConstraint=1, seasonsConstraint=1, after_cursor=after_cursor, **kwargs)

    def get_new_seasons(self, result_count=300, start_date=None, end_date=None, after_cursor=None, **kwargs):
        # type: (int, u_date, u_date, str, ...) -> Tuple[List[TVInfoShow], str, int]
        """
        get new seasons

        :param result_count: how many results to return (optional)
        :param start_date: start year or date: 2030}-12-31 or datetime.date object
        :param end_date: end year or date 2030}-12-31 or datetime.date object
        :param after_cursor: for pagination: end_cursor of previous call
        :return: Tuple of List of TVInfoShow, end_cursor, total count of results
        """
        return self._get_new_shows(result_count=result_count, start_date=start_date, end_date=end_date,
                                   episodicConstraint=1, seasonsExlcudeConstraint=1, after_cursor=after_cursor,
                                   **kwargs)

    def get_coming_soon(self, result_count=100, after_cursor=None, **kwargs):
        # type: (int, str,...) -> Tuple[List[TVInfoShow], str]
        """
        get coming soon shows

        :param result_count: max count of results to return (optional)
        :param after_cursor: for pagination: end_cursor of previous call
        :return: Tuple of List of TVInfoShow, end_cursor
        """
        start_date = datetime.date.today()
        end_date = start_date + datetime.timedelta(days=365)
        res = ([], None)
        result = []
        try:
            imdb_obj = imdbgql.IMDb()
            res = self._get_graphql_data(
                imdb_obj.get_coming_soon,
                limit=result_count, title_type='TV', min_date=start_date,
                max_date=end_date, sort_by='RELEASE_DATE', sort_order='ASC',
                after_cursor=after_cursor)
            de_dupe = []
            for _s_d in res[0]:
                if (_id := _s_d['id']) in de_dupe:
                    continue
                de_dupe.append(_id)
                ti_show = self._convert_graphql_show(_s_d)
                if ti_show:
                    result.append(ti_show)
        except (BaseException, Exception) as e:
            log.error(f'Trending error: {e}')
            log.debug(traceback.format_exc())
            res = ([], None, 0)
        return result, res[1]

    def get_watchlist(self, user_id, result_count=250, after_cursor=None, **kwargs):
        # type: (str, int, str, ...) -> Tuple[List[TVInfoShow],str,int,dict]
        """
        get watchlist shows

        :param user_id: the number part of the user id: ur12345678
        :param result_count: count of results to return (optional)
        :param after_cursor: for pagination: end_cursor of previous call
        :return: Tuple of List of TVInfoShow, end_cursor, total count of results, List info dict
        """
        res = ([], None, 0, {})
        result = []
        try:
            imdb_obj = imdbgql.IMDb()
            res = self._get_graphql_data(
                imdb_obj.get_watchlist,
                user_id, limit=result_count, title_type=["tvSeries", "tvMiniSeries", "tvEpisode"], loc=None,
                sort_by='LIST_ORDER', sort_order='ASC', after_cursor=after_cursor)
            for _s_d in res[0]:
                ti_show = self._convert_graphql_show(_s_d)
                if ti_show:
                    result.append(ti_show)
        except (BaseException, Exception) as e:
            log.error(f'Watchlist error: {e}')
            res = ([], None, 0, {})
        return result, res[1], res[2], res[3]

    def get_favorite_actors(self, user_id, result_count=1000, sort_by='LIST_ORDER', sort_order='ASC',
                            after_cursor=None, **kwargs):
        # type: (...) -> Tuple[List[TVInfoPerson],str,int,dict]
        """
        get favorite actors

        :param user_id: the number part of the user id: ur12345678
        :param result_count: count of results to return (optional)
        :param sort_by: sort by
        :param sort_order: sort order
        :param after_cursor: for pagination: end_cursor of previous call
        :return: Tuple of List of TVInfoPerson, end_cursor, total count of results, List info dict
        """
        res = ([], None, 0, {})
        result = []
        try:
            imdb_obj = imdbgql.IMDb()
            res = self._get_graphql_data(
                imdb_obj.get_favorite_people,
                user_id, limit=result_count, sort_by=sort_by, sort_order=sort_order, after_cursor=after_cursor)
            for _p_d in res[0]:
                if not any(_p['category']['text'] in ('Actress', 'Actor', 'Archive Footage')
                           for _p in _p_d['primaryProfessions']):
                    continue
                ti_person = self._convert_graphql_person(_p_d, [])
                if ti_person:
                    result.append(ti_person)
        except (BaseException, Exception) as e:
            log.error(f'Favorite actors error: {e}')
            res = ([], None, 0, {})
        return result, res[1], res[2], res[3]
