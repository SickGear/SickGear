import datetime
import logging
import re
from .exceptions import TraktException, TraktAuthException, TraktMethodNotExisting
from exceptions_helper import ConnectionSkipException, ex
from six import iteritems
from .trakt import TraktAPI
from lib.tvinfo_base.exceptions import BaseTVinfoShownotfound
from lib.tvinfo_base import PersonGenders, TVInfoBase, TVINFO_TRAKT, TVINFO_TMDB, TVINFO_TVDB, TVINFO_TVRAGE, TVINFO_IMDB, \
    TVINFO_SLUG, TVInfoPerson, TVINFO_TWITTER, TVINFO_FACEBOOK, TVINFO_WIKIPEDIA, TVINFO_INSTAGRAM, TVInfoCharacter, \
    TVInfoShow, TVInfoIDs, TVInfoSocialIDs, TVINFO_TRAKT_SLUG, TVInfoEpisode, TVInfoSeason, RoleTypes
from sg_helpers import clean_data, enforce_type, try_int
from lib.dateutil.parser import parser

# noinspection PyUnreachableCode
if False:
    from typing import Any, AnyStr, Dict, List, Optional, Union
    from six import integer_types

id_map = {
    'trakt': TVINFO_TRAKT,
    'slug': TVINFO_SLUG,
    'tvdb': TVINFO_TVDB,
    'imdb': TVINFO_IMDB,
    'tmdb': TVINFO_TMDB,
    'tvrage': TVINFO_TVRAGE
}

id_map_reverse = {v: k for k, v in iteritems(id_map)}

tz_p = parser()
log = logging.getLogger('api_trakt.api')
log.addHandler(logging.NullHandler())


def _convert_imdb_id(src, s_id):
    # type: (int, integer_types) -> integer_types
    if TVINFO_IMDB == src:
        try:
            return try_int(re.search(r'(\d+)', s_id).group(1), s_id)
        except (BaseException, Exception):
            pass
    return s_id


class TraktSearchTypes(object):
    text = 1
    trakt_id = 'trakt'
    trakt_slug = 'trakt_slug'
    tvdb_id = 'tvdb'
    imdb_id = 'imdb'
    tmdb_id = 'tmdb'
    tvrage_id = 'tvrage'
    all = [text, trakt_id, tvdb_id, imdb_id, tmdb_id, tvrage_id, trakt_slug]

    def __init__(self):
        pass


map_id_search = {TVINFO_TVDB: TraktSearchTypes.tvdb_id, TVINFO_IMDB: TraktSearchTypes.imdb_id,
                 TVINFO_TMDB: TraktSearchTypes.tmdb_id, TVINFO_TRAKT: TraktSearchTypes.trakt_id,
                 TVINFO_TRAKT_SLUG: TraktSearchTypes.trakt_slug}


class TraktResultTypes(object):
    show = 'show'
    episode = 'episode'
    movie = 'movie'
    person = 'person'
    list = 'list'
    all = [show, episode, movie, person, list]

    def __init__(self):
        pass


