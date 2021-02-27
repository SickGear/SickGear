# encoding:utf-8
# author:Prinz23
# project:tvmaze_api

__author__ = 'Prinz23'
__version__ = '1.0'
__api_version__ = '1.0.0'

import logging
import datetime
import requests
from requests.packages.urllib3.util.retry import Retry
from requests.adapters import HTTPAdapter

from six import iteritems
from sg_helpers import get_url, try_int
from lib.dateutil.parser import parser
from lib.dateutil.tz.tz import _datetime_to_timestamp
from lib.exceptions_helper import ConnectionSkipException, ex
from .tvmaze_exceptions import *
from lib.tvinfo_base import TVInfoBase, TVInfoImage, TVInfoImageSize, TVInfoImageType, Character, Crew, \
    crew_type_names, Person, RoleTypes, TVInfoShow, TVInfoEpisode, TVInfoIDs, TVInfoSeason, PersonGenders, \
    TVINFO_TVMAZE, TVINFO_TVDB, TVINFO_IMDB
from lib.pytvmaze import tvmaze

# noinspection PyUnreachableCode
if False:
    from typing import Any, AnyStr, Dict, List, Optional, Union
    from six import integer_types

log = logging.getLogger('tvmaze.api')
log.addHandler(logging.NullHandler())


# Query TVMaze free endpoints
def tvmaze_endpoint_standard_get(url):
    s = requests.Session()
    retries = Retry(total=5,
                    backoff_factor=0.1,
                    status_forcelist=[429])
    s.mount('http://', HTTPAdapter(max_retries=retries))
    s.mount('https://', HTTPAdapter(max_retries=retries))
    return get_url(url, json=True, session=s, hooks={'response': tvmaze._record_hook}, raise_skip_exception=True)


tvmaze.TVMaze.endpoint_standard_get = staticmethod(tvmaze_endpoint_standard_get)
tvm_obj = tvmaze.TVMaze()
empty_ep = TVInfoEpisode()
empty_se = TVInfoSeason()
tz_p = parser()

img_type_map = {
    'poster': TVInfoImageType.poster,
    'banner': TVInfoImageType.banner,
    'background': TVInfoImageType.fanart,
    'typography': TVInfoImageType.typography,
}

img_size_map = {
    'original': TVInfoImageSize.original,
    'medium': TVInfoImageSize.medium,
}

show_map = {
    'id': 'maze_id',
    'ids': 'externals',
    # 'slug': '',
    'seriesid': 'maze_id',
    'seriesname': 'name',
    'aliases': 'akas',
    # 'season': '',
    'classification': 'type',
    # 'genre': '',
    'genre_list': 'genres',
    # 'actors': '',
    # 'cast': '',
    # 'show_type': '',
    # 'network': 'network',
    # 'network_id': '',
    # 'network_timezone': '',
    # 'network_country': '',
    # 'network_country_code': '',
    # 'network_is_stream': '',
    'runtime': 'runtime',
    'language': 'language',
    'official_site': 'official_site',
    # 'imdb_id': '',
    # 'zap2itid': '',
    # 'airs_dayofweek': '',
    # 'airs_time': '',
    # 'time': '',
    'firstaired': 'premiered',
    # 'added': '',
    # 'addedby': '',
    # 'siteratingcount': '',
    # 'lastupdated': '',
    # 'contentrating': '',
    'rating': 'rating',
    'status': 'status',
    'overview': 'summary',
    # 'poster': 'image',
    # 'poster_thumb': '',
    # 'banner': '',
    # 'banner_thumb': '',
    # 'fanart': '',
    # 'banners': '',
    'updated_timestamp': 'updated',
}
season_map = {
    'id': 'id',
    'number': 'season_number',
    'name': 'name',
    # 'actors': '',
    # 'cast': '',
    # 'network': '',
    # 'network_id': '',
    # 'network_timezone': '',
    # 'network_country': '',
    # 'network_country_code': '',
    # 'network_is_stream': '',
    'ordered': '',
    'start_date': 'premiere_date',
    'end_date': 'end_date',
    # 'poster': '',
    'summery': 'summary',
    'episode_order': 'episode_order',
}


