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
from sickbeard import logger
from sickbeard.bs4_parser import BS4Parser
from sickbeard.helpers import tryInt
from sickbeard.config import naming_ep_type
from dateutil.parser import parse
from lib.unidecode import unidecode


class TVChaosUKProvider(generic.TorrentProvider):

    def __init__(self):
        generic.TorrentProvider.__init__(self, 'TVChaosUK')

        self.url_base = 'https://www.tvchaosuk.com/'
        self.urls = {'config_provider_home_uri': self.url_base,
                     'login_action': self.url_base + 'login.php',
                     'search': self.url_base + 'browse.php',
                     'get': self.url_base + '%s'}

        self.url = self.urls['config_provider_home_uri']

        self.username, self.password, self.freeleech, self.minseed, self.minleech = 5 * [None]
        self.search_fallback = True

    def _authorised(self, **kwargs):

        return super(TVChaosUKProvider, self)._authorised(
            logged_in=(lambda y=None: self.has_all_cookies(pre='c_secure_')))

    def _search_provider(self, search_params, **kwargs):

        results = []
        if not self._authorised():
            return results

        items = {'Cache': [], 'Season': [], 'Episode': [], 'Propers': []}

        rc = dict((k, re.compile('(?i)' + v)) for (k, v) in {'info': 'detail', 'get': 'download', 'fl': 'free'}.items())
        for mode in search_params.keys():
            for search_string in search_params[mode]:
                search_string = isinstance(search_string, unicode) and unidecode(search_string) or search_string

                kwargs = dict(post_data={'keywords': search_string, 'do': 'quick_sort', 'page': '0',
                                         'category': '0', 'search_type': 't_name', 'sort': 'added',
                                         'order': 'desc', 'daysprune': '-1'})

                html = self.get_url(self.urls['search'], **kwargs)

                cnt = len(items[mode])
                try:
                    if not html or self._has_no_results(html):
                        raise generic.HaltParseException

                    with BS4Parser(html, 'html.parser') as soup:
                        torrent_table = soup.find('table', id='sortabletable')
                        torrent_rows = [] if not torrent_table else torrent_table.find_all('tr')
                        get_detail = True

                        if 2 > len(torrent_rows):
                            raise generic.HaltParseException

                        head = None
                        for tr in torrent_rows[1:]:
                            cells = tr.find_all('td')
                            if 6 > len(cells):
                                continue
                            try:
                                head = head if None is not head else self._header_row(tr)
                                seeders, leechers, size = [tryInt(n, n) for n in [
                                    cells[head[x]].get_text().strip() for x in 'seed', 'leech', 'size']]
                                if self._peers_fail(mode, seeders, leechers) \
                                        or self.freeleech and None is cells[1].find('img', title=rc['fl']):
                                    continue

                                info = tr.find('a', href=rc['info'])
                                title = (tr.find('div', class_='tooltip-content').get_text() or info.get_text()).strip()
                                title = re.findall('(?m)(^[^\r\n]+)', title)[0]
                                download_url = self._link(tr.find('a', href=rc['get'])['href'])
                            except (StandardError, Exception):
                                continue

                            if get_detail and title.endswith('...'):
                                try:
                                    with BS4Parser(self.get_url('%s%s' % (
                                            self.urls['config_provider_home_uri'], info['href'].lstrip('/').replace(
                                                self.urls['config_provider_home_uri'], ''))),
                                                   'html.parser') as soup_detail:
                                        title = soup_detail.find(
                                            'td', class_='thead', attrs={'colspan': '3'}).get_text().strip()
                                        title = re.findall('(?m)(^[^\r\n]+)', title)[0]
                                except IndexError:
                                    continue
                                except (StandardError, Exception):
                                    get_detail = False

                            try:
                                title = self.regulate_title(title, mode)
                                if title and download_url:
                                    items[mode].append((title, download_url, seeders, self._bytesizer(size)))
                            except (StandardError, Exception):
                                pass

                except generic.HaltParseException:
                    pass
                except (StandardError, Exception):
                    logger.log(u'Failed to parse. Traceback: %s' % traceback.format_exc(), logger.ERROR)

                self._log_search(mode, len(items[mode]) - cnt,
                                 ('search string: ' + search_string.replace('%', ' '), self.name)['Cache' == mode])

                if mode in 'Season' and len(items[mode]):
                    break

            results = self._sort_seeding(mode, results + items[mode])

        return results

    @staticmethod
    def regulate_title(title, mode='-'):

        has_series = re.findall('(?i)(.*?series[^\d]*?\d+)(.*)', title)
        if has_series:
            rc_xtras = re.compile('(?i)([. _-]|^)(special|extra)s?\w*([. _-]|$)')
            has_special = rc_xtras.findall(has_series[0][1])
            if has_special:
                title = has_series[0][0] + rc_xtras.sub(list(set(
                    list(has_special[0][0]) + list(has_special[0][2])))[0], has_series[0][1])
            title = re.sub('(?i)series', r'Season', title)

        years = re.findall('((?:19|20)\d\d)', title)
        title = re.sub('(19|20)\d\d', r'{{yr}}', title)
        title_parts = re.findall(
            '(?im)^(.*?)(?:Season[^\d]*?(\d+).*?)?' +
            '(?:(?:pack|part|pt)\W*?)?(\d+)[^\d]*?of[^\d]*?(?:\d+)(.*?)$', title)
        if len(title_parts):
            new_parts = [tryInt(part, part) for part in title_parts[0]]
            if not new_parts[1]:
                new_parts[1] = 1
            new_parts[2] = ('E%02d', ' Pack %d')[any([re.search('(?i)season|series', title),
                                                      mode in 'Season'])] % new_parts[2]
            title = '%s`S%02d%s`%s' % tuple(new_parts)
        for yr in years:
            title = re.sub('\{\{yr\}\}', yr, title, count=1)

        dated = re.findall('(?i)([(\s]*)((?:\d+\s)?)([adfjmnos]\w{2,}\s+)((?:19|20)\d\d)([)\s]*)', title)
        for d in dated:
            try:
                dout = parse(''.join(d[1:4])).strftime('%Y-%m-%d')
                title = title.replace(''.join(d), '%s%s%s' % (
                    ('', ' ')[1 < len(d[0])], dout[0: not any(d[2]) and 4 or not any(d[1]) and 7 or len(dout)],
                    ('', ' ')[1 < len(d[4])]))
            except (StandardError, Exception):
                pass
        if dated:
            add_pad = re.findall('((?:19|20)\d\d[-]\d\d[-]\d\d)([\w\W])', title)
            if any(add_pad) and add_pad[0][1] not in [' ', '.']:
                title = title.replace(''.join(
                    add_pad[0]), '%s %s' % (add_pad[0][0], add_pad[0][1]))
            title = re.sub(r'(?sim)(.*?)(?:Episode|Season).\d+.(.*)', r'\1\2', title)

        t = ['']
        bl = '[*\[({]+\s*'
        br = '\s*[})\]*]+'
        title = re.sub('(.*?)((?i)%sproper%s)(.*)' % (bl, br), r'\1\3\2', title)
        for r in '\s+-\s+', '(?:19|20)\d\d(?:\-\d\d\-\d\d)?', 'S\d\d+(?:E\d\d+)?':
            m = re.findall('(.*%s)(.*)' % r, title)
            if any(m) and len(m[0][0]) > len(t[0]):
                t = m[0]
        t = ([title], t)[any(t)]

        tags = [re.findall(x, t[-1], flags=re.X) for x in
                ('(?i)%sProper%s|\bProper\b$' % (bl, br),
                 '(?i)\d{3,4}(?:[pi]|hd)',
                 '''
                 (?i)(hr.ws.pdtv|blu.?ray|hddvd|
                 pdtv|hdtv|dsr|tvrip|web.?(?:dl|rip)|dvd.?rip|b[r|d]rip|mpeg-?2)
                 ''', '''
                 (?i)([hx].?26[45]|divx|xvid)
                 ''', '''
                 (?i)(avi|mkv|mp4|sub(?:b?ed|pack|s))
                 ''')]
        title = ('%s`%s' % (
            re.sub('|'.join(['|'.join([re.escape(y) for y in x]) for x in tags if x]).strip('|'), '', t[-1]),
            re.sub('(?i)(\d{3,4})hd', r'\1p', '`'.join(['`'.join(x) for x in tags[:-1]]).rstrip('`')) +
            ('', '`hdtv')[not any(tags[2])] + ('', '`x264')[not any(tags[3])]))
        for r in [('(?i)(?:\W(?:Series|Season))?\W(Repack)\W', r'`\1`'),
                  ('(?i)%s(Proper)%s' % (bl, br), r'`\1`'), ('%s\s*%s' % (bl, br), '`')]:
            title = re.sub(r[0], r[1], title)

        title = '%s%s-nogrp' % (('', t[0])[1 < len(t)], title)
        for r in [('\s+[-]?\s+|\s+`|`\s+', '`'), ('`+', '.')]:
            title = re.sub(r[0], r[1], title)

        return title

    def _season_strings(self, ep_obj, **kwargs):

        return generic.TorrentProvider._season_strings(self, ep_obj, scene=False, prefix='%', sp_detail=(
            lambda e: [
                (('', 'Series %(seasonnumber)d%%')[1 < tryInt(e.get('seasonnumber'))] + '%(episodenumber)dof') % e,
                'Series %(seasonnumber)d' % e]))

    def _episode_strings(self, ep_obj, **kwargs):

        return generic.TorrentProvider._episode_strings(self, ep_obj, scene=False, prefix='%', date_detail=(
            lambda d: [d.strftime('%d %b %Y')] + ([d.strftime('%d %B %Y')], [])[d.strftime('%b') == d.strftime('%B')]),
            ep_detail=(lambda e: [naming_ep_type[2] % e] + (
                [], ['%(episodenumber)dof' % e])[1 == tryInt(e.get('seasonnumber'))]), **kwargs)

    @staticmethod
    def ui_string(key):

        return ('tvchaosuk_tip' == key
                and 'releases are often "Air by date release names" - edit search settings of show if required' or '')


provider = TVChaosUKProvider()
