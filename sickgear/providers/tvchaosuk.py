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

import random
import re
import time
import traceback

from . import generic
from .. import logger
from ..config import naming_ep_type
from ..helpers import try_int
from bs4_parser import BS4Parser
from dateutil.parser import parse

from _23 import unidecode, unquote_plus
from six import iteritems


class TVChaosUKProvider(generic.TorrentProvider):

    def __init__(self):
        generic.TorrentProvider.__init__(self, 'TVChaosUK')

        self.url_base = 'https://tvchaosuk.com/'
        self.urls = {'config_provider_home_uri': self.url_base,
                     'login_action': self.url_base + 'login',
                     'search': self.url_base + 'torrents/filter?%s' % '&'.join(
                         ['search=%s', 'page=0', 'tmdb=', 'imdb=', 'tvdb=', 'description=', 'uploader=', 'view=list',
                          'start_year=', 'end_year=', 'sorting=created_at', 'direction=desc', 'qty=100', '_token=%s',
                          'types[]=SD', 'types[]=HD720p', 'types[]=HD1080p',
                          'types[]=SD Pack', 'types[]=HD720p Pack', 'types[]=HD1080p Pack'])}

        self.url = self.urls['config_provider_home_uri']

        self.username, self.password, self._token, \
            self.freeleech, self.minseed, self.minleech, self.use_after_get_data = 7 * [None]

    def _authorised(self, **kwargs):

        return super(TVChaosUKProvider, self)._authorised(logged_in=self.logged_in, post_params={'remember': '1'})

    def logged_in(self, resp=None):

        result = True
        if not self._token:
            try:
                result = 'Username' not in resp and 'Logout' in resp
                input_tag = re.findall(r'(<input[^>]+?"(?:hidden|_token)"[^>]+?"(?:hidden|_token)"[^>]+?>)', resp)[0]
                token = re.findall(r'value\s*=\s*["\']\s*([^"\'\s]+)', input_tag)[0]
                csrf = re.findall(r'<meta[^>]+csrf-token[^>]+content[^"]+"\s*([^\s"]+)', resp)[0]
                self._token = result and csrf == token and token
            except (BaseException, Exception):
                result = False
        return result

    def _search_provider(self, search_params, **kwargs):

        results = []
        if not self._authorised():
            return results

        items = {'Cache': [], 'Season': [], 'Episode': [], 'Propers': []}

        rc = dict([(k, re.compile('(?i)' + v)) for (k, v) in iteritems({
            'info': r'/torrents?/(?P<tid>(?P<tid_num>\d{2,})[^"]*)', 'get': 'download'})])
        for mode in search_params:
            for search_string in search_params[mode]:
                search_string = unidecode(unquote_plus(search_string))

                vals = [i for i in range(5, 16)]
                random.SystemRandom().shuffle(vals)
                attempts = html = soup = tbl = None
                fetch = 'failed fetch'
                for attempts, s in enumerate((0, vals[0], vals[5], vals[10])):
                    time.sleep(s)
                    html = self.get_url(self.urls['search'] % (search_string, self._token))
                    if self.should_skip():
                        return results
                    if html:
                        try:
                            soup = BS4Parser(html).soup
                            tbl = soup.find('table', class_='table')
                            if tbl:
                                fetch = 'data fetched'
                                break
                        except (BaseException, Exception):
                            pass
                if attempts:
                    logger.log('%s %s after %s attempts' % (mode, fetch, attempts+1))

                cnt = len(items[mode])
                try:
                    if not html or self._has_no_results(html) or not tbl:
                        raise generic.HaltParseException

                    tbl_rows = tbl.find_all('tr')

                    if 2 > len(tbl_rows):
                        raise generic.HaltParseException

                    head = None
                    for tr in tbl_rows[1:]:
                        cells = tr.find_all('td')
                        if 6 > len(cells):
                            continue
                        try:
                            head = head if None is not head else self._header_row(tr)
                            seeders, leechers, size = [try_int(n, n) for n in [
                                cells[head[x]].get_text().strip() for x in ('seed', 'leech', 'size')]]
                            if self._reject_item(seeders, leechers, self.freeleech and (
                                    None is tr.find('i', class_='fa-star'))):
                                continue

                            title = tr.find('a', href=rc['info']).get_text().strip()
                            download_url = self._link(tr.find('a', href=rc['get'])['href'])
                        except (BaseException, Exception):
                            continue

                        try:
                            titles = self.regulate_title(title, mode, search_string)
                            if download_url and titles:
                                for title in titles:
                                    items[mode].append((title, download_url, seeders, self._bytesizer(size)))
                        except (BaseException, Exception):
                            pass

                except generic.HaltParseException:
                    pass
                except (BaseException, Exception):
                    logger.log(u'Failed to parse. Traceback: %s' % traceback.format_exc(), logger.ERROR)

                if soup:
                    soup.clear(True)
                    del soup

                self._log_search(mode, len(items[mode]) - cnt,
                                 ('search string: ' + search_string.replace('%', '%%'), self.name)['Cache' == mode])

                if mode in 'Season' and len(items[mode]):
                    break

            results = self._sort_seeding(mode, results + items[mode])

        return results

    @staticmethod
    def regulate_title(title, mode='-', search_string=''):

        # normalise abnormal naming patterns e.g. 2019/20 -> 2019
        title = re.sub(r'((?:19|20)\d\d)/20(\d\d)?', r'\1', title)
        # s<x> ep<y> -> s<x>e<y>
        title = re.sub(r'(?i)s(\d\d+)[\W]*?e+(?:p|pisode)*(\d\d+)', r'S\1E\2', title)

        has_series = re.findall(r'(?i)(.*?series[^\d]*?\d+)(.*)', title)
        if has_series:
            rc_xtras = re.compile(r'(?i)([. _-]|^)(special|extra)s?\w*([. _-]|$)')
            has_special = rc_xtras.findall(has_series[0][1])
            if has_special:
                title = has_series[0][0] + rc_xtras.sub(list(set(
                    list(has_special[0][0]) + list(has_special[0][2])))[0], has_series[0][1])
            title = re.sub('(?i)series', r'Season', title)

        years = re.findall(r'((?:19|20)\d\d)', title)
        title = re.sub(r'(19|20)\d\d', r'{{yr}}', title)
        title_parts = re.findall(
            r'(?im)^(.*?)(?:Season[^\d]*?(\d+).*?)?' +
            r'(?:(?:pack|part|pt)\W*?)?(\d+)[^\d]*?of[^\d]*?(?:\d+)(.*?)$', title)
        sxe_build = None

        if len(title_parts):
            new_parts = [try_int(part, part) for part in title_parts[0]]
            if not new_parts[1]:
                new_parts[1] = 1
            new_parts[2] = ('E%02d', ' Pack %d')[any([re.search('(?i)season|series', title),
                                                      mode in 'Season'])] % new_parts[2]
            sxe_build = 'S%02d%s' % tuple(new_parts[1:3])
            title = '%s`%s`%s' % (new_parts[0], sxe_build, new_parts[-1])
        for yr in years:
            # noinspection RegExpRedundantEscape
            title = re.sub(r'\{\{yr\}\}', yr, title, count=1)

        date_re = r'(?i)([(\s.]*)((?:\d+[\s.]*(?:st|nd|rd|th)?[\s.])?)([adfjmnos]\w{2,}[\s.]+)((?:19|20)\d\d)([)\s.]*)'
        dated = re.findall(date_re, title)
        dnew = None
        for d in dated:
            try:
                dout = parse(''.join(d[1:4])).strftime('%Y-%m-%d')
                dnew = dout[0: not any(d[2]) and 4 or not any(d[1]) and 7 or len(dout)]
                title = title.replace(''.join(d), '%s%s%s' % (('', ' ')[1 < len(d[0])], dnew, ('', ' ')[1 < len(d[4])]))
            except (BaseException, Exception):
                pass
        if dated:
            add_pad = re.findall(r'((?:19|20)\d\d[-]\d\d[-]\d\d)([\w\W])', title)
            if any(add_pad) and add_pad[0][1] not in [' ', '.']:
                title = title.replace(''.join(
                    add_pad[0]), '%s %s' % (add_pad[0][0], add_pad[0][1]))
            title = re.sub(r'(?sim)(.*?)(?:Episode|Season).\d+.(.*)', r'\1\2', title)

        t = ['']
        bl = r'[*\[({]+\s*'
        br = r'\s*[})\]*]+'
        title = re.sub('(?i)(.*?)(%sproper%s)(.*)' % (bl, br), r'\1\3\2', title)
        for r in (r'\s+-\s+', r'(?:19|20)\d\d(?:\-\d\d\-\d\d)?', r'S\d\d+(?:E\d\d+)?'):
            m = re.findall('(.*%s)(.*)' % r, title)
            if any(m) and len(m[0][0]) > len(t[0]):
                t = m[0]
        t = ([title], t)[any(t)]

        tags = [re.findall(x, t[-1], flags=re.X) for x in
                ('(?i)%sProper%s|\bProper\b$' % (bl, br),
                 r'(?i)(?:\d{3,4}(?:[pi]|hd)|hd(?:tv)?\s*\d{3,4}(?:[pi])?)',
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
            re.sub(r'(?i)(?:hd(?:tv)?\s*)?(\d{3,4})(?:hd|p)?', r'\1p',
                   '`'.join(['`'.join(x) for x in tags[:-1]]).rstrip('`')) +
            ('', '`hdtv')[not any(tags[2])] + ('', '`x264')[not any(tags[3])]))
        title = re.sub(r'([hx]26[45])p', r'\1', title)
        for r in [(r'(?i)(?:\W(?:Series|Season))?\W(Repack)\W', r'`\1`'),
                  ('(?i)%s(Proper)%s' % (bl, br), r'`\1`'), (r'%s\s*%s' % (bl, br), '`')]:
            title = re.sub(r[0], r[1], title)

        title = re.sub(r'[][]', '', title)
        title = '%s%s-nogrp' % (('', t[0])[1 < len(t)], title)
        for r in [(r'\s+[-]?\s+|\s+`|`\s+', '`'), ('`+', ' ')]:
            title = re.sub(r[0], r[1], title)

        titles = []
        if dnew:
            snew = None
            dated_s = re.findall(date_re, search_string)
            for d in dated_s:
                try:
                    sout = parse(''.join(d[1:4])).strftime('%Y-%m-%d')
                    snew = sout[0: not any(d[2]) and 4 or not any(d[1]) and 7 or len(sout)]
                except (BaseException, Exception):
                    pass

            if snew and dnew and snew != dnew:
                return titles

            try:
                sxxexx_r = r'(?i)S\d\d+E\d\d+'
                if dnew and re.search(sxxexx_r, title):
                    titles += [re.sub(sxxexx_r, dnew, re.sub(r'[_.\-\s]?%s' % dnew, '', title))]
            except (BaseException, Exception):
                pass

        titles += [title]

        result = []
        for cur_item in titles:
            sxe_find = r'(?i)%s' % (sxe_build, r'S\d\d+E\d\d+|season\s*\d+')[not sxe_build]
            sxe = re.findall(sxe_find, cur_item) or ''
            if sxe:
                sxe = sxe[0]
                cur_item = re.sub(sxe, r'{{sxe}}', cur_item)
            dated = dnew and re.findall(dnew, cur_item) or ''
            if dated:
                dated = dated[0]
                cur_item = re.sub(dated, r'{{dated}}', cur_item)

            parts = []
            pre_post = re.findall(r'(.*?){{.*}}[.]*(.*)', cur_item)
            item = re.sub(r'{{(sxe|dated)}}[.]*', '', cur_item)
            end = [item]
            if pre_post and (sxe or dated):
                divider = ':'
                tail = re.findall(r'(?i)^([^%s]+)(.*)' % divider, item)[0]
                if tail[1]:  # show name divider found
                    parts = [tail[0].strip()]
                    end = [tail[1].lstrip('%s ' % divider)]
                else:
                    parts = [pre_post[0][0]]
                    end = [pre_post[0][1]]

            parts += ([sxe], [])[not sxe] + ([dated], [])[not dated] + end
            result += [re.sub(r'(\s\.|\.\s|\s+)', '.', ' '.join(parts))]

        return result

    @staticmethod
    def regulate_cache_torrent_file(title):
        return re.sub(r'\b(\s*subs)\b([\W\w]{0,20})$', r'\2', title)

    def after_get_data(self, result):
        if self.use_after_get_data:
            try:
                self.get_url(self.url_base + 'thanks/%s' % re.findall(r'download/(\d+)', result.url)[0])
            except IndexError:
                pass

    def _season_strings(self, ep_obj, **kwargs):

        return \
            generic.TorrentProvider._season_strings(
                self, ep_obj, scene=False, sp_detail=(
                    lambda e: [(('', 'Series %(seasonnumber)d ')[1 < try_int(e.get('seasonnumber'))]
                                + '%(episodenumber)d of') % e, 'Series %(seasonnumber)d' % e]))

    def _episode_strings(self, ep_obj, **kwargs):

        return \
            super(TVChaosUKProvider, self)._episode_strings(
                ep_obj, scene=False, date_detail=(
                    lambda date: ['%s %s %s'.lstrip('0') % x for x in
                                  [((d[-1], '%s' % m, y), (d, m, y)) + (((d, mf, y),), ())[m == mf]
                                   for (d, m, mf, y) in [(date.strftime(x) for x in ('%d', '%b', '%B', '%Y'))]][0]]),
                ep_detail=(lambda e: [naming_ep_type[2] % e] + (
                    [], ['%(episodenumber)d of' % e])[1 == try_int(e.get('seasonnumber'))]), **kwargs)

    @staticmethod
    def ui_string(key):

        return ('tvchaosuk_tip' == key
                and 'releases are often "Air by date release names" - edit search settings of show if required'
                or 'tvchaosuk_use_after_get_data' == key and 'Send "Say thanks!"'
                or 'tvchaosuk_use_after_get_data_tip' == key and 'to each release that is snatched'
                or '')


provider = TVChaosUKProvider()
