import logging
import re
import time
from .exceptions import TraktShowNotFound, TraktException
from sickbeard.exceptions import ex
from trakt import TraktAPI


class ShowContainer(dict):
    """Simple dict that holds a series of Show instances
    """

    def __init__(self, **kwargs):
        super(ShowContainer, self).__init__(**kwargs)

        self._stack = []
        self._lastgc = time.time()

    def __setitem__(self, key, value):

        self._stack.append(key)

        # keep only the 100th latest results
        if time.time() - self._lastgc > 20:
            for o in self._stack[:-100]:
                del self[o]

            self._stack = self._stack[-100:]

            self._lastgc = time.time()

        super(ShowContainer, self).__setitem__(key, value)


def log():
    return logging.getLogger('trakt_api')


class TraktSearchTypes:
    text = 1
    trakt_id = 'trakt'
    tvdb_id = 'tvdb'
    imdb_id = 'imdb'
    tmdb_id = 'tmdb'
    tvrage_id = 'tvrage'
    all = [text, trakt_id, tvdb_id, imdb_id, tmdb_id, tvrage_id]

    def __init__(self):
        pass


class TraktResultTypes:
    show = 'show'
    episode = 'episode'
    movie = 'movie'
    person = 'person'
    list = 'list'
    all = [show, episode, movie, person, list]

    def __init__(self):
        pass


class TraktIndexer:
    # noinspection PyUnusedLocal
    # noinspection PyDefaultArgument
    def __init__(self, custom_ui=None, sleep_retry=None, search_type=TraktSearchTypes.text,
                 result_types=[TraktResultTypes.show], *args, **kwargs):

        self.config = {
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
            'result_types': result_types if isinstance(result_types, list) and all(x in TraktResultTypes.all for x in result_types) else [TraktResultTypes.show],
        }

        self.corrections = {}
        self.shows = ShowContainer()

    def _get_series(self, series):
        """This searches Trakt for the series name,
        If a custom_ui UI is configured, it uses this to select the correct
        series.
        """
        all_series = self.search(series)
        if not isinstance(all_series, list):
            all_series = [all_series]

        if 0 == len(all_series):
            log().debug('Series result returned zero')
            raise TraktShowNotFound('Show-name search returned zero results (cannot find show on TVDB)')

        if None is not self.config['custom_ui']:
            log().debug('Using custom UI %s' % (repr(self.config['custom_ui'])))
            custom_ui = self.config['custom_ui']
            ui = custom_ui(config=self.config)

            return ui.select_series(all_series)

        return all_series

    def __getitem__(self, key):
        """Handles trakt_instance['seriesname'] calls.
        The dict index should be the show id
        """
        if isinstance(key, tuple) and 2 == len(key):
            key = key[0]

        self.config['searchterm'] = key
        selected_series = self._get_series(key)
        if isinstance(selected_series, dict):
            selected_series = [selected_series]

        return selected_series

    def __repr__(self):
        return str(self.shows)

    def _clean_data(self, data):
        """Cleans up strings, lists, dicts returned

        Issues corrected:
        - Replaces &amp; with &
        - Trailing whitespace
        """
        if isinstance(data, list):
            return [self._clean_data(d) for d in data]
        if isinstance(data, dict):
            return {k: self._clean_data(v) for k, v in data.iteritems()}
        return data if not isinstance(data, (str, unicode)) else data.strip().replace(u'&amp;', u'&')

    @staticmethod
    def _dict_prevent_none(d, key, default):
        v = None
        if isinstance(d, dict):
            v = d.get(key, default)
        return (v, default)[None is v]

    def search(self, series):
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
            resp = TraktAPI().trakt_request(url, **kwargs)
            if len(resp):
                for d in resp:
                    if isinstance(d, dict) and 'type' in d and d['type'] in self.config['result_types']:
                        for k, v in d.iteritems():
                            d[k] = self._clean_data(v)
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
            log().debug('Could not connect to Trakt service: %s' % ex(e))

        return filtered
