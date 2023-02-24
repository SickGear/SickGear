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

from . import generic
from .. import logger
from ..helpers import anon_url, try_int
from bs4_parser import BS4Parser

from six import iteritems


class SceneTimeProvider(generic.TorrentProvider):

    def __init__(self):
        generic.TorrentProvider.__init__(self, 'SceneTime')

        self.url_home = ['https://%s.scenetime.com/' % u for u in ('www', 'uk')]

        self.url_vars = {'login': 'support.php', 'search': 'browse.php?cata=yes&%s&search=%s%s',
                         'get': 'download.php/%s.torrent'}
        self.url_tmpl = {'config_provider_home_uri': '%(home)s', 'login': '%(home)s%(vars)s',
                         'search': '%(home)s%(vars)s', 'get': '%(home)s%(vars)s'}

        self.categories = {'Season': [43], 'Episode': [2, 9, 63, 77, 79, 100, 83, 8, 19], 'anime': [18]}
        self.categories['Cache'] = self.categories['Season'] + self.categories['Episode']

        self.digest, self.freeleech, self.minseed, self.minleech = 4 * [None]

    def _authorised(self, **kwargs):

        return super(SceneTimeProvider, self)._authorised(
            logged_in=(lambda y='': all(
                ['staff-support' in y, self.has_all_cookies()] +
                [(self.session.cookies.get(x, domain='') or 'sg!no!pw') in self.digest
                 for x in ('uid', 'pass')])),
            failed_msg=(lambda y=None: u'Invalid cookie details for %s. Check settings'))

    @staticmethod
    def _has_signature(data=None):
        return generic.TorrentProvider._has_signature(data) or (data and re.search(r'(?i)<title[^<]+?(Scenetim)', data))

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
                search_url = self.urls['search'] % (self._categories_string(),
                                                    '+'.join(search_string.replace('.', ' ').split()),
                                                    ('', '&freeleech=on')[self.freeleech])
                for page in range((3, 5)['Cache' == mode])[:-1]:
                    urls[-1] += [search_url + '&page=%s' % page]
            results += self._search_urls(mode, last_recent_search, urls)
            last_recent_search = ''

        return results

    def _search_urls(self, mode, last_recent_search, urls):

        results = []
        items = {'Cache': [], 'Season': [], 'Episode': [], 'Propers': []}

        rc = dict([(k, re.compile('(?i)' + v)) for (k, v) in iteritems({
            'info': 'detail', 'get': r'.*id=(\d+).*', 'id': r'.php\/(\d+)', 'fl': r'\[freeleech\]',
            'cats': 'cat=(?:%s)' % self._categories_string(mode=mode, template='', delimiter='|')})])

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

                    with BS4Parser(html, parse_only=dict(div={'id': 'torrenttable'})) as soup:
                        tbl = soup.find('table', attrs={'cellpadding': 5})
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
                                head = head if None is not head else self._header_row(tr)

                                info = tr.find('a', href=rc['info'])
                                dl_id = re.sub(rc['get'], r'\1', str(info.attrs['href']))
                                lrs_found = dl_id == last_recent_search
                                if lrs_found:
                                    break

                                seeders, leechers, size = [try_int(n, n) for n in [
                                    cells[head[x]].get_text().strip() for x in ('seed', 'leech', 'size')]]
                                if None is tr.find('a', href=rc['cats']) or self._reject_item(
                                        seeders, leechers,
                                        self.freeleech and (None is rc['fl'].search(cells[1].get_text()))):
                                    continue

                                title = self.regulate_title((info.attrs.get('title') or info.get_text()).strip())
                                download_url = self._link('%s/%s' % (dl_id, str(title).replace(' ', '.')))
                            except (AttributeError, TypeError, ValueError, KeyError):
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
    def regulate_title(name):
        # convert a non-standard release title into a usable format
        name_has = (lambda quality_list, func=all: func([re.search(q, name, re.I) for q in quality_list]))
        fmt = '((h.?|x)26[45]|vp9|av1|hevc)'
        webfmt = 'web.?(dl|rip|.%s)' % fmt
        rips = 'b[r|d]rip'
        # check none of the formal structures apply to this title
        if not name_has(['(720|1080|2160)[pi]|720hd']) and \
                not name_has(['(dvd.?rip|%s)(.ws)?(.(xvid|divx|%s))?' % (rips, fmt)]):
            if (not name_has(['hr.ws.pdtv.(h.?|x)264'])
                and not (name_has([r'(hdtv|pdtv|dsr|tvrip)([-]|.((aac|ac3|dd).?\d\.?\d.)*(xvid|%s))' % fmt])
                         or name_has(['(xvid|divx|480p|hevc|x265)']))) \
                    or not name_has([webfmt, 'xvid|%s' % fmt]):
                # non standard SD `aac.mp4-` -> `hdtv.x264.aac-`
                name = re.sub(r'([.\s])AAC([.\s])MP4[-]', r'\1hdtv\2x264\2aac-', name)
        return name

    def ui_string(self, key):
        cookies = 'use... \'uid=xx; pass=yy\''
        if 'cookie_str_only' == key:
            return cookies
        if 'scenetime_digest' == key and self._valid_home():
            current_url = getattr(self, 'urls', {}).get('config_provider_home_uri')
            return (cookies + (current_url and (' from a session logged in at <a target="_blank" href="%s">%s</a>' %
                                                (anon_url(current_url), current_url.strip('/'))) or ''))
        return ''


provider = SceneTimeProvider()
