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

import base64
import re
import time
import traceback
from urllib import quote_plus

from . import generic
from sickbeard import config, logger
from sickbeard.bs4_parser import BS4Parser
from sickbeard.helpers import tryInt
from lib.unidecode import unidecode


class Torrentz2Provider(generic.TorrentProvider):

    def __init__(self):
        generic.TorrentProvider.__init__(self, 'Torrentz2')

        self.url_home = ['https://torrentz2.eu/'] + \
                        ['https://%s/' % base64.b64decode(x) for x in [''.join(x) for x in [
                            [re.sub('[ \sQ]+', '', x[::-1]) for x in [
                                'GQQd', 'yQQ9', 'mQ c', 'uQ V', 'HQd', 'yQ o', 'm  L', 'z Ql']],
                            [re.sub('[S\sl]+', '', x[::-1]) for x in [
                                'Glld', 'yll9', 'ml c', 'uSlV', 'HS d', 'yl o', 'mSSL', 'jS N']],
                            [re.sub('[1\sq]+', '', x[::-1]) for x in [
                                'G qd', 'y  9', 'm1qc', 'u1 V', 'H 1d', 'yqqo', 'n1qL', '21 R']],
                            [re.sub('[F\sf]+', '', x[::-1]) for x in [
                                'G fd', 'y  9', 'm  c', 'u FV', 'H Fd', 'uf o', 'nffY', '=fFo']],
                            [re.sub('[j\sF]+', '', x[::-1]) for x in [
                                'cy9F Gd', 'HFdFuVm', 'lnFYu o', 'zNXFY w', 'Yu jQWZ', 'AbFv9F2', '=FF=']],
                            [re.sub('[K\sP]+', '', x[::-1]) for x in [
                                'yK9 Gd', 'uVm Pc', 'uoH Pd', 'w  lnY', 'zP NXY', 'uQ PWZ', '=QK3Pc']],
                            [re.sub('[R\sh]+', '', x[::-1]) for x in [
                                'cyhR9Gd', 'HRdhuVm', '1hWaRuo', 'p5RWdRt', 'e0l2h Y', 'Adz h5S', '= R=']],
                            [re.sub('[K\s ]+', '', x[::-1]) for x in [
                                'cKy9G d', 'Hdu KVm', 'tWdu  o', 'sJKKmb1', 'Lr N 2b', 'g bKl1m', '= K=']],
                            [re.sub('[s\sx]+', '', x[::-1]) for x in [
                                'cy 9G d', 'HdxxuVm', '5xWsduo', 'j9Gb si', 'L skV2a', 'AZp Jsm', '=s =']],
                            [re.sub('[P\s ]+', '', x[::-1]) for x in [
                                'cy9 PGd', 'H duPVm', '5WdPu o', 'jP 9Gbi', 'LPkV 2a', 'APbvx m', '=PP=']],
                            [re.sub('[X\sP]+', '', x[::-1]) for x in [
                                'yP9XGd', 'uVm Pc', 'uX oHd', 'i X5Wd', 'j 9GXb', 'k VX2a', '0PXNnL']],
                            [re.sub('[w\sf]+', '', x[::-1]) for x in [
                                'cwy9Gfd', 'H duV m', '5Wfwduo', 'j9G bfi', 'bsFw2 a', 'mwcfv5C', '=ffc']],
                            [re.sub('[Z\sj]+', '', x[::-1]) for x in [
                                'm cjy9Gd', 'uZoHduZV', '2bs5jWZd', 'vJZHcZrN', 'XYw 5 ia', '==Qejj0J']],
                        ]]]

        self.url_vars = {'search': 'searchA?f=%s&safe=1', 'searchv': 'verifiedA?f=%s&safe=1'}
        self.url_tmpl = {'config_provider_home_uri': '%(home)s',
                         'search': '%(home)s%(vars)s', 'searchv': '%(home)s%(vars)s'}

        self.proper_search_terms = '.proper.|.repack.'
        self.minseed, self.minleech = 2 * [None]
        self.confirmed = False

    @staticmethod
    def _has_signature(data=None):
        return data and re.search(r'(?i)Torrentz', data)

    def _search_provider(self, search_params, **kwargs):

        results = []
        if not self.url:
            return results

        items = {'Cache': [], 'Season': [], 'Episode': [], 'Propers': []}

        rc = dict((k, re.compile('(?i)' + v)) for (k, v) in {'info': r'>>.*tv'}.iteritems())
        for mode in search_params.keys():
            for search_string in search_params[mode]:

                search_string = isinstance(search_string, unicode) and unidecode(search_string) or search_string

                search_url = self.urls['search' + ('', 'v')[self.confirmed]] % (
                    'tv%s' % ('+' + quote_plus(search_string), '')['Cache' == mode])

                html = self.get_url(search_url)

                cnt = len(items[mode])
                try:
                    if not html or self._has_no_results(html):
                        raise generic.HaltParseException
                    with BS4Parser(html, features=['html5lib', 'permissive']) as soup:
                        torrent_rows = soup.select('dl')

                        if not len(torrent_rows):
                            raise generic.HaltParseException

                        for tr in torrent_rows:
                            cells = tr.dd.find_all('span')
                            if 4 > len(cells):
                                continue
                            try:
                                if not rc['info'].search(unidecode(tr.dt.get_text().strip())):
                                    continue
                                seeders, leechers, size = [tryInt(n, n) for n in [
                                    cells[x].get_text().strip() for x in -2, -1, -3]]
                                if self._peers_fail(mode, seeders, leechers):
                                    continue

                                info = tr.dt.a
                                title = info and info.get_text().strip()
                                title = title and isinstance(title, unicode) and unidecode(title) or title
                                download_url = info and title and self._dhtless_magnet(info['href'], title)
                            except (AttributeError, TypeError, ValueError, IndexError):
                                continue

                            if title and download_url:
                                items[mode].append((title, download_url, seeders, self._bytesizer(size)))

                except generic.HaltParseException:
                    time.sleep(1.1)
                except (StandardError, Exception):
                    logger.log(u'Failed to parse. Traceback: %s' % traceback.format_exc(), logger.ERROR)

                self._log_search(mode, len(items[mode]) - cnt, search_url)

            results = self._sort_seeding(mode, results + items[mode])

        return results

    def _episode_strings(self, ep_obj, **kwargs):
        return super(Torrentz2Provider, self)._episode_strings(
            ep_obj, date_detail=(lambda d: [x % str(d).replace('-', '.') for x in ('"%s"', '%s')]),
            ep_detail=(lambda ep_dict: [x % (config.naming_ep_type[2] % ep_dict) for x in ('"%s"', '%s')]), **kwargs)


provider = Torrentz2Provider()
