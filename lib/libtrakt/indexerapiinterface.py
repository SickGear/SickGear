import logging
import re
from .exceptions import TraktException
from exceptions_helper import ex
from six import iteritems
from .trakt import TraktAPI
from tvinfo_base.exceptions import BaseTVinfoShownotfound
from tvinfo_base import TVInfoBase

# noinspection PyUnreachableCode
if False:
    from typing import Any, AnyStr, List, Optional
    from tvinfo_base import TVInfoShow

log = logging.getLogger('trakt_api')
log.addHandler(logging.NullHandler())


class TraktSearchTypes(object):
    text = 1
    trakt_id = 'trakt'
    tvdb_id = 'tvdb'
    imdb_id = 'imdb'
    tmdb_id = 'tmdb'
    tvrage_id = 'tvrage'
    all = [text, trakt_id, tvdb_id, imdb_id, tmdb_id, tvrage_id]

    def __init__(self):
        pass


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

    def _search_show(self, name, **kwargs):
        # type: (AnyStr, Optional[Any]) -> List[TVInfoShow]
        """This searches Trakt for the series name,
        If a custom_ui UI is configured, it uses this to select the correct
        series.
        """
        all_series = self.search(name)
        if not isinstance(all_series, list):
            all_series = [all_series]

        if 0 == len(all_series):
            log.debug('Series result returned zero')
            raise BaseTVinfoShownotfound('Show-name search returned zero results (cannot find show on TVDB)')

        if None is not self.config['custom_ui']:
            log.debug('Using custom UI %s' % (repr(self.config['custom_ui'])))
            custom_ui = self.config['custom_ui']
            ui = custom_ui(config=self.config)

            return ui.select_series(all_series)

        return all_series

    @staticmethod
    def _dict_prevent_none(d, key, default):
        v = None
        if isinstance(d, dict):
            v = d.get(key, default)
        return (v, default)[None is v]

    def search(self, series):
        # type: (AnyStr) -> List
        if TraktSearchTypes.text != self.config['search_type']:
            url = '/search/%s/%s?type=%s&extended=full&limit=100' % (self.config['search_type'], series,
                                                                     ','.join(self.config['result_types']))
        else:
            url = '/search/%s?query=%s&extended=full&limit=100' % (','.join(self.config['result_types']), series)
        filtered = []
        kwargs = {}
        if None is not self.config['sleep_retry']:
            kwargs['sleep_retry'] = self.config['sleep_retry']
        try:
            from sickbeard.helpers import clean_data
            resp = TraktAPI().trakt_request(url, **kwargs)
            if len(resp):
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
        except TraktException as e:
            log.debug('Could not connect to Trakt service: %s' % ex(e))

        return filtered