class TvMaze(TVInfoBase):
    supported_id_searches = [TVINFO_TVMAZE, TVINFO_TVDB, TVINFO_IMDB]
    supported_person_id_searches = [TVINFO_TVMAZE]

    def __init__(self, *args, **kwargs):
        super(TvMaze, self).__init__(*args, **kwargs)

    def _search_show(self, name=None, ids=None, **kwargs):
        def _make_result_dict(s):
            return {'seriesname': s.name, 'id': s.id, 'firstaired': s.premiered,
                    'network': s.network and s.network.name,
                    'genres': s.genres, 'overview': s.summary,
                    'aliases': [a.name for a in s.akas], 'image': s.image and s.image.get('original'), 
                    'ids': TVInfoIDs(tvdb=s.externals.get('thetvdb'), rage=s.externals.get('tvrage'), tvmaze=s.id,
                                     imdb=s.externals.get('imdb') and try_int(s.externals.get('imdb').replace('tt', ''),
                                                                              None))}
        results = []
        if ids:
            for t, p in iteritems(ids):
                if t in self.supported_id_searches:
                    if t == TVINFO_TVDB:
                        try:
                            show = tvmaze.lookup_tvdb(p)
                        except (BaseException, Exception):
                            continue
                    elif t == TVINFO_IMDB:
                        try:
                            show = tvmaze.lookup_imdb((p, 'tt%07d' % p)[not str(p).startswith('tt')])
                        except (BaseException, Exception):
                            continue
                    elif t == TVINFO_TVMAZE:
                        try:
                            show = tvm_obj.get_show(maze_id=p)
                        except (BaseException, Exception):
                            continue
                    else:
                        continue
                    if show:
                        try:
                            if show.id not in [i['id'] for i in results]:
                                results.append(_make_result_dict(show))
                        except (BaseException, Exception) as e:
                            log.debug('Error creating result dict: %s' % ex(e))
        if name:
            for n in ([name], name)[isinstance(name, list)]:
                try:
                    shows = tvmaze.show_search(n)
                    results = [_make_result_dict(s) for s in shows]
                except (BaseException, Exception) as e:
                    log.debug('Error searching for show: %s' % ex(e))
        return results

    def _set_episode(self, sid, ep_obj):
        for _k, _s in [('seasonnumber', 'season_number'), ('episodenumber', 'episode_number'),
                       ('episodename', 'title'), ('overview', 'summary'), ('firstaired', 'airdate'),
                       ('airtime', 'airtime'), ('runtime', 'runtime'),
                       ('seriesid', 'maze_id'), ('id', 'maze_id'), ('is_special', 'special'),
                       ('filename', 'image')]:
            if 'filename' == _k:
                image = getattr(ep_obj, _s, {}) or {}
                image = image.get('original') or image.get('medium')
                self._set_item(sid, ep_obj.season_number, ep_obj.episode_number, _k, image)
            else:
                self._set_item(sid, ep_obj.season_number, ep_obj.episode_number, _k,
                               getattr(ep_obj, _s, getattr(empty_ep, _k)))

        if ep_obj.airstamp:
            try:
                at = _datetime_to_timestamp(tz_p.parse(ep_obj.airstamp))
                self._set_item(sid, ep_obj.season_number, ep_obj.episode_number, 'timestamp', at)
            except (BaseException, Exception):
                pass

    def _set_network(self, show_obj, network, is_stream):
        show_obj['network'] = network.name
        show_obj['network_timezone'] = network.timezone
        show_obj['network_country'] = network.country
        show_obj['network_country_code'] = network.code
        show_obj['network_id'] = network.maze_id
        show_obj['network_is_stream'] = is_stream

    def _get_show_data(self, sid, language, get_ep_info=False, banners=False, posters=False, seasons=False,
                       seasonwides=False, fanart=False, actors=False, **kwargs):
        log.debug('Getting all series data for %s' % sid)
        try:
            self.show_not_found = False
            show_data = tvm_obj.get_show(maze_id=sid, embed='cast%s' % ('', ',episodes')[get_ep_info])
        except tvmaze.ShowNotFound:
            self.show_not_found = True
            return False
        except (BaseException, Exception) as e:
            log.debug('Error getting data for tvmaze show id: %s' % sid)
            return False

        show_obj = self.shows[sid].__dict__
        for k, v in iteritems(show_obj):
            if k not in ('cast', 'crew', 'images'):
                show_obj[k] = getattr(show_data, show_map.get(k, k), show_obj[k])
        if show_data.image:
            show_obj['poster'] = show_data.image.get('original')
            show_obj['poster_thumb'] = show_data.image.get('medium')

        if (banners or posters or fanart or
                any(self.config.get('%s_enabled' % t, False) for t in ('banners', 'posters', 'fanart'))) and \
                not all(getattr(self.shows[sid], '%s_loaded' % t, False) for t in ('poster', 'banner', 'fanart')):
            if show_data.images:
                b_set, f_set = False, False
                self.shows[sid].poster_loaded = True
                self.shows[sid].banner_loaded = True
                self.shows[sid].fanart_loaded = True
                for img in show_data.images:
                    img_type = img_type_map.get(img.type, TVInfoImageType.other)
                    img_src = {}
                    for res, img_url in iteritems(img.resolutions):
                        img_size = img_size_map.get(res)
                        if img_size:
                            img_src[img_size] = img_url.get('url')
                    show_obj['images'].setdefault(img_type, []).append(
                        TVInfoImage(image_type=img_type, sizes=img_src, img_id=img.id, main_image=img.main,
                                    type_str=img.type))
                    if not b_set and 'banner' == img.type:
                        b_set = True
                        show_obj['banner'] = img.resolutions.get('original')['url']
                        show_obj['banner_thumb'] = img.resolutions.get('medium')['url']
                    elif not f_set and 'background' == img.type:
                        f_set = True
                        show_obj['fanart'] = img.resolutions.get('original')['url']

        if show_data.schedule:
            if 'time' in show_data.schedule:
                show_obj['airs_time'] = show_data.schedule['time']
                try:
                    h, m = show_data.schedule['time'].split(':')
                    h, m = try_int(h, None), try_int(m, None)
                    if None is not h and None is not m:
                        show_obj['time'] = datetime.time(hour=h, minute=m)
                except (BaseException, Exception):
                    pass
            if 'days' in show_data.schedule:
                show_obj['airs_dayofweek'] = ', '.join(show_data.schedule['days'])
        if show_data.genres:
            show_obj['genre'] = ','.join(show_data.genres)

        if (actors or self.config['actors_enabled']) and not getattr(self.shows.get(sid), 'actors_loaded', False):
            if show_data.cast:
                character_person_ids = {}
                for ch in show_obj['cast'][RoleTypes.ActorMain]:
                    character_person_ids.setdefault(ch.id, []).extend([p.id for p in ch.person])
                for ch in show_data.cast.characters:
                    existing_character = next((c for c in show_obj['cast'][RoleTypes.ActorMain] if c.id == ch.id),
                                              None)  # type: Optional[Character]
                    person = self._convert_person(ch.person)
                    if existing_character:
                        existing_person = next((p for p in existing_character.person
                                                if person.id == p.ids.get(TVINFO_TVMAZE)),
                                               None)  # type: Person
                        if existing_person:
                            try:
                                character_person_ids[ch.id].remove(existing_person.id)
                            except (BaseException, Exception):
                                print('error')
                                pass
                            existing_person.p_id, existing_person.name, existing_person.image, existing_person.gender, \
                            existing_person.birthdate, existing_person.deathdate, existing_person.country, \
                            existing_person.country_code, existing_person.country_timezone, existing_person.thumb_url, \
                            existing_person.url, existing_person.ids = \
                                ch.person.id, ch.person.name, ch.person.image and ch.person.image.get('original'), \
                                PersonGenders.named.get(ch.person.gender and ch.person.gender.lower(),
                                                        PersonGenders.unknown),\
                                person.birthdate, person.deathdate,\
                                ch.person.country and ch.person.country.get('name'),\
                                ch.person.country and ch.person.country.get('code'),\
                                ch.person.country and ch.person.country.get('timezone'),\
                                ch.person.image and ch.person.image.get('medium'),\
                                ch.person.url, {TVINFO_TVMAZE: ch.person.id}
                        else:
                            existing_character.person.append(person)
                    else:
                        show_obj['cast'][RoleTypes.ActorMain].append(
                            Character(p_id=ch.id, name=ch.name, image=ch.image and ch.image.get('original'),
                                      person=[person],
                                      plays_self=ch.plays_self, thumb_url=ch.image and ch.image.get('medium')
                                      ))

                if character_person_ids:
                    for c, p_ids in iteritems(character_person_ids):
                        if p_ids:
                            char = next((mc for mc in show_obj['cast'][RoleTypes.ActorMain] if mc.id == c),
                                        None)  # type: Optional[Character]
                            if char:
                                char.person = [p for p in char.person if p.id not in p_ids]

                if show_data.cast:
                    show_obj['actors'] = [
                        {'character': {'id': ch.id,
                                       'name': ch.name,
                                       'url': 'https://www.tvmaze.com/character/view?id=%s' % ch.id,
                                       'image': ch.image and ch.image.get('original'),
                                       },
                         'person': {'id': ch.person and ch.person.id,
                                    'name': ch.person and ch.person.name,
                                    'url': ch.person and 'https://www.tvmaze.com/person/view?id=%s' % ch.person.id,
                                    'image': ch.person and ch.person.image and ch.person.image.get('original'),
                                    'birthday': None,  # not sure about format
                                    'deathday': None,  # not sure about format
                                    'gender': ch.person and ch.person.gender and ch.person.gender,
                                    'country': ch.person and ch.person.country and ch.person.country.get('name'),
                                    },
                         } for ch in show_data.cast.characters]

            if show_data.crew:
                for cw in show_data.crew:
                    rt = crew_type_names.get(cw.type.lower(), RoleTypes.CrewOther)
                    show_obj['crew'][rt].append(
                        Crew(p_id=cw.person.id, name=cw.person.name,
                             image=cw.person.image and cw.person.image.get('original'),
                             gender=cw.person.gender, birthdate=cw.person.birthday, deathdate=cw.person.death_day,
                             country=cw.person.country and cw.person.country.get('name'),
                             country_code=cw.person.country and cw.person.country.get('code'),
                             country_timezone=cw.person.country and cw.person.country.get('timezone'),
                             crew_type_name=cw.type,
                             )
                    )

        if show_data.externals:
            show_obj['ids'] = TVInfoIDs(tvdb=show_data.externals.get('thetvdb'),
                                        rage=show_data.externals.get('tvrage'),
                                        imdb=show_data.externals.get('imdb') and
                                             try_int(show_data.externals.get('imdb').replace('tt', ''), None))

        if show_data.network:
            self._set_network(show_obj, show_data.network, False)
        elif show_data.web_channel:
            self._set_network(show_obj, show_data.web_channel, True)

        if get_ep_info and not getattr(self.shows.get(sid), 'ep_loaded', False):
            log.debug('Getting all episodes of %s' % sid)
            if None is show_data:
                try:
                    self.show_not_found = False
                    show_data = tvm_obj.get_show(maze_id=sid, embed='cast%s' % ('', ',episodes')[get_ep_info])
                except tvmaze.ShowNotFound:
                    self.show_not_found = True
                    return False
                except (BaseException, Exception) as e:
                    log.debug('Error getting data for tvmaze show id: %s' % sid)
                    return False

            if show_data.episodes:
                specials = []
                for cur_ep in show_data.episodes:
                    if cur_ep.is_special():
                        specials.append(cur_ep)
                    else:
                        self._set_episode(sid, cur_ep)

                if specials:
                    specials.sort(key=lambda ep: ep.airstamp or 'Last')
                    for ep_n, cur_sp in enumerate(specials, start=1):
                        cur_sp.season_number, cur_sp.episode_number = 0, ep_n
                        self._set_episode(sid, cur_sp)

            if show_data.seasons:
                for cur_s_k, cur_s_v in iteritems(show_data.seasons):
                    season_obj = None
                    if cur_s_v.season_number not in self.shows[sid]:
                        if all(_e.is_special() for _e in cur_s_v.episodes or []):
                            season_obj = self.shows[sid][0].__dict__
                        else:
                            log.error('error episodes have no numbers')
                    season_obj = season_obj or self.shows[sid][cur_s_v.season_number].__dict__
                    for k, v in iteritems(season_map):
                        season_obj[k] = getattr(cur_s_v, v, None) or empty_se.get(v)
                    if cur_s_v.network:
                        self._set_network(season_obj, cur_s_v.network, False)
                    elif cur_s_v.web_channel:
                        self._set_network(season_obj, cur_s_v.web_channel, True)
                    if cur_s_v.image:
                        season_obj['poster'] = cur_s_v.image.get('original')
                self.shows[sid].season_images_loaded = True

            self.shows[sid].ep_loaded = True

        return True

    def get_updated_shows(self):
        # type: (...) -> Dict[integer_types, integer_types]
        return {sid: v.seconds_since_epoch for sid, v in iteritems(tvmaze.show_updates().updates)}

    @staticmethod
    def _convert_person(person_obj):
        # type: (tvmaze.Person) -> Person
        ch = []
        for c in person_obj.castcredits or []:
            show = TVInfoShow()
            show.seriesname = c.show.name
            show.id = c.show.id
            show.firstaired = c.show.premiered
            show.ids = TVInfoIDs(ids={TVINFO_TVMAZE: show.id})
            show.overview = c.show.summary
            show.status = c.show.status
            net = c.show.network or c.show.web_channel
            show.network = net.name
            show.network_id = net.maze_id
            show.network_country = net.country
            show.network_timezone = net.timezone
            show.network_country_code = net.code
            show.network_is_stream = None is not c.show.web_channel
            ch.append(Character(name=c.character.name, show=show))
        try:
            birthdate = person_obj.birthday and tz_p.parse(person_obj.birthday).date()
        except (BaseException, Exception):
            birthdate = None
        try:
            deathdate = person_obj.death_day and tz_p.parse(person_obj.death_day).date()
        except (BaseException, Exception):
            deathdate = None
        return Person(p_id=person_obj.id, name=person_obj.name,
                      image=person_obj.image and person_obj.image.get('original'),
                      gender=PersonGenders.named.get(person_obj.gender and person_obj.gender.lower(),
                                                     PersonGenders.unknown),
                      birthdate=birthdate, deathdate=deathdate,
                      country=person_obj.country and person_obj.country.get('name'),
                      country_code=person_obj.country and person_obj.country.get('code'),
                      country_timezone=person_obj.country and person_obj.country.get('timezone'),
                      thumb_url=person_obj.image and person_obj.image.get('medium'),
                      url=person_obj.url, ids={TVINFO_TVMAZE: person_obj.id}, characters=ch
                      )

    def _search_person(self, name=None, ids=None):
        # type: (AnyStr, Dict[integer_types, integer_types]) -> List[Person]
        urls, result, ids = [], [], ids or {}
        for tv_src in self.supported_person_id_searches:
            if tv_src in ids:
                if TVINFO_TVMAZE == tv_src:
                    try:
                        r = self.get_person(ids[tv_src])
                    except ConnectionSkipException as e:
                        raise e
                    except (BaseException, Exception):
                        r = None
                    if r:
                        result.append(r)
        if name:
            try:
                r = tvmaze.people_search(name)
            except ConnectionSkipException as e:
                raise e
            except (BaseException, Exception):
                r = None
            if r:
                for p in r:
                    if not any(1 for ep in result if p.id == ep.id):
                        result.append(self._convert_person(p))
        return result

    def get_person(self, p_id, get_show_credits=False, get_images=False, **kwargs):
        # type: (integer_types, bool, bool, Any) -> Optional[Person]
        if not p_id:
            return
        kw = {}
        to_embed = []
        if get_show_credits:
            to_embed.append('castcredits')
        if to_embed:
            kw['embed'] = ','.join(to_embed)
        try:
            p = tvmaze.person_main_info(p_id, **kw)
        except ConnectionSkipException as e:
            raise e
        except (BaseException, Exception):
            p = None
        if p:
            return self._convert_person(p)
