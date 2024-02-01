# encoding:utf-8
# author:Prinz23
# project:tvmaze_api

__author__ = 'Prinz23'
__version__ = '1.0'
__api_version__ = '1.0.0'

import datetime
import logging
import re

import requests
from requests.adapters import HTTPAdapter
# noinspection PyProtectedMember
from tornado._locale_data import LOCALE_NAMES
from urllib3.util.retry import Retry

from sg_helpers import clean_data, enforce_type, get_url, try_int
from lib.dateutil.parser import parser
# noinspection PyProtectedMember
from lib.dateutil.tz.tz import _datetime_to_timestamp
from lib.exceptions_helper import ConnectionSkipException, ex
from lib.pytvmaze import tvmaze
# from .tvmaze_exceptions import *
from lib.tvinfo_base import TVInfoBase, TVInfoImage, TVInfoImageSize, TVInfoImageType, TVInfoCharacter, Crew, \
    crew_type_names, TVInfoPerson, RoleTypes, TVInfoShow, TVInfoEpisode, TVInfoIDs, TVInfoNetwork, TVInfoSeason, \
    PersonGenders, TVINFO_TVMAZE, TVINFO_TVDB, TVINFO_IMDB

from six import integer_types, iteritems, string_types

# noinspection PyUnreachableCode
if False:
    from typing import Any, AnyStr, Dict, List, Optional
    from lib.pytvmaze.tvmaze import Episode as TVMazeEpisode, Show as TVMazeShow

log = logging.getLogger('tvmaze.api')
log.addHandler(logging.NullHandler())


# Query TVmaze free endpoints
def tvmaze_endpoint_standard_get(url):
    s = requests.Session()
    retries = Retry(total=5,
                    backoff_factor=0.1,
                    status_forcelist=[429])
    # noinspection HttpUrlsUsage
    s.mount('http://', HTTPAdapter(max_retries=retries))
    s.mount('https://', HTTPAdapter(max_retries=retries))
    # noinspection PyProtectedMember
    return get_url(url, json=True, session=s, hooks={'response': tvmaze._record_hook}, raise_skip_exception=True)


