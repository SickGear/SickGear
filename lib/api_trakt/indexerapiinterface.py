import logging
import re
from .exceptions import TraktException
from exceptions_helper import ConnectionSkipException, ex
from six import iteritems
from .trakt import TraktAPI
from lib.tvinfo_base.exceptions import BaseTVinfoShownotfound
from lib.tvinfo_base import TVInfoBase, TVINFO_TRAKT, TVINFO_TMDB, TVINFO_TVDB, TVINFO_TVRAGE, TVINFO_IMDB, \
    TVINFO_SLUG, Person, TVINFO_TWITTER, TVINFO_FACEBOOK, TVINFO_WIKIPEDIA, TVINFO_INSTAGRAM, Character, TVInfoShow, \
    TVInfoIDs, TVINFO_TRAKT_SLUG
from sg_helpers import try_int
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
        if shows:
            try:
                for s in shows:
                    if s['ids']['trakt'] not in [i['ids'].trakt for i in results]:
                        s['id'] = s['ids']['trakt']
                        s['ids'] = TVInfoIDs(
                            trakt=s['ids']['trakt'], tvdb=s['ids']['tvdb'], tmdb=s['ids']['tmdb'],
                            rage=s['ids']['tvrage'],
                            imdb=s['ids']['imdb'] and try_int(s['ids']['imdb'].replace('tt', ''), None))
                        results.append(s)
            except (BaseException, Exception) as e:
                log.debug('Error creating result dict: %s' % ex(e))

    def _search_show(self, name=None, ids=None, **kwargs):
        # type: (AnyStr, Dict[integer_types, integer_types], Optional[Any]) -> List[TVInfoShow]
        """This searches Trakt for the series name,
        If a custom_ui UI is configured, it uses this to select the correct
        series.
        """
        results = []
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

        final_result = []
        seen = set()
        film_type = re.compile(r'(?i)films?\)$')
        for r in results:
            if r['id'] not in seen:
                seen.add(r['id'])
                title = r.get('title') or ''
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
            from sickbeard.helpers import clean_data
            resp = TraktAPI().trakt_request(url, failure_monitor=False, raise_skip_exception=False, **kwargs)
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
        # type: (Dict) -> Person
        try:
            birthdate = person_obj['birthday'] and tz_p.parse(person_obj['birthday']).date()
        except (BaseException, Exception):
            birthdate = None
        try:
            deathdate = person_obj['death'] and tz_p.parse(person_obj['death']).date()
        except (BaseException, Exception):
            deathdate = None

        return Person(p_id=person_obj['ids']['trakt'],
                      name=person_obj['name'],
                      bio=person_obj['biography'],
                      birthdate=birthdate,
                      deathdate=deathdate,
                      homepage=person_obj['homepage'],
                      birthplace=person_obj['birthplace'],
                      social_ids={TVINFO_TWITTER: person_obj['social_ids']['twitter'],
                                  TVINFO_FACEBOOK: person_obj['social_ids']['facebook'],
                                  TVINFO_INSTAGRAM: person_obj['social_ids']['instagram'],
                                  TVINFO_WIKIPEDIA: person_obj['social_ids']['wikipedia']
                                  },
                      ids={TVINFO_TRAKT: person_obj['ids']['trakt'], TVINFO_SLUG: person_obj['ids']['slug'],
                           TVINFO_IMDB:
                               person_obj['ids']['imdb'] and
                               try_int(person_obj['ids']['imdb'].replace('nm', ''), None),
                           TVINFO_TMDB: person_obj['ids']['tmdb'],
                           TVINFO_TVRAGE: person_obj['ids']['tvrage']})

    def get_person(self, p_id, get_show_credits=False, get_images=False, **kwargs):
        # type: (integer_types, bool, bool, Any) -> Optional[Person]
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

        result = None

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
                        for c in resp.get('cast') or []:
                            show = TVInfoShow()
                            show.id = c['show']['ids'].get('trakt')
                            show.seriesname = c['show']['title']
                            show.ids = TVInfoIDs(ids={id_map[src]: _convert_imdb_id(id_map[src], sid)
                                                      for src, sid in iteritems(c['show']['ids']) if src in id_map})
                            show.network = c['show']['network']
                            show.firstaired = c['show']['first_aired']
                            show.overview = c['show']['overview']
                            show.status = c['show']['status']
                            show.imdb_id = c['show']['ids'].get('imdb')
                            show.runtime = c['show']['runtime']
                            show.genre_list = c['show']['genres']
                            for ch in c.get('characters') or []:
                                pc.append(
                                    Character(
                                        name=ch, regular=c.get('series_regular'),
                                        show=show
                                    )
                                )
                        result.characters = pc
                    else:
                        result = self._convert_person_obj(resp)
            except ConnectionSkipException as e:
                raise e
            except TraktException as e:
                log.debug('Could not connect to Trakt service: %s' % ex(e))
        return result

    def _search_person(self, name=None, ids=None):
        # type: (AnyStr, Dict[integer_types, integer_types]) -> List[Person]
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
