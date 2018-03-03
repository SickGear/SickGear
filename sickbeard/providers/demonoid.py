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
import traceback
import urllib

from . import generic
from sickbeard import logger
from sickbeard.bs4_parser import BS4Parser
from sickbeard.helpers import tryInt
from lib.unidecode import unidecode


class DemonoidProvider(generic.TorrentProvider):

    def __init__(self):
        generic.TorrentProvider.__init__(self, 'Demonoid')

        self.url_home = ['https://www.demonoid.pw/']

        self.url_vars = {'search': 'files/?category=3&subcategory=0&language=0&quality=0' +
                                   '&seeded=2&external=2&uid=0&sort=&query=%s'}
        self.url_tmpl = {'config_provider_home_uri': '%(home)s', 'search': '%(home)s%(vars)s'}

        self.minseed, self.minleech = 2 * [None]

    @staticmethod
    def _has_signature(data=None):
        return data and re.search(r'(?i)Demonoid', data[33:1024:])

    def _search_provider(self, search_params, **kwargs):

        results = []
        if not self.url:
            return results

        items = {'Cache': [], 'Season': [], 'Episode': [], 'Propers': []}

        rc = dict((k, re.compile('(?i)' + v)) for (k, v) in {'info': '/details/', 'get': '/download/'}.iteritems())
        for mode in search_params.keys():
            for search_string in search_params[mode]:

                search_string = isinstance(search_string, unicode) and unidecode(search_string) or search_string
                search_url = self.urls['search'] % ((search_string, '')['Cache' == mode])

                html = self.get_url(search_url)

                cnt = len(items[mode])
                try:
                    if not html or self._has_no_results(html):
                        raise generic.HaltParseException

                    re_table = re.search('(?is)no_pad.*?(<table[^>]+class="font_12px".*</table>)', html)
                    torrent_table = '' if not re_table else re_table.group(1)

                    with BS4Parser('<html><body>%s</body></html>' % torrent_table,
                                   features=['html5lib', 'permissive']) as soup:
                        torrent_rows = soup.find('table').find_all('tr')[5:]

                        if not len(torrent_rows):
                            raise generic.HaltParseException

                        title = None
                        for tr in torrent_rows:
                            try:
                                if None is title:
                                    title = tr.find('a', href=rc['info']).get_text().strip()
                                    title = '.' in title and title.replace(' ', '') or title
                                    continue

                                seeders, leechers, size = [tryInt(n, n) for n in [
                                    tr.find_all('td')[x].get_text().strip() for x in -2, -1, -5]]
                                if self._peers_fail(mode, seeders, leechers):
                                    title = None
                                    continue

                                download_url = self._link(tr.find('a', href=rc['get'])['href'])
                            except (AttributeError, TypeError, ValueError, IndexError):
                                continue

                            try:
                                has_series = re.findall('(?i)(.*?series[^\d]*?\d+)(.*)', title)
                                if has_series:
                                    rc_xtras = re.compile('(?i)([. _-]|^)(special|extra)s?\w*([. _-]|$)')
                                    has_special = rc_xtras.findall(has_series[0][1])
                                    if has_special:
                                        title = has_series[0][0] + rc_xtras.sub(list(set(
                                            list(has_special[0][0]) + list(has_special[0][2])))[0],
                                                                                has_series[0][1])
                                    title = re.sub('(?i)series', r'Season', title)

                                title_parts = re.findall(
                                    '(?im)^(.*?)(?:Season[^\d]*?(\d+).*?)?' +
                                    '(?:(?:pack|part|pt)\W*?)?(\d+)[^\d]*?of[^\d]*?(?:\d+)(.*?)$', title)
                                if len(title_parts):
                                    new_parts = [tryInt(part, part.strip()) for part in title_parts[0]]
                                    if not new_parts[1]:
                                        new_parts[1] = 1
                                    new_parts[2] = ('E%02d', ' Pack %d')[mode in 'Season'] % new_parts[2]
                                    title = '%s.S%02d%s.%s' % tuple(new_parts)

                                dated = re.findall(
                                    '(?i)([(\s]*)((?:\d+\s*(?:st|nd|rd|th)?\s)?[adfjmnos]\w{2,}\s+(?:19|20)\d\d)([)\s]*)', title)
                                if dated:
                                    title = title.replace(''.join(dated[0]), '%s%s%s' % (
                                        ('', ' ')[1 < len(dated[0][0])], parse(dated[0][1]).strftime('%Y-%m-%d'),
                                        ('', ' ')[1 < len(dated[0][2])]))
                                    add_pad = re.findall('((?:19|20)\d\d[-]\d\d[-]\d\d)([\w\W])', title)
                                    if len(add_pad) and add_pad[0][1] not in [' ', '.']:
                                        title = title.replace(''.join(
                                            add_pad[0]), '%s %s' % (add_pad[0][0], add_pad[0][1]))
                                    title = re.sub(r'(?sim)(.*?)(?:Episode|Season).\d+.(.*)', r'\1\2', title)

                                if title and download_url:
                                    items[mode].append((title, download_url, seeders, self._bytesizer(size)))
                            except (StandardError, Exception):
                                pass

                            title = None

                except generic.HaltParseException:
                    pass
                except (StandardError, Exception):
                    logger.log(u'Failed to parse. Traceback: %s' % traceback.format_exc(), logger.ERROR)

                self._log_search(mode, len(items[mode]) - cnt, search_url)

            results = self._sort_seeding(mode, results + items[mode])

        return results


provider = DemonoidProvider()