class TraktIndexer(TVInfoBase):
    supported_id_searches = [TVINFO_TVDB, TVINFO_IMDB, TVINFO_TMDB, TVINFO_TRAKT, TVINFO_TRAKT_SLUG]
    supported_person_id_searches = [TVINFO_TRAKT, TVINFO_IMDB, TVINFO_TMDB]

    # noinspection PyUnusedLocal
    # noinspection PyDefaultArgument
    def __init__(self, custom_ui=None, sleep_retry=None, search_type=TraktSearchTypes.text,
                 result_types=[TraktResultTypes.show], *args, **kwargs):
        super(TraktIndexer, self).__init__(*args, **kwargs)
        self.config.update({
            'apikey': '',
            'debug_enabled': False,
            'custom_ui': custom_ui,
            'proxy': None,
            'cache_enabled': False,
            'cache_location': '',
            'valid_languages': [],
            'langabbv_to_id': {},
            'language': 'en',
            'base_url': '',
            'search_type': search_type if search_type in TraktSearchTypes.all else TraktSearchTypes.text,
            'sleep_retry': sleep_retry,
            'result_types': result_types if isinstance(result_types, list) and all(
                [x in TraktResultTypes.all for x in result_types]) else [TraktResultTypes.show],
        })

    @staticmethod
    def _make_result_obj(shows, results):
        # type: (List[Dict], List[TVInfoShow]) -> None
        if shows:
            try:
                for s in shows:
                    if s['ids']['trakt'] not in [i['ids'].trakt for i in results]:
                        ti_show = TVInfoShow()
                        countries = clean_data(s['country'])
                        if countries:
                            countries = [countries]
                        else:
                            countries = []
                        ti_show.id, ti_show.seriesname, ti_show.overview, ti_show.firstaired, ti_show.airs_dayofweek, \
                            ti_show.runtime, ti_show.network, ti_show.origin_countries, ti_show.official_site, \
                            ti_show.status, ti_show.rating, ti_show.genre_list, ti_show.ids = s['ids']['trakt'], \
                            clean_data(s['title']), enforce_type(clean_data(s['overview']), str, ''), s['firstaired'], \
                            (isinstance(s['airs'], dict) and s['airs']['day']) or '', \
                            s['runtime'], s['network'], countries, s['homepage'], s['status'], s['rating'], \
                            s['genres_list'], \
                            TVInfoIDs(trakt=s['ids']['trakt'], tvdb=s['ids']['tvdb'], tmdb=s['ids']['tmdb'],
                                      rage=s['ids']['tvrage'],
                                      imdb=s['ids']['imdb'] and try_int(s['ids']['imdb'].replace('tt', ''), None))
                        ti_show.genre = '|'.join(ti_show.genre_list or [])
                        results.append(ti_show)
            except (BaseException, Exception) as e:
                log.debug('Error creating result dict: %s' % ex(e))

    def _search_show(self, name=None, ids=None, **kwargs):
        # type: (AnyStr, Dict[integer_types, integer_types], Optional[Any]) -> List[TVInfoShow]
        """This searches Trakt for the series name,
        If a custom_ui UI is configured, it uses this to select the correct
        series.
        """
        results = []  # type: List[TVInfoShow]
        if ids:
            for t, p in iteritems(ids):
                if t in self.supported_id_searches:
                    if t in (TVINFO_TVDB, TVINFO_IMDB, TVINFO_TMDB, TVINFO_TRAKT, TVINFO_TRAKT_SLUG):
                        cache_id_key = 's-id-%s-%s' % (t, p)
                        is_none, shows = self._get_cache_entry(cache_id_key)
                        if not self.config.get('cache_search') or (None is shows and not is_none):
                            try:
                                show = self.search(p, search_type=map_id_search[t])
                            except (BaseException, Exception):
                                continue
                            self._set_cache_entry(cache_id_key, show, expire=self.search_cache_expire)
                        else:
                            show = shows
                    else:
                        continue
                    self._make_result_obj(show, results)
        if name:
            names = ([name], name)[isinstance(name, list)]
            len_names = len(names)
            for i, n in enumerate(names, 1):
                cache_name_key = 's-name-%s' % n
                is_none, shows = self._get_cache_entry(cache_name_key)
                if not self.config.get('cache_search') or (None is shows and not is_none):
                    try:
                        all_series = self.search(n)
                        self._set_cache_entry(cache_name_key, all_series, expire=self.search_cache_expire)
                    except (BaseException, Exception):
                        all_series = []
                else:
                    all_series = shows
                if not isinstance(all_series, list):
                    all_series = [all_series]

                if i == len_names and 0 == len(all_series) and not results:
                    log.debug('Series result returned zero')
                    raise BaseTVinfoShownotfound('Show-name search returned zero results (cannot find show on TVDB)')

                if all_series:
                    if None is not self.config['custom_ui']:
                        log.debug('Using custom UI %s' % self.config['custom_ui'].__name__)
                        custom_ui = self.config['custom_ui']
                        ui = custom_ui(config=self.config)
                        self._make_result_obj(ui.select_series(all_series), results)

                    else:
                        self._make_result_obj(all_series, results)

        final_result = []  # type: List[TVInfoShow]
        seen = set()
        film_type = re.compile(r'(?i)films?\)$')
        for r in results:
            if r.id not in seen:
                seen.add(r.id)
                title = r.seriesname or ''
                if not film_type.search(title):
                    final_result.append(r)
                else:
                    log.debug('Search result ignored: %s ' % title)

        return final_result

    @staticmethod
    def _dict_prevent_none(d, key, default):
        v = None
        if isinstance(d, dict):
            v = d.get(key, default)
        return (v, default)[None is v]

    def search(self, series, search_type=None):
        # type: (AnyStr, Union[int, AnyStr]) -> List
        search_type = search_type or self.config['search_type']
        if TraktSearchTypes.trakt_slug == search_type:
            url = '/shows/%s?extended=full' % series
        elif TraktSearchTypes.text != search_type:
            url = '/search/%s/%s?type=%s&extended=full&limit=100' % (search_type, (series, 'tt%07d' % series)[
                TraktSearchTypes.imdb_id == search_type and not str(series).startswith('tt')],
                                                                     ','.join(self.config['result_types']))
        else:
            url = '/search/%s?query=%s&extended=full&limit=100' % (','.join(self.config['result_types']), series)
        filtered = []
        kwargs = {}
        if None is not self.config['sleep_retry']:
            kwargs['sleep_retry'] = self.config['sleep_retry']
        try:
            from sickgear.helpers import clean_data
            resp = TraktAPI().trakt_request(url, **kwargs)
            if len(resp):
                if isinstance(resp, dict):
                    resp = [{'type': 'show', 'score': 1, 'show': resp}]
                for d in resp:
                    if isinstance(d, dict) and 'type' in d and d['type'] in self.config['result_types']:
                        for k, v in iteritems(d):
                            d[k] = clean_data(v)
                        if 'show' in d and TraktResultTypes.show == d['type']:
                            d.update(d['show'])
                            del d['show']
                            d['seriesname'] = self._dict_prevent_none(d, 'title', '')
                            d['genres_list'] = d.get('genres', [])
                            d['genres'] = ', '.join(['%s' % v for v in d.get('genres', []) or [] if v])
                            d['firstaired'] = (d.get('first_aired') and
                                               re.sub(r'T.*$', '', str(d.get('first_aired'))) or d.get('year'))
                        filtered.append(d)
        except (ConnectionSkipException, TraktException) as e:
            log.debug('Could not connect to Trakt service: %s' % ex(e))

        return filtered

    @staticmethod
    def _convert_person_obj(person_obj):
        # type: (Dict) -> TVInfoPerson
        try:
            birthdate = person_obj['birthday'] and tz_p.parse(person_obj['birthday']).date()
        except (BaseException, Exception):
            birthdate = None
        try:
            deathdate = person_obj['death'] and tz_p.parse(person_obj['death']).date()
        except (BaseException, Exception):
            deathdate = None

        return TVInfoPerson(p_id=person_obj['ids']['trakt'],
                            name=person_obj['name'],
                            bio=person_obj['biography'],
                            birthdate=birthdate,
                            deathdate=deathdate,
                            homepage=person_obj['homepage'],
                            birthplace=person_obj['birthplace'],
                            gender=PersonGenders.trakt_map.get(person_obj['gender'], PersonGenders.unknown),
                            social_ids=TVInfoSocialIDs(
                                ids={TVINFO_TWITTER: person_obj['social_ids']['twitter'],
                                     TVINFO_FACEBOOK: person_obj['social_ids']['facebook'],
                                     TVINFO_INSTAGRAM: person_obj['social_ids']['instagram'],
                                     TVINFO_WIKIPEDIA: person_obj['social_ids']['wikipedia']
                                     }),
                            ids=TVInfoIDs(ids={
                                TVINFO_TRAKT: person_obj['ids']['trakt'], TVINFO_SLUG: person_obj['ids']['slug'],
                                TVINFO_IMDB:
                                    person_obj['ids']['imdb'] and
                                    try_int(person_obj['ids']['imdb'].replace('nm', ''), None),
                                TVINFO_TMDB: person_obj['ids']['tmdb'],
                                TVINFO_TVRAGE: person_obj['ids']['tvrage']}))

    def get_person(self, p_id, get_show_credits=False, get_images=False, **kwargs):
        # type: (integer_types, bool, bool, Any) -> Optional[TVInfoPerson]
        """
        get person's data for id or list of matching persons for name

        :param p_id: persons id
        :param get_show_credits: get show credits (only for native id)
        :param get_images: get images for person
        :return: person object
        """
        if not p_id:
            return

        urls = [('/people/%s?extended=full' % p_id, False)]
        if get_show_credits:
            urls.append(('/people/%s/shows?extended=full' % p_id, True))

        if not urls:
            return

        result = None  # type: Optional[TVInfoPerson]

        for url, show_credits in urls:
            try:
                cache_key_name = 'p-%s-%s' % (('main', 'credits')[show_credits], p_id)
                is_none, resp = self._get_cache_entry(cache_key_name)
                if None is resp and not is_none:
                    resp = TraktAPI().trakt_request(url, **kwargs)
                    self._set_cache_entry(cache_key_name, resp)
                if resp:
                    if show_credits:
                        pc = []
                        clean_lower_person_name = (result.name or '').lower()
                        for c in resp.get('cast') or []:
                            ti_show = TVInfoShow()
                            ti_show.id = c['show']['ids'].get('trakt')
                            ti_show.seriesname = c['show']['title']
                            ti_show.ids = TVInfoIDs(ids={id_map[src]: _convert_imdb_id(id_map[src], sid)
                                                         for src, sid in iteritems(c['show']['ids']) if src in id_map})
                            ti_show.network = c['show']['network']
                            ti_show.firstaired = c['show']['first_aired']
                            ti_show.overview = enforce_type(clean_data(c['show']['overview']), str, '')
                            ti_show.status = c['show']['status']
                            ti_show.imdb_id = c['show']['ids'].get('imdb')
                            ti_show.runtime = c['show']['runtime']
                            ti_show.genre_list = c['show']['genres']
                            ti_show.slug = c['show'].get('ids', {}).get('slug')
                            ti_show.language = c['show'].get('language')
                            ti_show.network_country = c['show'].get('country')
                            ti_show.rating = c['show'].get('rating')
                            ti_show.vote_count = c['show'].get('votes')
                            for ch in c.get('characters') or []:
                                clean_ch = clean_data(ch)
                                _ti_character = TVInfoCharacter(
                                    name=clean_ch, regular=c.get('series_regular'), ti_show=ti_show, person=[result],
                                    episode_count=c.get('episode_count'),
                                    plays_self=enforce_type((clean_ch or '').lower() in
                                                            ('self', clean_lower_person_name), bool, False))
                                pc.append(_ti_character)
                                ti_show.cast[(RoleTypes.ActorGuest, RoleTypes.ActorMain)[
                                    c.get('series_regular', False)]].append(_ti_character)
                        result.characters = pc
                    else:
                        result = self._convert_person_obj(resp)
            except ConnectionSkipException as e:
                raise e
            except TraktMethodNotExisting:
                log.debug(f'Person id doesn\'t exist: {p_id}')
            except TraktException as e:
                log.debug('Could not connect to Trakt service: {ex(e)}')
        return result

    def _search_person(self, name=None, ids=None):
        # type: (AnyStr, Dict[integer_types, integer_types]) -> List[TVInfoPerson]
        urls, result, ids = [], [], ids or {}
        for tv_src in self.supported_person_id_searches:
            if tv_src in ids:
                if TVINFO_TRAKT == tv_src:
                    url = '/people/%s?extended=full' % ids.get(tv_src)
                elif tv_src in (TVINFO_IMDB, TVINFO_TMDB):
                    url = '/search/%s/%s?type=person&extended=full&limit=100' % \
                          (id_map_reverse[tv_src], (ids.get(tv_src), 'nm%07d' % ids.get(tv_src))[TVINFO_IMDB == tv_src])
                else:
                    continue
                urls.append((tv_src, ids.get(tv_src), url))
        if name:
            urls.append(('text', name, '/search/person?query=%s&extended=full&limit=100' % name))

        for src, s_id, url in urls:
            try:
                cache_key_name = 'p-src-%s-%s' % (src, s_id)
                is_none, resp = self._get_cache_entry(cache_key_name)
                if None is resp and not is_none:
                    resp = TraktAPI().trakt_request(url)
                    self._set_cache_entry(cache_key_name, resp)
                if resp:
                    for per in (resp, [{'person': resp, 'type': 'person'}])[url.startswith('/people')]:
                        if 'person' != per['type']:
                            continue
                        person = per['person']
                        if not any(1 for p in result if person['ids']['trakt'] == p.id):
                            result.append(self._convert_person_obj(person))
            except ConnectionSkipException as e:
                raise e
            except TraktException as e:
                log.debug('Could not connect to Trakt service: %s' % ex(e))

        return result

    @staticmethod
    def _convert_episode(episode_data, show_obj, season_obj):
        # type: (Dict, TVInfoShow, TVInfoSeason) -> TVInfoEpisode
        ti_episode = TVInfoEpisode(show=show_obj)
        ti_episode.season = season_obj
        ti_episode.id, ti_episode.episodename, ti_episode.seasonnumber, ti_episode.episodenumber, \
            ti_episode.absolute_number, ti_episode.overview, ti_episode.firstaired, ti_episode.runtime, \
            ti_episode.rating, ti_episode.vote_count = episode_data.get('ids', {}).get('trakt'), \
            clean_data(episode_data.get('title')), episode_data.get('season'), episode_data.get('number'), \
            episode_data.get('number_abs'), enforce_type(clean_data(episode_data.get('overview')), str, ''), \
            re.sub('T.+$', '', episode_data.get('first_aired') or ''), \
            episode_data['runtime'], episode_data.get('rating'), episode_data.get('votes')
        if episode_data.get('available_translations'):
            ti_episode.language = clean_data(episode_data['available_translations'][0])
        ti_episode.ids = TVInfoIDs(ids={id_map[src]: _convert_imdb_id(id_map[src], sid)
                                   for src, sid in iteritems(episode_data['ids']) if src in id_map})
        return ti_episode

    @staticmethod
    def _convert_show(show_data):
        # type: (Dict) -> TVInfoShow
        _s_d = (show_data, show_data.get('show'))['show' in show_data]
        ti_show = TVInfoShow()
        ti_show.seriesname, ti_show.id, ti_show.firstaired, ti_show.overview, ti_show.runtime, ti_show.network, \
            ti_show.network_country, ti_show.status, ti_show.genre_list, ti_show.language, ti_show.watcher_count, \
            ti_show.play_count, ti_show.collected_count, ti_show.collector_count, ti_show.vote_count, \
            ti_show.vote_average, ti_show.rating, ti_show.contentrating, ti_show.official_site, ti_show.slug = \
            clean_data(_s_d['title']), _s_d['ids']['trakt'], \
            re.sub('T.+$', '', _s_d.get('first_aired') or '') or _s_d.get('year'), \
            enforce_type(clean_data(_s_d.get('overview')), str, ''), _s_d.get('runtime'), _s_d.get('network'), \
            _s_d.get('country'), _s_d.get('status'), _s_d.get('genres', []), _s_d.get('language'), \
            show_data.get('watcher_count'), show_data.get('play_count'), show_data.get('collected_count'), \
            show_data.get('collector_count'), _s_d.get('votes'), _s_d.get('rating'), _s_d.get('rating'), \
            _s_d.get('certification'), _s_d.get('homepage'), _s_d['ids']['slug']
        ti_show.ids = TVInfoIDs(ids={id_map[src]: _convert_imdb_id(id_map[src], sid)
                                for src, sid in iteritems(_s_d['ids']) if src in id_map})
        ti_show.genre = '|'.join(ti_show.genre_list or [])
        if _s_d.get('trailer'):
            ti_show.trailers = {'any': _s_d['trailer']}
        if 'episode' in show_data:
            ep_data = show_data['episode']
            ti_show.next_season_airdate = re.sub('T.+$', '', ep_data.get('first_aired') or '')
            ti_season = TVInfoSeason(show=ti_show)
            ti_season.number = ep_data['season']
            ti_season[ep_data['number']] = TraktIndexer._convert_episode(ep_data, ti_show, ti_season)
            ti_show[ep_data['season']] = ti_season
        return ti_show

    def _get_show_lists(self, url, account=None):
        # type: (str, Any) -> List[TVInfoShow]
        result = []
        if account:
            from sickgear import TRAKT_ACCOUNTS
            if account in TRAKT_ACCOUNTS and TRAKT_ACCOUNTS[account].active:
                kw = {'send_oauth': account}
            else:
                raise TraktAuthException('Account missing or disabled')
        else:
            kw = {}
        resp = TraktAPI().trakt_request(url, **kw)
        if resp:
            for _show in resp:
                result.append(self._convert_show(_show))
        return result

    def get_most_played(self, result_count=100, period='weekly', **kwargs):
        # type: (...) -> List[TVInfoShow]
        """
        get most played shows
        :param period: possible values: 'daily', 'weekly', 'monthly', 'yearly', 'all'
        :param result_count: how many results are suppose to be returned
        """
        use_period = ('weekly', period)[period in ('daily', 'weekly', 'monthly', 'yearly', 'all')]
        return self._get_show_lists('shows/played/%s?extended=full&page=%d&limit=%d' % (use_period, 1, result_count))

    def get_most_watched(self, result_count=100, period='weekly', **kwargs):
        # type: (...) -> List[TVInfoShow]
        """
        get most watched shows
        :param period: possible values: 'daily', 'weekly', 'monthly', 'yearly', 'all'
        :param result_count: how many results are suppose to be returned
        """
        use_period = ('weekly', period)[period in ('daily', 'weekly', 'monthly', 'yearly', 'all')]
        return self._get_show_lists('shows/watched/%s?extended=full&page=%d&limit=%d' % (use_period, 1, result_count))

    def get_most_collected(self, result_count=100, period='weekly', **kwargs):
        # type: (...) -> List[TVInfoShow]
        """
        get most collected shows
        :param period: possible values: 'daily', 'weekly', 'monthly', 'yearly', 'all'
        :param result_count: how many results are suppose to be returned
        """
        use_period = ('weekly', period)[period in ('daily', 'weekly', 'monthly', 'yearly', 'all')]
        return self._get_show_lists('shows/collected/%s?extended=full&page=%d&limit=%d' % (use_period, 1, result_count))

    def get_recommended(self, result_count=100, period='weekly', **kwargs):
        # type: (...) -> List[TVInfoShow]
        """
        get most recommended shows
        :param period: possible values: 'daily', 'weekly', 'monthly', 'yearly', 'all'
        :param result_count: how many results are suppose to be returned
        """
        use_period = ('weekly', period)[period in ('daily', 'weekly', 'monthly', 'yearly', 'all')]
        return self._get_show_lists('shows/recommended/%s?extended=full&page=%d&limit=%d' % (use_period, 1, result_count))

    def get_recommended_for_account(self, account, result_count=100, ignore_collected=False, ignore_watchlisted=False,
                                    **kwargs):
        # type: (...) -> List[TVInfoShow]
        """
        get most recommended shows for account
        :param account: account to get recommendations for
        :param result_count: how many results are suppose to be returned
        :param ignore_collected: exclude colleded shows
        :param ignore_watchlisted: exclude watchlisted shows
        """
        from sickgear import TRAKT_ACCOUNTS
        if not account or account not in TRAKT_ACCOUNTS or not TRAKT_ACCOUNTS[account].active:
            raise TraktAuthException('Account missing or disabled')
        extra_param = []
        if ignore_collected:
            extra_param.append('ignore_collected=true')
        if ignore_watchlisted:
            extra_param.append('ignore_watchlisted=true')
        return self._get_show_lists('recommendations/shows?extended=full&page=%d&limit=%d%s' %
                                    (1, result_count, ('', '&%s' % '&'.join(extra_param))[0 < len(extra_param)]),
                                    account=account)

    def hide_recommended_for_account(self, account, show_ids, **kwargs):
        # type: (integer_types, List[integer_types], Any) -> List[integer_types]
        """
        hide recommended show for account
        :param account: account to get recommendations for
        :param show_ids: list of show_ids to no longer recommend for account
        :return: list of added ids
        """
        from sickgear import TRAKT_ACCOUNTS
        if not account or account not in TRAKT_ACCOUNTS or not TRAKT_ACCOUNTS[account].active:
            raise TraktAuthException('Account missing or disabled')
        if not isinstance(show_ids, list) or not show_ids or any(not isinstance(_i, int) for _i in show_ids):
            raise TraktException('list of show_ids (trakt id) required')
        resp = TraktAPI().trakt_request('users/hidden/recommendations', send_oauth=account,
                                        data={'shows': [{'ids': {'trakt': _i}} for _i in show_ids]})
        if resp and isinstance(resp, dict) and 'added' in resp and 'shows' in resp['added']:
            if len(show_ids) == resp['added']['shows']:
                return show_ids
            if 'not_found' in resp and 'shows' in resp['not_found']:
                not_found = [_i['ids']['trakt'] for _i in resp['not_found']['shows']]
            else:
                not_found = []
            return [_i for _i in show_ids if _i not in not_found]
        return []

    def unhide_recommended_for_account(self, account, show_ids, **kwargs):
        # type: (integer_types, List[integer_types], Any) -> List[integer_types]
        """
        unhide recommended show for account
        :param account: account to get recommendations for
        :param show_ids: list of show_ids to be included in possible recommend for account
        :return: list of removed ids
        """
        from sickgear import TRAKT_ACCOUNTS
        if not account or account not in TRAKT_ACCOUNTS or not TRAKT_ACCOUNTS[account].active:
            raise TraktAuthException('Account missing or disabled')
        if not isinstance(show_ids, list) or not show_ids or any(not isinstance(_i, int) for _i in show_ids):
            raise TraktException('list of show_ids (trakt id) required')
        resp = TraktAPI().trakt_request('users/hidden/recommendations/remove', send_oauth=account,
                                        data={'shows': [{'ids': {'trakt': _i}} for _i in show_ids]})
        if resp and isinstance(resp, dict) and 'deleted' in resp and 'shows' in resp['deleted']:
            if len(show_ids) == resp['deleted']['shows']:
                return show_ids
            if 'not_found' in resp and 'shows' in resp['not_found']:
                not_found = [_i['ids']['trakt'] for _i in resp['not_found']['shows']]
            else:
                not_found = []
            return [_i for _i in show_ids if _i not in not_found]
        return []

    def list_hidden_recommended_for_account(self, account, **kwargs):
        # type: (integer_types, Any) -> List[TVInfoShow]
        """
        list hidden recommended show for account
        :param account: account to get recommendations for
        :return: list of hidden shows
        """
        from sickgear import TRAKT_ACCOUNTS
        if not account or account not in TRAKT_ACCOUNTS or not TRAKT_ACCOUNTS[account].active:
            raise TraktAuthException('Account missing or disabled')
        return self._get_show_lists('users/hidden/recommendations?type=show', account=account)

    def get_watchlisted_for_account(self, account, result_count=100, sort='rank', **kwargs):
        # type: (...) -> List[TVInfoShow]
        """
        get watchlisted shows for the account
        :param account: account to get recommendations for
        :param result_count: how many results are suppose to be returned
        :param sort: possible values: 'rank', 'added', 'released', 'title'
        """
        from sickgear import TRAKT_ACCOUNTS
        if not account or account not in TRAKT_ACCOUNTS or not TRAKT_ACCOUNTS[account].active:
            raise TraktAuthException('Account missing or disabled')
        sort = ('rank', sort)[sort in ('rank', 'added', 'released', 'title')]
        return self._get_show_lists('users/%s/watchlist/shows/%s?extended=full&page=%d&limit=%d' %
                                    (TRAKT_ACCOUNTS[account].slug, sort, 1, result_count), account=account)

    def get_anticipated(self, result_count=100, **kwargs):
        # type: (...) -> List[TVInfoShow]
        """
        get most anticipated shows
        :param result_count: how many results are suppose to be returned
        """
        return self._get_show_lists('shows/anticipated?extended=full&page=%d&limit=%d' % (1, result_count))

    def get_trending(self, result_count=100, **kwargs):
        # type: (...) -> List[TVInfoShow]
        """
        get trending shows
        :param result_count: how many results are suppose to be returned
        """
        return self._get_show_lists('shows/trending?extended=full&page=%d&limit=%d' % (1, result_count))

    def get_popular(self, result_count=100, **kwargs):
        # type: (...) -> List[TVInfoShow]
        """
        get all popular shows
        :param result_count: how many results are suppose to be returned
        """
        return self._get_show_lists('shows/popular?extended=full&page=%d&limit=%d' % (1, result_count))

    def get_similar(self, tvid, result_count=100, **kwargs):
        # type: (integer_types, int, Any) -> List[TVInfoShow]
        """
        return list of similar shows to given id
        :param tvid: id to give similar shows for
        :param result_count: count of results requested
        """
        if not isinstance(tvid, int):
            raise TraktException('tvid/trakt id for show required')
        return self._get_show_lists('shows/%d/related?extended=full&page=%d&limit=%d' % (tvid, 1, result_count))

    def get_new_shows(self, result_count=100, start_date=None, days=32, **kwargs):
        # type: (...) -> List[TVInfoShow]
        """
        get new shows
        :param result_count: how many results are suppose to be returned
        :param start_date: start date for returned data in format: '2014-09-01'
        :param days: number of days to return from start date
        """
        if None is start_date:
            start_date = (datetime.datetime.now() + datetime.timedelta(days=-16)).strftime('%Y-%m-%d')
        return self._get_show_lists('calendars/all/shows/new/%s/%s?extended=full&page=%d&limit=%d' %
                                    (start_date, days, 1, result_count))

    def get_new_seasons(self, result_count=100, start_date=None, days=32, **kwargs):
        # type: (...) -> List[TVInfoShow]
        """
        get new seasons
        :param result_count: how many results are suppose to be returned
        :param start_date: start date for returned data in format: '2014-09-01'
        :param days: number of days to return from start date
        """
        if None is start_date:
            start_date = (datetime.datetime.now() + datetime.timedelta(days=-16)).strftime('%Y-%m-%d')
        return self._get_show_lists('calendars/all/shows/premieres/%s/%s?extended=full&page=%d&limit=%d' %
                                    (start_date, days, 1, result_count))
