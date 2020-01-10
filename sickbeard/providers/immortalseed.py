# coding=utf-8
#
# Author: SickGear
#
# This file is part of SickGear.
#
# SickGear is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# SickGear is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with SickGear.  If not, see <http://www.gnu.org/licenses/>.

import re
import time

import sickbeard
from . import generic
from ..helpers import try_int

import exceptions_helper
import feedparser

from _23 import unidecode
from six import iteritems


class ImmortalSeedProvider(generic.TorrentProvider):

    def __init__(self):

        generic.TorrentProvider.__init__(self, 'ImmortalSeed')

        self.url_base = 'https://immortalseed.me/'
        self.urls = {'config_provider_home_uri': self.url_base,
                     'search': self.url_base + 'rss.php?feedtype=download&timezone=0&showrows=100'
                                               '&%s&categories=%s&incl=%s'}

        self.categories = {'Season': [6, 4], 'Episode': [8, 48, 9], 'anime': [32]}
        self.categories['Cache'] = self.categories['Season'] + self.categories['Episode']

        self.url = self.urls['config_provider_home_uri']

        self.api_key, self.minseed, self.minleech = 3 * [None]

    def _check_auth(self, **kwargs):
        try:
            secret_key = 'secret_key=' + re.split(r'secret_key\s*=\s*([0-9a-zA-Z]+)', self.api_key)[1]
        except (BaseException, Exception):
            raise exceptions_helper.AuthException('Invalid secret key for %s in Media Providers/Options' % self.name)

        if secret_key != self.api_key:
            self.api_key = secret_key
            sickbeard.save_config()

        return True

    def _search_provider(self, search_params, **kwargs):

        results = []

        items = {'Cache': [], 'Season': [], 'Episode': [], 'Propers': []}

        rc = dict([(k, re.compile('(?i)' + v)) for (k, v) in iteritems({
            'seed': r'seed[^\d/]+([\d]+)', 'leech': r'leech[^\d/]+([\d]+)',
            'size': r'size[^\d/]+([^/]+)', 'get': '(.*download.*)', 'title': r'NUKED\b\.(.*)$'})])
        for mode in search_params:
            for search_string in search_params[mode]:
                search_string = unidecode(search_string)
                search_string = search_string.replace(' ', '.')

                search_url = self.urls['search'] % (
                    self.api_key, self._categories_string(mode, template='%s', delimiter=','), search_string)

                resp = self.get_url(search_url)
                if self.should_skip():
                    return results

                data = feedparser.parse(resp)
                tr = data and data.get('entries', []) or []

                cnt = len(items[mode])
                for item in tr:
                    try:
                        seeders, leechers, size = [try_int(n, n) for n in [
                            rc[x].findall(item.summary)[0].strip() for x in ('seed', 'leech', 'size')]]
                        if self._reject_item(seeders, leechers):
                            continue
                        title = rc['title'].sub(r'\1', item.title.strip())
                        download_url = self._link(rc['get'].findall(getattr(item, 'link', ''))[0])
                    except (BaseException, Exception):
                        continue

                    if download_url and title:
                        items[mode].append((title, download_url, seeders, self._bytesizer(size)))

                time.sleep(1.1)
                self._log_search(mode, len(items[mode]) - cnt, search_url)

            results = self._sort_seeding(mode, results + items[mode])

        return results

    def ui_string(self, key):
        return ('%s_api_key' % self.get_id()) == key and 'Secret key' or \
               ('%s_api_key_tip' % self.get_id()) == key and \
               '\'secret_key=\' from the <a href="%sgetrss.php">generated RSS link</a> at %s' % \
               (self.url_base, self.name) or ''


provider = ImmortalSeedProvider()
