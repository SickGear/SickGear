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

import base64
import re
import traceback

from . import generic
from sickbeard import logger
from sickbeard.bs4_parser import BS4Parser
from sickbeard.helpers import tryInt
from lib.unidecode import unidecode


class BBProvider(generic.TorrentProvider):

    def __init__(self):

        generic.TorrentProvider.__init__(self, 'bB', cache_update_freq=15)

        self.url_base = [re.sub('(?i)[qx\sz]+', '', x[::-1]) for x in [
            'HaQ', 'c0Rz', 'MH', 'yL6', 'NW Yi9', 'pJmbv', 'Hd', 'buMz', 'wLn J3', '=xXx=']]
        self.url_base = base64.b64decode(''.join(self.url_base))
        self.urls = {'config_provider_home_uri': self.url_base,
                     'login_action': self.url_base + 'login.php',
                     'search': self.url_base + 'torrents.php?%s&searchstr=%s'}

        self.categories = {'Season': [10], 'Episode': [10], 'Cache': [10], 'anime': [8]}

        self.url = self.urls['config_provider_home_uri']

        self.username, self.password, self.freeleech, self.minseed, self.minleech = 5 * [None]

    def _authorised(self, **kwargs):

        return super(BBProvider, self)._authorised(logged_in=(lambda y=None: self.has_all_cookies('session')),
                                                   post_params={'keeplogged': '1', 'form_tmpl': True})

    def _search_provider(self, search_params, **kwargs):

        results = []
        if not self._authorised():
            return results

        items = {'Cache': [], 'Season': [], 'Episode': [], 'Propers': []}

        rc = dict((k, re.compile('(?i)' + v)) for (k, v) in {
            'info': 'view', 'get': 'download', 'nodots': '[\.\s]+'}.items())
        for mode in search_params.keys():
            for search_string in search_params[mode]:
                search_string = isinstance(search_string, unicode) and unidecode(search_string) or search_string
                search_url = self.urls['search'] % (
                    self._categories_string(mode, 'filter_cat[%s]=1'), rc['nodots'].sub('+', search_string))
                html = self.get_url(search_url)

                cnt = len(items[mode])
                try:
                    if not html or self._has_no_results(html) or 'Translation: No search results' in html:
                        raise generic.HaltParseException

                    with BS4Parser(html, features=['html5lib', 'permissive']) as soup:
                        torrent_table = soup.find(id='torrent_table')
                        torrent_rows = [] if not torrent_table else torrent_table.find_all('tr')

                        if 2 > len(torrent_rows):
                            raise generic.HaltParseException

                        head = None
                        for tr in torrent_rows[1:]:
                            cells = tr.find_all('td')
                            if 5 > len(cells):
                                continue
                            try:
                                head = head if None is not head else self._header_row(tr)
                                seeders, leechers, size = [tryInt(n, n) for n in [
                                    cells[head[x]].get_text().strip() for x in 'seed', 'leech', 'size']]
                                if self._reject_item(seeders, leechers, self.freeleech and (not bool(
                                        re.search('(?i)>\s*Freeleech!*\s*<', cells[1].encode(formatter='minimal'))))):
                                    continue

                                title = self.regulate_title(tr.find('a', title=rc['info']).get_text().strip())
                                download_url = self._link(tr.find('a', title=rc['get'])['href'])
                            except (AttributeError, TypeError, ValueError):
                                continue

                            if title and download_url:
                                items[mode].append((title, download_url, seeders, self._bytesizer(size)))

                except generic.HaltParseException:
                    pass
                except (StandardError, Exception):
                    logger.log(u'Failed to parse. Traceback: %s' % traceback.format_exc(), logger.ERROR)
                self._log_search(mode, len(items[mode]) - cnt, search_url)

            results = self._sort_seeding(mode, results + items[mode])

        return results

    @staticmethod
    def regulate_title(item_text):

        t = ['']
        bl = '[*\[({]+\s*'
        br = '\s*[})\]*]+'
        title = re.sub('(.*?)((?i)%sproper%s)(.*)' % (bl, br), r'\1\3\2', item_text)
        for r in ('\s+-\s+', '(?:\(\s*)?(?:19|20)\d\d(?:\-\d\d\-\d\d)?(?:\s*\))?',
                  'S\d\d+(?:E\d\d+)?', '(?:Series|Season)\s*\d+'):
            m = re.findall('(.*%s)(.*)' % r, title)
            if any(m) and len(m[0][0]) > len(t[0]):
                t = m[0]
        t = (tuple(title), t)[any(t)]

        title_parts = title.rsplit('[')
        title_tags = [] if 2 > len(title_parts) else [x.strip() for x in title_parts[1].rstrip(']').split('/')]

        tag_str = '_'.join(title_tags)
        tags = [re.findall(x, tag_str, flags=re.X) for x in
                ('(?i)Proper|Repack',
                 '(?i)(?:48|72|108|216|)0(?:[pi]|hd)?',
                 '''
                 (?i)(hr.ws.pdtv|blu.?ray|hddvd|
                 pdtv|hdtv|dsr|tvrip|web.?(?:dl|rip)|dvd.?rip|b[r|d]rip|mpeg-?2)
                 ''', '''
                 (?i)([hx].?26[45]|divx|xvid)
                 ''', '''
                 (?i)(avi|mkv|mp4|sub(?:b?ed|pack|s))
                 ''')]

        title = ('%s`%s' % (
            re.sub('|'.join(['|'.join([re.escape(y) for y in x]) for x in tags + [['/', ' ']] if x]).strip('|'),
                   '`', t[-1]),
            re.sub('(?i)((?:48|72|108|216|)0)(?:[pi]|hd)?', r'\1p',
                   '`'.join(['`'.join(x) for x in tags[:-1]]).rstrip('`')) +
            ('', '`hdtv')[not any(tags[2])] + ('', '`x264')[not any(tags[3])]))

        title = '`'.join([x.strip('.') for x in ([], [t[0]])[1 < len(t)] + ['%s-NOGRP' % title]])

        for r in [('\[`+', '['), ('`+\]', ']'), ('\s+[-]?\s+|\s+`|`\s+', '`'), ('`+', '.')]:
            title = re.sub(r[0], r[1], title)

        title += + any(tags[4]) and ('.%s' % tags[4][0]) or ''
        return title


provider = BBProvider()
