# coding=utf-8
# Author: Nic Wolfe <nic@wolfeden.ca>
# URL: http://code.google.com/p/sickbeard/
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

from __future__ import with_statement

import datetime
import itertools
import math
import os
import re
import time
import urlparse
from urllib import quote_plus
import zlib
from base64 import b16encode, b32decode

import sickbeard
import requests
import requests.cookies
from cfscrape import CloudflareScraper
from hachoir_parser import guessParser
from hachoir_core.error import HachoirError
from hachoir_core.stream import FileInputStream

from sickbeard import helpers, classes, logger, db, tvcache, encodingKludge as ek
from sickbeard.common import Quality, MULTI_EP_RESULT, SEASON_RESULT, USER_AGENT
from sickbeard.exceptions import SickBeardException, AuthException, ex
from sickbeard.helpers import maybe_plural, remove_file_failed
from sickbeard.name_parser.parser import NameParser, InvalidNameException, InvalidShowException
from sickbeard.show_name_helpers import allPossibleShowNames


class HaltParseException(SickBeardException):
    """Something requires the current processing to abort"""


class GenericProvider:
    NZB = 'nzb'
    TORRENT = 'torrent'

    def __init__(self, name, supports_backlog=False, anime_only=False):
        # these need to be set in the subclass
        self.providerType = None
        self.name = name
        self.supports_backlog = supports_backlog
        self.anime_only = anime_only
        if anime_only:
            self.proper_search_terms = 'v1|v2|v3|v4|v5'
        self.url = ''

        self.show = None

        self.search_mode = None
        self.search_fallback = False
        self.enabled = False
        self.enable_recentsearch = False
        self.enable_backlog = False
        self.enable_scheduled_backlog = True
        self.categories = None

        self.cache = tvcache.TVCache(self)

        self.session = CloudflareScraper.create_scraper()

        self.headers = {
            # Using USER_AGENT instead of Mozilla to keep same user agent along authentication and download phases,
            # otherwise session might be broken and download fail, asking again for authentication
            # 'User-Agent': 'Mozilla/5.0 (Windows NT 6.1; WOW64) AppleWebKit/537.36 (KHTML, like Gecko) ' +
            #              'Chrome/32.0.1700.107 Safari/537.36'}
            'User-Agent': USER_AGENT}

    def get_id(self):
        return GenericProvider.make_id(self.name)

    @staticmethod
    def make_id(name):
        return re.sub('[^\w\d_]', '_', name.strip().lower())

    def image_name(self, *default_name):

        for name in ['%s.%s' % (self.get_id(), image_ext) for image_ext in ['png', 'gif', 'jpg']]:
            if ek.ek(os.path.isfile,
                     ek.ek(os.path.join, sickbeard.PROG_DIR, 'gui', sickbeard.GUI_NAME, 'images', 'providers', name)):
                return name

        return '%s.png' % ('newznab', default_name[0])[any(default_name)]

    def _authorised(self):
        return True

    def _check_auth(self, is_required=None):
        return True

    def is_public_access(self):
        try:
            return bool(re.search('(?i)rarbg|sick|anizb', self.name)) \
                   or False is bool(('_authorised' in self.__class__.__dict__ or hasattr(self, 'digest')
                                     or self._check_auth(is_required=True)))
        except AuthException:
            return False

    def is_active(self):
        if GenericProvider.NZB == self.providerType and sickbeard.USE_NZBS:
            return self.is_enabled()
        elif GenericProvider.TORRENT == self.providerType and sickbeard.USE_TORRENTS:
            return self.is_enabled()
        else:
            return False

    def is_enabled(self):
        """
        This should be overridden and should return the config setting eg. sickbeard.MYPROVIDER
        """
        return self.enabled

    def get_result(self, episodes, url):
        """
        Returns a result of the correct type for this provider
        """

        if GenericProvider.NZB == self.providerType:
            result = classes.NZBSearchResult(episodes)
        elif GenericProvider.TORRENT == self.providerType:
            result = classes.TorrentSearchResult(episodes)
        else:
            result = classes.SearchResult(episodes)

        result.provider = self
        result.url = url

        return result

    # noinspection PyUnusedLocal
    def cb_response(self, r, *args, **kwargs):
        self.session.response = dict(url=r.url, status_code=r.status_code, elapsed=r.elapsed, from_cache=r.from_cache)
        return r

    def get_url(self, url, post_data=None, params=None, timeout=30, json=False):
        """
        By default this is just a simple urlopen call but this method should be overridden
        for providers with special URL requirements (like cookies)
        """

        # check for auth
        if not self._authorised():
            return

        return helpers.getURL(url, post_data=post_data, params=params, headers=self.headers, timeout=timeout,
                              session=self.session, json=json, hooks=dict(response=self.cb_response))

    def download_result(self, result):
        """
        Save the result to disk.
        """

        # check for auth
        if not self._authorised():
            return False

        if GenericProvider.TORRENT == self.providerType:
            final_dir = sickbeard.TORRENT_DIR
            link_type = 'magnet'
            try:
                torrent_hash = re.findall('(?i)urn:btih:([0-9a-f]{32,40})', result.url)[0].upper()

                if 32 == len(torrent_hash):
                    torrent_hash = b16encode(b32decode(torrent_hash)).lower()

                if not torrent_hash:
                    logger.log('Unable to extract torrent hash from link: ' + ex(result.url), logger.ERROR)
                    return False

                urls = ['http%s://%s/torrent/%s.torrent' % (u + (torrent_hash,))
                        for u in (('s', 'itorrents.org'), ('s', 'torra.pro'), ('s', 'torra.click'),
                                  ('s', 'torrage.info'), ('', 'reflektor.karmorra.info'),
                                  ('s', 'torrentproject.se'), ('', 'thetorrent.org'))]
            except (StandardError, Exception):
                link_type = 'torrent'
                urls = [result.url]

        elif GenericProvider.NZB == self.providerType:
            final_dir = sickbeard.NZB_DIR
            link_type = 'nzb'
            urls = [result.url]

        else:
            return

        ref_state = 'Referer' in self.session.headers and self.session.headers['Referer']
        saved = False
        for url in urls:
            cache_dir = sickbeard.CACHE_DIR or helpers._getTempDir()
            base_name = '%s.%s' % (helpers.sanitizeFileName(result.name), self.providerType)
            cache_file = ek.ek(os.path.join, cache_dir, base_name)

            self.session.headers['Referer'] = url
            if getattr(result, 'cache_file', None) or helpers.download_file(url, cache_file, session=self.session):

                if self._verify_download(cache_file):
                    logger.log(u'Downloaded %s result from %s' % (self.name, url))
                    final_file = ek.ek(os.path.join, final_dir, base_name)
                    try:
                        helpers.moveFile(cache_file, final_file)
                        msg = 'moved'
                    except (OSError, Exception):
                        msg = 'copied cached file'
                    logger.log(u'Saved %s link and %s to %s' % (link_type, msg, final_file))
                    saved = True
                    break

                remove_file_failed(cache_file)

        if 'Referer' in self.session.headers:
            if ref_state:
                self.session.headers['Referer'] = ref_state
            else:
                del(self.session.headers['Referer'])

        if not saved and 'magnet' == link_type:
            logger.log(u'All torrent cache servers failed to return a downloadable result', logger.ERROR)
            logger.log(u'Advice: in search settings, change from method blackhole to direct torrent client connect',
                       logger.ERROR)
            final_file = ek.ek(os.path.join, final_dir, '%s.%s' % (helpers.sanitizeFileName(result.name), link_type))
            try:
                with open(final_file, 'wb') as fp:
                    fp.write(result.url)
                    fp.flush()
                    os.fsync(fp.fileno())
                logger.log(u'Saved magnet link to file as some clients (or plugins) support this, %s' % final_file)

            except (StandardError, Exception):
                pass
        elif not saved:
            logger.log(u'Server failed to return anything useful', logger.ERROR)

        return saved

    def _verify_download(self, file_name=None):
        """
        Checks the saved file to see if it was actually valid, if not then consider the download a failure.
        """
        result = True
        # primitive verification of torrents, just make sure we didn't get a text file or something
        if GenericProvider.TORRENT == self.providerType:
            parser = stream = None
            try:
                stream = FileInputStream(file_name)
                parser = guessParser(stream)
            except (HachoirError, Exception):
                pass
            result = parser and 'application/x-bittorrent' == parser.mime_type

            try:
                stream._input.close()
            except (HachoirError, Exception):
                pass

        return result

    def search_rss(self, episodes):
        return self.cache.findNeededEpisodes(episodes)

    def get_quality(self, item, anime=False):
        """
        Figures out the quality of the given RSS item node

        item: An elementtree.ElementTree element representing the <item> tag of the RSS feed

        Returns a Quality value obtained from the node's data
        """
        (title, url) = self._title_and_url(item)  # @UnusedVariable
        quality = Quality.sceneQuality(title, anime)
        return quality

    def _search_provider(self, search_params, search_mode='eponly', epcount=0, age=0, **kwargs):
        return []

    def _season_strings(self, episode):
        return []

    def _episode_strings(self, *args, **kwargs):
        return []

    def _title_and_url(self, item):
        """
        Retrieves the title and URL data from the item

        item: An elementtree.ElementTree element representing the <item> tag of the RSS feed, or a two part tup

        Returns: A tuple containing two strings representing title and URL respectively
        """

        title, url = None, None
        try:
            title, url = isinstance(item, tuple) and (item[0], item[1]) or \
                (item.get('title', None), item.get('link', None))
        except (StandardError, Exception):
            pass

        title = title and re.sub(r'\s+', '.', u'%s' % title)
        url = url and str(url).replace('&amp;', '&')

        return title, url

    def _link(self, url, url_tmpl=None):

        url = url and str(url).strip().replace('&amp;', '&') or ''
        try:
            url_tmpl = url_tmpl or self.urls['get']
        except (StandardError, Exception):
            url_tmpl = '%s'
        return url if re.match('(?i)(https?://|magnet:)', url) else (url_tmpl % url.lstrip('/'))

    def _header_row(self, table_row, custom_match=None, header_strip=''):
        """
        :param header_row: Soup resultset of table header row
        :param custom_match: Dict key/values to override one or more default regexes
        :param header_strip: String regex of ambiguities to remove from headers
        :return: dict column indices or None for leech, seeds, and size
        """
        results = {}
        rc = dict((k, re.compile('(?i)' + r)) for (k, r) in dict(
            {'seed': r'(?:seed|s/l)', 'leech': r'(?:leech|peers)', 'size': r'(?:size)'}.items()
            + ({}, custom_match)[any([custom_match])].items()).items())
        table = table_row.find_parent('table')
        header_row = table.tr or table.thead.tr or table.tbody.tr
        for y in [x for x in header_row(True) if x.attrs.get('class')]:
            y['class'] = '..'.join(y['class'])
        all_cells = header_row.find_all('th')
        all_cells = all_cells if any(all_cells) else header_row.find_all('td')

        headers = [re.sub(
            r'[\s]+', '',
            ((any([cell.get_text()]) and any([rc[x].search(cell.get_text()) for x in rc.keys()]) and cell.get_text())
             or (cell.attrs.get('id') and any([rc[x].search(cell['id']) for x in rc.keys()]) and cell['id'])
             or (cell.attrs.get('title') and any([rc[x].search(cell['title']) for x in rc.keys()]) and cell['title'])
             or next(iter(set(filter(lambda z: any([z]), [
                next(iter(set(filter(lambda y: any([y]), [
                    cell.find(tag, **p) for p in [{attr: rc[x]} for x in rc.keys()]]))), {}).get(attr)
                for (tag, attr) in [
                    ('img', 'title'), ('img', 'src'), ('i', 'title'), ('i', 'class'),
                    ('abbr', 'title'), ('a', 'title'), ('a', 'href')]]))), '')
             or cell.get_text()
             )).strip() for cell in all_cells]
        headers = [re.sub(header_strip, '', x) for x in headers]
        all_headers = headers
        colspans = [int(cell.attrs.get('colspan', 0)) for cell in all_cells]
        if any(colspans):
            all_headers = []
            for i, width in enumerate(colspans):
                all_headers += [headers[i]] + ([''] * (width - 1))

        for k, r in rc.iteritems():
            if k not in results:
                for name in filter(lambda v: any([v]) and r.search(v), all_headers[::-1]):
                    results[k] = all_headers.index(name) - len(all_headers)
                    break

        for missing in set(rc.keys()) - set(results.keys()):
            results[missing] = None

        return results

    @staticmethod
    def _dhtless_magnet(btih, name=None):
        """
        :param btih: torrent hash
        :param name: torrent name
        :return: a magnet loaded with default trackers for clients without enabled DHT or None if bad hash
        """
        try:
            btih = btih.lstrip('/').upper()
            if 32 == len(btih):
                btih = b16encode(b32decode(btih)).lower()
            btih = re.search('(?i)[0-9a-f]{32,40}', btih) and btih or None
        except (StandardError, Exception):
            btih = None
        return (btih and 'magnet:?xt=urn:btih:%s&dn=%s&tr=%s' % (btih, quote_plus(name or btih), '&tr='.join(
            [quote_plus(tr) for tr in
             'http://atrack.pow7.com/announce', 'http://mgtracker.org:2710/announce',
             'http://pow7.com/announce', 'http://t1.pow7.com/announce',
             'http://tracker.tfile.me/announce', 'udp://9.rarbg.com:2710/announce',
             'udp://9.rarbg.me:2710/announce', 'udp://9.rarbg.to:2710/announce',
             'udp://eddie4.nl:6969/announce', 'udp://explodie.org:6969/announce',
             'udp://inferno.demonoid.pw:3395/announce', 'udp://inferno.subdemon.com:3395/announce',
             'udp://ipv4.tracker.harry.lu:80/announce', 'udp://p4p.arenabg.ch:1337/announce',
             'udp://shadowshq.yi.org:6969/announce', 'udp://tracker.aletorrenty.pl:2710/announce',
             'udp://tracker.coppersurfer.tk:6969', 'udp://tracker.coppersurfer.tk:6969/announce',
             'udp://tracker.internetwarriors.net:1337', 'udp://tracker.internetwarriors.net:1337/announce',
             'udp://tracker.leechers-paradise.org:6969', 'udp://tracker.leechers-paradise.org:6969/announce',
             'udp://tracker.opentrackr.org:1337/announce', 'udp://tracker.torrent.eu.org:451/announce',
             'udp://tracker.trackerfix.com:80/announce', 'udp://tracker.zer0day.to:1337/announce'])) or None)

    def get_show(self, item, **kwargs):
        return None

    def find_search_results(self, show, episodes, search_mode, manual_search=False, **kwargs):

        self._check_auth()
        self.show = show

        results = {}
        item_list = []

        searched_scene_season = None
        for ep_obj in episodes:
            # search cache for episode result
            cache_result = self.cache.searchCache(ep_obj, manual_search)
            if cache_result:
                if ep_obj.episode not in results:
                    results[ep_obj.episode] = cache_result
                else:
                    results[ep_obj.episode].extend(cache_result)

                # found result, search next episode
                continue

            if 'sponly' == search_mode:
                # skip if season already searched
                if 1 < len(episodes) and searched_scene_season == ep_obj.scene_season:
                    continue

                searched_scene_season = ep_obj.scene_season

                # get season search params
                search_params = self._season_strings(ep_obj)
            else:
                # get single episode search params
                search_params = self._episode_strings(ep_obj)

            for cur_param in search_params:
                item_list += self._search_provider(cur_param, search_mode=search_mode, epcount=len(episodes))

        return self.finish_find_search_results(show, episodes, search_mode, manual_search, results, item_list)

    def finish_find_search_results(self, show, episodes, search_mode, manual_search, results, item_list, **kwargs):

        # if we found what we needed already from cache then return results and exit
        if len(results) == len(episodes):
            return results

        # sort list by quality
        if len(item_list):
            items = {}
            items_unknown = []
            for item in item_list:
                quality = self.get_quality(item, anime=show.is_anime)
                if Quality.UNKNOWN == quality:
                    items_unknown += [item]
                else:
                    if quality not in items:
                        items[quality] = [item]
                    else:
                        items[quality].append(item)

            item_list = list(itertools.chain(*[v for (k, v) in sorted(items.items(), reverse=True)]))
            item_list += items_unknown if items_unknown else []

        # filter results
        cl = []
        for item in item_list:
            (title, url) = self._title_and_url(item)

            parser = NameParser(False, showObj=self.get_show(item, **kwargs), convert=True)
            # parse the file name
            try:
                parse_result = parser.parse(title)
            except InvalidNameException:
                logger.log(u'Unable to parse the filename %s into a valid episode' % title, logger.DEBUG)
                continue
            except InvalidShowException:
                logger.log(u'No match for search criteria in the parsed filename ' + title, logger.DEBUG)
                continue

            show_obj = parse_result.show
            quality = parse_result.quality
            release_group = parse_result.release_group
            version = parse_result.version

            add_cache_entry = False
            if not (show_obj.air_by_date or show_obj.is_sports):
                if 'sponly' == search_mode:
                    if len(parse_result.episode_numbers):
                        logger.log(u'This is supposed to be a season pack search but the result ' + title +
                                   u' is not a valid season pack, skipping it', logger.DEBUG)
                        add_cache_entry = True
                    if len(parse_result.episode_numbers)\
                            and (parse_result.season_number not in set([ep.season for ep in episodes]) or not [
                                ep for ep in episodes if ep.scene_episode in parse_result.episode_numbers]):
                        logger.log(u'The result ' + title + u' doesn\'t seem to be a valid episode that we are trying' +
                                   u' to snatch, ignoring', logger.DEBUG)
                        add_cache_entry = True
                else:
                    if not len(parse_result.episode_numbers)\
                            and parse_result.season_number\
                            and not [ep for ep in episodes
                                     if ep.season == parse_result.season_number and
                                     ep.episode in parse_result.episode_numbers]:
                        logger.log(u'The result ' + title + u' doesn\'t seem to be a valid season that we are trying' +
                                   u' to snatch, ignoring', logger.DEBUG)
                        add_cache_entry = True
                    elif len(parse_result.episode_numbers)\
                            and not [ep for ep in episodes
                                     if ep.season == parse_result.season_number and
                            ep.episode in parse_result.episode_numbers]:
                        logger.log(u'The result ' + title + ' doesn\'t seem to be a valid episode that we are trying' +
                                   u' to snatch, ignoring', logger.DEBUG)
                        add_cache_entry = True

                if not add_cache_entry:
                    # we just use the existing info for normal searches
                    actual_season = parse_result.season_number
                    actual_episodes = parse_result.episode_numbers
            else:
                if not parse_result.is_air_by_date:
                    logger.log(u'This is supposed to be a date search but the result ' + title +
                               u' didn\'t parse as one, skipping it', logger.DEBUG)
                    add_cache_entry = True
                else:
                    airdate = parse_result.air_date.toordinal()
                    my_db = db.DBConnection()
                    sql_results = my_db.select('SELECT season, episode FROM tv_episodes ' +
                                               'WHERE showid = ? AND airdate = ?', [show_obj.indexerid, airdate])

                    if 1 != len(sql_results):
                        logger.log(u'Tried to look up the date for the episode ' + title + ' but the database didn\'t' +
                                   u' give proper results, skipping it', logger.WARNING)
                        add_cache_entry = True

                if not add_cache_entry:
                    actual_season = int(sql_results[0]['season'])
                    actual_episodes = [int(sql_results[0]['episode'])]

            # add parsed result to cache for usage later on
            if add_cache_entry:
                logger.log(u'Adding item from search to cache: ' + title, logger.DEBUG)
                ci = self.cache.add_cache_entry(title, url, parse_result=parse_result)
                if None is not ci:
                    cl.append(ci)
                continue

            # make sure we want the episode
            want_ep = True
            for epNo in actual_episodes:
                if not show_obj.wantEpisode(actual_season, epNo, quality, manual_search):
                    want_ep = False
                    break

            if not want_ep:
                logger.log(u'Ignoring result %s because we don\'t want an episode that is %s'
                           % (title, Quality.qualityStrings[quality]), logger.DEBUG)
                continue

            logger.log(u'Found result %s at %s' % (title, url), logger.DEBUG)

            # make a result object
            ep_obj = []
            for curEp in actual_episodes:
                ep_obj.append(show_obj.getEpisode(actual_season, curEp))

            result = self.get_result(ep_obj, url)
            if None is result:
                continue
            result.show = show_obj
            result.name = title
            result.quality = quality
            result.release_group = release_group
            result.content = None
            result.version = version

            if 1 == len(ep_obj):
                ep_num = ep_obj[0].episode
                logger.log(u'Single episode result.', logger.DEBUG)
            elif 1 < len(ep_obj):
                ep_num = MULTI_EP_RESULT
                logger.log(u'Separating multi-episode result to check for later - result contains episodes: ' +
                           str(parse_result.episode_numbers), logger.DEBUG)
            elif 0 == len(ep_obj):
                ep_num = SEASON_RESULT
                logger.log(u'Separating full season result to check for later', logger.DEBUG)

            if ep_num not in results:
                results[ep_num] = [result]
            else:
                results[ep_num].append(result)

        # check if we have items to add to cache
        if 0 < len(cl):
            my_db = self.cache.get_db()
            my_db.mass_action(cl)

        return results

    def find_propers(self, search_date=None, **kwargs):

        results = self.cache.listPropers(search_date)

        return [classes.Proper(x['name'], x['url'], datetime.datetime.fromtimestamp(x['time']), self.show) for x in
                results]

    def seed_ratio(self):
        """
        Provider should override this value if custom seed ratio enabled
        It should return the value of the provider seed ratio
        """
        return ''

    def _log_search(self, mode='Cache', count=0, url='url missing'):
        """
        Simple function to log the result of a search types except propers
        :param count: count of successfully processed items
        :param url: source url of item(s)
        """
        if 'Propers' != mode:
            self.log_result(mode, count, url)

    def log_result(self, mode='Cache', count=0, url='url missing'):
        """
        Simple function to log the result of any search
        :param mode: string that this log relates to
        :param count: count of successfully processed items
        :param url: source url of item(s)
        """
        str1, thing, str3 = (('', '%s item' % mode.lower(), ''), (' usable', 'proper', ' found'))['Propers' == mode]
        logger.log(u'%s %s in response from %s' % (('No' + str1, count)[0 < count], (
            '%s%s%s%s' % (('', 'freeleech ')[getattr(self, 'freeleech', False)], thing, maybe_plural(count), str3)),
            re.sub('(\s)\s+', r'\1', url)))

    def check_auth_cookie(self):

        if hasattr(self, 'cookies'):
            cookies = self.cookies

            if not (cookies and re.match('^(?:\w+=[^;\s]+[;\s]*)+$', cookies)):
                return False

            cj = requests.utils.add_dict_to_cookiejar(self.session.cookies,
                                                      dict([x.strip().split('=') for x in cookies.split(';')
                                                            if x != ''])),
            for item in cj:
                if not isinstance(item, requests.cookies.RequestsCookieJar):
                    return False

        return True

    def _check_cookie(self):

        if self.check_auth_cookie():
            return True, None

        return False, 'Cookies not correctly formatted key=value pairs e.g. uid=xx;pass=yy)'

    def has_all_cookies(self, cookies=None, pre=''):

        cookies = cookies and ([cookies], cookies)[isinstance(cookies, list)] or ['uid', 'pass']
        return all(['%s%s' % (pre, item) in self.session.cookies for item in cookies])

    def _categories_string(self, mode='Cache', template='c%s=1', delimiter='&'):

        return delimiter.join([('%s', template)[any(template)] % c for c in sorted(
            'shows' in self.categories and (isinstance(self.categories['shows'], type([])) and
                                            self.categories['shows'] or [self.categories['shows']]) or
            self.categories[(mode, 'Episode')['Propers' == mode]] +
            ([], self.categories.get('anime') or [])[
                (mode in ['Cache', 'Propers'] and helpers.has_anime()) or
                ((mode in ['Season', 'Episode']) and self.show and self.show.is_anime)])])

    @staticmethod
    def _bytesizer(size_dim=''):

        try:
            value = float('.'.join(re.findall('(?i)(\d+)(?:[.,](\d+))?', size_dim)[0]))
        except TypeError:
            return size_dim
        except IndexError:
            return None
        try:
            value *= 1024 ** ['b', 'k', 'm', 'g', 't'].index(re.findall('(t|g|m|k)[i]?b', size_dim.lower())[0])
        except IndexError:
            pass
        return long(math.ceil(value))


