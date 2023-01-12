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

import sickgear
from . import generic
from .. import logger
from ..helpers import try_int
from bs4_parser import BS4Parser
from requests.cookies import cookiejar_from_dict

from _23 import filter_list, quote, unquote
from six import string_types, iteritems


class SpeedCDProvider(generic.TorrentProvider):

    def __init__(self):
        generic.TorrentProvider.__init__(self, 'SpeedCD', update_iv=4 * 60)

        self.url_home = ['https://speed.cd/']

        self.url_vars = dict(
            login_1='checkpoint/API', login_2='checkpoint/', login_chk='rss.php', logout='logout.php', search='API/')
        self.url_tmpl = dict(
            config_provider_home_uri='%(home)s', login_1='%(home)s%(vars)s', login_2='%(home)s%(vars)s',
            login_chk='%(home)s%(vars)s', logout='%(home)s%(vars)s', search='%(home)s%(vars)s')

        self.categories = dict(Season=[41, 52, 53, 57], Episode=[2, 49, 50, 55, 57], anime=[30])
        self.categories['Cache'] = self.categories['Season'] + self.categories['Episode']

        self.username, self.password, self.digest, self.freeleech, self.minseed, self.minleech = 6 * [None]

    def _authorised(self, **kwargs):
        result = False
        if self.digest and 'None' not in self.digest and 'login_chk' in self.urls:
            digest = [x[::-1] for x in self.digest[::-1].rpartition('=')]
            self.digest = digest[2] + digest[1] + quote(unquote(digest[0]))
            self.session.cookies = cookiejar_from_dict(dict({digest[2]: quote(unquote(digest[0]))}))
            html = self.get_url(self.urls['login_chk'], skip_auth=True)
            result = html and 'RSS' in html and 'type="password"' not in html

        if not result and not self.failure_count:
            if self.url and self.digest:
                self.get_url(self.urls['logout'], skip_auth=True, post_data={'submit.x': 24, 'submit.y': 11})
            self.digest = ''
            self.session.cookies.clear()
            json = self.get_url(self.urls['login_1'], skip_auth=True,
                                post_data={'username': self.username}, parse_json=True)
            resp = filter_list(lambda l: isinstance(l, list), json.get('Fs', []))

            def get_html(_resp):
                for cur_item in _resp:
                    if isinstance(cur_item, list):
                        _html = filter_list(lambda s: isinstance(s, string_types) and 'password' in s, cur_item)
                        if not _html:
                            _html = get_html(cur_item)
                        if _html:
                            return _html

            params = {}
            html = get_html(resp)
            if html:
                tags = re.findall(r'(?is)(<input[^>]*?name=[\'"][^\'"]+[^>]*)', html[0])
                attrs = [[(re.findall(r'(?is)%s=[\'"]([^\'"]+)' % attr, x) or [''])[0]
                          for attr in ['type', 'name', 'value']] for x in tags]
                for itype, name, value in attrs:
                    if 'password' in [itype, name]:
                        params[name] = self.password
                    if name not in ('username', 'password') and 'password' != itype:
                        params.setdefault(name, value)

            if params:
                html = self.get_url(self.urls['login_2'], skip_auth=True, post_data=params)
                if html and 'RSS' in html:
                    self.digest = None
                    if self.session.cookies.get('inSpeed_speedian'):
                        self.digest = 'inSpeed_speedian=%s' % self.session.cookies.get('inSpeed_speedian')
                    sickgear.save_config()
                    result = True
                    logger.log('Cookie details for %s updated.' % self.name, logger.DEBUG)
            elif not self.failure_count:
                logger.log('Invalid cookie details for %s and login failed. Check settings' % self.name, logger.ERROR)
        return result

    @staticmethod
    def _has_signature(data=None):
        return generic.TorrentProvider._has_signature(data) or (data and re.search(r'(?sim)speed', data))

    def _search_provider(self, search_params, **kwargs):

        results = []
        if not self._authorised():
            return results

        items = {'Cache': [], 'Season': [], 'Episode': [], 'Propers': []}

        rc = dict([(k, re.compile('(?i)' + v)) for (k, v) in iteritems({
            'info': '/t/', 'get': 'download', 'fl': r'\[freeleech\]'})])

        for mode in search_params:
            rc['cats'] = re.compile(r'(?i)browse/(?:%s)'
                                    % self._categories_string(mode, template='', delimiter='|'))
            for search_string in search_params[mode]:
                post_data = dict(jxt=2, jxw='b', route='/browse/%s%s/q/%s' % (
                    self._categories_string(mode, '%s', '/'), ('/freeleech', '')[not self.freeleech],
                    search_string.replace('.', ' ').replace('^@^', '.')))

                data_json = self.get_url(self.urls['search'], post_data=post_data, parse_json=True)
                if self.should_skip():
                    return results

                cnt = len(items[mode])
                try:
                    html = filter_list(lambda l: isinstance(l, list), data_json.get('Fs', []))
                    while html:
                        if html and all(isinstance(x, string_types) for x in html):
                            str_lengths = [len(x) for x in html]
                            html = html[str_lengths.index(max(str_lengths))]
                            break
                        html = filter_list(lambda l: isinstance(l, list), html)
                        if html and 0 < len(html):
                            html = html[0]

                    if not html or self._has_no_results(html):
                        raise generic.HaltParseException

                    with BS4Parser(html, parse_only='table') as tbl:
                        tbl_rows = [] if not tbl else tbl.find_all('tr')

                        if 2 > len(tbl_rows):
                            raise generic.HaltParseException

                        head = None
                        for tr in tbl_rows[1:]:
                            cells = tr.find_all('td')
                            if 4 > len(cells):
                                continue
                            try:
                                head = head if None is not head else self._header_row(tr)
                                seeders, leechers, size = [try_int(n, n) for n in [
                                    cells[head[x]].get_text().strip() for x in ('seed', 'leech', 'size')]]
                                if None is tr.find('a', href=rc['cats']) or self._reject_item(
                                        seeders, leechers, self.freeleech and (
                                        None is rc['fl'].search(cells[1].get_text()))):
                                    continue

                                info = tr.find('a', 'torrent') or tr.find('a', href=rc['info'])
                                title = (info.attrs.get('title') or info.get_text()).strip()
                                download_url = self._link(tr.find('a', href=rc['get'])['href'])
                            except (AttributeError, TypeError, ValueError):
                                continue

                            if title and download_url:
                                items[mode].append((title, download_url, seeders, self._bytesizer(size)))

                except (BaseException, Exception):
                    time.sleep(1.1)

                self._log_search(mode, len(items[mode]) - cnt,
                                 ('search string: ' + search_string, self.name)['Cache' == mode])

            results = self._sort_seeding(mode, results + items[mode])

        return results

    def _episode_strings(self, ep_obj, **kwargs):

        return super(SpeedCDProvider, self)._episode_strings(ep_obj, sep_date='^@^', **kwargs)

    @staticmethod
    def ui_string(key):

        return 'speedcd_digest' == key and \
               'use... \'inSpeed_speedian=yy\' - warning: SpeedCD cookies often expire, ' \
               'username/pw may update them automatically, else update manually from browser' or ''


provider = SpeedCDProvider()
