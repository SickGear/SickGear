# coding=utf-8
#
#  This file is part of SickGear.
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

try:
    import json as json
except (BaseException, Exception):
    import simplejson as json
from os import path, sep
import datetime
import socket
import sys
import time
import traceback

# these are Kodi specific libs, so block the error reports in pycharm
# noinspection PyUnresolvedReferences
import xbmc
# noinspection PyUnresolvedReferences
import xbmcaddon
# noinspection PyUnresolvedReferences
import xbmcgui
# noinspection PyUnresolvedReferences
import xbmcvfs

ADDON_VERSION = '1.0.7'

PY2 = 2 == sys.version_info[0]

if PY2:
    # noinspection PyCompatibility,PyUnresolvedReferences
    from urllib2 import Request, urlopen, URLError
    # noinspection PyUnresolvedReferences
    from urllib import urlencode

    # noinspection PyCompatibility,PyUnresolvedReferences
    string_types = (basestring,)
    binary_type = str

    def iterkeys(d, **kw):
        # noinspection PyCompatibility
        return d.iterkeys(**kw)

    def itervalues(d, **kw):
        # noinspection PyCompatibility
        return d.itervalues(**kw)

    def iteritems(d, **kw):
        # noinspection PyCompatibility
        return d.iteritems(**kw)

    # noinspection PyUnusedLocal
    def decode_bytes(d, **kw):
        if not isinstance(d, binary_type):
            return bytes(d)
        return d

else:
    # noinspection PyCompatibility,PyUnresolvedReferences
    from urllib.error import URLError
    # noinspection PyCompatibility,PyUnresolvedReferences
    from urllib.parse import urlencode
    # noinspection PyCompatibility,PyUnresolvedReferences
    from urllib.request import Request, urlopen

    string_types = (str,)
    binary_type = bytes

    def iterkeys(d, **kw):
        return iter(d.keys(**kw))

    def itervalues(d, **kw):
        return iter(d.values(**kw))

    def iteritems(d, **kw):
        return iter(d.items(**kw))

    def decode_bytes(d, encoding='utf-8', errors='replace'):
        if not isinstance(d, binary_type):
            # noinspection PyArgumentList
            return bytes(d, encoding=encoding, errors=errors)
        return d


def decode_str(s, encoding='utf-8', errors=None):
    if isinstance(s, binary_type):
        if None is errors:
            return s.decode(encoding)
        return s.decode(encoding, errors)
    return s


