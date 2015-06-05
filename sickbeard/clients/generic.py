import re
import time
from hashlib import sha1
from base64 import b16encode, b32decode

import sickbeard
from sickbeard import logger
from sickbeard.exceptions import ex
from sickbeard.clients import http_error_code
from lib.bencode import bencode, bdecode
from lib import requests


class GenericClient(object):
    def __init__(self, name, host=None, username=None, password=None):

        self.name = name
        self.username = sickbeard.TORRENT_USERNAME if username is None else username
        self.password = sickbeard.TORRENT_PASSWORD if password is None else password
        self.host = sickbeard.TORRENT_HOST if host is None else host

        self.url = None
        self.auth = None
        self.last_time = time.time()
        self.session = requests.session()
        self.session.auth = (self.username, self.password)

    def _request(self, method='get', params={}, data=None, files=None):
        response = None
        if time.time() > self.last_time + 1800 or not self.auth:
            self.last_time = time.time()
            self._get_auth()

        logger.log(
            self.name + u': Requested a ' + method.upper() +
            ' connection to url ' + self.url + ' with Params= ' + str(params) +
            ' Data=' + str(data if data else 'None')[0:99] +
            ('...' if len(data if data else 'None') > 200 else ''),
            logger.DEBUG
        )

        logger.log(
            self.name + u': Requested a ' + method.upper() +
            ' connection to url ' + self.url + ' with Params= ' + str(params) +
            ((' Data=' + str(data)[0:100] + ('...' if len(data) > 100 else ''))
             if data is not None else ''),
            logger.DEBUG
        )

        if not self.auth:
            logger.log(self.name + u': Authentication Failed', logger.ERROR)
            return False
        try:
            response = self.session.__getattribute__(method)(self.url, params=params, data=data, files=files,
                                                                  timeout=120, verify=False)
        except requests.exceptions.ConnectionError as e:
            logger.log(self.name + u': Unable to connect ' + ex(e), logger.ERROR)
            return False
        except (requests.exceptions.MissingSchema, requests.exceptions.InvalidURL):
            logger.log(self.name + u': Invalid Host', logger.ERROR)
            return False
        except requests.exceptions.HTTPError as e:
            logger.log(self.name + u': Invalid HTTP Request ' + ex(e), logger.ERROR)
            return False
        except requests.exceptions.Timeout as e:
            logger.log(self.name + u': Connection Timeout ' + ex(e), logger.ERROR)
            return False
        except Exception as e:
            logger.log(self.name + u': Unknown exception raised when sending torrent to ' + self.name + ': ' + ex(e),
                       logger.ERROR)
            return False

        if response.status_code == 401:
            logger.log(self.name + u': Invalid Username or Password, check your config', logger.ERROR)
            return False

        if response.status_code in http_error_code.keys():
            logger.log(self.name + u': ' + http_error_code[response.status_code], logger.DEBUG)
            return False

        logger.log(self.name + u': Response to ' + method.upper() + ' request is ' + response.text, logger.DEBUG)

        return response

    def _get_auth(self):
        '''
        This should be overridden and should return the auth_id needed for the client
        '''
        return None

    def _add_torrent_uri(self, result):
        '''
        This should be overridden should return the True/False from the client
        when a torrent is added via url (magnet or .torrent link)
        '''
        return False

    def _add_torrent_file(self, result):
        '''
        This should be overridden should return the True/False from the client
        when a torrent is added via result.content (only .torrent file)
        '''
        return False

    def _set_torrent_label(self, result):
        '''
        This should be overridden should return the True/False from the client
        when a torrent is set with label
        '''
        return True

    def _set_torrent_ratio(self, result):
        '''
        This should be overridden should return the True/False from the client
        when a torrent is set with ratio
        '''
        return True

    def _set_torrent_seed_time(self, result):
        '''
        This should be overridden should return the True/False from the client
        when a torrent is set with a seed time
        '''
        return True

    def _set_torrent_priority(self, result):
        '''
        This should be overriden should return the True/False from the client
        when a torrent is set with result.priority (-1 = low, 0 = normal, 1 = high)
        '''
        return True

    def _set_torrent_path(self, torrent_path):
        '''
        This should be overridden should return the True/False from the client
        when a torrent is set with path
        '''
        return True

    def _set_torrent_pause(self, result):
        '''
        This should be overridden should return the True/False from the client
        when a torrent is set with pause
        '''
        return True

    def _get_torrent_hash(self, result):

        if result.url.startswith('magnet'):
            result.hash = re.findall('urn:btih:([\w]{32,40})', result.url)[0]
            if len(result.hash) == 32:
                result.hash = b16encode(b32decode(result.hash)).lower()
        else:
            info = bdecode(result.content)['info']
            result.hash = sha1(bencode(info)).hexdigest()

        return result

    def sendTORRENT(self, result):

        r_code = False

        logger.log(u'Calling ' + self.name + ' Client', logger.DEBUG)

        if not self._get_auth():
            logger.log(self.name + u': Authentication Failed', logger.ERROR)
            return r_code

        try:
            # Sets per provider seed ratio
            result.ratio = result.provider.seedRatio()

            result = self._get_torrent_hash(result)

            if result.url.startswith('magnet'):
                r_code = self._add_torrent_uri(result)
            else:
                r_code = self._add_torrent_file(result)

            if not r_code:
                logger.log(self.name + u': Unable to send Torrent: Return code undefined', logger.ERROR)
                return False

            if not self._set_torrent_pause(result):
                logger.log(self.name + u': Unable to set the pause for Torrent', logger.ERROR)

            if not self._set_torrent_label(result):
                logger.log(self.name + u': Unable to set the label for Torrent', logger.ERROR)

            if not self._set_torrent_ratio(result):
                logger.log(self.name + u': Unable to set the ratio for Torrent', logger.ERROR)

            if not self._set_torrent_seed_time(result):
                logger.log(self.name + u': Unable to set the seed time for Torrent', logger.ERROR)

            if not self._set_torrent_path(result):
                logger.log(self.name + u': Unable to set the path for Torrent', logger.ERROR)

            if result.priority != 0 and not self._set_torrent_priority(result):
                logger.log(self.name + u': Unable to set priority for Torrent', logger.ERROR)

        except Exception as e:
            logger.log(self.name + u': Failed Sending Torrent: ' + result.name + ' - ' + result.hash, logger.ERROR)
            logger.log(self.name + u': Exception raised when sending torrent: ' + ex(e), logger.DEBUG)
            return r_code

        return r_code

    def testAuthentication(self):
        response = None
        try:
            response = self.session.get(self.url, timeout=120, verify=False)

            if response.status_code == 401:
                return False, 'Error: Invalid ' + self.name + ' Username or Password, check your config!'
        except requests.exceptions.ConnectionError:
            return False, 'Error: ' + self.name + ' Connection Error'
        except (requests.exceptions.MissingSchema, requests.exceptions.InvalidURL):
            return False, 'Error: Invalid ' + self.name + ' host'

        try:
            authenticated = self._get_auth()
            # FIXME: This test is redundant
            if authenticated and self.auth:
                return True, 'Success: Connected and Authenticated'
            else:
                return False, 'Error: Unable to get ' + self.name + ' Authentication, check your config!'
        except Exception:
            return False, 'Error: Unable to connect to ' + self.name
