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

    def _request(self, method='get', params=None, data=None, files=None, **kwargs):

        params = params or {}

        if time.time() > self.last_time + 1800 or not self.auth:
            self.last_time = time.time()
            self._get_auth()

        logger.log('%s: sending %s request to %s with ...' % (self.name, method.upper(), self.url), logger.DEBUG)
        lines = [('params', (str(params), '')[not params]),
                 ('data', (str(data), '')[not data]),
                 ('files', (str(files), '')[not files]),
                 ('json', (str(kwargs.get('json')), '')[not kwargs.get('json')])]
        m, c = 300, 100
        type_chunks = [(linetype, [ln[i:i + c] for i in range(0, min(len(ln), m), c)]) for linetype, ln in lines if ln]
        for (arg, chunks) in type_chunks:
            output = []
            nch = len(chunks) - 1
            for i, seg in enumerate(chunks):
                if nch == i and 'files' == arg:
                    sample = ' ..excerpt(%s/%s)' % (m, len(lines[2][1]))
                    seg = seg[0:c - (len(sample) - 2)] + sample
                output += ['%s: request %s= %s%s%s' % (self.name, arg, ('', '..')[bool(i)], seg, ('', '..')[i != nch])]
            for out in output:
                logger.log(out, logger.DEBUG)

        if not self.auth:
            logger.log('%s: Authentication Failed' % self.name, logger.ERROR)
            return False
        try:
            response = self.session.__getattribute__(method)(self.url, params=params, data=data, files=files,
                                                             timeout=kwargs.pop('timeout', 120), verify=False, **kwargs)
        except requests.exceptions.ConnectionError as e:
            logger.log('%s: Unable to connect %s' % (self.name, ex(e)), logger.ERROR)
            return False
        except (requests.exceptions.MissingSchema, requests.exceptions.InvalidURL):
            logger.log('%s: Invalid Host' % self.name, logger.ERROR)
            return False
        except requests.exceptions.HTTPError as e:
            logger.log('%s: Invalid HTTP Request %s' % (self.name, ex(e)), logger.ERROR)
            return False
        except requests.exceptions.Timeout as e:
            logger.log('%s: Connection Timeout %s' % (self.name, ex(e)), logger.ERROR)
            return False
        except Exception as e:
            logger.log('%s: Unknown exception raised when sending torrent to %s: %s' % (self.name, self.name, ex(e)),
                       logger.ERROR)
            return False

        if 401 == response.status_code:
            logger.log('%s: Invalid Username or Password, check your config' % self.name, logger.ERROR)
            return False

        if response.status_code in http_error_code.keys():
            logger.log('%s: %s' % (self.name, http_error_code[response.status_code]), logger.DEBUG)
            return False

        logger.log('%s: Response to %s request is %s' % (self.name, method.upper(), response.text), logger.DEBUG)

        return response

    def _get_auth(self):
        """
        This should be overridden and should return the auth_id needed for the client
        """
        return None

    def _add_torrent_uri(self, result):
        """
        This should be overridden should return the True/False from the client
        when a torrent is added via url (magnet or .torrent link)
        """
        return False

    def _add_torrent_file(self, result):
        """
        This should be overridden should return the True/False from the client
        when a torrent is added via result.content (only .torrent file)
        """
        return False

    def _set_torrent_label(self, result):
        """
        This should be overridden should return the True/False from the client
        when a torrent is set with label
        """
        return True

    def _set_torrent_ratio(self, result):
        """
        This should be overridden should return the True/False from the client
        when a torrent is set with ratio
        """
        return True

    def _set_torrent_seed_time(self, result):
        """
        This should be overridden should return the True/False from the client
        when a torrent is set with a seed time
        """
        return True

    def _set_torrent_priority(self, result):
        """
        This should be overriden should return the True/False from the client
        when a torrent is set with result.priority (-1 = low, 0 = normal, 1 = high)
        """
        return True

    def _set_torrent_path(self, torrent_path):
        """
        This should be overridden should return the True/False from the client
        when a torrent is set with path
        """
        return True

    def _set_torrent_pause(self, result):
        """
        This should be overridden should return the True/False from the client
        when a torrent is set with pause
        """
        return True

    @staticmethod
    def _get_torrent_hash(result):

        if result.url.startswith('magnet'):
            result.hash = re.findall('urn:btih:([\w]{32,40})', result.url)[0]
            if 32 == len(result.hash):
                result.hash = b16encode(b32decode(result.hash)).lower()
        else:
            info = bdecode(result.content)['info']
            result.hash = sha1(bencode(info)).hexdigest()

        return result

    def send_torrent(self, result):

        r_code = False

        logger.log('Calling %s Client' % self.name, logger.DEBUG)

        if not self._get_auth():
            logger.log('%s: Authentication Failed' % self.name, logger.ERROR)
            return r_code

        try:
            # Sets per provider seed ratio
            result.ratio = result.provider.seed_ratio()

            result = self._get_torrent_hash(result)

            if result.url.startswith('magnet'):
                r_code = self._add_torrent_uri(result)
            else:
                r_code = self._add_torrent_file(result)

            if not r_code:
                logger.log('%s: Unable to send Torrent: Return code undefined (already exists in client?)' % self.name, logger.ERROR)
                return False

            if not self._set_torrent_pause(result):
                logger.log('%s: Unable to set the pause for Torrent' % self.name, logger.ERROR)

            if not self._set_torrent_label(result):
                logger.log('%s: Unable to set the label for Torrent' % self.name, logger.ERROR)

            if not self._set_torrent_ratio(result):
                logger.log('%s: Unable to set the ratio for Torrent' % self.name, logger.ERROR)

            if not self._set_torrent_seed_time(result):
                logger.log('%s: Unable to set the seed time for Torrent' % self.name, logger.ERROR)

            if not self._set_torrent_path(result):
                logger.log('%s: Unable to set the path for Torrent' % self.name, logger.ERROR)

            if 0 != result.priority and not self._set_torrent_priority(result):
                logger.log('%s: Unable to set priority for Torrent' % self.name, logger.ERROR)

        except Exception as e:
            logger.log('%s: Failed sending torrent: %s - %s' % (self.name, result.name, result.hash), logger.ERROR)
            logger.log('%s: Exception raised when sending torrent: %s' % (self.name, ex(e)), logger.DEBUG)
            return r_code

        return r_code

    def test_authentication(self):

        try:
            response = self.session.get(self.url, timeout=120, verify=False)

            if 401 == response.status_code:
                return False, 'Error: Invalid %s Username or Password, check your config!' % self.name
        except requests.exceptions.ConnectionError:
            return False, 'Error: %s Connection Error' % self.name
        except (requests.exceptions.MissingSchema, requests.exceptions.InvalidURL):
            return False, 'Error: Invalid %s host' % self.name

        try:
            authenticated = self._get_auth()
            # FIXME: This test is redundant
            if authenticated and self.auth:
                return True, 'Success: Connected and Authenticated'
            return False, 'Error: Unable to get %s authentication, check your config!' % self.name
        except (StandardError, Exception):
            return False, 'Error: Unable to connect to %s' % self.name
