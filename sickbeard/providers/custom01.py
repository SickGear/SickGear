# coding=utf-8
# $Id: custom01.py 381 2016-06-30 22:20:13Z root $
# location: <your_sg_install_dir>/sickbeard/providers/custom01.py

# FSC SickGear module.
# It was kindly provided by JackDandy from the SickGear development team.


import re
import time
import traceback

from . import generic
from sickbeard import logger
from sickbeard.helpers import tryInt
from lib.unidecode import unidecode


class Custom01Provider(generic.TorrentProvider):
    def __init__(self):
        generic.TorrentProvider.__init__(self, 'Custom01')
        self.url_home = []
        self.url_edit = True
        self.url_vars = {'search': '&cats=%s&fl=%s&s=%s'}
        self.url_tmpl = {'config_provider_home_uri': '%(home)s', 'search': '%(home)s%(vars)s'}
        self.categories = {'Season': [5, 50, 41, 42], 'Episode': [5, 50, 42], 'anime': [23]}
        self.categories['Cache'] = list(set(self.categories['Season'] + self.categories['Episode']))
        self.proper_search_terms = '(proper%20repack)'
        self.freeleech, self.minseed, self.minleech = 3 * [None]

    def _valid_url(self):
        try:
            self._url = re.findall('^(https://[^/]+/)[\w.]{16,32}.key=[\w]{16,64}.*?uid=[0-9]+', self.url_home[0])[0]
        except (IndexError, TypeError, NameError):
            self._url = None
        return bool(self._url)

    def _authorised(self, **kwargs):
        return self._valid_home()

    @staticmethod
    def _has_signature(data=None):
        return 'uid=' in data

    def _search_provider(self, search_params, **kwargs):
        results = []
        if not self._authorised():
            return results
        items = {'Cache': [], 'Season': [], 'Episode': [], 'Propers': []}
        for mode in search_params.keys():
            for search_string in search_params[mode]:
                search_string = isinstance(search_string, unicode) and unidecode(search_string) or search_string
                search_string = '%20%2b'.join(re.sub(r'(\d{4}(?:\.\d\d){2})', r'%22\1%22', search_string).split())
                data_json = self.get_url(self.urls['search'] % (
                    self._categories_string(mode, template='%s', delimiter=','), ('1', '0')[not self.freeleech],
                    search_string and ('%2b' + search_string) or ''), json=True)
                cnt = len(items[mode])
                try:
                    self.parse_items(mode, data_json, **items)
                except AttributeError:
                    pass
                except Exception:
                    logger.log(u'Failed to parse. Traceback: %s' % traceback.format_exc(), logger.ERROR)
                self._log_search(mode, len(items[mode]) - cnt, '%s ... %s' % (self.name, search_string))
                time.sleep(1.1)
            self._sort_seeders(mode, items)
            results = list(set(results + items[mode]))
        return results

    def parse_items(self, mode, data_json, **items):
        for item in data_json:
            seeders, leechers, size, freeleech = [tryInt(n, n) for n in [
                item.get(x) for x in 'seeders', 'leechers', 'size', 'freeleech']]
            if self._peers_fail(mode, seeders, leechers) or (self.freeleech and not freeleech):
                continue
            title, download_url = item.get('name'), item.get('get').replace('\/', '/')
            if title and download_url:
                items[mode].append((title, download_url, seeders, size))

    def _season_strings(self, ep_obj, **kwargs):
        return generic.TorrentProvider._season_strings(self, ep_obj, scene=False, **kwargs)

    def _episode_strings(self, ep_obj, **kwargs):
        return generic.TorrentProvider._episode_strings(self, ep_obj, scene=False, sep_date='.', **kwargs)

    def ui_string(self, key):
        return ('%s_url_edit' % self.get_id()) == key and 'must contain both \'key=\' and \'uid=\'' or \
               ('%s_site_url' % self.get_id()) == key and 'Site API URL' or ''

provider = Custom01Provider()
