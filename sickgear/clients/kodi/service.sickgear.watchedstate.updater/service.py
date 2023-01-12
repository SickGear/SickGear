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

import datetime
try:
    import json as json
except (BaseException, Exception):
    import simplejson as json
from os import path
import socket
# noinspection PyUnresolvedReferences,PyProtectedMember
from ssl import _create_unverified_context
import sys
import time
import traceback

# noinspection PyCompatibility,PyUnresolvedReferences
from urllib.error import URLError
from urllib.parse import urlencode
from urllib.request import (Request, urlopen)

# these are Kodi specific libs, so block the error reports in pycharm
import xbmc
import xbmcaddon
import xbmcgui
import xbmcvfs

ADDON_ID = 'service.sickgear.watchedstate.updater'
ADDON_VERSION = '1.0.9'


class SickGearWatchedStateUpdater(xbmc.Monitor):

    def __init__(self):
        super(SickGearWatchedStateUpdater, self).__init__()
        self.wait_onstartup = 2000

        # noinspection PyTypeChecker
        self.addon = None  # type: xbmcaddon.Addon
        self.addon_name = None
        self.path_addon = None
        self.path_addon_data = None
        self.path_addons = None

        self.red_logo = None
        self.green_logo = None
        self.black_logo = None

        self.kodi_ip = None
        self.kodi_port = None

        self.kodi_events = None
        self.sock_kodi = None

    def run(self):
        """
        Main start
        """
        self.addon = xbmcaddon.Addon()
        self.addon_name = self.addon.getAddonInfo('name')
        self.path_addon = self.addon.getAddonInfo('path')
        self.path_addon_data = self.addon.getAddonInfo('profile')
        self.path_addons = self.make_path([xbmcvfs.translatePath('special://home'), 'addons'])

        icon_size = '%s'
        try:
            if 1350 > xbmcgui.Window.getWidth(xbmcgui.Window()):
                icon_size += '-sm'
        except (BaseException, Exception):
            pass
        icon = f'{self.path_addon}/resources/icon-{icon_size}.png'
        self.red_logo = icon % 'red'
        self.green_logo = icon % 'green'
        self.black_logo = icon % 'black'

        self.kodi_ip = self.get_setting('kodi_ip')
        self.kodi_port = int(self.get_setting('kodi_port'))

        if not self.enable_kodi_allow_remote():
            return

        # migrate legacy data from pre Kodi (Matrix)
        legacy_temp = self.make_path([self.path_addons, 'temp', ''])
        if xbmcvfs.exists(legacy_temp):
            for fname in ['sickgear_buffer.txt', 'sickgear_extra.txt']:
                src = self.make_path([legacy_temp, fname])
                if xbmcvfs.exists(src):
                    dest = self.make_path([self.path_addon_data, fname])
                    try:
                        xbmcvfs.copy(src, dest)
                        xbmcvfs.delete(src)
                    except (BaseException, Exception) as e:
                        self.log(f'Failed to move {src} to {dest} err: {self.ex(e)}')

        self.sock_kodi = socket.socket()
        self.sock_kodi.setblocking(True)
        xbmc.sleep(self.wait_onstartup)
        try:
            self.sock_kodi.connect((self.kodi_ip, self.kodi_port))
        except (BaseException, Exception) as e:
            return self.report_contact_fail(e)

        self.log('Started')
        self.notify('Started in background')

        cache_pkg = f'{self.path_addons}/packages/{ADDON_ID}-{ADDON_VERSION}.zip'
        if xbmcvfs.exists(cache_pkg):
            try:
                xbmcvfs.delete(cache_pkg)
            except (BaseException, Exception):
                pass

        self.kodi_events = xbmc.Monitor()

        sock_buffer, depth, methods, method = '', 0, {'VideoLibrary.OnUpdate': self.video_library_on_update}, None

        # socks listener parsing Kodi json output into action to perform
        while not self.abortRequested():
            chunk = self.decode_str(self.sock_kodi.recv(1))
            sock_buffer += chunk
            if chunk in '{}':
                if '{' == chunk:
                    depth += 1
                else:
                    depth -= 1
                    if not depth:
                        json_msg = json.loads(sock_buffer)
                        try:
                            method = json_msg.get('method')
                            method_handler = methods[method]
                            method_handler(json_msg)
                        except KeyError:
                            if 'System.OnQuit' == method:
                                break
                            if __dev__:
                                self.log(f'pass on event: {json_msg.get("method")}')

                        sock_buffer = ''

        self.sock_kodi.close()
        del self.kodi_events
        self.log('Stopped')

    def get_setting(self, name):
        """
        Return value of an Add-on setting as String

        :param name: id of Addon setting
        :type name: AnyStr
        :return: Success as setting string
        :rtype: AnyStr
        """
        # return self.addon.getSettings().getString(name) # for v10 when they fix the bug
        return self.addon.getSetting(name)

    def is_enabled(self, name):
        """
        Return state of an Add-on setting as Boolean

        :param name: id of Addon setting
        :type name: String
        :return: Success as True if addon setting is enabled, else False
        :rtype: Bool
        """
        # return self.addon.getSettings().getBool(name) # for v10 when they fix the bug
        return 'true' == self.addon.getSetting(name)

    def log(self, msg, error=False):
        """
        Add a message to the Kodi logging system (provided setting allows it)

        :param msg: Text to add to log file
        :type msg: String
        :param error: Specify whether text indicates an error or action
        :type error: Boolean
        :return:
        :rtype:
        """
        if self.is_enabled('verbose_log'):
            xbmc.log(f'[{self.addon_name}]:: {msg}', (xbmc.LOGINFO, xbmc.LOGERROR)[error])

    def notify(self, msg, period=4, error=None):
        """
        Invoke the Kodi onscreen notification panel with a message (provided setting allows it)

        :param msg: Text to display in panel
        :type msg: String
        :param period: Wait seconds before closing dialog
        :type period: Integer
        :param error: Specify whether text indicates an error or action
        :type error: Boolean
        :return:
        :rtype:
        """
        if not error and self.is_enabled('action_notification') or (error and self.is_enabled('error_notification')):
            xbmc.executebuiltin(f'Notification({self.addon_name}, "{msg}", {1000 * period}, '
                                f'{((self.green_logo, self.red_logo)[any([error])], self.black_logo)[None is error]})')

    @staticmethod
    def make_path(path_parts):
        # #type: List[AnyStr] -> AnyStr
        return xbmcvfs.translatePath(path.join(*path_parts))

    @staticmethod
    def ex(e):
        return '\n'.join(['\nEXCEPTION Raised: --> Python callback/script returned the following error <--',
                          'Error type: <type \'{0}\'>',
                          'Error content: {1!r}',
                          '{2}',
                          '--> End of Python script error report <--\n'
                          ]).format(type(e).__name__, e.args, traceback.format_exc())

    def report_contact_fail(self, e):
        msg = f'Failed to contact Kodi at {self.kodi_ip}:{self.kodi_port}'
        self.log(f'{msg} {self.ex(e)}', error=True)
        self.notify(msg, period=20, error=True)

    def kodi_request(self, params):
        params.update(dict(jsonrpc='2.0', id='SickGear'))
        try:
            response = xbmc.executeJSONRPC(json.dumps(params))
        except (BaseException, Exception) as e:
            return self.report_contact_fail(e)
        return json.loads(response)

    def video_library_on_update(self, json_msg):
        """
        Actions to perform for: Kodi Notifications / VideoLibrary / VideoLibrary.OnUpdate
        invoked in Kodi when: A video item has been updated
        source: https://kodi.wiki/view/JSON-RPC_API/v8#VideoLibrary.OnUpdate

        :param json_msg: A JSON parsed from socks
        :type json_msg: String
        :return:
        :rtype:
        """
        try:
            # note: this is called multiple times when a season is marked as un-/watched
            if 'episode' == json_msg['params']['data']['item']['type']:
                media_id = json_msg['params']['data']['item']['id']
                play_count = json_msg['params']['data']['playcount']

                json_resp = self.kodi_request(dict(
                    method='Profiles.GetCurrentProfile'))
                current_profile = json_resp['result']['label']

                json_resp = self.kodi_request(dict(
                    method='VideoLibrary.GetEpisodeDetails',
                    params=dict(episodeid=media_id, properties=['file'])))
                path_file = self.decode_str(json_resp['result']['episodedetails']['file'])

                self.update_sickgear(media_id, path_file, play_count, current_profile)
        except (BaseException, Exception):
            pass

    def update_sickgear(self, media_id, path_file, play_count, profile):

        self.notify('Update sent to SickGear')

        file_name = 'sickgear_extra.txt'
        data_extra = self.load_json(file_name)
        scheme = data_extra.get('scheme', 'http')

        url = f'{scheme}://{self.get_setting("sickgear_ip")}:{self.get_setting("sickgear_port")}/' \
              'update-watched-state-kodi/'
        self.log(f'Notify state to {url} with path_file={path_file}')

        msg_bad = f'Failed to contact SickGear on port ' \
                  f'{self.get_setting("sickgear_port")} at {self.get_setting("sickgear_ip")}'

        payload_json = self.payload_prep(dict(media_id=media_id, path_file=path_file, played=play_count, label=profile))
        if payload_json:
            payload = urlencode(dict(payload=payload_json, version=ADDON_VERSION))
            r = None
            change_scheme = False
            try:
                rq = Request(url, data=self.decode_bytes(payload))
                param = ({'context': _create_unverified_context()}, {})[url.startswith('http:')]
                r = urlopen(rq, **param)
            except (BaseException, Exception):
                change_scheme = True

            try:
                if change_scheme:
                    old_scheme, scheme = 'http', 'https'
                    if url.startswith('https'):
                        old_scheme, scheme = 'https', 'http'
                    url = url.replace(old_scheme, scheme)

                    self.log(f'Change scheme, notify state to {url}')

                    rq = Request(url, data=self.decode_bytes(payload))
                    param = ({'context': _create_unverified_context()}, {})[url.startswith('http:')]
                    r = urlopen(rq, **param)

                response = json.load(r)
                r.close()
                if 'OK' == r.msg:
                    if change_scheme:
                        data_extra['scheme'] = scheme
                        output = json.dumps(data_extra)
                        self.save_json(file_name, output)

                    self.payload_prep(response)
                    if not all(iter(response.values())):
                        msg = 'Success, watched state updated'
                    else:
                        msg = f'Success, {len([None for v in iter(response.values()) if v])}' \
                              f'/{len([None for _ in iter(response.values())])} watched stated updated'
                    self.log(msg)
                    self.notify(msg, error=False)
                else:
                    msg_bad = 'Failed to update watched state'
                    self.log(msg_bad)
                    self.notify(msg_bad, error=True)
            except (BaseException, Exception) as e:
                self.log(f'Couldn\'t contact SickGear {self.ex(e)}', error=True)
                self.notify(msg_bad, error=True, period=15)

    def load_json(self, file_name):
        result = {}

        file_path = self.make_path([self.path_addon_data, file_name])
        if xbmcvfs.exists(file_path):
            try:
                with xbmcvfs.File(file_path) as fh:
                    result = json.load(fh)
            except (BaseException, Exception):
                pass

        return result

    def save_json(self, file_name, data):
        temp_ok = xbmcvfs.exists(self.path_addon_data) or xbmcvfs.exists(self.make_path([self.path_addon_data, '']))
        if not temp_ok:
            temp_ok = xbmcvfs.mkdirs(self.path_addon_data)

        if temp_ok:
            try:
                with xbmcvfs.File(self.make_path([self.path_addon_data, file_name]), 'w') as fh:
                    fh.write(data)
            except (BaseException, Exception):
                pass

    def payload_prep(self, payload):
        # type: (dict) -> str

        file_name = 'sickgear_buffer.txt'

        data_pool = self.load_json(file_name)

        response_data = False
        for k, v in iter(payload.items()):
            if response_data or k in data_pool:
                response_data = True
                if not v:
                    # whether no fail response or bad input, remove this from data
                    data_pool.pop(k)
                elif isinstance(v, str):
                    # error so retry next time
                    continue
        if not response_data:
            ts_now = time.mktime(datetime.datetime.now().timetuple())
            timeout = 100
            while ts_now in data_pool and timeout:
                ts_now = time.mktime(datetime.datetime.now().timetuple())
                timeout -= 1

            max_payload = 50-1
            for k in list(iter(data_pool.keys()))[max_payload:]:
                data_pool.pop(k)
            payload.update(dict(date_watched=ts_now))
            data_pool.update({ts_now: payload})

        output = json.dumps(data_pool)
        self.save_json(file_name, output)

        return output

    def enable_kodi_allow_remote(self):
        try:
            # setting esenabled: allow remote control by programs on this system
            # setting esallinterfaces: allow remote control by programs on other systems
            settings = [dict(esenabled=True), dict(esallinterfaces=True)]
            for setting in settings:
                name = next(iter(setting.keys()))
                if not self.kodi_request(dict(
                        method='Settings.SetSettingValue',
                        params=dict(setting=f'services.{name}', value=next(iter(setting.values())))
                )).get('result', {}):
                    settings[setting] = self.kodi_request(dict(
                        method='Settings.GetSettingValue',
                        params=dict(setting=f'services.{name}')
                    )).get('result', {}).get('value')
        except (BaseException, Exception):
            return

        setting_states = [next(iter(setting.values())) for setting in settings]
        if not all(setting_states):
            if not (any(setting_states)):
                msg = 'Please enable *all* Kodi settings to allow remote control by programs...'
            else:
                msg = 'Please enable Kodi setting to allow remote control by programs on other systems'
            msg = f'Failed startup. {msg} in system service/remote control'
            self.log(msg, error=True)
            self.notify(msg, period=20, error=True)
            return
        return True

    @staticmethod
    def decode_bytes(d, encoding='utf-8', errors='replace'):
        if not isinstance(d, bytes):
            return bytes(d, encoding=encoding, errors=errors)
        return d

    @staticmethod
    def decode_str(s, encoding='utf-8', errors=None):
        if isinstance(s, bytes):
            if None is errors:
                return s.decode(encoding)
            return s.decode(encoding, errors)
        return s


__dev__ = True
if __dev__:
    try:
        # specific to a dev env
        # noinspection PyProtectedMember, PyUnresolvedReferences
        import _devenv as devenv
    except ImportError:
        __dev__ = False


if 1 < len(sys.argv):
    if __dev__:
        devenv.setup_devenv(False)
    if 3 <= len(sys.argv) and sys.argv[2].endswith('send_all'):
        print('>>>>>> TESTTESTTEST')

elif '__main__' == __name__:
    if __dev__:
        devenv.setup_devenv(True)
    WSU = SickGearWatchedStateUpdater()
    WSU.run()
    del WSU

if __dev__:
    devenv.stop()
