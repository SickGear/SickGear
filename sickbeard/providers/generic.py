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
from base64 import b16encode, b32decode

import sickbeard
import requests
import requests.cookies
from hachoir_parser import guessParser
from hachoir_core.stream import FileInputStream

from sickbeard import helpers, classes, logger, db, tvcache, encodingKludge as ek
from sickbeard.common import Quality, MULTI_EP_RESULT, SEASON_RESULT, USER_AGENT
from sickbeard.exceptions import SickBeardException, AuthException, ex
from sickbeard.helpers import maybe_plural, _remove_file_failed as remove_file_failed
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
        self.supportsBacklog = supports_backlog
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
        self.categories = None

        self.cache = tvcache.TVCache(self)

        self.session = requests.session()

        self.headers = {
            # Using USER_AGENT instead of Mozilla to keep same user agent along authentication and download phases,
            # otherwise session might be broken and download fail, asking again for authentication
            # 'User-Agent': 'Mozilla/5.0 (Windows NT 6.1; WOW64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/32.0.1700.107 Safari/537.36'}
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

    def _check_auth(self):
        return True

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

                urls = ['http%s://%s/%s.torrent' % (u + (torrent_hash,))
                        for u in (('s', 'torcache.net/torrent'), ('', 'thetorrent.org/torrent'),
                                  ('s', 'itorrents.org/torrent'))]
            except:
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
            if helpers.download_file(url, cache_file, session=self.session):

                if self._verify_download(cache_file):
                    logger.log(u'Downloaded %s result from %s' % (self.name, url))
                    final_file = ek.ek(os.path.join, final_dir, base_name)
                    try:
                        helpers.moveFile(cache_file, final_file)
                        msg = 'moved'
                    except:
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

        if not saved:
            logger.log(u'All torrent cache servers failed to return a downloadable result', logger.ERROR)

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
            except:
                pass
            result = parser and 'application/x-bittorrent' == parser.mime_type

            try:
                stream._input.close()
            except:
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

    def _search_provider(self, search_params, search_mode='eponly', epcount=0, age=0):
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
        except Exception:
            pass

        title = title and re.sub(r'\s+', '.', u'%s' % title)
        url = url and str(url).replace('&amp;', '&')

        return title, url

    def find_search_results(self, show, episodes, search_mode, manual_search=False):

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
        parser = NameParser(False, convert=True)
        for item in item_list:
            (title, url) = self._title_and_url(item)

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
                    elif len(parse_result.episode_numbers) and not [ep for ep in episodes if
                                                                    ep.season == parse_result.season_number and ep.episode in parse_result.episode_numbers]:
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
                    sql_results = my_db.select('SELECT season, episode FROM tv_episodes WHERE showid = ? AND airdate = ?',
                                               [show_obj.indexerid, airdate])

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

            if not re.match('^(\w+=\w+[;\s]*)+$', cookies):
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

        cookies = cookies or ['uid', 'pass']
        return False not in ['%s%s' % (pre, item) in self.session.cookies for item in ([cookies], cookies)[isinstance(cookies, list)]]

    def _categories_string(self, mode='Cache', template='c%s=1', delimiter='&'):

        return delimiter.join([('%s', template)[any(template)] % c for c in sorted(self.categories['shows'] + (
            [], [] if 'anime' not in self.categories else self.categories['anime'])[
            ('Cache' == mode and helpers.has_anime()) or ((mode in ['Season', 'Episode']) and self.show and self.show.is_anime)])])

    @staticmethod
    def _bytesizer(size_dim=''):

        try:
            value = float('.'.join(re.findall('(?i)(\d+)(?:[\.,](\d+))?', size_dim)[0]))
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

        if hasattr(self, 'needs_auth') and self.needs_auth:
            if hasattr(self, 'key') and 0 < len(self.key):
                return self.key
            if hasattr(self, 'api_key') and 0 < len(self.api_key):
                return self.api_key
            return None
        return False

    def _check_auth(self):

        has_key = self.maybe_apikey()
        if has_key:
            return has_key
        if None is has_key:
            raise AuthException('%s for %s is empty in config provider options'
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
                    logger.log(u'Unable to figure out the date for entry %s, skipping it', title)
                    continue

                if not search_date or search_date < result_date:
                    search_result = classes.Proper(title, url, result_date, self.show)
                    results.append(search_result)

            time.sleep(0.5)

        return results

    def cache_data(self, *args, **kwargs):

        search_params = {'Cache': [{}]}
        return self._search_provider(search_params)


class TorrentProvider(object, GenericProvider):

    def __init__(self, name, supports_backlog=True, anime_only=False):
        GenericProvider.__init__(self, name, supports_backlog, anime_only)

        self.providerType = GenericProvider.TORRENT

        self._seed_ratio = None
        self.seed_time = None

    def image_name(self):

        return GenericProvider.image_name(self, 'torrent')

    def seed_ratio(self):

        return self._seed_ratio

    @staticmethod
    def _sort_seeders(mode, items):

        mode in ['Season', 'Episode'] and items[mode].sort(key=lambda tup: tup[2], reverse=True)

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
                     'S%(seasonnumber)02d' % ep_dict if 'sp_detail' not in kwargs.keys() else kwargs['sp_detail'](ep_dict))
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
        crop = re.compile(r'([\.\s])(?:\1)+')
        for name in set(allPossibleShowNames(self.show)):
            if process_name:
                name = helpers.sanitizeSceneName(name)
            for detail in ep_detail:
                search_params += [crop.sub(r'\1', '%s %s%s' % (name, x, detail)) for x in prefix]
        return search_params

    def _authorised(self, logged_in=None, post_params=None, failed_msg=None, url=None, timeout=30):

        maxed_out = (lambda x: re.search(r'(?i)[1-3]((<[^>]+>)|\W)*(attempts|tries|remain)[\W\w]{,40}?(remain|left|attempt)', x))
        logged_in, failed_msg = [None is not a and a or b for (a, b) in (
            (logged_in, (lambda x=None: self.has_all_cookies())),
            (failed_msg, (lambda x='': maxed_out(x) and u'Urgent abort, running low on login attempts. Password flushed to prevent service disruption to %s.' or
                          (re.search(r'(?i)(username|password)((<[^>]+>)|\W)*(or|and|/|\s)((<[^>]+>)|\W)*(password|incorrect)', x) and
                           u'Invalid username or password for %s. Check settings' or
                           u'Failed to authenticate or parse a response from %s, abort provider')))
        )]

        if logged_in():
            return True

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

        if not url:
            if hasattr(self, 'urls'):
                url = self.urls.get('login_action')
                if url:
                    response = helpers.getURL(url, session=self.session)
                    try:
                        action = re.findall('[<]form[\w\W]+?action="([^"]+)', response)[0]
                        url = (self.urls.get('login_base') or
                               self.urls['config_provider_home_uri']) + action.lstrip('/')

                        tags = re.findall(r'(?is)(<input.*?name="[^"]+".*?>)', response)
                        nv = [(tup[0]) for tup in [re.findall(r'(?is)name="([^"]+)"(?:.*?value="([^"]+)")?', x)
                                                   for x in tags]]
                        for name, value in nv:
                            if name not in ('username', 'password'):
                                post_params = isinstance(post_params, type({})) and post_params or {}
                                post_params.setdefault(name, value)
                    except KeyError:
                        return super(TorrentProvider, self)._authorised()
                else:
                    url = self.urls.get('login')
            if not url:
                return super(TorrentProvider, self)._authorised()

        if hasattr(self, 'username') and hasattr(self, 'password'):
            creds = dict(username=self.username, password=self.password)
            if not post_params:
                post_params = creds.copy()
            elif self.password not in post_params.values() and isinstance(post_params, type({})):
                post_params.update(creds)

        response = helpers.getURL(url, post_data=post_params, session=self.session, timeout=timeout)
        if response:
            if logged_in(response):
                return True

            if maxed_out(response) and hasattr(self, 'password'):
                self.password = None
                sickbeard.save_config()
            logger.log(failed_msg(response) % self.name, logger.ERROR)

        return False

    def _check_auth(self):

        if hasattr(self, 'username') and hasattr(self, 'password'):
            if self.username and self.password:
                return True
            setting = 'Password or Username'
        elif hasattr(self, 'username') and hasattr(self, 'passkey'):
            if self.username and self.passkey:
                return True
            setting = 'Passkey or Username'
        elif hasattr(self, 'api_key'):
            if self.api_key:
                return True
            setting = 'Apikey'
        elif hasattr(self, 'passkey'):
            if self.passkey:
                return True
            setting = 'Passkey'
        else:
            return GenericProvider._check_auth(self)

        raise AuthException('%s for %s is empty in config provider options' % (setting, self.name))

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

        clean_term = re.compile(r'(?i)[^a-z1-9\|\.]+')
        for proper_term in search_terms:

            proper_check = re.compile(r'(?i)(?:%s)' % clean_term.sub('', proper_term))
            for item in items:
                title, url = self._title_and_url(item)
                if proper_check.search(title):
                    results.append(classes.Proper(title, url, datetime.datetime.today(),
                                                  helpers.findCertainShow(sickbeard.showList, None)))
        return results

    @staticmethod
    def _has_no_results(*html):
        return re.search(r'(?i)<(?:b|h\d|strong)[^>]*>(?:' +
                         'your\ssearch\sdid\snot\smatch|' +
                         'nothing\sfound|' +
                         'no\storrents\sfound|' +
                         '.*?there\sare\sno\sresults|' +
                         '.*?no\shits\.\sTry\sadding' +
                         ')', html[0])

    def cache_data(self, *args, **kwargs):

        search_params = {'Cache': ['']}
        return self._search_provider(search_params)
