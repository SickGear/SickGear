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
from lib.unidecode import unidecode


class PotUKProvider(generic.TorrentProvider):

    def __init__(self):
        generic.TorrentProvider.__init__(self, 'PotUK')

        self.url_base = 'http://www.potuk.com/newforum/'
        self.urls = {'config_provider_home_uri': self.url_base,
                     'login': self.url_base + 'search.php',
                     'browse': self.url_base + 'search.php?do=getdaily&exclude=%s',
                     'get_data': self.url_base + 'misc.php?do=showattachments&t=%s'}

        self.url = self.urls['config_provider_home_uri']

        self.digest, self.resp = 2 * [None]

    def logged_in(self, resp):
        try:
            self.resp = re.findall('(?sim)<form .*?search.php.*?</form>', resp)[0]
        except (IndexError, TypeError):
            return False
        return self.has_all_cookies('bbsessionhash')

    def _authorised(self, **kwargs):

        return super(PotUKProvider, self)._authorised(
            logged_in=(lambda y=None: self.logged_in(y)),
            failed_msg=(lambda y=None: u'Invalid cookie details for %s. Check settings'))

    def _search_provider(self, search_params, **kwargs):

        results = []
        if not self._authorised():
            return results

        items = {'Cache': [], 'Season': [], 'Episode': [], 'Propers': []}

        opts = re.findall('(?sim)forumchoice\[\][^<]+(.*?)</select>', self.resp)[0]
        cat_opts = re.findall(r'(?mis)<option[^>]*?value=[\'"](\d+)[^>]*>(.*?)</option>', opts)
        include = []
        tv = False
        for c in cat_opts:
            if not tv and 'TV Shows' in c[1]:
                tv = True
            elif tv:
                if 3 > len(re.findall('&nbsp;', c[1])):
                    break
                elif not filter(lambda v: v in c[1], ('Requests', 'Offer', 'Discussion')):
                    include += [c[0]]
        exclude = ','.join(list(filter(lambda v: v not in include, map(lambda x: x[0], cat_opts))))

        for mode in search_params.keys():
            for search_string in search_params[mode]:
                search_string = isinstance(search_string, unicode) and unidecode(search_string) or search_string

                params = {}
                if 'Cache' == mode:
                    search_url = self.urls['browse'] % exclude
                else:
                    search_url = self._link(re.findall('(?i)action="([^"]+?)"', self.resp)[0])
                    params = {'query': search_string, 'showposts': 0, 'titleonly': 1, 'prefixchoice': '',
                              'replyless': 0, 'searchdate': 0, 'beforeafter': 'after', 'sortby': 'threadstart',
                              'order': 'descending', 'starteronly': 0, 'forumchoice': include}
                    tags = re.findall(r'(?is)(<input[^>]*?name=[\'"][^\'"]+[^>]*)', self.resp)
                    attrs = [[(re.findall(r'(?is)%s=[\'"]([^\'"]+)' % attr, c) or [''])[0]
                              for attr in ['type', 'name', 'value']] for c in tags]
                    for itype, name, value in attrs:
                        params.setdefault(name, value)
                    del params['doprefs']
                html = self.get_url(search_url, post_data=params)

                cnt = len(items[mode])
                try:
                    if not html or self._has_no_results(html):
                        raise generic.HaltParseException

                    with BS4Parser(html, features=['html5lib', 'permissive']) as soup:
                        torrent_table = soup.find('table', id='threadslist')
                        torrent_rows = [] if not torrent_table else torrent_table.find_all('tr')

                        if 2 > len(torrent_rows):
                            raise generic.HaltParseException

                        for tr in torrent_rows[1:]:
                            if 6 > len(tr.find_all('td')) or not tr.select('img[alt*="ttach"]'):
                                continue
                            try:
                                link = tr.select('td[id^="td_threadtitle"]')[0].select('a[id*="title"]')[0]
                                title = link.get_text().strip()
                                download_url = self.urls['get_data'] % re.findall('t=(\d+)', link['href'])[0]
                            except (AttributeError, TypeError, ValueError, IndexError):
                                continue

                            if title and download_url:
                                items[mode].append((title, download_url, '', ''))

                except generic.HaltParseException:
                    pass
                except (StandardError, Exception):
                    logger.log(u'Failed to parse. Traceback: %s' % traceback.format_exc(), logger.ERROR)

                self._log_search(
                    mode, len(items[mode]) - cnt, ('search_param: ' + search_string, search_url)['Cache' == mode])

            results = self._sort_seeding(mode, results + items[mode])

        return results

    def get_data(self, url):
        result = None
        html = self.get_url(url, timeout=90)
        try:
            result = self._link(re.findall('(?i)"(attachment\.php[^"]+?)"', html)[0])
        except IndexError:
            logger.log('Failed no torrent in response', logger.DEBUG)
        return result

    def get_result(self, episodes, url):
        result = None

        if url:
            result = super(PotUKProvider, self).get_result(episodes, url)
            result.get_data_func = self.get_data

        return result

    def ui_string(self, key):
        return ('%s_digest' % self.get_id()) == key and 'use... \'bbuserid=xx; bbpassword=yy\'' or ''


provider = PotUKProvider()
