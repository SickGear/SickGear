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
from .. import logger
from ..helpers import try_int

from bs4_parser import BS4Parser

from _23 import b64decodestring, unidecode
from six import iteritems


class IPTorrentsProvider(generic.TorrentProvider):

    def __init__(self):
        generic.TorrentProvider.__init__(self, 'IPTorrents')

        self.url_home = (['https://iptorrents.com/'] +
                         [b64decodestring(x) for x in [''.join(x) for x in [
                             [re.sub(r'(?i)[q\s1]+', '', x[::-1]) for x in [
                                 'c0RHa', 'vo1QD', 'hJ2L', 'GdhdXe', 'vdnLoN', 'J21cptmc', '5yZulmcv', '02bj', '=iq=']],
                             [re.sub(r'(?i)[q\seg]+', '', x[::-1]) for x in [
                                 'RqHEa', 'LvEoDc0', 'Zvex2', 'LuF2', 'NXdu Vn', 'XZwQxeWY1', 'Yu42bzJ', 'tgG92']],
                         ]]])

        self.url_vars = {'login': 't', 'search': 't?%s;q=%s;qf=ti%s%s;p=%s#torrents'}
        self.url_tmpl = {'config_provider_home_uri': '%(home)s', 'login': '%(home)s%(vars)s',
                         'search': '%(home)s%(vars)s'}

        self.categories = {'shows': [4, 5, 22, 23, 24, 25, 26, 55, 65, 66, 78, 79, 99], 'anime': [60]}

        self.proper_search_terms = None

        self.digest, self.freeleech, self.minseed, self.minleech = 4 * [None]

    def _authorised(self, **kwargs):

        return super(IPTorrentsProvider, self)._authorised(
            logged_in=(lambda y='': all(
                ['IPTorrents' in y, 'type="password"' not in y[0:2048], self.has_all_cookies()] +
                [(self.session.cookies.get(x, domain='') or 'sg!no!pw') in self.digest for x in ('uid', 'pass')])),
            failed_msg=(lambda y=None: u'Invalid cookie details for %s. Check settings'))

    @staticmethod
    def _has_signature(data=None):
        return generic.TorrentProvider._has_signature(data) or (data and re.search(r'(?i)<title[^<]+?ipt', data))

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
                search_string = unidecode(search_string) or search_string
                for page in range((3, 5)['Cache' == mode])[1:]:
                    # URL with 50 tv-show results, or max 150 if adjusted in IPTorrents profile
                    urls[-1] += [self.urls['search'] % (
                        self._categories_string(mode, '%s', ';'), search_string,
                        (';free', '')[not self.freeleech], (';o=seeders', '')['Cache' == mode], page)]
                results += self._search_urls(mode, last_recent_search, urls)
                last_recent_search = ''

            return results

    def _search_urls(self, mode, last_recent_search, urls):

        results = []
        items = {'Cache': [], 'Season': [], 'Episode': [], 'Propers': []}

        rc = dict((k, re.compile('(?i)' + v)) for (k, v) in iteritems(dict(
            info='detail', get='download', id=r'download.*?/([\d]+)')))
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

                    with BS4Parser(html) as soup:
                        tbl = soup.find(id='torrents') or soup.find('table', class_='torrents')
                        tbl_rows = [] if not tbl else tbl.find_all('tr')

                        if 2 > len(tbl_rows):
                            raise generic.HaltParseException

                        if 'Cache' == mode and 100 > len(tbl_rows):
                            log_settings_hint = True

                        head = None
                        for tr in tbl_rows[1:]:
                            cells = tr.find_all('td')
                            if 5 > len(cells):
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

                                seeders, leechers = [try_int(tr.find('td', class_='t_' + x).get_text().strip())
                                                     for x in ('seeders', 'leechers')]
                                if self._reject_item(seeders, leechers):
                                    continue

                                info = tr.find('a', href=rc['info'])
                                title = (info.attrs.get('title') or info.get_text()).strip()
                                size = cells[head['size']].get_text().strip()
                                download_url = self._link(dl)
                            except (AttributeError, TypeError, ValueError):
                                continue

                            if title and download_url:
                                items[mode].append((title, download_url, seeders, self._bytesizer(size)))

                except generic.HaltParseException:
                    pass
                except (BaseException, Exception):
                    logger.log(u'Failed to parse. Traceback: %s' % traceback.format_exc(), logger.ERROR)
                self._log_search(mode, len(items[mode]) - cnt, search_url, log_settings_hint)

                if self.is_search_finished(mode, items, cnt_search, rc['id'], last_recent_search, lrs_new, lrs_found):
                    break
                lrs_new = False

            results = self._sort_seeding(mode, results + items[mode])

        return results

    @staticmethod
    def ui_string(key):
        return 'iptorrents_digest' == key and 'use... \'uid=xx; pass=yy\'' or ''


provider = IPTorrentsProvider()