tvmaze.TVmaze.endpoint_standard_get = staticmethod(tvmaze_endpoint_standard_get)
tvm_obj = tvmaze.TVmaze()
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
    # 'runtime': 'runtime',
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
    # 'rating': 'rating',
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
            # type: (tvmaze.Show) -> Dict
            language = s.language and clean_data(s.language.lower())
            language_country_code = None
            if language:
                for cur_locale in iteritems(LOCALE_NAMES):
                    if language in cur_locale[1]['name_en'].lower():
                        language_country_code = cur_locale[0].split('_')[1].lower()
                        break
            ti_show = TVInfoShow()
            show_type = clean_data(s.type)
            if show_type:
                show_type = [show_type]
            else:
                show_type = []
            ti_show.seriesname, ti_show.id, ti_show.firstaired, ti_show.network, ti_show.genre_list, ti_show.overview, \
                ti_show.language, ti_show.runtime, ti_show.show_type, ti_show.airs_dayofweek, ti_show. status, \
                ti_show.official_site, ti_show.aliases, ti_show.poster, ti_show.ids = clean_data(s.name), s.id, \
                clean_data(s.premiered), \
                clean_data((s.network and s.network.name) or (s.web_channel and s.web_channel.name)), \
                isinstance(s.genres, list) and [clean_data(g.lower()) for g in s.genres], \
                enforce_type(clean_data(s.summary), str, ''), clean_data(s.language), \
                s.average_runtime or s.runtime, show_type, ', '.join(s.schedule['days'] or []), clean_data(s.status), \
                clean_data(s.official_site), [clean_data(a.name) for a in s.akas], \
                s.image and s.image.get('original'), \
                TVInfoIDs(tvdb=s.externals.get('thetvdb'), rage=s.externals.get('tvrage'), tvmaze=s.id,
                          imdb=clean_data(s.externals.get('imdb') and
                                          try_int(s.externals.get('imdb').replace('tt', ''), None)))
            ti_show.genre = '|'.join(ti_show.genre_list or [])
            return ti_show

        results = []
        if ids:
            for t, p in iteritems(ids):
                if t in self.supported_id_searches:
                    cache_id_key = 's-id-%s-%s' % (t, ids[t])
                    is_none, shows = self._get_cache_entry(cache_id_key)
                    if t == TVINFO_TVDB:
                        if not self.config.get('cache_search') or (None is shows and not is_none):
                            try:
                                show = tvmaze.lookup_tvdb(p)
                                self._set_cache_entry(cache_id_key, show, expire=self.search_cache_expire)
                            except (BaseException, Exception):
                                continue
                        else:
                            show = shows
                    elif t == TVINFO_IMDB:
                        if not self.config.get('cache_search') or (None is shows and not is_none):
                            try:
                                show = tvmaze.lookup_imdb((p, 'tt%07d' % p)[not str(p).startswith('tt')])
                                self._set_cache_entry(cache_id_key, show, expire=self.search_cache_expire)
                            except (BaseException, Exception):
                                continue
                        else:
                            show = shows
                    elif t == TVINFO_TVMAZE:
                        if not self.config.get('cache_search') or (None is shows and not is_none):
                            try:
                                show = tvm_obj.get_show(maze_id=p)
                                self._set_cache_entry(cache_id_key, show, expire=self.search_cache_expire)
                            except (BaseException, Exception):
                                continue
                        else:
                            show = shows
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
                cache_name_key = 's-name-%s' % n
                is_none, shows = self._get_cache_entry(cache_name_key)
                if not self.config.get('cache_search') or (None is shows and not is_none):
                    try:
                        shows = tvmaze.show_search(n)
                    except (BaseException, Exception) as e:
                        log.debug('Error searching for show: %s' % ex(e))
                        continue
                results.extend([_make_result_dict(s) for s in shows or []])

        seen = set()
        results = [seen.add(r['id']) or r for r in results if r['id'] not in seen]
        return results

    def _set_episode(self, sid, ep_obj):
        for _k, _s in (
                ('seasonnumber', 'season_number'), ('episodenumber', 'episode_number'),
                ('episodename', 'title'), ('overview', 'summary'), ('firstaired', 'airdate'),
                ('airtime', 'airtime'), ('runtime', 'runtime'),
                ('seriesid', 'maze_id'), ('id', 'maze_id'), ('is_special', 'special'), ('filename', 'image')):
            if 'airtime' == _k:
                try:
                    airtime = datetime.time.fromisoformat(clean_data(getattr(ep_obj, _s, getattr(empty_ep, _k))))
                except (BaseException, Exception):
                    airtime = None
                self._set_item(sid, ep_obj.season_number, ep_obj.episode_number or 0, _k, airtime)
            elif 'filename' == _k:
                image = getattr(ep_obj, _s, {}) or {}
                image = image.get('original') or image.get('medium')
                self._set_item(sid, ep_obj.season_number, ep_obj.episode_number or 0, _k, image)
            else:
                self._set_item(sid, ep_obj.season_number, ep_obj.episode_number or 0, _k,
                               clean_data(getattr(ep_obj, _s, getattr(empty_ep, _k))))

        if ep_obj.airstamp:
            try:
                at = _datetime_to_timestamp(tz_p.parse(ep_obj.airstamp))
                self._set_item(sid, ep_obj.season_number, ep_obj.episode_number or 0, 'timestamp', at)
            except (BaseException, Exception):
                pass

    @staticmethod
    def _set_network(ti_obj, network, is_stream):
        ti_obj.network = clean_data(network.name)
        ti_obj.network_timezone = clean_data(network.timezone)
        ti_obj.network_country = clean_data(network.country)
        ti_obj.network_country_code = clean_data(network.code)
        ti_obj.network_id = clean_data(network.maze_id)
        ti_obj.network_is_stream = is_stream

    def _set_images(self, ti_show, show_data, p_set):
        # type: (TVInfoShow, TVMazeShow, bool) -> None
        """
        Populate TVInfoShow with images show data

        :param ti_show:
        :param show_data:
        :param p_set:
        """

        b_set, f_set = False, False
        for cur_img in show_data.images:
            img_type = img_type_map.get(cur_img.type, TVInfoImageType.other)
            img_width, img_height, img_url = ([cur_img.resolutions['original'].get(this)
                                               for this in ('width', 'height', 'url')])
            img_ar = img_width and img_height and float(img_width) / float(img_height)
            img_ar_type = self._which_type(img_width, img_ar)
            if TVInfoImageType.poster == img_type and img_ar and img_ar_type != img_type and \
                    ti_show.poster == img_url:
                p_set = False
                ti_show.poster = None
                ti_show.poster_thumb = None
            img_type = (TVInfoImageType.other, img_type)[
                not img_ar or img_ar_type == img_type or
                img_type not in (TVInfoImageType.banner, TVInfoImageType.poster, TVInfoImageType.fanart)]
            img_src = {}
            for cur_res, cur_img_url in iteritems(cur_img.resolutions):
                img_size = img_size_map.get(cur_res)
                if img_size:
                    img_src[img_size] = cur_img_url.get('url')
            ti_show.images.setdefault(img_type, []).append(
                TVInfoImage(
                    image_type=img_type, sizes=img_src, img_id=cur_img.id, main_image=cur_img.main,
                    type_str=cur_img.type, width=img_width, height=img_height, aspect_ratio=img_ar))
            if not p_set and TVInfoImageType.poster == img_type:
                p_set = True
                ti_show.poster = img_url
                ti_show.poster_thumb = img_url
            elif not b_set and 'banner' == cur_img.type and TVInfoImageType.banner == img_type:
                b_set = True
                ti_show.banner = img_url
                ti_show.banner_thumb = cur_img.resolutions.get('medium')['url']
            elif not f_set and 'background' == cur_img.type and TVInfoImageType.fanart == img_type:
                f_set = True
                ti_show.fanart = img_url

    def _get_tvm_show(self, show_id, get_ep_info):
        try:
            self.show_not_found = False
            return tvm_obj.get_show(maze_id=show_id, embed='cast%s' % ('', ',episodeswithspecials')[get_ep_info])
        except tvmaze.ShowNotFound:
            self.show_not_found = True
        except (BaseException, Exception):
            log.debug('Error getting data for TVmaze show id: %s' % show_id)

    def _get_show_data(self, sid, language, get_ep_info=False, banners=False, posters=False, seasons=False,
                       seasonwides=False, fanart=False, actors=False, **kwargs):
        log.debug('Getting all series data for %s' % sid)

        show_data = self._get_tvm_show(sid, get_ep_info)
        if not show_data:
            return False

        ti_show = self.ti_shows[sid]  # type: TVInfoShow
        self._show_info_loader(
            sid, show_data, ti_show,
            load_images=banners or posters or fanart or
            any(self.config.get('%s_enabled' % t, False) for t in ('banners', 'posters', 'fanart')),
            load_actors=(actors or self.config['actors_enabled'])
        )

        if get_ep_info and not getattr(self.ti_shows.get(sid), 'ep_loaded', False):
            log.debug('Getting all episodes of %s' % sid)
            if None is show_data:
                show_data = self._get_tvm_show(sid, get_ep_info)
                if not show_data:
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
                    for cur_ep_num, cur_sp in enumerate(specials, start=1):
                        cur_sp.season_number, cur_sp.episode_number = 0, cur_ep_num
                        self._set_episode(sid, cur_sp)

            if show_data.seasons:
                networks = {}
                for _, cur_season in iteritems(show_data.seasons):
                    ti_season = None
                    if cur_season.season_number not in ti_show:
                        if all(_e.is_special() for _e in cur_season.episodes or []):
                            ti_season = ti_show[0]
                        else:
                            log.error('error episodes have no numbers')
                    ti_season = ti_season or ti_show[cur_season.season_number]  # type: TVInfoSeason
                    for k, v in iteritems(season_map):
                        setattr(ti_season, k, clean_data(getattr(cur_season, v, None)) or empty_se.get(v))
                    if cur_season.network:
                        self._set_network(ti_season, cur_season.network, False)
                    elif cur_season.web_channel:
                        self._set_network(ti_season, cur_season.web_channel, True)
                    if ti_season.network:
                        networks[cur_season.season_number] = TVInfoNetwork(
                            name=ti_season.network, country=ti_season.network_country,
                            country_code=ti_season.network_country_code, n_id=ti_season.network_id,
                            stream=ti_season.network_is_stream, timezone=ti_season.network_timezone
                        )
                    if cur_season.image:
                        ti_season.poster = cur_season.image.get('original')
                ti_show.season_images_loaded = True
                seen = set()
                ti_show.networks = [seen.add(r[1].name) or r[1]
                                    for r in sorted(iteritems(networks), key=lambda a: a[0], reverse=True)
                                    if r[1].name not in seen]

            ti_show.ep_loaded = True

        return True

    def get_updated_shows(self):
        # type: (...) -> Dict[integer_types, integer_types]
        return {sid: v.seconds_since_epoch for sid, v in iteritems(tvmaze.show_updates().updates)}

    def _convert_person(self, tvmaze_person_obj, load_credits=True):
        # type: (tvmaze.Person, bool) -> TVInfoPerson
        ch = []
        _dupes = []
        if load_credits:
            for c in tvmaze_person_obj.castcredits or []:
                ti_show = TVInfoShow()
                ti_show.seriesname = clean_data(c.show.name)
                ti_show.id = c.show.id
                ti_show.firstaired = clean_data(c.show.premiered)
                ti_show.ids = TVInfoIDs(ids={TVINFO_TVMAZE: ti_show.id})
                ti_show.overview = clean_data(c.show.summary)
                ti_show.status = clean_data(c.show.status)
                net = c.show.network or c.show.web_channel
                if net:
                    ti_show.network = clean_data(net.name)
                    ti_show.network_id = net.maze_id
                    ti_show.network_country = clean_data(net.country)
                    ti_show.network_country_code = clean_data(net.code)
                    ti_show.network_timezone = clean_data(net.timezone)
                    ti_show.network_is_stream = None is not c.show.web_channel
                ch.append(TVInfoCharacter(name=clean_data(c.character.name), ti_show=ti_show, episode_count=1))
        try:
            birthdate = tvmaze_person_obj.birthday and tz_p.parse(tvmaze_person_obj.birthday).date()
        except (BaseException, Exception):
            birthdate = None
        try:
            deathdate = tvmaze_person_obj.death_day and tz_p.parse(tvmaze_person_obj.death_day).date()
        except (BaseException, Exception):
            deathdate = None

        _ti_person_obj = TVInfoPerson(
            p_id=tvmaze_person_obj.id, name=clean_data(tvmaze_person_obj.name),
            image=tvmaze_person_obj.image and tvmaze_person_obj.image.get('original'),
            gender=PersonGenders.named.get(tvmaze_person_obj.gender and tvmaze_person_obj.gender.lower(),
                                           PersonGenders.unknown),
            birthdate=birthdate, deathdate=deathdate,
            country=tvmaze_person_obj.country and clean_data(tvmaze_person_obj.country.get('name')),
            country_code=tvmaze_person_obj.country and clean_data(tvmaze_person_obj.country.get('code')),
            country_timezone=tvmaze_person_obj.country and clean_data(tvmaze_person_obj.country.get('timezone')),
            thumb_url=tvmaze_person_obj.image and tvmaze_person_obj.image.get('medium'),
            url=tvmaze_person_obj.url, ids=TVInfoIDs(ids={TVINFO_TVMAZE: tvmaze_person_obj.id})
        )

        if load_credits:
            for (c_t, regular) in [(tvmaze_person_obj.castcredits or [], True),
                                   (tvmaze_person_obj.guestcastcredits or [], False)]:
                for c in c_t:  # type: tvmaze.CastCredit
                    _show = c.show or c.episode.show
                    _clean_char_name = clean_data(c.character.name)
                    ti_show = TVInfoShow()
                    if None is not _show:
                        _clean_show_name = clean_data(_show.name)
                        _clean_show_id = clean_data(_show.id)
                        _cur_dup = (_clean_char_name, _clean_show_id)
                        if _cur_dup in _dupes:
                            _co = next((_c for _c in ch if _clean_show_id == _c.ti_show.id
                                        and _c.name == _clean_char_name), None)
                            if None is not _co:
                                ti_show = _co.ti_show
                                _co.episode_count += 1
                                if not regular:
                                    ep_no = c.episode.episode_number or 0
                                    _co.guest_episodes_numbers.setdefault(c.episode.season_number, []).append(ep_no)
                                    if c.episode.season_number not in ti_show:
                                        season = TVInfoSeason(show=ti_show, number=c.episode.season_number)
                                        ti_show[c.episode.season_number] = season
                                    else:
                                        season = ti_show[c.episode.season_number]
                                    episode = self._make_episode(c.episode, show_obj=ti_show)
                                    episode.season = season
                                    ti_show[c.episode.season_number][ep_no] = episode
                            continue
                        else:
                            _dupes.append(_cur_dup)
                        ti_show.seriesname = clean_data(_show.name)
                        ti_show.id = _show.id
                        ti_show.firstaired = clean_data(_show.premiered)
                        ti_show.ids = TVInfoIDs(ids={TVINFO_TVMAZE: ti_show.id})
                        ti_show.overview = enforce_type(clean_data(_show.summary), str, '')
                        ti_show.status = clean_data(_show.status)
                        net = _show.network or _show.web_channel
                        if net:
                            ti_show.network = clean_data(net.name)
                            ti_show.network_id = net.maze_id
                            ti_show.network_country = clean_data(net.country)
                            ti_show.network_timezone = clean_data(net.timezone)
                            ti_show.network_country_code = clean_data(net.code)
                        ti_show.network_is_stream = None is not _show.web_channel
                        if c.episode:

                            ti_show.show_loaded = False
                            ti_show.load_method = self._show_info_loader
                            season = TVInfoSeason(show=ti_show, number=c.episode.season_number)
                            ti_show[c.episode.season_number] = season
                            episode = self._make_episode(c.episode, show_obj=ti_show)
                            episode.season = season
                            ti_show[c.episode.season_number][c.episode.episode_number or 0] = episode
                    if not regular:
                        _g_kw = {'guest_episodes_numbers': {c.episode.season_number: [c.episode.episode_number or 0]}}
                    else:
                        _g_kw = {}
                    ch.append(TVInfoCharacter(name=_clean_char_name, ti_show=ti_show, regular=regular, episode_count=1,
                                              person=[_ti_person_obj], **_g_kw))
            _ti_person_obj.characters = ch
        return _ti_person_obj

    def _show_info_loader(self, show_id, show_data=None, show_obj=None, load_images=True, load_actors=True):
        # type: (int, TVMazeShow, TVInfoShow, bool, bool) -> TVInfoShow
        try:
            _s_d = show_data or tvmaze.show_main_info(show_id, embed='cast')
            if _s_d:
                if None is not show_obj:
                    _s_o = show_obj
                else:
                    _s_o = TVInfoShow()
                show_dict = _s_o.__dict__
                for k, v in iteritems(show_dict):
                    if k not in ('cast', 'crew', 'images', 'aliases', 'rating'):
                        show_dict[k] = getattr(_s_d, show_map.get(k, k), clean_data(show_dict[k]))
                _s_o.aliases = [clean_data(a.name) for a in _s_d.akas]
                _s_o.runtime = _s_d.average_runtime or _s_d.runtime
                p_set = False
                if _s_d.image:
                    p_set = True
                    _s_o.poster = _s_d.image.get('original')
                    _s_o.poster_thumb = _s_d.image.get('medium')

                if load_images and \
                        not all(getattr(_s_o, '%s_loaded' % t, False) for t in ('poster', 'banner', 'fanart')):
                    if _s_d.images:
                        _s_o.poster_loaded = True
                        _s_o.banner_loaded = True
                        _s_o.fanart_loaded = True
                        self._set_images(_s_o, _s_d, p_set)

                if _s_d.schedule:
                    if 'time' in _s_d.schedule:
                        _s_o.airs_time = _s_d.schedule['time']
                        try:
                            h, m = _s_d.schedule['time'].split(':')
                            h, m = try_int(h, None), try_int(m, None)
                            if None is not h and None is not m:
                                _s_o.time = datetime.time(hour=h, minute=m)
                        except (BaseException, Exception):
                            pass
                    if 'days' in _s_d.schedule:
                        _s_o.airs_dayofweek = ', '.join(_s_d.schedule['days'])

                if load_actors and not _s_o.actors_loaded:
                    if _s_d.cast:
                        character_person_ids = {}
                        for cur_ch in _s_o.cast[RoleTypes.ActorMain]:
                            character_person_ids.setdefault(cur_ch.id, []).extend([p.id for p in cur_ch.person])
                        for cur_ch in _s_d.cast.characters:
                            existing_character = next(
                                (c for c in _s_o.cast[RoleTypes.ActorMain] if c.id == cur_ch.id),
                                None)  # type: Optional[TVInfoCharacter]
                            person = self._convert_person(cur_ch.person, load_credits=False)
                            if existing_character:
                                existing_person = next((p for p in existing_character.person
                                                        if person.id == p.ids.get(TVINFO_TVMAZE)),
                                                       None)  # type: TVInfoPerson
                                if existing_person:
                                    try:
                                        character_person_ids[cur_ch.id].remove(existing_person.id)
                                    except (BaseException, Exception):
                                        print('error')
                                        pass
                                    (existing_person.p_id, existing_person.name, existing_person.image,
                                     existing_person.gender,
                                     existing_person.birthdate, existing_person.deathdate, existing_person.country,
                                     existing_person.country_code, existing_person.country_timezone,
                                     existing_person.thumb_url,
                                     existing_person.url, existing_person.ids) = \
                                        (cur_ch.person.id, clean_data(cur_ch.person.name),
                                         cur_ch.person.image and cur_ch.person.image.get('original'),
                                         PersonGenders.named.get(
                                             cur_ch.person.gender and cur_ch.person.gender.lower(),
                                             PersonGenders.unknown),
                                         person.birthdate, person.deathdate,
                                         cur_ch.person.country and clean_data(cur_ch.person.country.get('name')),
                                         cur_ch.person.country and clean_data(cur_ch.person.country.get('code')),
                                         cur_ch.person.country and clean_data(cur_ch.person.country.get('timezone')),
                                         cur_ch.person.image and cur_ch.person.image.get('medium'),
                                         cur_ch.person.url, {TVINFO_TVMAZE: cur_ch.person.id})
                                else:
                                    existing_character.person.append(person)
                            else:
                                _s_o.cast[RoleTypes.ActorMain].append(
                                    TVInfoCharacter(image=cur_ch.image and cur_ch.image.get('original'),
                                                    name=clean_data(cur_ch.name),
                                                    ids=TVInfoIDs({TVINFO_TVMAZE: cur_ch.id}),
                                                    p_id=cur_ch.id, person=[person], plays_self=cur_ch.plays_self,
                                                    thumb_url=cur_ch.image and cur_ch.image.get('medium'),
                                                    ti_show=_s_o
                                                    ))

                        if character_person_ids:
                            for cur_ch, cur_p_ids in iteritems(character_person_ids):
                                if cur_p_ids:
                                    char = next((mc for mc in _s_o.cast[RoleTypes.ActorMain] if mc.id == cur_ch),
                                                None)  # type: Optional[TVInfoCharacter]
                                    if char:
                                        char.person = [p for p in char.person if p.id not in cur_p_ids]

                        if _s_d.cast:
                            _s_o.actors = [
                                {'character': {'id': ch.id,
                                               'name': clean_data(ch.name),
                                               'url': 'https://www.tvmaze.com/character/view?id=%s' % ch.id,
                                               'image': ch.image and ch.image.get('original'),
                                               },
                                 'person': {'id': ch.person and ch.person.id,
                                            'name': ch.person and clean_data(ch.person.name),
                                            'url': ch.person and 'https://www.tvmaze.com/person/view?id=%s' % ch.person.id,
                                            'image': ch.person and ch.person.image and ch.person.image.get('original'),
                                            'birthday': None,  # not sure about format
                                            'deathday': None,  # not sure about format
                                            'gender': ch.person and ch.person.gender and ch.person.gender,
                                            'country': ch.person and ch.person.country and
                                                       clean_data(ch.person.country.get('name')),
                                            },
                                 } for ch in _s_d.cast.characters]

                    if _s_d.crew:
                        for cur_cw in _s_d.crew:
                            rt = crew_type_names.get(cur_cw.type.lower(), RoleTypes.CrewOther)
                            _s_o.crew[rt].append(
                                Crew(p_id=cur_cw.person.id, name=clean_data(cur_cw.person.name),
                                     image=cur_cw.person.image and cur_cw.person.image.get('original'),
                                     gender=cur_cw.person.gender,
                                     birthdate=cur_cw.person.birthday, deathdate=cur_cw.person.death_day,
                                     country=cur_cw.person.country and cur_cw.person.country.get('name'),
                                     country_code=cur_cw.person.country and clean_data(
                                         cur_cw.person.country.get('code')),
                                     country_timezone=cur_cw.person.country
                                                      and clean_data(cur_cw.person.country.get('timezone')),
                                     crew_type_name=cur_cw.type,
                                     )
                            )

                if _s_d.externals:
                    _s_o.ids = TVInfoIDs(tvdb=_s_d.externals.get('thetvdb'),
                                         rage=_s_d.externals.get('tvrage'),
                                         imdb=clean_data(_s_d.externals.get('imdb') and
                                                         try_int(_s_d.externals.get('imdb').replace('tt', ''),
                                                                 None)))

                if _s_d.network:
                    self._set_network(_s_o, _s_d.network, False)
                elif _s_d.web_channel:
                    self._set_network(_s_o, _s_d.web_channel, True)

                return _s_o
        except (BaseException, Exception):
            pass

    def _search_person(self, name=None, ids=None):
        # type: (AnyStr, Dict[integer_types, integer_types]) -> List[TVInfoPerson]
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
        # type: (integer_types, bool, bool, Any) -> Optional[TVInfoPerson]
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

    def get_premieres(self, **kwargs):
        # type: (...) -> List[TVInfoShow]
        return [_e.show for _e in self._filtered_schedule(**kwargs).get('premieres')]

    def get_returning(self, **kwargs):
        # type: (...) -> List[TVInfoShow]
        return [_e.show for _e in self._filtered_schedule(**kwargs).get('returning')]

    def _make_episode(self, episode_data, show_data=None, get_images=False, get_akas=False, show_obj=None):
        # type: (TVMazeEpisode, TVMazeShow, bool, bool, TVInfoShow) -> TVInfoEpisode
        """
        make out of TVMazeEpisode object and optionally TVMazeShow a TVInfoEpisode
        """
        if None is not show_obj:
            ti_show = show_obj
        else:
            ti_show = TVInfoShow()
            ti_show.seriesname = clean_data(show_data.name)
            ti_show.id = show_data.maze_id
            ti_show.seriesid = ti_show.id
            ti_show.language = clean_data(show_data.language)
            ti_show.overview = enforce_type(clean_data(show_data.summary), str, '')
            ti_show.firstaired = clean_data(show_data.premiered)
            ti_show.runtime = show_data.average_runtime or show_data.runtime
            ti_show.vote_average = show_data.rating and show_data.rating.get('average')
            ti_show.rating = ti_show.vote_average
            ti_show.popularity = show_data.weight
            ti_show.genre_list = clean_data(show_data.genres or [])
            ti_show.genre = '|'.join(ti_show.genre_list).lower()
            ti_show.official_site = clean_data(show_data.official_site)
            ti_show.status = clean_data(show_data.status)
            ti_show.show_type = clean_data((isinstance(show_data.type, string_types) and [show_data.type.lower()] or
                                            isinstance(show_data.type, list) and [x.lower() for x in show_data.type] or []))
            ti_show.lastupdated = show_data.updated
            ti_show.poster = show_data.image and show_data.image.get('original')
            if get_akas:
                ti_show.aliases = [clean_data(a.name) for a in show_data.akas]
            if show_data.schedule and 'days' in show_data.schedule:
                ti_show.airs_dayofweek = ', '.join(clean_data(show_data.schedule['days']))
            network = show_data.network or show_data.web_channel
            if network:
                ti_show.network_is_stream = None is not show_data.web_channel
                ti_show.network = clean_data(network.name)
                ti_show.network_id = network.maze_id
                ti_show.network_country = clean_data(network.country)
                ti_show.network_country_code = clean_data(network.code)
                ti_show.network_timezone = clean_data(network.timezone)
            if get_images and show_data.images:
                self._set_images(ti_show, show_data, False)
            ti_show.ids = TVInfoIDs(
                tvdb=show_data.externals.get('thetvdb'), rage=show_data.externals.get('tvrage'), tvmaze=show_data.id,
                imdb=clean_data(show_data.externals.get('imdb') and
                                try_int(show_data.externals.get('imdb').replace('tt', ''), None)))
            ti_show.imdb_id = clean_data(show_data.externals.get('imdb'))
            if isinstance(ti_show.imdb_id, integer_types):
                ti_show.imdb_id = 'tt%07d' % ti_show.imdb_id

        ti_episode = TVInfoEpisode(show=ti_show)
        ti_episode.id = episode_data.maze_id
        ti_episode.seasonnumber = episode_data.season_number
        ti_episode.episodenumber = episode_data.episode_number or 0
        ti_episode.episodename = clean_data(episode_data.title)
        try:
            ti_episode.airtime = datetime.time.fromisoformat(clean_data(episode_data.airtime))
        except (BaseException, Exception):
            ti_episode.airtime = None
        ti_episode.firstaired = clean_data(episode_data.airdate)
        if episode_data.airstamp:
            try:
                at = _datetime_to_timestamp(tz_p.parse(episode_data.airstamp))
                ti_episode.timestamp = at
            except (BaseException, Exception):
                pass
        ti_episode.filename = episode_data.image and (episode_data.image.get('original') or
                                                      episode_data.image.get('medium'))
        ti_episode.is_special = episode_data.is_special()
        ti_episode.overview = enforce_type(clean_data(episode_data.summary), str, '')
        ti_episode.runtime = episode_data.runtime
        if ti_episode.seasonnumber not in ti_show:
            season = TVInfoSeason(show=ti_show, number=ti_episode.seasonnumber)
            ti_show[ti_episode.seasonnumber] = season
            ti_episode.season = season
        ti_show[ti_episode.seasonnumber][ti_episode.episodenumber] = ti_episode
        return ti_episode

    def _filtered_schedule(self, **kwargs):
        cache_name_key = 'tvmaze_schedule'
        is_none, schedule = self._get_cache_entry(cache_name_key)
        if None is schedule and not is_none:
            schedule = []
            try:
                schedule = tvmaze.get_full_schedule()
            except(BaseException, Exception):
                pass

            premieres = []
            returning = []
            rc_lang = re.compile('(?i)eng|jap')
            for cur_show in filter(lambda s: 1 == s.episode_number and (
                    None is s.show.language or rc_lang.search(s.show.language)), schedule):
                if 1 == cur_show.season_number:
                    premieres += [cur_show]
                else:
                    returning += [cur_show]

            premieres = [self._make_episode(r, r.show, **kwargs)
                         for r in sorted(premieres, key=lambda e: e.show.premiered)]
            returning = [self._make_episode(r, r.show, **kwargs)
                         for r in sorted(returning, key=lambda e: e.airstamp)]

            schedule = dict(premieres=premieres, returning=returning)
            self._set_cache_entry(cache_name_key, schedule, expire=self.schedule_cache_expire)

        return schedule
