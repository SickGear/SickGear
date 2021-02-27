# encoding:utf-8
# author:Prinz23
# project:tmdb_api

__author__ = 'Prinz23'
__version__ = '1.0'
__api_version__ = '1.0.0'

import json
import logging
import datetime

from six import iteritems
from sg_helpers import get_tmdb_info, get_url, try_int
from lib.dateutil.parser import parser
from lib.dateutil.tz.tz import _datetime_to_timestamp
from lib.exceptions_helper import ConnectionSkipException, ex
from .tmdb_exceptions import *
from lib.tvinfo_base import TVInfoBase, TVInfoImage, TVInfoImageSize, TVInfoImageType, Character, Crew, \
    crew_type_names, Person, RoleTypes, TVInfoEpisode, TVInfoIDs, TVInfoSeason, PersonGenders, TVINFO_TVMAZE, \
    TVINFO_TVDB, TVINFO_IMDB, TVINFO_TMDB, TVINFO_TWITTER, TVINFO_INSTAGRAM, TVINFO_FACEBOOK, TVInfoShow
from lib import tmdbsimple

# noinspection PyUnreachableCode
if False:
    from typing import Any, AnyStr, Dict, List, Optional, Union
    from six import integer_types

log = logging.getLogger('tmdb.api')
log.addHandler(logging.NullHandler())
tz_p = parser()
tmdbsimple.API_KEY = 'edc5f123313769de83a71e157758030b'

id_map = {TVINFO_IMDB: 'imdb_id', TVINFO_TVDB: 'tvdb_id', TVINFO_FACEBOOK: 'facebook_id', TVINFO_TWITTER: 'twitter_id',
          TVINFO_INSTAGRAM: 'instagram_id'}


def tmdb_GET(self, path, params=None):
    url = self._get_complete_url(path)
    params = self._get_params(params)
    return get_url(url=url, params=params, json=True, raise_skip_exception=True)


def tmdb_POST(self, path, params=None, payload=None):
    url = self._get_complete_url(path)
    params = self._get_params(params)
    data = json.dumps(payload) if payload else payload
    return get_url(url=url, params=params, post_data=data, json=True, raise_skip_exception=True)


tmdbsimple.base.TMDB._GET = tmdb_GET
tmdbsimple.base.TMDB._POST = tmdb_POST