class NZBProvider(object, GenericProvider):

    def __init__(self, name, supports_backlog=True, anime_only=False):
        GenericProvider.__init__(self, name, supports_backlog, anime_only)

        self.providerType = GenericProvider.NZB

    def image_name(self):

        return GenericProvider.image_name(self, 'newznab')

    def maybe_apikey(self):

        if getattr(self, 'needs_auth', None):
            return (getattr(self, 'key', '') and self.key) or (getattr(self, 'api_key', '') and self.api_key) or None
        return False

    def _check_auth(self, is_required=None):

        has_key = self.maybe_apikey()
        if has_key:
            return has_key
        if None is has_key:
            raise AuthException('%s for %s is empty in Media Providers/Options'
                                % ('API key' + ('', ' and/or Username')[hasattr(self, 'username')], self.name))

        return GenericProvider._check_auth(self)

    def find_propers(self, search_date=None, shows=None, anime=None, **kwargs):

        cache_results = self.cache.listPropers(search_date)
        results = [classes.Proper(x['name'], x['url'], datetime.datetime.fromtimestamp(x['time']), self.show) for x in
                   cache_results]

        index = 0
        alt_search = ('nzbs_org' == self.get_id())
        do_search_alt = False

        search_terms = []
        regex = []
        if shows:
            search_terms += ['.proper.', '.repack.']
            regex += ['proper|repack']
            proper_check = re.compile(r'(?i)(\b%s\b)' % '|'.join(regex))
        if anime:
            terms = 'v1|v2|v3|v4|v5'
            search_terms += [terms]
            regex += [terms]
            proper_check = re.compile(r'(?i)(%s)' % '|'.join(regex))

        urls = []
        while index < len(search_terms):
            search_params = {'q': search_terms[index], 'maxage': sickbeard.BACKLOG_DAYS + 2}
            if alt_search:

                if do_search_alt:
                    search_params['t'] = 'search'
                    index += 1

                do_search_alt = not do_search_alt

            else:
                index += 1

            for item in self._search_provider({'Propers': [search_params]}):

                (title, url) = self._title_and_url(item)

                if not proper_check.search(title) or url in urls:
                    continue
                urls.append(url)

                if 'published_parsed' in item and item['published_parsed']:
                    result_date = item.published_parsed
                    if result_date:
                        result_date = datetime.datetime(*result_date[0:6])
                else:
                    logger.log(u'Unable to figure out the date for entry %s, skipping it' % title)
                    continue

                if not search_date or search_date < result_date:
                    search_result = classes.Proper(title, url, result_date, self.show)
                    results.append(search_result)

            time.sleep(0.5)

        return results

    def cache_data(self, *args, **kwargs):

        search_params = {'Cache': [{}]}
        return self._search_provider(search_params=search_params, **kwargs)