class SickGearWatchedStateUpdater(object):

    def __init__(self):
        self.wait_onstartup = 4000

        icon_size = '%s'
        try:
            if 1350 > xbmcgui.Window.getWidth(xbmcgui.Window()):
                icon_size += '-sm'
        except (BaseException, Exception):
            pass
        icon = 'special://home/addons/service.sickgear.watchedstate.updater/resources/icon-%s.png' % icon_size

        self.addon = xbmcaddon.Addon()
        self.red_logo = icon % 'red'
        self.green_logo = icon % 'green'
        self.black_logo = icon % 'black'
        self.addon_name = self.addon.getAddonInfo('name')
        self.kodi_ip = self.addon.getSetting('kodi_ip')
        self.kodi_port = int(self.addon.getSetting('kodi_port'))

        self.kodi_events = None
        self.sock_kodi = None

    def run(self):
        """
        Main start

        :return:
        :rtype:
        """

        if not self.enable_kodi_allow_remote():
            return

        self.sock_kodi = socket.socket()
        self.sock_kodi.setblocking(True)
        xbmc.sleep(self.wait_onstartup)
        try:
            self.sock_kodi.connect((self.kodi_ip, self.kodi_port))
        except (BaseException, Exception) as e:
            return self.report_contact_fail(e)

        self.log('Started')
        self.notify('Started in background')

        cache_pkg = 'special://home/addons/packages/service.sickgear.watchedstate.updater-%s.zip' % ADDON_VERSION
        if xbmcvfs.exists(cache_pkg):
            try:
                xbmcvfs.delete(cache_pkg)
            except (BaseException, Exception):
                pass

        self.kodi_events = xbmc.Monitor()

        sock_buffer, depth, methods, method = '', 0, {'VideoLibrary.OnUpdate': self.video_library_on_update}, None

        # socks listener parsing Kodi json output into action to perform
        while not self.kodi_events.abortRequested():
            chunk = decode_str(self.sock_kodi.recv(1))
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
                                self.log('pass on event: %s' % json_msg.get('method'))

                        sock_buffer = ''

        self.sock_kodi.close()
        del self.kodi_events
        self.log('Stopped')

    def is_enabled(self, name):
        """
        Return state of an Add-on setting as Boolean

        :param name: Name of Addon setting
        :type name: String
        :return: Success as True if addon setting is enabled, else False
        :rtype: Bool
        """
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
            xbmc.log('[%s]:: %s' % (self.addon_name, msg), (xbmc.LOGNOTICE, xbmc.LOGERROR)[error])

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
            xbmc.executebuiltin('Notification(%s, "%s", %s, %s)' % (
                self.addon_name, msg, 1000 * period,
                ((self.green_logo, self.red_logo)[any([error])], self.black_logo)[None is error]))

    @staticmethod
    def ex(e):
        return '\n'.join(['\nEXCEPTION Raised: --> Python callback/script returned the following error <--',
                          'Error type: <type \'{0}\'>',
                          'Error content: {1!r}',
                          '{2}',
                          '--> End of Python script error report <--\n'
                          ]).format(type(e).__name__, e.args, traceback.format_exc())

    def report_contact_fail(self, e):
        msg = 'Failed to contact Kodi at %s:%s' % (self.kodi_ip, self.kodi_port)
        self.log('%s %s' % (msg, self.ex(e)), error=True)
        self.notify(msg, period=20, error=True)

    def kodi_request(self, params):
        params.update(dict(jsonrpc='2.0', id='SickGear'))
        try:
            response = xbmc.executeJSONRPC(json.dumps(params))
        except (BaseException, Exception) as e:
            return self.report_contact_fail(e)
        try:
            return json.loads(response)
        except UnicodeDecodeError:
            return json.loads(response.decode('utf-8', 'ignore'))

    def video_library_on_update(self, json_msg):
        """
        Actions to perform for: Kodi Notifications / VideoLibrary / VideoLibrary.OnUpdate
        invoked in Kodi when: A video item has been updated
        source: http://kodi.wiki/view/JSON-RPC_API/v8#VideoLibrary.OnUpdate

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
                path_file = json_resp['result']['episodedetails']['file'].encode('utf-8')

                self.update_sickgear(media_id, path_file, play_count, current_profile)
        except (BaseException, Exception):
            pass

    def update_sickgear(self, media_id, path_file, play_count, profile):

        self.notify('Update sent to SickGear')

        url = 'http://%s:%s/update-watched-state-kodi/' % (
            self.addon.getSetting('sickgear_ip'), self.addon.getSetting('sickgear_port'))
        self.log('Notify state to %s with path_file=%s' % (url, path_file))

        msg_bad = 'Failed to contact SickGear on port %s at %s' % (
            self.addon.getSetting('sickgear_port'), self.addon.getSetting('sickgear_ip'))

        payload_json = self.payload_prep(dict(media_id=media_id, path_file=path_file, played=play_count, label=profile))
        if payload_json:
            payload = urlencode(dict(payload=payload_json, version=ADDON_VERSION))
            try:
                rq = Request(url, data=decode_bytes(payload))
                r = urlopen(rq)
                response = json.load(r)
                r.close()
                if 'OK' == r.msg:
                    self.payload_prep(response)
                    if not all(itervalues(response)):
                        msg = 'Success, watched state updated'
                    else:
                        msg = 'Success, %s/%s watched stated updated' % (
                            len([None for v in itervalues(response) if v]), len([None for _ in itervalues(response)]))
                    self.log(msg)
                    self.notify(msg, error=False)
                else:
                    msg_bad = 'Failed to update watched state'
                    self.log(msg_bad)
                    self.notify(msg_bad, error=True)
            except (URLError, IOError) as e:
                self.log(u'Couldn\'t contact SickGear %s' % self.ex(e), error=True)
                self.notify(msg_bad, error=True, period=15)
            except (BaseException, Exception) as e:
                self.log(u'Couldn\'t contact SickGear %s' % self.ex(e), error=True)
                self.notify(msg_bad, error=True, period=15)

    @staticmethod
    def payload_prep(payload):
        # type: (dict) -> str

        name = 'sickgear_buffer.txt'
        # try to locate /temp at parent location
        path_temp = path.join(path.dirname(path.dirname(path.realpath(__file__))), 'temp')
        path_data = path.join(path_temp, name)

        data_pool = {}
        if xbmcvfs.exists(path_data):
            fh = None
            try:
                fh = xbmcvfs.File(path_data)
                data_pool = json.load(fh)
            except (BaseException, Exception):
                pass
            fh and fh.close()

        temp_ok = True
        if not any([data_pool]):
            temp_ok = xbmcvfs.exists(path_temp) or xbmcvfs.exists(path.join(path_temp, sep))
            if not temp_ok:
                temp_ok = xbmcvfs.mkdirs(path_temp)

        response_data = False
        for k, v in iteritems(payload):
            if response_data or k in data_pool:
                response_data = True
                if not v:
                    # whether no fail response or bad input, remove this from data
                    data_pool.pop(k)
                elif isinstance(v, string_types):
                    # error so retry next time
                    continue
        if not response_data:
            ts_now = time.mktime(datetime.datetime.now().timetuple())
            timeout = 100
            while ts_now in data_pool and timeout:
                ts_now = time.mktime(datetime.datetime.now().timetuple())
                timeout -= 1

            max_payload = 50-1
            for k in list(iterkeys(data_pool))[max_payload:]:
                data_pool.pop(k)
            payload.update(dict(date_watched=ts_now))
            data_pool.update({ts_now: payload})

        output = json.dumps(data_pool)
        if temp_ok:
            fh = None
            try:
                fh = xbmcvfs.File(path_data, 'w')
                fh.write(output)
            except (BaseException, Exception):
                pass
            fh and fh.close()

        return output

    def enable_kodi_allow_remote(self):
        try:
            # setting esenabled: allow remote control by programs on this system
            # setting esallinterfaces: allow remote control by programs on other systems
            settings = [dict(esenabled=True), dict(esallinterfaces=True)]
            for setting in settings:
                name = next(iterkeys(setting))
                if not self.kodi_request(dict(
                        method='Settings.SetSettingValue',
                        params=dict(setting='services.%s' % name, value=next(itervalues(setting)))
                )).get('result', {}):
                    settings[setting] = self.kodi_request(dict(
                        method='Settings.GetSettingValue',
                        params=dict(setting='services.%s' % name)
                    )).get('result', {}).get('value')
        except (BaseException, Exception):
            return

        setting_states = [next(itervalues(setting)) for setting in settings]
        if not all(setting_states):
            if not (any(setting_states)):
                msg = 'Please enable *all* Kodi settings to allow remote control by programs...'
            else:
                msg = 'Please enable Kodi setting to allow remote control by programs on other systems'
            msg = 'Failed startup. %s in system service/remote control' % msg
            self.log(msg, error=True)
            self.notify(msg, period=20, error=True)
            return
        return True


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
    if sys.argv[2].endswith('send_all'):
        print('>>>>>> TESTTESTTEST')

elif '__main__' == __name__:
    if __dev__:
        devenv.setup_devenv(True)
    WSU = SickGearWatchedStateUpdater()
    WSU.run()
    del WSU

if __dev__:
    devenv.stop()