class TmdbIndexer(TVInfoBase):
    API_KEY = tmdbsimple.API_KEY
    # supported_id_searches = [TVINFO_TVDB, TVINFO_IMDB, TVINFO_TMDB, TVINFO_TRAKT]
    supported_person_id_searches = [TVINFO_TMDB, TVINFO_IMDB, TVINFO_TWITTER, TVINFO_INSTAGRAM, TVINFO_FACEBOOK]

    # noinspection PyUnusedLocal
    # noinspection PyDefaultArgument
    def __init__(self, *args, **kwargs):
        super(TmdbIndexer, self).__init__(*args, **kwargs)
        response = get_tmdb_info()
        self.img_base_url = response['images']['base_url']
        self.img_sizes = response['images']['profile_sizes']
        self.tv_genres = get_tmdb_info(get_tv_genres=True)

    def _convert_person_obj(self, person_obj):
        gender = PersonGenders.tmdb_map.get(person_obj.get('gender'), PersonGenders.unknown)
        try:
            birthdate = person_obj.get('birthday') and tz_p.parse(person_obj.get('birthday')).date()
        except (BaseException, Exception):
            birthdate = None
        try:
            deathdate = person_obj.get('deathday') and tz_p.parse(person_obj.get('deathday')).date()
        except (BaseException, Exception):
            deathdate = None

        cast = person_obj.get('cast') or person_obj.get('tv_credits', {}).get('cast')

        characters = []
        for character in cast or []:
            show = TVInfoShow()
            show.id = character.get('id')
            show.ids = TVInfoIDs(ids={TVINFO_TMDB: show.id})
            show.seriesname = character.get('original_name')
            show.overview = character.get('overview')
            show.firstaired = character.get('first_air_date')
            characters.append(
                Character(name=character.get('character'), show=show)
            )

        pi = person_obj.get('images')
        image_url, thumb_url = None, None
        if pi:
            def size_str_to_int(x):
                return float('inf') if 'original' == x else int(x[1:])

            thumb_size = next(s for s in sorted(self.img_sizes, key=size_str_to_int)
                              if 150 < size_str_to_int(s))
            for i in sorted(pi['profiles'], key=lambda a: a['vote_average'] or 0, reverse=True):
                if 500 < i['height'] and not image_url:
                    image_url = '%s%s%s' % (self.img_base_url, 'original', i['file_path'])
                    thumb_url = '%s%s%s' % (self.img_base_url, thumb_size, i['file_path'])
                elif not thumb_url:
                    thumb_url = '%s%s%s' % (self.img_base_url, 'original', i['file_path'])
                if image_url and thumb_url:
                    break

        return Person(p_id=person_obj.get('id'), gender=gender, name=person_obj.get('name'), birthdate=birthdate,
                      deathdate=deathdate, bio=person_obj.get('biography'), birthplace=person_obj.get('place_of_birth'),
                      homepage=person_obj.get('homepage'), characters=characters, image=image_url, thumb_url=thumb_url,
                      ids={TVINFO_TMDB: person_obj.get('id'),
                           TVINFO_IMDB:
                               person_obj.get('imdb_id') and try_int(person_obj['imdb_id'].replace('nm', ''), None)})

    def _search_person(self, name=None, ids=None):
        # type: (AnyStr, Dict[integer_types, integer_types]) -> List[Person]
        """
        search for person by name
        :param name: name to search for
        :param ids: dict of ids to search
        :return: list of found person's
        """
        results, ids = [], ids or {}
        search_text_obj = tmdbsimple.Search()
        for tv_src in self.supported_person_id_searches:
            if tv_src in ids:
                if TVINFO_TMDB == tv_src:
                    try:
                        people_obj = self.get_person(ids[tv_src])
                    except ConnectionSkipException as e:
                        raise e
                    except (BaseException, Exception):
                        people_obj = None
                    if people_obj and not any(1 for r in results if r.id == people_obj.id):
                        results.append(people_obj)
                elif tv_src in (TVINFO_IMDB, TVINFO_TMDB):
                    try:
                        cache_key_name = 'p-src-%s-%s' % (tv_src, ids.get(tv_src))
                        is_none, result_objs = self._get_cache_entry(cache_key_name)
                        if None is result_objs and not is_none:
                            result_objs = tmdbsimple.Find(id=(ids.get(tv_src),
                                                          'nm%07d' % ids.get(tv_src))[TVINFO_IMDB == tv_src]).info(
                                external_source=id_map[tv_src]).get('person_results')
                            self._set_cache_entry(cache_key_name, result_objs)
                    except ConnectionSkipException as e:
                        raise e
                    except (BaseException, Exception):
                        result_objs = None
                    if result_objs:
                        for person_obj in result_objs:
                            if not any(1 for r in results if r.id == person_obj['id']):
                                results.append(self._convert_person_obj(person_obj))
                else:
                    continue
        if name:
            cache_key_name = 'p-src-text-%s' % name
            is_none, people_objs = self._get_cache_entry(cache_key_name)
            if None is people_objs and not is_none:
                try:
                    people_objs = search_text_obj.person(query=name, include_adult=True)
                    self._set_cache_entry(cache_key_name, people_objs)
                except ConnectionSkipException as e:
                    raise e
                except (BaseException, Exception):
                    people_objs = None
            if people_objs and people_objs.get('results'):
                for person_obj in people_objs['results']:
                    if not any(1 for r in results if r.id == person_obj['id']):
                        results.append(self._convert_person_obj(person_obj))

        return results

    def get_person(self, p_id, get_show_credits=False, get_images=False, **kwargs):
        # type: (integer_types, bool, bool, Any) -> Optional[Person]
        kw = {}
        to_append = []
        if get_show_credits:
            to_append.append('tv_credits')
        if get_images:
            to_append.append('images')
        if to_append:
            kw['append_to_response'] = ','.join(to_append)

        cache_key_name = 'p-%s-%s' % (p_id, '-'.join(to_append))
        is_none, people_obj = self._get_cache_entry(cache_key_name)
        if None is people_obj and not is_none:
            try:
                people_obj = tmdbsimple.People(id=p_id).info(**kw)
            except ConnectionSkipException as e:
                raise e
            except (BaseException, Exception):
                people_obj = None
            self._set_cache_entry(cache_key_name, people_obj)

        if people_obj:
            return self._convert_person_obj(people_obj)

    def _convert_show(self, show_dict):
        # type: (Dict) -> TVInfoShow
        tv_s = TVInfoShow()
        if show_dict:
            tv_s.seriesname = show_dict.get('name') or show_dict.get('original_name') or show_dict.get('original_title')
            org_title = show_dict.get('original_name') or show_dict.get('original_title')
            if org_title != tv_s.seriesname:
                tv_s.aliases = [org_title]
            tv_s.id = show_dict.get('id')
            tv_s.seriesid = tv_s.id
            tv_s.language = show_dict.get('original_language')
            tv_s.overview = show_dict.get('overview')
            tv_s.firstaired = show_dict.get('first_air_date')
            tv_s.vote_count = show_dict.get('vote_count')
            tv_s.vote_average = show_dict.get('vote_average')
            tv_s.popularity = show_dict.get('popularity')
            tv_s.origin_countries = show_dict.get('origin_country') or []
            tv_s.genre_list = []
            for g in show_dict.get('genre_ids') or []:
                if g in self.tv_genres:
                    tv_s.genre_list.append(self.tv_genres.get(g))
            tv_s.genre = ', '.join(tv_s.genre_list)
            image_url = show_dict.get('poster_path') and '%s%s%s' % (self.img_base_url, 'original',
                                                                     show_dict.get('poster_path'))
            backdrop_url = show_dict.get('backdrop_path') and '%s%s%s' % (self.img_base_url, 'original',
                                                                          show_dict.get('backdrop_path'))
            tv_s.poster = image_url
            tv_s.fanart = backdrop_url
            tv_s.ids = TVInfoIDs(tmdb=tv_s.id)
        return tv_s

    def _get_show_list(self, src_method, result_count, **kwargs):
        result = []
        try:
            c_page = 1
            while len(result) < result_count:
                results = src_method(page=c_page, **kwargs)
                t_pages = results.get('total_pages')
                if c_page != results.get('page') or c_page >= t_pages:
                    break
                c_page += 1
                if results and 'results' in results:
                    result += [self._convert_show(t) for t in results['results']]
                else:
                    break
        except (BaseException, Exception):
            pass
        return result[:result_count]

    def get_trending(self, result_count=100, time_window='day', **kwargs):
        """
        list of trending tv shows for day or week
        :param result_count:
        :param time_window: valid values: 'day', 'week'
        """
        t_windows = ('day', 'week')['week' == time_window]
        return self._get_show_list(tmdbsimple.Trending(media_type='tv', time_window=t_windows).info, result_count)

    def get_popular(self, result_count=100, **kwargs):
        return self._get_show_list(tmdbsimple.TV().popular, result_count)

    def get_top_rated(self, result_count=100, **kwargs):
        return self._get_show_list(tmdbsimple.TV().top_rated, result_count)

    def discover(self, result_count=100, **kwargs):
        """
        Discover TV shows by different types of data like average rating,
        number of votes, genres, the network they aired on and air dates.

        Discover also supports a nice list of sort options. See below for all
        of the available options.

        Also note that a number of filters support being comma (,) or pipe (|)
        separated. Comma's are treated like an AND and query while pipe's are
        an OR.

        Some examples of what can be done with discover can be found at
        https://www.themoviedb.org/documentation/api/discover.

        kwargs:
            language: (optional) ISO 639-1 code.
            sort_by: (optional) Available options are 'vote_average.desc',
                     'vote_average.asc', 'first_air_date.desc',
                     'first_air_date.asc', 'popularity.desc', 'popularity.asc'
            sort_by: (optional) Allowed values: vote_average.desc,
                vote_average.asc, first_air_date.desc, first_air_date.asc,
                popularity.desc, popularity.asc
                Default: popularity.desc
            air_date.gte: (optional) Filter and only include TV shows that have
                a air date (by looking at all episodes) that is greater or
                equal to the specified value.
            air_date.lte: (optional) Filter and only include TV shows that have
                a air date (by looking at all episodes) that is less than or
                equal to the specified value.
            first_air_date.gte: (optional) Filter and only include TV shows
                that have a original air date that is greater or equal to the
                specified value. Can be used in conjunction with the
                "include_null_first_air_dates" filter if you want to include
                items with no air date.
            first_air_date.lte: (optional) Filter and only include TV shows
                that have a original air date that is less than or equal to the
                specified value. Can be used in conjunction with the
                "include_null_first_air_dates" filter if you want to include
                items with no air date.
            first_air_date_year: (optional) Filter and only include TV shows
                that have a original air date year that equal to the specified
                value. Can be used in conjunction with the
                "include_null_first_air_dates" filter if you want to include
                items with no air date.
            timezone: (optional) Used in conjunction with the air_date.gte/lte
                filter to calculate the proper UTC offset. Default
                America/New_York.
            vote_average.gte: (optional) Filter and only include movies that
                have a rating that is greater or equal to the specified value.
                Minimum 0.
            vote_count.gte: (optional) Filter and only include movies that have
                a rating that is less than or equal to the specified value.
                Minimum 0.
            with_genres: (optional) Comma separated value of genre ids that you
                want to include in the results.
            with_networks: (optional) Comma separated value of network ids that
                you want to include in the results.
            without_genres: (optional) Comma separated value of genre ids that
                you want to exclude from the results.
            with_runtime.gte: (optional) Filter and only include TV shows with
                an episode runtime that is greater than or equal to a value.
            with_runtime.lte: (optional) Filter and only include TV shows with
                an episode runtime that is less than or equal to a value.
            include_null_first_air_dates: (optional) Use this filter to include
                TV shows that don't have an air date while using any of the
                "first_air_date" filters.
            with_original_language: (optional) Specify an ISO 639-1 string to
                filter results by their original language value.
            without_keywords: (optional) Exclude items with certain keywords.
                You can comma and pipe seperate these values to create an 'AND'
                or 'OR' logic.
            screened_theatrically: (optional) Filter results to include items
                that have been screened theatrically.
            with_companies: (optional) A comma separated list of production
                company ID's. Only include movies that have one of the ID's
                added as a production company.
            with_keywords: (optional) A comma separated list of keyword ID's.
                Only includes TV shows that have one of the ID's added as a
                keyword.

        :param result_count:
        """
        return self._get_show_list(tmdbsimple.Discover().tv, result_count, **kwargs)
