from hashlib import sha1
import re
import time

from . import http_error_code
from .. import logger
import sickgear
from exceptions_helper import ex
from lib.bencode import bencode, bdecode
from lib import requests

from _23 import make_btih
from six import string_types


class GenericClient(object):
    def __init__(self, name, host=None, username=None, password=None):

        self.name = name
        self.username = sickgear.TORRENT_USERNAME if username is None else username
        self.password = sickgear.TORRENT_PASSWORD if password is None else password
        self.host = sickgear.TORRENT_HOST if host is None else f'{host.rstrip("/")}/'

        self.url = None
        self.auth = None
        self.last_time = time.time()
        self.session = requests.session()
        self.session.auth = (self.username, self.password)
        self.created_id = None

    def _log_request_details(self, method, params=None, data=None, files=None, **kwargs):

        output = []
        output += [f'{self.name}: sending {method} request to {self.url}']

        lines = [('params', (str(params), '')[not params]),
                 ('data', (str(data), '')[not data]),
                 ('files', (str(files), '')[not files]),
                 ('post_data', (str(kwargs.get('post_data')), '')[not kwargs.get('post_data')]),
                 ('post_json', (str(kwargs.get('post_json')), '')[not kwargs.get('post_json')]),
                 ('json', (str(kwargs.get('json')), '')[not kwargs.get('json')])]
        m, c = 300, 100
        type_chunks = [(linetype, [ln[i:i + c] for i in range(0, min(len(ln), m), c)]) for linetype, ln in lines if ln]
        if type_chunks:
            output[-1] += ' with ...'
        for (arg, chunks) in type_chunks:
            nch = len(chunks) - 1
            for i, seg in enumerate(chunks):
                if nch == i and 'files' == arg:
                    sample = f' ..excerpt({m}/{len(lines[2][1])})'
                    seg = seg[0:c - (len(sample) - 2)] + sample
                output += [f'{self.name}: request {arg}= {("", "..")[bool(i)]}{seg}{("", "..")[i != nch]}']

        logger.debug(output)

    def _request(self, method='get', params=None, data=None, files=None, **kwargs):

        params = params or {}

        if time.time() > self.last_time + 1800 or not self.auth:
            self.last_time = time.time()

            if not self._get_auth():
                logger.error(f'{self.name}: Authentication failed')
                return False

        # self._log_request_details(method, params, data, files, **kwargs)

        try:
            response = self.session.__getattribute__(method)(self.url, params=params, data=data, files=files,
                                                             timeout=kwargs.pop('timeout', 120), verify=False, **kwargs)
        except requests.exceptions.ConnectionError as e:
            logger.error(f'{self.name}: Unable to connect {ex(e)}')
            return False
        except (requests.exceptions.MissingSchema, requests.exceptions.InvalidURL):
            logger.error(f'{self.name}: Invalid host')
            return False
        except requests.exceptions.HTTPError as e:
            logger.error(f'{self.name}: Invalid HTTP request {ex(e)}')
            return False
        except requests.exceptions.Timeout as e:
            logger.error(f'{self.name}: Connection timeout {ex(e)}')
            return False
        except (BaseException, Exception) as e:
            logger.error(f'{self.name}: Unknown exception raised when sending torrent to {self.name}: {ex(e)}')
            return False

        if 401 == response.status_code:
            logger.error(f'{self.name}: Invalid username or password, check your config')
            return False

        if response.status_code in http_error_code:
            logger.debug(f'{self.name}: {http_error_code[response.status_code]}')
            return False

        logger.debug(f'{self.name}: Response to {method.upper()} request is {response.text}')

        return response

    def _tinf(self, ids=None):
        """
        This should be overridden and return client fetched task information

        :param ids: Optional id(s) to get task info for. None to get all task info
        :type ids: list or None
        :return: Zero or more task object(s) from response
        :rtype: list
        """
        return []

    def _active_state(self, ids=None):
        """
        This should be overridden to fetch state of items, return items that are actually downloading or seeding
        :param ids: Optional id(s) to get state info for. None to get all
        :type ids: list or None
        :return: Zero or more object(s) assigned with state `down`loading or `seed`ing
        :rtype: list
        """
        return []

    def _add_torrent_uri(self, result):
        """
        This should be overridden to return the True/False from the client
        when a torrent is added via url (magnet or .torrent link)
        """
        return False

    def _add_torrent_file(self, result):
        """
        This should be overridden to return the True/False from the client
        when a torrent is added via `result.content` (only .torrent file)
        """
        return False

    def _set_torrent_label(self, result):
        """
        This should be overridden to return the True/False from the client
        when a torrent is set with label
        """
        return True

    def _set_torrent_ratio(self, result):
        """
        This should be overridden to return the True/False from the client
        when a torrent is set with ratio
        """
        return True

    def _set_torrent_seed_time(self, result):
        """
        This should be overridden to return the True/False from the client
        when a torrent is set with a seed time
        """
        return True

    def _set_torrent_priority(self, result):
        """
        This should be overridden to return the True/False from the client
        when a torrent is set with result.priority (-1 = low, 0 = normal, 1 = high)
        """
        return True

    def _set_torrent_path(self, torrent_path):
        """
        This should be overridden to return the True/False from the client
        when a torrent is set with path
        """
        return True

    def _set_torrent_pause(self, result):
        """
        This should be overridden to return the True/False from the client
        when a torrent is set with pause
        """
        return True

    def _resume_torrent(self, ids):
        """
        This should be overridden to resume task(s) in client

        :param ids: ID(s) to act on
        :type ids: list or string
        :return: True if success, ID(s) that could not be resumed, else Falsy if failure
        :rtype: bool or list
        """
        return False

    def _delete_torrent(self, ids):
        """
        This should be overridden to delete task(s) from client
        :param ids: ID(s) to act on
        :type ids: list or string
        :return: True if success, ID(s) that could not be deleted, else Falsy if failure
        :rtype: bool or list
        """
        return False

    @staticmethod
    def _get_torrent_hash(result):

        if result.url.startswith('magnet'):
            result.hash = re.findall(r'urn:btih:(\w{32,40})', result.url)[0]
            if 32 == len(result.hash):
                result.hash = make_btih(result.hash).lower()
        else:
            info = bdecode(result.content)['info']
            result.hash = sha1(bencode(info)).hexdigest()

        return result

    def send_torrent(self, result):

        r_code = False

        logger.debug(f'Calling {self.name} client')

        if not self._get_auth():
            logger.error(f'{self.name}: Authentication failed')
            return r_code

        try:
            # Sets per provider seed ratio
            result.ratio = result.provider.seed_ratio()

            result = self._get_torrent_hash(result)
        except (BaseException, Exception) as e:
            logger.error(f'Bad torrent data: hash is {result.hash} for [{result.name}]')
            logger.debug(f'Exception raised when checking torrent data: {ex(e)}')
            return r_code

        try:
            if result.url.startswith('magnet'):
                r_code = self._add_torrent_uri(result)
            else:
                r_code = self._add_torrent_file(result)

            self.created_id = isinstance(r_code, string_types) and r_code or None
            if not r_code:
                logger.error(f'{self.name}: Unable to send torrent to client')
                return False

            if not self._set_torrent_pause(result):
                logger.error(f'{self.name}: Unable to set the pause for torrent')

            if not self._set_torrent_label(result):
                logger.error(f'{self.name}: Unable to set the label for torrent')

            if not self._set_torrent_ratio(result):
                logger.error(f'{self.name}: Unable to set the ratio for torrent')

            if not self._set_torrent_seed_time(result):
                logger.error(f'{self.name}: Unable to set the seed time for torrent')

            if not self._set_torrent_path(result):
                logger.error(f'{self.name}: Unable to set the path for torrent')

            if 0 != result.priority and not self._set_torrent_priority(result):
                logger.error(f'{self.name}: Unable to set priority for torrent')

        except (BaseException, Exception) as e:
            logger.error(f'{self.name}: Failed sending torrent: {result.name} - {result.hash}')
            logger.debug(f'{self.name}: Exception raised when sending torrent: {ex(e)}')

        return r_code

    def _get_auth(self):
        """
        This may be overridden and should return the auth_id needed for the client
        """
        try:
            response = self.session.get(self.url, timeout=120, verify=False)

            if 401 == response.status_code:
                return False, f'Error: Invalid {self.name} username or password, check your config!'
        except requests.exceptions.ConnectionError:
            return False, f'Error: Connecting to {self.name}'
        except (requests.exceptions.MissingSchema, requests.exceptions.InvalidURL):
            return False, f'Error: Invalid {self.name} host'

    def test_authentication(self):

        try:
            result = self._get_auth()
            if result:
                return ((True, f'Success: Connected and authenticated to {self.name}'),
                        result)[isinstance(result, tuple)]

            failed_msg = f'Error: Failed {self.name} authentication.{getattr(self, "_errmsg", None) or ""}'
        except (BaseException, Exception):
            failed_msg = f'Error: Unable to connect to {self.name}'

        return False, failed_msg
