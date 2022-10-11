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

from datetime import datetime
import re

from . import generic
from ..helpers import anon_url, try_int

from _23 import unidecode
from six import iteritems, PY2


class TorrentLeechProvider(generic.TorrentProvider):
    def __init__(self):
        generic.TorrentProvider.__init__(self, 'TorrentLeech')

        self.url_base = 'https://tlgetin.cc/'
        self.urls = {'config_provider_home_uri': self.url_base,
                     'login': self.url_base,
                     'browse': self.url_base + 'torrents/browse/list/categories/%(cats)s/%(x)s',
                     'search': self.url_base + 'torrents/browse/list/categories/%(cats)s/%(x)s/query/%(query)s'}

        self.categories = {'shows': [26, 27, 32, 35], 'anime': [34]}

        self.url = self.urls['config_provider_home_uri']
        self.digest, self.minseed, self.minleech, self.freeleech = 4 * [None]

    def _authorised(self, **kwargs):

        return super(TorrentLeechProvider, self)._authorised(
            logged_in=(lambda y='': all(
                ['TorrentLeech' in y, 'type="password"' not in y[0:4096], self.has_all_cookies(pre='tl')])),
            failed_msg=(lambda y=None: u'Invalid cookie details for %s. Check settings'))

    @staticmethod
    def _has_signature(data=None):
        return generic.TorrentProvider._has_signature(data) or (data and re.search(r'(?i)<title[^<]+?leech', data))

    def _search_provider(self, search_params, **kwargs):

        results = []
        if not self._authorised():
            return results

        last_recent_search = self.last_recent_search
        last_recent_search = '' if not last_recent_search else last_recent_search.replace('id-', '')
        for mode in search_params:
            urls = []
            for search_string in search_params[mode]:
                urls += [[]]
                for page in range((3, 5)['Cache' == mode])[1:]:
                    urls[-1] += [self.urls[('search', 'browse')['Cache' == mode]] % {
                        'cats': self._categories_string(mode, '', ','),
                        'query': unidecode(search_string) or search_string,
                        'x': '%spage/%s' % (('facets/tags:FREELEECH/', '')[not self.freeleech], page)
                    }]
            results += self._search_urls(mode, last_recent_search, urls)
            last_recent_search = ''

        return results

    def _search_urls(self, mode, last_recent_search, urls):

        results = []
        items = {'Cache': [], 'Season': [], 'Episode': [], 'Propers': []}

        rc = dict((k, re.compile('(?i)' + v)) for (k, v) in iteritems(dict(id=r'download.*?/([\d]+)')))
        lrs_found = False
        lrs_new = True
        for search_urls in urls:  # this intentionally iterates once to preserve indentation
            for search_url in search_urls:

                data_json = self.get_url(search_url, parse_json=True)
                if self.should_skip():
                    return results

                cnt = len(items[mode])
                cnt_search = 0
                log_settings_hint = False
                try:
                    if not isinstance(data_json, dict) or not data_json.get('torrentList'):
                        raise generic.HaltParseException

                    if 'Cache' == mode and 100 > len(data_json.get('torrentList')):
                        log_settings_hint = True

                    try:
                        # attempt to order the data
                        order_by = '%sTimestamp' % (data_json.get('orderBy') or 'added')
                        tbl_rows = sorted(data_json['torrentList'], key=lambda _i: datetime.strptime(
                            _i.get(order_by) or '0001-01-01 00:00:00', '%Y-%m-%d %H:%M:%S'), reverse=True)
                    except (BaseException, Exception):
                        tbl_rows = []

                    for item in tbl_rows or data_json.get('torrentList'):
                        try:
                            dl = item.get('filename')
                            dl_id = item.get('fid')
                            lrs_found = dl_id == last_recent_search
                            if tbl_rows and lrs_found:
                                break  # can break when data is ordered

                            seeders, leechers = [try_int(n) for n in [item.get(x) for x in ('seeders', 'leechers')]]
                            if self._reject_item(seeders, leechers):
                                continue

                            title = item.get('name').strip()
                            size = item.get('size')

                            download_url = None
                            if dl and dl_id:
                                # noinspection PyUnresolvedReferences
                                download_url = self._link('download/%s/%s' % (dl_id, dl),
                                                          url_quote=PY2 and isinstance(dl, unicode) or None)
                        except (BaseException, Exception):
                            continue

                        if title and download_url:
                            items[mode].append((title, download_url, seeders, self._bytesizer(size)))

                except generic.HaltParseException:
                    pass
                self._log_search(mode, len(items[mode]) - cnt, search_url, log_settings_hint)

                if self.is_search_finished(mode, items, cnt_search, rc['id'], last_recent_search, lrs_new, lrs_found):
                    break
                lrs_new = False

            results = self._sort_seeding(mode, results + items[mode])

        return results

    def _episode_strings(self, ep_obj, **kwargs):

        return super(TorrentLeechProvider, self)._episode_strings(ep_obj, sep_date='|', **kwargs)

    def ui_string(self, key):
        cookies = 'use... \'tluid=xx; tlpass=yy\''
        if 'cookie_str_only' == key:
            return cookies
        if 'torrentleech_digest' == key and self._valid_home():
            current_url = getattr(self, 'urls', {}).get('config_provider_home_uri')
            return (cookies + (current_url and ('<br>from a session logged in at <a target="_blank" href="%s">%s</a>' %
                                                (anon_url(current_url), current_url.strip('/'))) or ''))
        return ''


provider = TorrentLeechProvider()
