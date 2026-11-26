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

from dateutil.parser import parse

from . import generic
from .. import logger
from ..config import naming_ep_type
from ..helpers import anon_url, try_int
from browser_ua import get_ua
from bs4_parser import BS4Parser
from _23 import unquote_plus


class TVChaosUKProvider(generic.TorrentProvider):

    def __init__(self):
        generic.TorrentProvider.__init__(self, 'TVChaosUK')

        self.url_base = 'https://tvchaosuk.com/'
        self.urls = {'config_provider_home_uri': self.url_base,
                     'login': self.url_base,
                     'search': f'{self.url_base}torrents/filter'}

        self.url = self.urls['config_provider_home_uri']

        self.headers['User-Agent'] = get_ua()
        self.session.headers['User-Agent'] = self.headers['User-Agent']

        self.digest, self._token, self.freeleech, self.minseed, self.minleech = 5 * [None]

    def _authorised(self, **kwargs):

        if not self.digest:
            logger.warning(f'{self.name} needs the Cookies setting from a logged in browser session')
            return False
        return super(TVChaosUKProvider, self)._authorised(
            logged_in=self.logged_in, failed_msg=(lambda y=None: 'Invalid cookie details for %s. Check settings'))

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

        rc = dict([(k, re.compile(f'(?i){v}')) for (k, v) in {
            'info': r'/torrents?/(?P<tid>(?P<tid_num>\d{2,})[^"]*)', 'get': 'download',
            'free': r'^\s*(?:free|weekly\s+freeleech)\s*$'}.items()])
        for mode in search_params:
            for search_string in search_params[mode]:
                search_string = unquote_plus(search_string)

                html = soup = tbl = None
                # the site search page posts this form by xhr, the headers are as its page script sends them
                post_data = {'_token': self._token, 'search': search_string, 'except': '', 'description': '',
                             'uploader': '', 'imdb': '', 'tvdb': '', 'view': 'list', 'tmdb': '', 'start_year': '',
                             'end_year': '', 'sorting': 'created_at', 'direction': 'desc', 'page': '0', 'qty': '50'}
                headers = dict(self.headers, **{
                    'Accept': '*/*', 'Origin': self.url_base.rstrip('/'), 'X-Requested-With': 'XMLHttpRequest',
                    'X-Csrf-Token': '[object HTMLMetaElement]'})
                for s in (0, random.SystemRandom().choice(range(5, 16))):
                    time.sleep(s)
                    html = self.get_url(self.urls['search'], post_data=post_data, headers=headers)
                    if self.should_skip():
                        return results
                    if html:  # only a failed fetch is tried again, a page with no results table will not change
                        break
                if html:
                    try:
                        soup = BS4Parser(html).soup
                        tbl = soup.find('table', class_='table')
                    except (BaseException, Exception):
                        pass
                    if not tbl and not self._has_no_results(html):
                        logger.warning(f'{mode} search page has no results table, the site layout may have changed')

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
                            # a free row has a star, a free or a weekly freeleech badge
                            if self._reject_item(seeders, leechers, self.freeleech and not (
                                    tr.find('i', class_='fa-star') or tr.find(title=rc['free'])
                                    or tr.find(attrs={'data-original-title': rc['free']}))):
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
                    logger.error(f'Failed to parse. Traceback: {traceback.format_exc()}')

                if soup:
                    soup.clear(True)
                    del soup

                self._log_search(mode, len(items[mode]) - cnt,
                                 (f'search string: {search_string.replace("%", "%%")}', self.name)['Cache' == mode])

                if mode in 'Season' and len(items[mode]):
                    break

            results = self._sort_seeding(mode, results + items[mode])

        return results

    @staticmethod
    def regulate_title(title, mode='-', search_string=''):

        # keep a starred proper or repack, drop uploader notes e.g. *Note*, * NOTE, **SEE LISTING**, @ *https://...*
        title = re.sub(r'(?i)\*+\s*(proper|repack)\s*\*+', r'\1', title)
        title = re.sub(r'(?i)\s*@\s*\*?https?://\S+|\s*\*+[^*]*\*+|\s*\*+\s*note\b.*$', '', title)
        # a trailing proper or repack after a dash goes inside the release name
        title = re.sub(r'(?i)\s+-\s+(proper|repack)\s*$', r' \1', title)
        # month first dates e.g. Nov 25 2026 -> 25 Nov 2026, and Oct 26-28 2026 -> 26-28 Oct 2026
        title = re.sub(r'\b([A-Z][a-z]{2,8})\s+(\d{1,2}(?:st|nd|rd|th)?(?:\s*-\s*\d{1,2})?),?\s+((?:19|20)\d\d)\b',
                       r'\2 \1 \3', title)
        # a multi episode range is not one air date, so drop its date e.g. S05E06-10 (23-27 Nov 2026)
        if re.search(r'(?i)S\d+E\d+\s*-\s*E?\d+', title):
            title = re.sub(r'\s*\(\d{1,2}(?:st|nd|rd|th)?(?:\s*-\s*\d{1,2})?\s+[A-Za-z]+\s+(?:19|20)\d\d\)', '', title)
        # a season of years beside an air date is not part of the show name e.g. Show 2026-27 (22 Nov 2026)
        if re.search(r'\(\d{1,2}(?:st|nd|rd|th)?\s+[A-Za-z]+\s+(?:19|20)\d\d\)', title):
            title = re.sub(r'\s+(?:19|20)\d\d-\d\d(?=\s)', '', title)
        # day first numeric dates as a month name date that is handled below e.g. (22-11-2026) -> (22 Nov 2026)
        title = re.sub(r'\((\d{1,2})-(1[0-2]|0?[1-9])-((?:19|20)\d\d)\)', lambda m: '(%s %s %s)' % (
            m.group(1), ('Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec')[
                int(m.group(2)) - 1], m.group(3)), title)
        # tags of resolution as release names use them e.g. FHD -> 1080p, UHD -> 2160p, 540 -> 540p
        title = re.sub(r'(?i)\bFHD\b', '1080p', title)
        title = re.sub(r'(?i)\b(?:UHD|4K)\b', '2160p', title)
        title = re.sub(r'(\[[^]]*?\b(?:360|468|480|504|540|576|720|1080|2160))(?=[\s\]])', r'\1p', title)
        # a standard definition name has no resolution tag, except the 480p that is known e.g. 540p, 576p, SD
        title = re.sub(r'(?i)\s*\b(?:360|468|504|540|576)p\b|(?<=\[)\s*SD\b\s*|\s+SD\b(?=[\s\]])', '', title)
        # normalise abnormal naming patterns e.g. 2019/20 -> 2019
        title = re.sub(r'((?:19|20)\d\d)/20(\d\d)?', r'\1', title)
        # s<x> ep<y> -> s<x>e<y>
        title = re.sub(r'(?i)s(\d\d+)[\W]*?e+(?:p|pisode)*(\d\d+)', r'S\1E\2', title)

        has_series = re.findall(r'(?i)(.*?\bseries\b[^\d]*?\d+)(.*)', title)
        if has_series:
            rc_xtras = re.compile(r'(?i)([. _-]|^)(special|extra)s?\w*([. _-]|$)')
            has_special = rc_xtras.findall(has_series[0][1])
            if has_special:
                title = has_series[0][0] + rc_xtras.sub(list(set(
                    list(has_special[0][0]) + list(has_special[0][2])))[0], has_series[0][1])
            title = re.sub(r'(?i)\bseries\b', r'Season', title)

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
            title = f'{new_parts[0]}`{sxe_build}`{new_parts[-1]}'
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
                title = title.replace(''.join(d), f'{("", " ")[1 < len(d[0])]}{dnew}{("", " ")[1 < len(d[4])]}')
            except (BaseException, Exception):
                pass
        if dated:
            add_pad = re.findall(r'((?:19|20)\d\d[-]\d\d[-]\d\d)([\w\W])', title)
            if any(add_pad) and add_pad[0][1] not in [' ', '.']:
                title = title.replace(''.join(
                    add_pad[0]), f'{add_pad[0][0]} {add_pad[0][1]}')
            title = re.sub(r'(?sim)(.*?)(?:Episode|Season).\d+.(.*)', r'\1\2', title)

        t = ['']
        bl = r'[*\[({]+\s*'
        br = r'\s*[})\]*]+'
        title = re.sub(f'(?i)(.*?)({bl}proper{br})(.*)', r'\1\3\2', title)
        for r in (r'\s+-\s+', r'(?:19|20)\d\d(?:\-\d\d\-\d\d)?', r'S\d\d+(?:E\d\d+)?'):
            m = re.findall(f'(.*{r})(.*)', title)
            if any(m) and len(m[0][0]) > len(t[0]):
                t = m[0]
        t = ([title], t)[any(t)]

        tags = [re.findall(x, t[-1], flags=re.X) for x in
                (f'(?i){bl}Proper{br}|\x08Proper\x08$',
                 r'(?i)(?:\d{3,4}(?:[pi]|hd)|hd(?:tv)?\s*\d{3,4}(?:[pi])?)',
                 '''
                 (?i)(hr.ws.pdtv|blu.?ray|hddvd|
                 pdtv|hdtv|dsr|tvrip|web.?(?:dl|rip)|dvd.?rip|b[r|d]rip)
                 ''', '''
                 (?i)([hx].?26[45]|hevc|av1|vp9|divx|xvid|mpeg-?2)
                 ''', '''
                 (?i)(avi|mkv|mp4|sub(?:b?ed|pack|s))
                 ''')]
        title = ('%s`%s' % (
            re.sub('|'.join(['|'.join([re.escape(y) for y in x]) for x in tags if x]).strip('|'), '', t[-1]),
            re.sub(r'(?i)(?:hd(?:tv)?\s*)?(\d{3,4})(?:hd|p)?', r'\1p', '`'.join(['`'.join(x) for x in tags[:2]]))
            # resolution, then source, then codec, as in a release name
            + '`' + '`'.join(tags[2] or ['HDTV']) + '`' + '`'.join(tags[3] or ['x264'])))
        title = re.sub(r'([hx]26[45])p', r'\1', title)
        for r in [(r'(?i)(?:\W(?:Series|Season))?\W(Repack)\W', r'`\1`'),
                  (f'(?i){bl}(Proper){br}', r'`\1`'), (rf'{bl}\s*{br}', '`')]:
            title = re.sub(r[0], r[1], title)

        title = re.sub(r'[][]', '', title)
        title = f'{("", t[0])[1 < len(t)]}{title}-nogrp'
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
                    titles += [re.sub(sxxexx_r, dnew, re.sub(rf'[_.\-\s]?{dnew}', '', title))]
            except (BaseException, Exception):
                pass

        titles += [title]

        # source tags as release names spell them e.g. hdtv -> HDTV, WebRip -> WEBRip
        standard = (lambda name: re.sub(r'(?i)\bweb.?dl\b', 'WEB-DL', re.sub(r'(?i)\bweb.?rip\b', 'WEBRip', re.sub(
            r'(?i)\bhdtv\b', 'HDTV', name))))

        result = []
        for cur_item in titles:
            sxe_find = r'(?i)%s' % (sxe_build, r'S\d\d+E\d\d+(?:-E?\d\d+)?|season\s*\d+')[not sxe_build]
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
                tail = re.findall(rf'(?i)^([^{divider}]+)(.*)', item)[0]
                if tail[1]:  # show name divider found
                    parts = [tail[0].strip()]
                    end = [tail[1].lstrip(f'{divider} ')]
                else:
                    parts = [pre_post[0][0]]
                    end = [pre_post[0][1]]

            parts += ([sxe], [])[not sxe] + ([dated], [])[not dated] + end
            result += [standard(re.sub(r'[][]', '', re.sub(r'(\s\.|\.\s|\s+)', '.', ' '.join(parts))))]

        return result

    @staticmethod
    def regulate_cache_torrent_file(title):
        return re.sub(r'\b(\s*subs)\b([\W\w]{0,20})$', r'\2', title)

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
                                  [((d[-1], f'{m}', y), (d, m, y)) + (((d, mf, y),), ())[m == mf]
                                   for (d, m, mf, y) in [(date.strftime(x) for x in ('%d', '%b', '%B', '%Y'))]][0]]),
                ep_detail=(lambda e: [naming_ep_type[2] % e] + (
                    [], ['%(episodenumber)d of' % e])[1 == try_int(e.get('seasonnumber'))]), **kwargs)

    def ui_string(self, key):

        return ('tvchaosuk_tip' == key
                and 'releases are often "Air by date release names" - edit search settings of show if required'
                or 'tvchaosuk_digest' == key and (
                    'use... all cookies of a logged in browser session,'
                    ' e.g. \'<name>_session=xx; remember_web_<id>=yy\''
                    ' from <a target="_blank" href="%s">%s</a>' % (anon_url(self.url_base), self.url_base.strip('/')))
                or '')


provider = TVChaosUKProvider()
