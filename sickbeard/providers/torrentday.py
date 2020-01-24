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
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with SickGear.  If not, see <http://www.gnu.org/licenses/>.

import re
import time

from . import generic
from ..helpers import anon_url, try_int
from bs4_parser import BS4Parser

from _23 import b64decodestring
from six import iteritems


class TorrentDayProvider(generic.TorrentProvider):

    def __init__(self):
        generic.TorrentProvider.__init__(self, 'TorrentDay')

        self.url_home = ['https://www.torrentday.com/'] + \
                        ['http://td.%s/' % b64decodestring(x) for x in [''.join(x) for x in [
                            [re.sub(r'(?i)[I\s1]+', '', x[::-1]) for x in [
                                'y92d', 'zl12a', 'y9mY', 'n5 Wa', 'vNmIL', '=i1=Qb']],
                            [re.sub(r'(?i)[T\sq]+', '', x[::-1]) for x in [
                                '15TWd', 'hV 3c', 'lBHb', 'vNncq', 'j5ib', '=qQ02b']],
                        ]]]

        self.url_vars = {'login': 'rss.php', 'search': 't?%s%s&qf=&p=%s&q=%s'}
        self.url_tmpl = {'config_provider_home_uri': '%(home)s', 'login': '%(home)s%(vars)s',
                         'search': '%(home)s%(vars)s'}

        self.categories = {'Season': [31, 33, 14], 'Episode': [24, 32, 26, 7, 34, 2], 'anime': [29]}
        self.categories['Cache'] = self.categories['Season'] + self.categories['Episode']

        self.proper_search_terms = None

        self.digest, self.freeleech, self.minseed, self.minleech = 4 * [None]

    def _authorised(self, **kwargs):

        return super(TorrentDayProvider, self)._authorised(
            logged_in=(lambda y='': all(
                ['RSS URL' in y, self.has_all_cookies()] +
                [(self.session.cookies.get(x, domain='') or 'sg!no!pw') in self.digest for x in ('uid', 'pass')])),
            failed_msg=(lambda y=None: u'Invalid cookie details for %s. Check settings'))

    @staticmethod
    def _has_signature(data=None):
        return generic.TorrentProvider._has_signature(data) or \
               (data and re.search(r'(?i)<title[^<]+?(td|torrentday)', data))

    def _search_provider(self, search_params, **kwargs):

        results = []
        if not self._authorised():
            return results

        last_recent_search = self.last_recent_search
        last_recent_search = '' if not last_recent_search else last_recent_search.replace('id-', '')
        for mode in search_params:
            urls = []
            for search_string in search_params[mode]:
                search_string = '+'.join(search_string.split())
                urls += [[]]
                for page in range((3, 5)['Cache' == mode])[1:]:
                    urls[-1] += [self.urls['search'] % (self._categories_string(mode, '%s=on'),
                                                        ('&free=on', '')[not self.freeleech], page, search_string)]
            results += self._search_urls(mode, last_recent_search, urls)
            last_recent_search = ''

        return results

    def _search_urls(self, mode, last_recent_search, urls):

        results = []
        items = {'Cache': [], 'Season': [], 'Episode': [], 'Propers': []}

        rc = dict((k, re.compile('(?i)' + v)) for (k, v) in iteritems(dict(get='download', id=r'download.*?/([\d]+)')))
        lrs_found = False
        lrs_new = True
        for search_urls in urls:  # this intentionally iterates once to preserve indentation
            for search_url in search_urls:
                html = self.get_url(search_url)
                if self.should_skip():
                    return results

                cnt = len(items[mode])
                cnt_search = 0
                log_settings_hint = False
                try:
                    if not html or self._has_no_results(html):
                        raise generic.HaltParseException

                    with BS4Parser(html, tag='table', attr='torrentTable') as soup:
                        tbl = soup.find('table', id='torrentTable')
                        tbl_rows = [] if not tbl else tbl.find_all('tr')

                        if 2 > len(tbl_rows):
                            raise generic.HaltParseException

                        if 'Cache' == mode and 100 > len(tbl_rows):
                            log_settings_hint = True

                        head = None
                        for tr in tbl_rows[1:]:
                            cells = tr.find_all('td')
                            if 4 > len(cells):
                                continue
                            cnt_search += 1
                            try:
                                head = head if None is not head else self._header_row(
                                    tr, header_strip='(?i)(?:leechers|seeders|size);')

                                dl = tr.find('a', href=rc['get'])['href']
                                dl_id = rc['id'].findall(dl)[0]
                                lrs_found = dl_id == last_recent_search
                                if lrs_found:
                                    break

                                seeders, leechers, size = [try_int(n, n) for n in [
                                    cells[head[x]].get_text().strip() for x in ('seed', 'leech', 'size')]]
                                if self._reject_item(seeders, leechers):
                                    continue

                                title = tr.find('a', href=re.compile('/t/%s' % dl_id)).get_text().strip()
                                download_url = self._link(dl)
                            except (AttributeError, TypeError, ValueError, IndexError):
                                continue

                            if title and download_url:
                                items[mode].append((title, download_url, seeders, self._bytesizer(size)))

                except generic.HaltParseException:
                    pass
                except (BaseException, Exception):
                    time.sleep(1.1)

                self._log_search(mode, len(items[mode]) - cnt, search_url, log_settings_hint)

                if self.is_search_finished(mode, items, cnt_search, rc['id'], last_recent_search, lrs_new, lrs_found):
                    break
                lrs_new = False

            results = self._sort_seeding(mode, results + items[mode])

        return results

    def _episode_strings(self, ep_obj, **kwargs):

        return super(TorrentDayProvider, self)._episode_strings(ep_obj, sep_date='.', date_or=True, **kwargs)

    def ui_string(self, key):
        if 'torrentday_digest' == key and self._valid_home():
            current_url = getattr(self, 'urls', {}).get('config_provider_home_uri')
            return ('use... \'uid=xx; pass=yy\'' +
                    (current_url and (' from a session logged in at <a target="_blank" href="%s">%s</a>' %
                                      (anon_url(current_url), current_url.strip('/'))) or ''))
        return ''


provider = TorrentDayProvider()
