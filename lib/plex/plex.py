# -*- coding: utf-8 -*-
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

from time import sleep

import platform
import re

try:
    import urllib.request as urllib2
except ImportError:
    import urllib2

from sickbeard import logger
from sickbeard.helpers import get_url, try_int, parse_xml

from _23 import unquote, urlencode
from six import iteritems


class Plex(object):
    def __init__(self, settings=None):

        settings = settings or {}
        self._plex_host = settings.get('plex_host') or '127.0.0.1'
        self.plex_port = settings.get('plex_port') or '32400'

        self.username = settings.get('username', '')
        self.password = settings.get('password', '')
        self.token = settings.get('token', '')

        self.device_name = settings.get('device_name', '')
        self.client_id = settings.get('client_id') or '5369636B47656172'
        self.machine_client_identifier = ''

        self.default_home_users = settings.get('default_home_users', '')

        # Progress percentage to consider video as watched
        # if set to anything > 0, videos with watch progress greater than this will be considered watched
        self.default_progress_as_watched = settings.get('default_progress_as_watched', 0)

        # Sections to scan. If empty all sections will be looked at,
        # the section id should be used which is the number found be in the url on PlexWeb after /section/[ID]
        self.section_list = settings.get('section_list', [])

        # Sections to skip scanning, for use when Settings['section_list'] is not specified,
        # the same as section_list, the section id should be used
        self.ignore_sections = settings.get('ignore_sections', [])

        # Filter sections by paths that are in this array
        self.section_filter_path = settings.get('section_filter_path', [])

        # Results
        self.show_states = {}
        self.file_count = 0

        # Conf
        self.config_version = 2.0
        self.use_logger = False
        self.test = None
        self.home_user_tokens = {}

        if self.username and '' == self.token:
            self.token = self.get_token(self.username, self.password)

    @property
    def plex_host(self):

        host = self._plex_host
        if not host.startswith('http'):
            host = 'http://%s' % host
        return host

    @plex_host.setter
    def plex_host(self, value):

        self._plex_host = value

    def log(self, msg, debug=True):

        try:
            if self.use_logger:
                msg = 'Plex:: ' + msg
                if debug:
                    logger.log(msg, logger.DEBUG)
                else:
                    logger.log(msg)
            # else:
            #     print(msg.encode('ascii', 'replace').decode())
        except (BaseException, Exception):
            pass

    def get_token(self, user, passw):

        auth = ''
        try:
            auth = get_url('https://plex.tv/users/sign_in.json',
                           headers={'X-Plex-Device-Name': 'SickGear',
                                    'X-Plex-Platform': platform.system(), 'X-Plex-Device': platform.system(),
                                    'X-Plex-Platform-Version': platform.release(),
                                    'X-Plex-Provides': 'Python', 'X-Plex-Product': 'Python',
                                    'X-Plex-Client-Identifier': self.client_id,
                                    'X-Plex-Version': str(self.config_version),
                                    'X-Plex-Username': user
                                    },
                           parse_json=True,
                           post_data=urlencode({b'user[login]': user, b'user[password]': passw}).encode('utf-8')
                           )['user']['authentication_token']
        except TypeError:
            self.log('Error in response from plex.tv auth server')
        except IndexError:
            self.log('Error getting Plex Token')

        return auth

    def get_access_token(self, token):

        resources = self.get_url_x('https://plex.tv/api/resources?includeHttps=1', token=token)
        if None is resources:
            return ''

        devices = resources.findall('Device')
        for device in devices:
            if 1 == len(devices) \
                    or self.machine_client_identifier == device.get('clientIdentifier') \
                    or (self.device_name
                        and (self.device_name.lower() in device.get('name').lower()
                             or self.device_name.lower() in device.get('clientIdentifier').lower())):
                access_token = device.get('accessToken')
                if not access_token:
                    return ''
                return access_token

            connections = device.findall('Connection')
            for connection in connections:
                if self.plex_host == connection.get('address'):
                    access_token = device.get('accessToken')
                    if not access_token:
                        return ''
                    uri = connection.get('uri')
                    match = re.compile(r'(http[s]?://.*?):(\d*)').match(uri)
                    if match:
                        self.plex_host = match.group(1)
                        self.plex_port = match.group(2)
                    return access_token
        return ''

    def get_plex_home_user_tokens(self):

        user_tokens = {}

        # check Plex is contactable
        home_users = self.get_url_x('https://plex.tv/api/home/users')
        if None is not home_users:
            for user in home_users.findall('User'):
                user_id = user.get('id')
                switch_page = self.get_url_x('https://plex.tv/api/home/users/%s/switch' % user_id, post_data=True)
                if None is not switch_page:
                    home_token = 'user' == switch_page.tag and switch_page.get('authenticationToken')
                    if home_token:
                        username = switch_page.get('title')
                        user_tokens[username] = self.get_access_token(home_token)
        return user_tokens

    def get_url_x(self, url, token=None, **kwargs):

        if not token:
            token = self.token
        if not url.startswith('http'):
            url = 'http://' + url

        for x in range(0, 3):
            if 0 < x:
                sleep(0.5)
            try:
                headers = {'X-Plex-Device-Name': 'SickGear',
                           'X-Plex-Platform': platform.system(), 'X-Plex-Device': platform.system(),
                           'X-Plex-Platform-Version': platform.release(),
                           'X-Plex-Provides': 'controller', 'X-Plex-Product': 'Python',
                           'X-Plex-Client-Identifier': self.client_id,
                           'X-Plex-Version': str(self.config_version),
                           'X-Plex-Token': token,
                           'Accept': 'application/xml'
                           }
                if self.username:
                    headers.update({'X-Plex-Username': self.username})
                page = get_url(url, headers=headers, **kwargs)
                if page:
                    parsed = parse_xml(page)
                    if None is not parsed and len(parsed):
                        return parsed
                    return None

            except Exception as e:
                self.log('Error requesting page: %s' % e)
                continue
        return None

    # uses the Plex API to delete files instead of system functions, useful for remote installations
    def delete_file(self, media_id=0):

        try:
            endpoint = ('/library/metadata/%s' % str(media_id))
            req = urllib2.Request('%s:%s%s' % (self.plex_host, self.plex_port, endpoint),
                                  None, {'X-Plex-Token': self.token})
            req.get_method = lambda: 'DELETE'
            urllib2.urlopen(req)
        except (BaseException, Exception):
            return False
        return True

    @staticmethod
    def get_media_info(video_node):

        progress = 0
        if None is not video_node.get('viewOffset') and None is not video_node.get('duration'):
            progress = try_int(video_node.get('viewOffset')) * 100 / try_int(video_node.get('duration'))

        for media in video_node.findall('Media'):
            for part in media.findall('Part'):
                file_name = part.get('file')
                # if '3' > sys.version:  # remove HTML quoted characters, only works in python < 3
                #     file_name = urllib2.unquote(file_name.encode('utf-8', errors='replace'))
                # else:
                file_name = unquote(file_name)

                return {'path_file': file_name, 'media_id': video_node.get('ratingKey'),
                        'played': int(video_node.get('viewCount') or 0), 'progress': progress}

    def check_users_watched(self, users, media_id):

        if not self.home_user_tokens:
            self.home_user_tokens = self.get_plex_home_user_tokens()

        result = {}
        if 'all' in users:
            users = self.home_user_tokens.keys()

        for user in users:
            user_media_page = self.get_url_pms('/library/metadata/%s' % media_id, token=self.home_user_tokens[user])
            if None is not user_media_page:
                video_node = user_media_page.find('Video')

                progress = 0
                if None is not video_node.get('viewOffset') and None is not video_node.get('duration'):
                    progress = try_int(video_node.get('viewOffset')) * 100 / try_int(video_node.get('duration'))

                played = int(video_node.get('viewCount') or 0)
                if not progress and not played:
                    continue

                date_watched = 0
                if (0 < try_int(video_node.get('viewCount'))) or (0 < self.default_progress_as_watched < progress):
                    last_viewed_at = video_node.get('lastViewedAt')
                    if last_viewed_at and last_viewed_at not in ('', '0'):
                        date_watched = last_viewed_at

                if date_watched:
                    result[user] = dict(played=played, progress=progress, date_watched=date_watched)
            else:
                self.log('Do not have the token for %s.' % user)

        return result

    def get_url_pms(self, endpoint=None, **kwargs):

        return endpoint and self.get_url_x(
            '%s:%s%s' % (self.plex_host, self.plex_port, endpoint), **kwargs)

    # parse episode information from season pages
    def stat_show(self, node):

        ep_nodes = []
        if 'directory' == node.tag.lower() and 'show' == node.get('type'):
            show = self.get_url_pms(node.get('key'))
            if None is show:  # Check if show page is None or empty
                self.log('Failed to load show page. Skipping...')
                return None

            for season_node in show.findall('Directory'):  # Each directory is a season
                if 'season' != season_node.get('type'):  # skips Specials
                    continue

                season_node_key = season_node.get('key')
                season_node = self.get_url_pms(season_node_key)
                if None is not season_node:
                    ep_nodes += [season_node]

        elif 'mediacontainer' == node.tag.lower() and 'episode' == node.get('viewGroup'):
            ep_nodes = [node]

        check_users = []
        if self.default_home_users:
            check_users = self.default_home_users.strip(' ,').lower().split(',')
            for k in range(0, len(check_users)):  # Remove extra spaces and commas
                check_users[k] = check_users[k].strip(', ')

        for episode_node in ep_nodes:
            for video_node in episode_node.findall('Video'):

                media_info = self.get_media_info(video_node)

                if check_users:
                    user_info = self.check_users_watched(check_users, media_info['media_id'])
                    for user_name, user_media_info in user_info.items():
                        self.show_states.update({len(self.show_states): dict(
                            path_file=media_info['path_file'],
                            media_id=media_info['media_id'],
                            played=(100 * user_media_info['played']) or user_media_info['progress'] or 0,
                            label=user_name,
                            date_watched=user_media_info['date_watched'])})
                else:
                    self.show_states.update({len(self.show_states): dict(
                        path_file=media_info['path_file'],
                        media_id=media_info['media_id'],
                        played=(100 * media_info['played']) or media_info['progress'] or 0,
                        label=self.username,
                        date_watched=video_node.get('lastViewedAt'))})

                self.file_count += 1

        return True

    def fetch_show_states(self, fetch_all=False):

        error_log = []
        self.show_states = {}

        server_check = self.get_url_pms('/')
        if None is server_check or 'MediaContainer' != server_check.tag:
            error_log.append('Cannot reach server!')

        else:
            if not self.device_name:
                self.device_name = server_check.get('friendlyName')

            if not self.machine_client_identifier:
                self.machine_client_identifier = server_check.get('machineIdentifier')

            access_token = None
            if self.token:
                access_token = self.get_access_token(self.token)
                if access_token:
                    self.token = access_token
                    if not self.home_user_tokens:
                        self.home_user_tokens = self.get_plex_home_user_tokens()
                else:
                    error_log.append('Access Token not found')

            resp_sections = None
            if None is access_token or len(access_token):
                resp_sections = self.get_url_pms('/library/sections/')

            if None is not resp_sections:

                unpather = []
                for loc in self.section_filter_path:
                    loc = re.sub(r'[/\\]+', '/', loc.lower())
                    loc = re.sub(r'^(.{,2})[/\\]', '', loc)
                    unpather.append(loc)
                self.section_filter_path = unpather

                for section in resp_sections.findall('Directory'):
                    if 'show' != section.get('type') or not section.findall('Location'):
                        continue

                    section_path = re.sub(r'[/\\]+', '/', section.find('Location').get('path').lower())
                    section_path = re.sub(r'^(.{,2})[/\\]', '', section_path)
                    if not any([section_path in path for path in self.section_filter_path]):
                        continue

                    if section.get('key') not in self.ignore_sections \
                            and section.get('title') not in self.ignore_sections:
                        section_key = section.get('key')

                        for (user, token) in iteritems(self.home_user_tokens or {'': None}):
                            self.username = user

                            resp_section = self.get_url_pms('/library/sections/%s/%s' % (
                                section_key, ('recentlyViewed', 'all')[fetch_all]), token=token)
                            if None is not resp_section:
                                view_group = 'MediaContainer' == resp_section.tag and \
                                             resp_section.get('viewGroup') or ''
                                if 'show' == view_group and fetch_all:
                                    for DirectoryNode in resp_section.findall('Directory'):
                                        self.stat_show(DirectoryNode)
                                elif 'episode' == view_group and not fetch_all:
                                    self.stat_show(resp_section)

        if 0 < len(error_log):
            self.log('Library errors...')
            for item in error_log:
                self.log(item)

        return 0 < len(error_log)
