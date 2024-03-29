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


class PrivateHDProvider(generic.TorrentProvider):

    def __init__(self):
        generic.TorrentProvider.__init__(self, 'PrivateHD')

        self.url_base = 'https://privatehd.to/'
        self.urls = {'config_provider_home_uri': self.url_base,
                     'login': self.url_base + 'rules',
                     'search': self.url_base + 'torrents?%s' % '&'.join(
                         ['in=1', 'tags=', 'type=2', 'language=0', 'subtitle=0', 'rip_type=0',
                          'video_quality=0', 'uploader=', 'search=%s', 'tv_type[]=%s'])}

        self.categories = {'Season': [2], 'Episode': [1], 'Cache': [0]}

        self.url = self.urls['config_provider_home_uri']

        self.filter = []
        self.may_filter = OrderedDict([
            ('f0', ('not marked', False)), ('free', ('free', True)),
            ('half', ('half down', True)), ('double', ('double up', True))])
        self.digest, self.minseed, self.minleech = 3 * [None]
        self.confirmed = False

    def _authorised(self, **kwargs):

        return super(PrivateHDProvider, self)._authorised(
            logged_in=(lambda y='': 'English' in y and 'auth/login' not in y and all(
                [(self.session.cookies.get('privatehdx_session', domain='') or 'sg!no!pw') in self.digest])),
            failed_msg=(lambda y=None: 'Invalid cookie details for %s. Check settings'))

    def _search_provider(self, search_params, **kwargs):

        results = []
        if not self._authorised():
            return results

        items = {'Cache': [], 'Season': [], 'Episode': [], 'Propers': []}

        rc = dict([(k, re.compile('(?i)' + v))
                   for (k, v) in iteritems({'info': r'.*?details\s*-\s*', 'get': 'download'})])
        log = ''
        if self.filter:
            non_marked = 'f0' in self.filter
            # if search_any, use unselected to exclude, else use selected to keep
            filters = ([f for f in self.may_filter if f in self.filter],
                       [f for f in self.may_filter if f not in self.filter])[non_marked]
            filters += (((all([x in filters for x in ('free', 'double')]) and ['freedouble'] or [])
                        + (all([x in filters for x in ('half', 'double')]) and ['halfdouble'] or [])),
                        ((not all([x not in filters for x in ('free', 'double')]) and ['freedouble'] or [])
                         + (not all([x not in filters for x in ('half', 'double')]) and ['halfdouble'] or []))
                        )[non_marked]
            rc['filter'] = re.compile('(?i)^(%s)$' % '|'.join(
                ['%s' % f for f in filters if (f in self.may_filter and self.may_filter[f][1]) or f]))
            log = '%sing (%s) ' % (('keep', 'skipp')[non_marked], ', '.join(
                [f in self.may_filter and self.may_filter[f][0] or f for f in filters]))
        for mode in search_params:
            if mode in ['Season', 'Episode']:
                show_type = self.show_obj.air_by_date and 'Air By Date' \
                            or self.show_obj.is_sports and 'Sports' or self.show_obj.is_anime and 'Anime' or None
                if show_type:
                    logger.debug(f'Provider does not carry shows of type: [{show_type}], skipping')
                    return results

            for search_string in search_params[mode]:
                search_url = self.urls['search'] % (
                    '+'.join(search_string.split()), self._categories_string(mode, ''))

                html = self.get_url(search_url)
                if self.should_skip():
                    return results

                cnt = len(items[mode])
                try:
                    if not html or self._has_no_results(html):
                        raise generic.HaltParseException

                    with BS4Parser(html, parse_only=dict(table={'class': (lambda at: at and 'table' in at)})) as tbl:
                        tbl_rows = [] if not tbl else tbl.find_all('tr')

                        if 2 > len(tbl_rows):
                            raise generic.HaltParseException

                        head = None
                        for tr in tbl_rows[1:]:
                            cells = tr.find_all('td')
                            if 5 > len(cells) or (self.confirmed and tr.find('i', title=re.compile('(?i)unverified'))):
                                continue
                            if any(self.filter):
                                marked = ','.join([x.attrs.get('title', '').lower() for x in tr.find_all(
                                    'i', attrs={'class': ['fa-star', 'fa-diamond', 'fa-star-half-o']})])
                                munged = ''.join(filter(marked.__contains__, ['free', 'half', 'double']))
                                # noinspection PyUnboundLocalVariable
                                if ((non_marked and rc['filter'].search(munged)) or
                                        (not non_marked and not rc['filter'].search(munged))):
                                    continue
                            try:
                                head = head if None is not head else self._header_row(tr)
                                seeders, leechers, size = [try_int(n, n) for n in [
                                    cells[head[x]].get_text().strip() for x in ('seed', 'leech', 'size')]]
                                if self._reject_item(seeders, leechers):
                                    continue

                                title = rc['info'].sub('', tr.find('a', attrs={'title': rc['info']})['title'])
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

    @staticmethod
    def ui_string(key):
        return 'privatehd_digest' == key and 'use... \'privatehdx_session=xx\'' or ''


provider = PrivateHDProvider()
