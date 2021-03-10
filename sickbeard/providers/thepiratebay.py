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

from __future__ import with_statement, division

import re
import traceback

from . import generic
from .. import logger
from ..helpers import try_int
from bs4_parser import BS4Parser

from _23 import b64decodestring, unidecode
from six import iteritems


class ThePirateBayProvider(generic.TorrentProvider):

    def __init__(self):
        generic.TorrentProvider.__init__(self, 'The Pirate Bay')

        self.url_home = ['https://thepiratebay.org/'] + \
                        ['https://%s/' % b64decodestring(x) for x in [''.join(x) for x in [
                            [re.sub(r'[h\sI]+', '', x[::-1]) for x in [
                                'm IY', '5  F', 'HhIc', 'vI J', 'HIhe', 'uI k', '2  d', 'uh l']],
                            [re.sub(r'[N\sQ]+', '', x[::-1]) for x in [
                                'lN Gc', 'X  Yy', 'c lNR', 'vNJNH', 'kQNHe', 'GQdQu', 'wNN9']],
                        ]]]

        self.url_vars = {'search': '/s/?q=%s&video=on&page=0&orderby=',
                         'search2': 'search.php?q=%s&video=on&search=Pirate+Search&page=0&orderby='}
        self.url_tmpl = {'config_provider_home_uri': '%(home)s',
                         'search': '%(home)s%(vars)s', 'search2': '%(home)s%(vars)s'}
        self.urls = {'api': 'https://apibay.org/q.php?q=%s'}

        self.proper_search_terms = None

        self.minseed, self.minleech = 2 * [None]
        self.confirmed = False

    @staticmethod
    def _has_signature(data=None):
        return data and re.search(r'Pirate\sBay', data[33:7632:])

    def _season_strings(self, ep_obj, **kwargs):

        if ep_obj.show_obj.air_by_date or ep_obj.show_obj.sports:
            airdate = str(ep_obj.airdate).split('-')[0]
            ep_detail = [airdate, 'Season ' + airdate]
        elif ep_obj.show_obj.anime:
            ep_detail = '%02i' % ep_obj.scene_absolute_number
        else:
            season = (ep_obj.season, ep_obj.scene_season)[bool(ep_obj.show_obj.is_scene)]
            ep_detail = ['S%02d' % int(season), 'Season %s -Ep*' % season]

        return [{'Season': self._build_search_strings(ep_detail)}]

    def _episode_strings(self, ep_obj, **kwargs):

        return super(ThePirateBayProvider, self)._episode_strings(
            ep_obj, date_or=True,
            ep_detail_anime=lambda x: '%02i' % x, **kwargs)

    def _search_provider(self, search_params, search_mode='eponly', epcount=0, **kwargs):

        results = []
        if not self.url:
            return results

        items = {'Cache': [], 'Season': [], 'Episode': [], 'Propers': []}

        rc = dict([(k, re.compile('(?i)' + v)) for (k, v) in iteritems({
            'info': 'detail|descript', 'get': 'magnet',
            'verify': '(?:helper|moderator|trusted|vip)', 'size': r'size[^\d]+(\d+(?:[.,]\d+)?\W*[bkmgt]\w+)'})])

        for mode in search_params:
            for search_string in search_params[mode]:
                search_string = unidecode(search_string)

                if 'Cache' != mode:
                    search_url = self.urls['api'] % search_string
                    pages = [self.get_url(search_url, parse_json=True)]
                else:
                    urls = [self.urls['api'] % 'category:%s' % cur_cat for cur_cat in (205, 208)]
                    search_url = ', '.join(urls)
                    pages = [self.get_url(cur_url, parse_json=True) for cur_url in urls]

                seen_not_found = False
                if any(pages):
                    cnt = len(items[mode])
                    for cur_page in pages:
                        for cur_item in cur_page or []:
                            title, total_found = [cur_item.get(k) for k in ('name', 'total_found')]
                            if 1 == try_int(total_found):
                                seen_not_found = True
                                continue
                            seeders, leechers, size = [try_int(n, n) for n in [
                                cur_item.get(k) for k in ('seeders', 'leechers', 'size')]]
                            if not self._reject_item(seeders, leechers):
                                status, info_hash = [cur_item.get(k) for k in ('status', 'info_hash')]
                                if self.confirmed and not rc['verify'].search(status):
                                    logger.log(u'Skipping untrusted non-verified result: ' + title, logger.DEBUG)
                                    continue
                                download_magnet = info_hash if '&tr=' in info_hash \
                                    else self._dhtless_magnet(info_hash, title)

                                if title and download_magnet:
                                    items[mode].append((title, download_magnet, seeders, self._bytesizer(size)))

                    if len(items[mode]):
                        self._log_search(mode, len(items[mode]) - cnt, search_url)
                        continue
                if seen_not_found and not len(items[mode]):
                    continue

                html = self.get_url(self.urls['config_provider_home_uri'])
                if self.should_skip() or not html:
                    return results

                body = re.sub(r'(?sim).*?(<body.*?)<foot.*', r'\1</body>', html)
                with BS4Parser(body) as soup:
                    if 'Cache' != mode:
                        search_url = None
                        if 'action="/s/' in body:
                            search_url = self.urls['search'] % search_string
                        elif 'action="/search.php' in body:
                            search_url = self.urls['search2'] % search_string
                        if search_url:
                            try:
                                pages = [self.get_url(search_url, proxy_browser=True)]
                            except ValueError:
                                pass
                    else:
                        try:
                            html = self.get_url(self._link(soup.find('a', title="Browse Torrents")['href']))
                            if html:
                                js = re.findall(r'check\sthat\s+(\w+.js)\s', html)
                                if js:
                                    js_file = re.findall('<script[^"]+?"([^"]*?%s[^"]*?).*?</script>' % js[0], html)
                                    if js_file:
                                        html = self.get_url(self._link(js_file[0]))
                            if html:  # could be none from previous get_url for js
                                # html or js can be source for parsing cat|browse links
                                urls = re.findall(
                                        '(?i)<a[^>]+?href="([^>]+?(?:cat|browse)[^>]+?)"[^>]+?>[^>]*?tv shows<', html)
                                search_url = ', '.join([self._link(cur_url) for cur_url in urls])
                                pages = [self.get_url(self._link(cur_url), proxy_browser=True) for cur_url in urls]
                        except ValueError:
                            pass

                if not any(pages):
                    return results

                list_type = None
                head = None
                rows = ''
                if len(pages) and '<thead' in pages[0]:
                    list_type = 0
                    headers = 'seed|leech|size'
                    for cur_html in pages:
                        try:
                            with BS4Parser(cur_html, parse_only=dict(table={'id': 'searchResult'})) as tbl:
                                rows += ''.join([_r.prettify() for _r in tbl.select('tr')[1:]])
                                if not head:
                                    header = [re.sub(r'(?i).*?(?:order\sy\s)?(%s)(?:ers)?.*?' % headers, r'\1',
                                                     '' if not x else x.get('title', '').lower()) for x in
                                              [t.select_one('[title]') for t in
                                               tbl.find('tr', class_='header').find_all('th')]]
                                    head = dict((k, header.index(k) - len(header)) for k in headers.split('|'))
                        except(BaseException, Exception):
                            pass
                    html = ('', '<table><tr data="header-placeholder"></tr>%s</table>' % rows)[all([head, rows])]
                elif len(pages) and '<ol' in pages[0]:
                    list_type = 1
                    headers = 'seed|leech|size'
                    for cur_html in pages:
                        try:
                            with BS4Parser(cur_html, parse_only=dict(ol={'id': 'torrents'})) as tbl:
                                rows += ''.join([_r.prettify() for _r in tbl.find_all('li', class_='list-entry')])
                                if not head:
                                    header = [re.sub(
                                        '(?i).*(?:item-(%s)).*' % headers, r'\1', ''.join(t.get('class', '')))
                                              for t in tbl.find('li', class_='list-header').find_all('span')]
                                    head = dict((k, header.index(k) - len(header)) for k in headers.split('|'))
                        except(BaseException, Exception):
                            pass
                    html = ('', '<ol><li data="header-placeholder"></li>%s</ol>' % rows)[all([head, rows])]

                html = '<!DOCTYPE html><html><head></head><body id="tpb_results">%s</body></html>' % html

                cnt = len(items[mode])
                try:
                    if None is list_type or not html or self._has_no_results(html):
                        self._url = None
                        raise generic.HaltParseException

                    with BS4Parser(html, parse_only=dict(body={'id': 'tpb_results'})) as tbl:
                        row_type = ('li', 'tr')[not list_type]
                        tbl_rows = [] if not tbl else tbl.find_all(row_type)

                        if 2 > len(tbl_rows):
                            raise generic.HaltParseException

                        for tr in tbl.find_all(row_type)[1:]:
                            cells = tr.find_all(('span', 'td')[not list_type])
                            if 3 > len(cells):
                                continue
                            try:
                                head = head if None is not head else self._header_row(tr)
                                seeders, leechers, size = [try_int(n, n) for n in [
                                    cells[head[x]].get_text().strip() for x in ('seed', 'leech', 'size')]]
                                if self._reject_item(seeders, leechers):
                                    continue

                                info = tr.find('a', title=rc['info']) or tr.find('a', href=rc['info'])
                                title = info.get_text().strip().replace('_', '.')
                                download_magnet = (tr.find('a', title=rc['get'])
                                                   or tr.find('a', href=rc['get']))['href']
                            except (AttributeError, TypeError, ValueError):
                                continue

                            if self.confirmed and not (
                                    tr.find('img', title=rc['verify']) or tr.find('img', alt=rc['verify'])
                                    or tr.find('img', src=rc['verify'])):
                                logger.log(u'Skipping untrusted non-verified result: ' + title, logger.DEBUG)
                                continue

                            if title and download_magnet:
                                items[mode].append((title, download_magnet, seeders, self._bytesizer(size)))

                except generic.HaltParseException:
                    pass
                except (BaseException, Exception):
                    logger.log(u'Failed to parse. Traceback: %s' % traceback.format_exc(), logger.ERROR)
                self._log_search(mode, len(items[mode]) - cnt, search_url)

            results = self._sort_seeding(mode, results + items[mode])

        return results


provider = ThePirateBayProvider()
