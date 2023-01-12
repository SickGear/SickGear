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

from _23 import filter_iter, unidecode
from six import iteritems


class BlutopiaProvider(generic.TorrentProvider):

    def __init__(self):
        generic.TorrentProvider.__init__(self, 'Blutopia')

        self.url_base = 'https://blutopia.xyz/'
        self.urls = {'config_provider_home_uri': self.url_base,
                     'login': self.url_base + 'pages/1',
                     'search': self.url_base + 'torrents/filter?%s' % '&'.join(
                         ['_token=%s', 'search=%s', 'categories[]=%s', 'freeleech=%s', 'doubleupload=%s', 'featured=%s',
                          'username=', 'imdb=', 'tvdb=', 'tmdb=', 'mal=', 'view=list', 'sorting=created_at', 'qty=50',
                          'direction=desc'])}

        self.categories = {'shows': [2]}

        self.url = self.urls['config_provider_home_uri']

        self.filter = []
        self.may_filter = OrderedDict([
            ('f0', ('not marked', False)), ('free', ('free', True)),
            ('double', ('double up', True)), ('feat', ('featured', True))])
        self.digest, self._token, self.resp, self.minseed, self.minleech = 5 * [None]

    def _authorised(self, **kwargs):

        return super(BlutopiaProvider, self)._authorised(
            logged_in=self.logged_in, failed_msg=(lambda y=None: u'Invalid cookie details for %s. Check settings'))

    def logged_in(self, resp=None):

        result = True
        if not self._token:
            try:
                result = 'Username' not in resp and 'Logout' in resp
                input_tag = re.findall(r'(<input[^>]+?"(?:hidden|_token)"[^>]+?"(?:hidden|_token)"[^>]+?>)', resp)[0]
                token = re.findall(r'value\s*=\s*["\']\s*([^"\'\s]+)', input_tag)[0]
                csrf = re.findall(r'<meta[^>]+csrf-token[^>]+content[^"]+"\s*([^\s"]+)', resp)[0]
                self._token = csrf == token and token
            except (BaseException, Exception):
                result = False
        return result

    def _search_provider(self, search_params, **kwargs):

        results = []
        if not self._authorised():
            return results

        items = {'Cache': [], 'Season': [], 'Episode': [], 'Propers': []}

        rc = dict([(k, re.compile('(?i)' + v))
                   for (k, v) in iteritems({'info': 'torrents', 'get': '(.*?download)(?:_check)?(.*)'})])
        log = ''
        if self.filter:
            non_marked = 'f0' in self.filter
            # if search_any, use unselected to exclude, else use selected to keep
            filters = ([f for f in self.may_filter if f in self.filter],
                       [f for f in self.may_filter if f not in self.filter])[non_marked]
            filters += (((all([x in filters for x in ('free', 'double', 'feat')]) and ['freedoublefeat'] or [])
                         + (all([x in filters for x in ('free', 'double')]) and ['freedouble'] or [])
                         + (all([x in filters for x in ('feat', 'double')]) and ['featdouble'] or [])),
                        ((not all([x not in filters for x in ('free', 'double', 'feat')]) and ['freedoublefeat'] or [])
                         + (not all([x not in filters for x in ('free', 'double')]) and ['freedouble'] or [])
                         + (not all([x not in filters for x in ('feat', 'double')]) and ['featdouble'] or []))
                        )[non_marked]
            rc['filter'] = re.compile(r'(?i)^(%s)$' % '|'.join(
                ['%s' % f for f in filters if (f in self.may_filter and self.may_filter[f][1]) or f]))
            log = '%sing (%s) ' % (('keep', 'skipp')[non_marked], ', '.join(
                [f in self.may_filter and self.may_filter[f][0] or f for f in filters]))
        for mode in search_params:
            if mode in ['Season', 'Episode']:
                show_type = self.show_obj.air_by_date and 'Air By Date' \
                            or self.show_obj.is_sports and 'Sports' or None
                if show_type:
                    logger.log(u'Provider does not carry shows of type: [%s], skipping' % show_type, logger.DEBUG)
                    return results

            for search_string in search_params[mode]:
                search_string = unidecode(search_string)
                search_url = self.urls['search'] % (
                    self._token, search_string.replace('.', ' '), self._categories_string(template=''), '', '', '')

                resp = self.get_url(search_url)
                if self.should_skip():
                    return results

                cnt = len(items[mode])
                try:
                    if not resp:
                        raise generic.HaltParseException

                    html = '<html><body>%s</body></html>' % resp
                    with BS4Parser(html, parse_only=dict(table={'class': (lambda at: at and 'table' in at)})) as tbl:
                        tbl_rows = [] if not tbl else tbl.find_all('tr')

                        if 2 > len(tbl_rows):
                            raise generic.HaltParseException

                        head = None
                        for tr in tbl_rows[1:]:
                            cells = tr.find_all('td')
                            if 5 > len(cells):
                                continue
                            if any(self.filter):
                                marked = ','.join([x.attrs.get('data-original-title', '').lower() for x in tr.find_all(
                                    'i', attrs={'class': ['text-gold', 'fa-diamond', 'fa-certificate']})])
                                # noinspection PyTypeChecker
                                munged = ''.join(filter_iter(marked.__contains__, ['free', 'double', 'feat']))
                                # noinspection PyUnboundLocalVariable
                                if ((non_marked and rc['filter'].search(munged)) or
                                        (not non_marked and not rc['filter'].search(munged))):
                                    continue
                            try:
                                head = head if None is not head else self._header_row(
                                    tr, {'seed': r'circle-up', 'leech': r'circle-down', 'size': r'fa-file'})
                                seeders, leechers, size = [try_int(n, n) for n in [
                                    cells[head[x]].get_text().strip() for x in ('seed', 'leech', 'size')]]
                                if self._reject_item(seeders, leechers):
                                    continue

                                title = tr.find('a', href=rc['info']).get_text().strip()
                                download_url = self._link(''.join(rc['get'].findall(
                                    tr.find('a', href=rc['get'])['href'])[0]))
                            except (AttributeError, TypeError, ValueError, IndexError):
                                continue

                            if title and download_url:
                                items[mode].append((title, download_url, seeders, self._bytesizer(size)))

                except generic.HaltParseException:
                    pass
                except (BaseException, Exception):
                    logger.log(u'Failed to parse. Traceback: %s' % traceback.format_exc(), logger.ERROR)

                self._log_search(mode, len(items[mode]) - cnt, log + search_url)

            results = self._sort_seeding(mode, results + items[mode])

        return results

    @staticmethod
    def ui_string(key):

        return 'blutopia_digest' == key and 'use... \'remember_web_xx=yy\'' or ''


provider = BlutopiaProvider()
