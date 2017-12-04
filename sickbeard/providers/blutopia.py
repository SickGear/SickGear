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

try:
    from collections import OrderedDict
except ImportError:
    from requests.compat import OrderedDict
import re
import traceback

from . import generic
from sickbeard import logger
from sickbeard.bs4_parser import BS4Parser
from sickbeard.helpers import tryInt
from lib.unidecode import unidecode


class BlutopiaProvider(generic.TorrentProvider):

    def __init__(self):
        generic.TorrentProvider.__init__(self, 'Blutopia')

        self.url_base = 'https://blutopia.xyz/'
        self.urls = {'config_provider_home_uri': self.url_base,
                     'login': self.url_base + 'torrents',
                     'search': self.url_base + 'filter?%s' % '&'.join(
                         ['_token=%s', 'search=%s', 'categories[]=%s', 'freeleech=%s', 'doubleupload=%s', 'featured=%s',
                          'username=', 'imdb=', 'tvdb=', 'tmdb=', 'sorting=created_at', 'qty=50', 'direction=desc'])}

        self.categories = {'Season': [2], 'Episode': [2], 'Cache': [2]}

        self.url = self.urls['config_provider_home_uri']

        self.filter = []
        self.may_filter = OrderedDict([
            ('f0', ('not marked', False)), ('free', ('free', True)),
            ('double', ('2x up', True)), ('feat', ('featured', True))])
        self.digest, self.token, self.resp, self.scene, self.minseed, self.minleech = 6 * [None]

    def logged_in(self, resp):
        try:
            self.token = re.findall('csrf\s*=\s*"([^"]+)', resp)[0]
            self.resp = re.findall('(?sim)(<table.*?Result.*?</table>)', resp)[0]
        except (IndexError, TypeError):
            return False
        return self.has_all_cookies('XSRF-TOKEN')

    def _authorised(self, **kwargs):

        return super(BlutopiaProvider, self)._authorised(
            logged_in=lambda y=None: self.logged_in(y))

    def _search_provider(self, search_params, **kwargs):

        results = []
        if not self._authorised():
            return results

        items = {'Cache': [], 'Season': [], 'Episode': [], 'Propers': []}

        rc = dict((k, re.compile('(?i)' + v))
                  for (k, v) in {'info': 'torrents', 'get': '(.*?download)_check(.*)'}.items())
        log = ''
        if self.filter:
            non_marked = 'f0' in self.filter
            # if search_any, use unselected to exclude, else use selected to keep
            filters = ([f for f in self.may_filter if f in self.filter],
                       [f for f in self.may_filter if f not in self.filter])[non_marked]
            filters += (((all([x in filters for x in 'free', 'double', 'feat']) and ['freedoublefeat'] or [])
                         + (all([x in filters for x in 'free', 'double']) and ['freedouble'] or [])
                         + (all([x in filters for x in 'feat', 'double']) and ['featdouble'] or [])),
                        ((not all([x not in filters for x in 'free', 'double', 'feat']) and ['freedoublefeat'] or [])
                         + (not all([x not in filters for x in 'free', 'double']) and ['freedouble'] or [])
                         + (not all([x not in filters for x in 'feat', 'double']) and ['featdouble'] or []))
                        )[non_marked]
            rc['filter'] = re.compile('(?i)^(%s)$' % '|'.join(
                ['%s' % f for f in filters if (f in self.may_filter and self.may_filter[f][1]) or f]))
            log = '%sing (%s) ' % (('keep', 'skipp')[non_marked], ', '.join(
                [f in self.may_filter and self.may_filter[f][0] or f for f in filters]))
        for mode in search_params.keys():
            if mode in ['Season', 'Episode']:
                show_type = self.show.air_by_date and 'Air By Date' \
                    or self.show.is_sports and 'Sports' or None
                if show_type:
                    logger.log(u'Provider does not carry shows of type: [%s], skipping' % show_type, logger.DEBUG)
                    return results

            for search_string in search_params[mode]:
                search_string = isinstance(search_string, unicode) and unidecode(search_string) or search_string
                search_url = self.urls['search'] % (
                    self.token, '+'.join(search_string.split()), self._categories_string(mode, ''), '', '', '')

                resp = self.get_url(search_url, json=True)

                cnt = len(items[mode])
                try:
                    if not resp or not resp.get('rows'):
                        raise generic.HaltParseException

                    html = '<html><body>%s</body></html>' % \
                           self.resp.replace('</tbody>', '%s</tbody>' % ''.join(resp.get('result', [])))
                    with BS4Parser(html, features=['html5lib', 'permissive']) as soup:
                        torrent_table = soup.find('table', class_='table')
                        torrent_rows = [] if not torrent_table else torrent_table.find_all('tr')

                        if 2 > len(torrent_rows):
                            raise generic.HaltParseException

                        head = None
                        for tr in torrent_rows[1:]:
                            cells = tr.find_all('td')
                            if 5 > len(cells):
                                continue
                            if any(self.filter):
                                marked = ','.join([x.attrs.get('data-original-title', '').lower() for x in tr.find_all(
                                    'i', attrs={'class': ['text-gold', 'fa-diamond', 'fa-certificate']})])
                                # noinspection PyTypeChecker
                                munged = ''.join(filter(marked.__contains__, ['free', 'double', 'feat']))
                                if ((non_marked and rc['filter'].search(munged)) or
                                        (not non_marked and not rc['filter'].search(munged))):
                                    continue
                            try:
                                head = head if None is not head else self._header_row(
                                    tr, {'seed': r'circle-up', 'leech': r'circle-down', 'size': r'fa-file'})
                                seeders, leechers, size = [tryInt(n, n) for n in [
                                    cells[head[x]].get_text().strip() for x in 'seed', 'leech', 'size']]
                                if self._peers_fail(mode, seeders, leechers):
                                    continue

                                title = tr.find('a', href=rc['info'])['data-original-title']
                                download_url = self._link(rc['get'].sub(r'\1\2', tr.find('a', href=rc['get'])['href']))
                            except (AttributeError, TypeError, ValueError, IndexError):
                                continue

                            if title and download_url:
                                items[mode].append((title, download_url, seeders, self._bytesizer(size)))

                except generic.HaltParseException:
                    pass
                except (StandardError, Exception):
                    logger.log(u'Failed to parse. Traceback: %s' % traceback.format_exc(), logger.ERROR)

                self._log_search(mode, len(items[mode]) - cnt, log + search_url)

            results = self._sort_seeding(mode, results + items[mode])

        return results

    @staticmethod
    def ui_string(key):

        return 'blutopia_digest' == key and 'use... \'remember_web_xx=yy\'' or ''


provider = BlutopiaProvider()
