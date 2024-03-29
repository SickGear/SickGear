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

from collections import OrderedDict

import re
import traceback

from . import generic
from .. import logger
from ..helpers import try_int
from bs4_parser import BS4Parser

from six import iteritems


class HDTorrentsProvider(generic.TorrentProvider):

    def __init__(self):
        generic.TorrentProvider.__init__(self, 'HDTorrents')

        self.url_home = ['https://hd-torrents.%s/' % x for x in ('org', 'net', 'me')] + ['https://hdts.ru/']

        self.url_vars = {'login_action': 'index.php',
                         'search': 'torrents.php?search=%s&active=0&options=0&%s'}
        self.url_tmpl = {'config_provider_home_uri': '%(home)s', 'login_action': '%(home)s%(vars)s',
                         'search': '%(home)s%(vars)s'}

        self.categories = {'Episode': [59, 60, 30, 38, 65], 'anime': [4489]}
        self.categories['Season'] = self.categories['Cache'] = self.categories['Episode']

        self.filter = []
        self.may_filter = OrderedDict(
            [('f0', ('not marked', False)), ('f25', ('-25%', True)), ('f50', ('-50%', True)), ('f75', ('-75%', True))])
        self.username, self.password, self.scene, self.minseed, self.minleech = 5 * [None]

    def _authorised(self, **kwargs):

        return super(HDTorrentsProvider, self)._authorised(post_params={'uid': self.username})

    @staticmethod
    def _has_signature(data=None):
        return generic.TorrentProvider._has_signature(data) or \
               (data and re.search(r'(?i)<title[^<]+?(HD-Torrents)', data))

    def _search_provider(self, search_params, **kwargs):

        results = []
        if not self._authorised():
            return results

        items = {'Cache': [], 'Season': [], 'Episode': [], 'Propers': []}

        rc = dict([(k, re.compile('(?i)' + v)) for (k, v) in iteritems({'info': 'details', 'get': 'download'})])
        log = ''
        if self.filter:
            non_marked = 'f0' in self.filter
            # if search_any, use unselected to exclude, else use selected to keep
            filters = ([f for f in self.may_filter if f in self.filter],
                       [f for f in self.may_filter if f not in self.filter])[non_marked]
            rc['filter'] = re.compile('(?i)(%s).png' % '|'.join(
                [f.replace('f', '') for f in filters if self.may_filter[f][1]]))
            log = '%sing (%s) ' % (('keep', 'skipp')[non_marked], ', '.join([self.may_filter[f][0] for f in filters]))

        for mode in search_params:
            rc['cats'] = re.compile('(?i)category=(?:%s)' % self._categories_string(mode, template='', delimiter='|'))
            for search_string in search_params[mode]:
                search_url = self.urls['search'] % (
                    search_string,
                    self._categories_string(mode, template='category[]=%s')
                        .replace('&category[]=4489', ('&genre[]=Animation', '')[mode in ['Cache', 'Propers']]))
                html = self.get_url(search_url)
                if self.should_skip():
                    return results

                cnt = len(items[mode])
                try:
                    if not html or self._has_no_results(html):
                        raise generic.HaltParseException

                    html = re.sub(r'(?ims)<div[^>]+display:\s*none;.*?</div>', '', html)
                    html = re.sub('(?im)href=([^\\"][^>]+)>', r'href="\1">', html)
                    html = (html.replace('"/></td>', '" /></a></td>')
                            .replace('"title="', '" title="')
                            .replace('</u></span></a></td>', '</u></a></span></td>'))
                    html = re.sub('(?im)<b([mtwfs][^>]+)', r'<b>\1</b', html)

                    with BS4Parser(html, attr='width="100%"') as soup:
                        tbl_rows = [tr for tr in ([] if not soup else soup.find_all('tr'))
                                    if tr.find('a', href=rc['info'])]

                        if not len(tbl_rows):
                            raise generic.HaltParseException

                        head = None
                        for tr in tbl_rows:
                            cells = tr.find_all('td')
                            # noinspection PyUnboundLocalVariable
                            if (6 > len(cells) or any(self.filter)
                                and ((non_marked and tr.find('img', src=rc['filter']))
                                     or (not non_marked and not tr.find('img', src=rc['filter'])))):
                                continue
                            try:
                                head = head if None is not head else self._header_row(tr)
                                seeders, leechers, size = [try_int(n, n) for n in [
                                    cells[head[x]].get_text().strip() for x in ('seed', 'leech', 'size')]]
                                if not tr.find('a', href=rc['cats']) or self._reject_item(seeders, leechers):
                                    continue
                                title = tr.find('a', href=rc['info']).get_text().strip()
                                download_url = self._link(tr.find('a', href=rc['get'])['href'])
                            except (AttributeError, TypeError, ValueError, IndexError):
                                continue

                            if title and download_url:
                                items[mode].append((title, download_url, seeders, self._bytesizer(size)))

                except generic.HaltParseException:
                    pass
                except (BaseException, Exception):
                    logger.error(f'Failed to parse. Traceback: {traceback.format_exc()}')

                self._log_search(mode, len(items[mode]) - cnt, log + search_url)

            results = self._sort_seeding(mode, results + items[mode])

        return results


provider = HDTorrentsProvider()
