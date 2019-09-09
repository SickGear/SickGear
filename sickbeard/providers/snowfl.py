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
from ..helpers import try_int

from _23 import b64encodestring, filter_iter, map_list, quote, unidecode
from six import iteritems

# noinspection PyUnreachableCode
if False:
    from typing import AnyStr, Tuple

try:
    import json
except ImportError:
    from lib import simplejson as json


class SnowflProvider(generic.TorrentProvider):

    def __init__(self):
        generic.TorrentProvider.__init__(self, 'Snowfl')

        self.url_base = 'https://snowfl.com/'

        self.urls = {'config_provider_home_uri': self.url_base,
                     'browse': self.url_base + '%(token)s/Q/%(ent)s/0/DATE/24/0?_=%(ts)s',
                     'search': self.url_base + '%(token)s/%(ss)s/%(ent)s/0/DATE/NONE/1?_=%(ts)s',
                     'get': self.url_base + '%(token)s/%(src)s/%(url)s?_=%(ts)s'}

        self.minseed, self.minleech = 2 * [None]
        self.confirmed = False

    @staticmethod
    def _has_signature(data=None):
        return data and re.search(r'(?i)snowfl', data[33:1024:])

    def _search_provider(self, search_params, **kwargs):

        results = []
        if not self.url:
            return results

        items = {'Cache': [], 'Season': [], 'Episode': [], 'Propers': []}

        quote_fx = (lambda t: quote(t, safe='~()*!.\''))
        for mode in search_params:
            for search_string in search_params[mode]:
                search_url = self.url
                cnt = len(items[mode])
                try:
                    for token in self._get_tokens():
                        if self.should_skip():
                            return results
                        if not token:
                            continue

                        params = dict(token=token[0], ent=token[1])
                        if 'Cache' != mode:
                            params.update({'ss': quote_fx(unidecode(search_string))})

                        data_json = None
                        vals = [i for i in range(3, 8)]
                        random.SystemRandom().shuffle(vals)
                        for x in vals[0], vals[2], vals[4]:
                            time.sleep(x)
                            params.update(dict(ts=self.ts()))
                            search_url = self.urls[('search', 'browse')['Cache' == mode]] % params
                            # decode json below as get resp will false -ve to 'nodata' when no search results
                            html_json = self.get_url(search_url)
                            if None is not html_json:
                                data_json = json.loads(html_json)
                                if data_json or 'Cache' != mode:
                                    break
                            if self.should_skip():
                                return results

                        for item in filter_iter(lambda di: re.match('(?i).*?(tv|television)',
                                                                    di.get('type', '') or di.get('category', ''))
                                                and (not self.confirmed or di.get('trusted') or di.get('verified')),
                                                data_json or {}):
                            seeders, leechers, size = map_list(lambda arg: try_int(
                                *([item.get(arg[0]) if None is not item.get(arg[0]) else item.get(arg[1])]) * 2),
                                (('seeder', 'seed'), ('leecher', 'leech'), ('size', 'size')))
                            if self._reject_item(seeders, leechers):
                                continue
                            title = item.get('name') or item.get('title')
                            download_url = item.get('magnet') or item.get('magnetLink')
                            if not download_url:
                                source = item.get('site') or item.get('source')
                                link = self._link(item.get('url') or item.get('pageLink'))
                                if not source or not link:
                                    continue
                                download_url = self.urls['get'] % dict(
                                    token=token[0], src=quote_fx(source),
                                    url=b64encodestring(quote_fx(link)), ts='%(ts)s')
                            if title and download_url:
                                items[mode].append((title, download_url, seeders, size))

                except generic.HaltParseException:
                    pass
                except (BaseException, Exception):
                    logger.log(u'Failed to parse. Traceback: %s' % traceback.format_exc(), logger.ERROR)

                self._log_search(mode, len(items[mode]) - cnt, search_url)

            results = self._sort_seeding(mode, results + items[mode])

        return results

    def _get_tokens(self):
        # type: (...) -> Tuple[AnyStr, AnyStr]
        html = self.get_url(self.url)
        if not self.should_skip():
            if not html:
                raise generic.HaltParseException

            rc = dict([(k, re.compile('(?i)' + v)) for (k, v) in iteritems({
                'js': r'<script[^>]+?src="([^"]+?js\?v=[\w]{8,})"',
                'token': r'\w\s*=\s*"(\w{30,40})"', 'seed': r'n random[^"]+"([^"]+)'})])

            js_src = rc['js'].findall(html)
            for src in js_src:
                js = self.get_url(self.url + src)
                if self.should_skip():
                    break
                if js:
                    try:
                        token, seed = rc['token'].findall(js)[0], rc['seed'].findall(js)[0]
                        yield token, ''.join([y for _ in range(0, 8) for y in random.SystemRandom().choice(seed)])
                    except IndexError:
                        pass

    @staticmethod
    def ts():
        return str(time.time()).replace('.', '').ljust(13, str(random.SystemRandom().choice(range(1, 10))))

    def get_data(self, url):
        result = None
        data_json = self.get_url(url % dict(ts=self.ts()), parse_json=True)
        if self.should_skip():
            return result
        url = data_json.get('url', '')
        if url.lower().startswith('magnet:'):
            result = url
        else:
            from sickbeard import providers
            if 'torlock' in url.lower():
                prov = next(filter_iter(lambda p: 'torlock' == p.name.lower(), (filter_iter(
                    lambda sp: sp.providerType == self.providerType, providers.sortedProviderList()))))
                state = prov.enabled
                prov.enabled = True
                _ = prov.url
                prov.enabled = state
                if prov.url:
                    try:
                        result = prov.urls.get('get', '') % re.findall(r'(\d+).torrent', url)[0]
                    except (IndexError, TypeError):
                        pass

        return result


provider = SnowflProvider()