class TorrentProvider(object, GenericProvider):

    def __init__(self, name, supports_backlog=True, anime_only=False, cache_update_freq=None):
        GenericProvider.__init__(self, name, supports_backlog, anime_only)

        self.providerType = GenericProvider.TORRENT

        self._seed_ratio = None
        self.seed_time = None
        self._url = None
        self.urls = {}
        self.cache._cache_data = self._cache_data
        if cache_update_freq:
            self.cache.update_freq = cache_update_freq

    @property
    def url(self):
        if None is self._url or (hasattr(self, 'url_tmpl') and not self.urls):
            self._url = self._valid_home(False)
            self._valid_url()
        return self._url

    @url.setter
    def url(self, value=None):
        self._url = value

    def _valid_url(self):
        return True

    def image_name(self):

        return GenericProvider.image_name(self, 'torrent')

    def seed_ratio(self):

        return self._seed_ratio

    @staticmethod
    def _sort_seeders(mode, items):
        """ legacy function used by a custom provider, do not remove """
        mode in ['Season', 'Episode'] and items[mode].sort(key=lambda tup: tup[2], reverse=True)

    @staticmethod
    def _sort_seeding(mode, items):

        if mode in ['Season', 'Episode']:
            return sorted(set(items), key=lambda tup: tup[2], reverse=True)
        return items

    def _peers_fail(self, mode, seeders=0, leechers=0):

        return 'Cache' != mode and (seeders < getattr(self, 'minseed', 0) or leechers < getattr(self, 'minleech', 0))

    def get_quality(self, item, anime=False):

        if isinstance(item, tuple):
            name = item[0]
        elif isinstance(item, dict):
            name, url = self._title_and_url(item)
        else:
            name = item.title
        return Quality.sceneQuality(name, anime)

    @staticmethod
    def _reverse_quality(quality):

        return {
            Quality.SDTV: 'HDTV x264',
            Quality.SDDVD: 'DVDRIP',
            Quality.HDTV: '720p HDTV x264',
            Quality.FULLHDTV: '1080p HDTV x264',
            Quality.RAWHDTV: '1080i HDTV mpeg2',
            Quality.HDWEBDL: '720p WEB-DL h264',
            Quality.FULLHDWEBDL: '1080p WEB-DL h264',
            Quality.HDBLURAY: '720p Bluray x264',
            Quality.FULLHDBLURAY: '1080p Bluray x264'
        }.get(quality, '')

    def _season_strings(self, ep_obj, detail_only=False, scene=True, prefix='', **kwargs):

        if not ep_obj:
            return []

        show = ep_obj.show
        ep_dict = self._ep_dict(ep_obj)
        sp_detail = (show.air_by_date or show.is_sports) and str(ep_obj.airdate).split('-')[0] or \
                    (show.is_anime and ep_obj.scene_absolute_number or
                     ('sp_detail' in kwargs.keys() and kwargs['sp_detail'](ep_dict)) or 'S%(seasonnumber)02d' % ep_dict)
        sp_detail = ([sp_detail], sp_detail)[isinstance(sp_detail, list)]
        detail = ({}, {'Season_only': sp_detail})[detail_only and not self.show.is_sports and not self.show.is_anime]
        return [dict({'Season': self._build_search_strings(sp_detail, scene, prefix)}.items() + detail.items())]

    def _episode_strings(self, ep_obj, detail_only=False, scene=True, prefix='', sep_date=' ', date_or=False, **kwargs):

        if not ep_obj:
            return []

        show = ep_obj.show
        if show.air_by_date or show.is_sports:
            ep_detail = [str(ep_obj.airdate).replace('-', sep_date)]\
                if 'date_detail' not in kwargs.keys() else kwargs['date_detail'](ep_obj.airdate)
            if show.is_sports:
                month = ep_obj.airdate.strftime('%b')
                ep_detail = (ep_detail + [month], ['%s|%s' % (x, month) for x in ep_detail])[date_or]
        elif show.is_anime:
            ep_detail = ep_obj.scene_absolute_number \
                if 'ep_detail_anime' not in kwargs.keys() else kwargs['ep_detail_anime'](ep_obj.scene_absolute_number)
        else:
            ep_dict = self._ep_dict(ep_obj)
            ep_detail = sickbeard.config.naming_ep_type[2] % ep_dict \
                if 'ep_detail' not in kwargs.keys() else kwargs['ep_detail'](ep_dict)
            if sickbeard.scene_exceptions.has_abs_episodes(ep_obj):
                ep_detail = ([ep_detail], ep_detail)[isinstance(ep_detail, list)] + ['%d' % ep_dict['episodenumber']]
        ep_detail = ([ep_detail], ep_detail)[isinstance(ep_detail, list)]
        detail = ({}, {'Episode_only': ep_detail})[detail_only and not show.is_sports and not show.is_anime]
        return [dict({'Episode': self._build_search_strings(ep_detail, scene, prefix)}.items() + detail.items())]

    @staticmethod
    def _ep_dict(ep_obj):
        season, episode = ((ep_obj.season, ep_obj.episode),
                           (ep_obj.scene_season, ep_obj.scene_episode))[bool(ep_obj.show.is_scene)]
        return {'seasonnumber': season, 'episodenumber': episode}

    def _build_search_strings(self, ep_detail, process_name=True, prefix=''):
        """
        Build a list of search strings for querying a provider
        :param ep_detail: String of episode detail or List of episode details
        :param process_name: Bool Whether to call sanitizeSceneName() on show name
        :param prefix: String to insert to search strings
        :return: List of search string parameters
        """
        ep_detail = ([ep_detail], ep_detail)[isinstance(ep_detail, list)]
        prefix = ([prefix], prefix)[isinstance(prefix, list)]

        search_params = []
        crop = re.compile(r'([.\s])(?:\1)+')
        for name in set(allPossibleShowNames(self.show)):
            if process_name:
                name = helpers.sanitizeSceneName(name)
            for detail in ep_detail:
                search_params += [crop.sub(r'\1', '%s %s%s' % (name, x, detail)) for x in prefix]
        return search_params

    @staticmethod
    def _has_signature(data=None):
        return data and re.search(r'(?sim)<input[^<]+name="password"', data) and \
               re.search(r'(?sim)<input[^<]+name="username"', data)

    def _valid_home(self, attempt_fetch=True):
        """
        :return: signature verified home url else None if validation fail
        """
        url_base = getattr(self, 'url_base', None)
        if url_base:
            return url_base

        url_list = getattr(self, 'url_home', None)
        if not url_list and getattr(self, 'url_edit', None) or 10 > max([len(x) for x in url_list]):
            return None

        url_list = ['%s/' % x.rstrip('/') for x in url_list]
        last_url, expire = sickbeard.PROVIDER_HOMES.get(self.get_id(), ('', None))
        if 'site down' == last_url:
            if expire and (expire > int(time.time())) or not self.enabled:
                return None
        elif last_url:
            last_url = last_url.replace('getrss.php', '/')  # correct develop typo after a network outage (0.11>0.12)
            last_url in url_list and url_list.remove(last_url)
            url_list.insert(0, last_url)

        if not self.enabled:
            return last_url

        for cur_url in url_list:
            if not self.is_valid_mod(cur_url):
                return None

            if 10 < len(cur_url) and ((expire and (expire > int(time.time()))) or
                                      self._has_signature(helpers.getURL(cur_url, session=self.session))):

                for k, v in getattr(self, 'url_tmpl', {}).items():
                    self.urls[k] = v % {'home': cur_url, 'vars': getattr(self, 'url_vars', {}).get(k, '')}

                if last_url != cur_url or (expire and not (expire > int(time.time()))):
                    sickbeard.PROVIDER_HOMES[self.get_id()] = (cur_url, int(time.time()) + (60*60))
                    sickbeard.save_config()
                return cur_url

        logger.log('Failed to identify a "%s" page with %s %s (local network issue, site down, or ISP blocked) ' %
                   (self.name, len(url_list), ('URL', 'different URLs')[1 < len(url_list)]) +
                   (attempt_fetch and ('Suggest; 1) Disable "%s" 2) Use a proxy/VPN' % self.get_id()) or ''),
                   (logger.WARNING, logger.ERROR)[self.enabled])
        self.urls = {}
        sickbeard.PROVIDER_HOMES[self.get_id()] = ('site down', int(time.time()) + (5 * 60))
        sickbeard.save_config()
        return None

    def is_valid_mod(self, url):
        parsed, s, is_valid = urlparse.urlparse(url), 70000700, True
        if 2012691328 == s + zlib.crc32(('.%s' % (parsed.netloc or parsed.path)).split('.')[-2]):
            is_valid = False
            file_name = '%s.py' % os.path.join(sickbeard.PROG_DIR, *self.__module__.split('.'))
            if ek.ek(os.path.isfile, file_name):
                with open(file_name, 'rb') as file_hd:
                    is_valid = s + zlib.crc32(file_hd.read()) in (1661931498, 472149389)
        return is_valid

    def _authorised(self, logged_in=None, post_params=None, failed_msg=None, url=None, timeout=30):

        maxed_out = (lambda y: re.search(r'(?i)[1-3]((<[^>]+>)|\W)*' +
                                         '(attempts|tries|remain)[\W\w]{,40}?(remain|left|attempt)', y))
        logged_in, failed_msg = [None is not a and a or b for (a, b) in (
            (logged_in, (lambda y=None: self.has_all_cookies())),
            (failed_msg, (lambda y='': maxed_out(y) and u'Urgent abort, running low on login attempts. ' +
                                                        u'Password flushed to prevent service disruption to %s.' or
                          (re.search(r'(?i)(username|password)((<[^>]+>)|\W)*' +
                                     '(or|and|/|\s)((<[^>]+>)|\W)*(password|incorrect)', y) and
                           u'Invalid username or password for %s. Check settings' or
                           u'Failed to authenticate or parse a response from %s, abort provider')))
        )]

        if logged_in() and (not hasattr(self, 'urls') or bool(len(getattr(self, 'urls')))):
            return True

        if not self._valid_home():
            return False

        if hasattr(self, 'digest'):
            self.cookies = re.sub(r'(?i)([\s\']+|cookie\s*:)', '', self.digest)
            success, msg = self._check_cookie()
            if not success:
                self.cookies = None
                logger.log(u'%s: [%s]' % (msg, self.cookies), logger.WARNING)
                return False
        elif not self._check_auth():
            return False

        if isinstance(url, type([])):
            for i in range(0, len(url)):
                helpers.getURL(url.pop(), session=self.session)

        passfield, userfield = None, None
        if not url:
            if hasattr(self, 'urls'):
                url = self.urls.get('login_action')
                if url:
                    response = helpers.getURL(url, session=self.session)
                    if None is response:
                        return False
                    try:
                        post_params = isinstance(post_params, type({})) and post_params or {}
                        form = 'form_tmpl' in post_params and post_params.pop('form_tmpl')
                        if form:
                            form = re.findall(
                                '(?is)(<form[^>]+%s.*?</form>)' % (True is form and 'login' or form), response)
                            response = form and form[0] or response

                        action = re.findall('<form[^>]+action=[\'"]([^\'"]*)', response)[0]
                        url = action if action.startswith('http') else \
                            url if not action else \
                            (url + action) if action.startswith('?') else \
                            (self.urls.get('login_base') or self.urls['config_provider_home_uri']) + action.lstrip('/')

                        tags = re.findall(r'(?is)(<input[^>]*?name=[\'"][^\'"]+[^>]*)', response)
                        attrs = [[(re.findall(r'(?is)%s=[\'"]([^\'"]+)' % attr, x) or [''])[0]
                                  for attr in ['type', 'name', 'value']] for x in tags]
                        for itype, name, value in attrs:
                            if 'password' in [itype, name]:
                                passfield = name
                            if name not in ('username', 'password') and 'password' != itype:
                                post_params.setdefault(name, value)
                    except KeyError:
                        return super(TorrentProvider, self)._authorised()
                else:
                    url = self.urls.get('login')
            if not url:
                return super(TorrentProvider, self)._authorised()

        if hasattr(self, 'username') and hasattr(self, 'password'):
            if not post_params:
                post_params = dict(username=self.username, password=self.password)
            elif isinstance(post_params, type({})):
                if self.username not in post_params.values():
                    post_params['username'] = self.username
                if self.password not in post_params.values():
                    post_params[(passfield, 'password')[not passfield]] = self.password

        response = helpers.getURL(url, post_data=post_params, session=self.session, timeout=timeout)
        if response:
            if logged_in(response):
                return True

            if maxed_out(response) and hasattr(self, 'password'):
                self.password = None
                sickbeard.save_config()
            logger.log(failed_msg(response) % self.name, logger.ERROR)

        return False

    def _check_auth(self, is_required=False):

        if hasattr(self, 'username') and hasattr(self, 'password'):
            if self.username and self.password:
                return True
            setting = 'Password or Username'
        elif hasattr(self, 'username') and hasattr(self, 'api_key'):
            if self.username and self.api_key:
                return True
            setting = 'Api key or Username'
        elif hasattr(self, 'username') and hasattr(self, 'passkey'):
            if self.username and self.passkey:
                return True
            setting = 'Passkey or Username'
        elif hasattr(self, 'uid') and hasattr(self, 'passkey'):
            if self.uid and self.passkey:
                return True
            setting = 'Passkey or uid'
        elif hasattr(self, 'api_key'):
            if self.api_key:
                return True
            setting = 'Api key'
        elif hasattr(self, 'passkey'):
            if self.passkey:
                return True
            setting = 'Passkey'
        else:
            return not is_required and GenericProvider._check_auth(self)

        raise AuthException('%s for %s is empty in Media Providers/Options' % (setting, self.name))

    def find_propers(self, **kwargs):
        """
        Search for releases of type PROPER
        :return: list of Proper objects
        """
        results = []

        search_terms = getattr(self, 'proper_search_terms', ['proper', 'repack'])
        if not isinstance(search_terms, list):
            if None is search_terms:
                search_terms = 'proper|repack'
            search_terms = [search_terms]

        items = self._search_provider({'Propers': search_terms})

        clean_term = re.compile(r'(?i)[^a-z1-9|.]+')
        for proper_term in search_terms:

            proper_check = re.compile(r'(?i)(?:%s)' % clean_term.sub('', proper_term))
            for item in items:
                title, url = self._title_and_url(item)
                if proper_check.search(title):
                    results.append(classes.Proper(title, url, datetime.datetime.today(),
                                                  helpers.findCertainShow(sickbeard.showList, None)))
        return results

    @staticmethod
    def _has_no_results(html):
        return re.search(r'(?i)<(?:b|div|h\d|p|span|strong|td)[^>]*>\s*(?:' +
                         'your\ssearch.*?did\snot\smatch|' +
                         '(?:nothing|0</b>\s+torrents)\sfound|' +
                         '(?:sorry,\s)?no\s(?:results|torrents)\s(found|here|match)|' +
                         'no\s(?:match|results|torrents)!*|'
                         '[^<]*?there\sare\sno\sresults|' +
                         '[^<]*?no\shits\.\sTry\sadding' +
                         ')', html)

    def _cache_data(self):

        return self._search_provider({'Cache': ['']})
