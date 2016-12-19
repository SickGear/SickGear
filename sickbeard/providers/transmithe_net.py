# coding=utf-8
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
#  GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with SickGear.  If not, see <http://www.gnu.org/licenses/>.

import re
import traceback

from . import generic
from sickbeard import common, helpers, logger
from sickbeard.bs4_parser import BS4Parser
from sickbeard.helpers import tryInt
from lib.unidecode import unidecode


class TransmithenetProvider(generic.TorrentProvider):

    def __init__(self):
        generic.TorrentProvider.__init__(self, 'Transmithe.net', cache_update_freq=17)

        self.url_base = 'https://transmithe.net/'
        self.urls = {'config_provider_home_uri': self.url_base,
                     'login_action': self.url_base + 'login.php',
                     'user': self.url_base + 'ajax.php?action=index',
                     'browse': self.url_base + 'ajax.php?action=browse&auth=%s&passkey=%s',
                     'search': '&searchstr=%s',
                     'get': self.url_base + 'torrents.php?action=download&authkey=%s&torrent_pass=%s&id=%s'}

        self.url = self.urls['config_provider_home_uri']
        self.user_authkey, self.user_passkey = 2 * [None]
        self.chk_td = True

        self.username, self.password, self.freeleech, self.minseed, self.minleech = 5 * [None]

    def _authorised(self, **kwargs):

        if not super(TransmithenetProvider, self)._authorised(
                logged_in=(lambda y=None: self.has_all_cookies('session')),
                post_params={'keeplogged': '1', 'form_tmpl': True}):
            return False
        if not self.user_authkey:
            response = helpers.getURL(self.urls['user'], session=self.session, json=True)
            if 'response' in response:
                self.user_authkey, self.user_passkey = [response['response'].get(v) for v in 'authkey', 'passkey']
        return self.user_authkey

    def _search_provider(self, search_params, **kwargs):

        results = []
        if not self._authorised():
            return results

        items = {'Cache': [], 'Season': [], 'Episode': [], 'Propers': []}

        rc = dict((k, re.compile('(?i)' + v)) for (k, v) in {'nodots': '[\.\s]+'}.items())
        for mode in search_params.keys():
            for search_string in search_params[mode]:
                search_string = isinstance(search_string, unicode) and unidecode(search_string) or search_string

                search_url = self.urls['browse'] % (self.user_authkey, self.user_passkey)
                if 'Cache' != mode:
                    search_url += self.urls['search'] % rc['nodots'].sub('+', search_string)

                data_json = self.get_url(search_url, json=True)

                cnt = len(items[mode])
                try:
                    for item in data_json['response'].get('results', []):
                        if self.freeleech and not item.get('isFreeleech'):
                            continue

                        seeders, leechers, group_name, torrent_id, size = [tryInt(n, n) for n in [item.get(x) for x in [
                            'seeders', 'leechers', 'groupName', 'torrentId', 'size']]]
                        if self._peers_fail(mode, seeders, leechers):
                            continue

                        try:
                            title_parts = group_name.split('[')
                            maybe_res = re.findall('((?:72|108|216)0\w)', title_parts[1])
                            maybe_ext = re.findall('(?i)(%s)' % '|'.join(common.mediaExtensions), title_parts[1])
                            detail = title_parts[1].split('/')
                            detail[1] = detail[1].strip().lower().replace('mkv', 'x264')
                            title = '%s.%s' % (BS4Parser(title_parts[0].strip(), 'html.parser').soup.string, '.'.join(
                                (maybe_res and [maybe_res[0]] or []) +
                                [detail[0].strip(), detail[1], maybe_ext and maybe_ext[0].lower() or 'mkv']))
                        except (IndexError, KeyError):
                            title = group_name
                        download_url = self.urls['get'] % (self.user_authkey, self.user_passkey, torrent_id)

                        if title and download_url:
                            items[mode].append((title, download_url, seeders, self._bytesizer(size)))

                except (StandardError, Exception):
                    logger.log(u'Failed to parse. Traceback: %s' % traceback.format_exc(), logger.ERROR)
                self._log_search(mode, len(items[mode]) - cnt, search_url)

            results = self._sort_seeding(mode, results + items[mode])

        return results

    def _season_strings(self, ep_obj, **kwargs):

        return generic.TorrentProvider._season_strings(self, ep_obj, scene=False)

    def _episode_strings(self, ep_obj, **kwargs):

        return generic.TorrentProvider._episode_strings(self, ep_obj, scene=False, **kwargs)


provider = TransmithenetProvider()
