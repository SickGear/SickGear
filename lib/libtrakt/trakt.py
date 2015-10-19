import requests
import certifi
import json
import sickbeard
import time
from sickbeard import logger

from exceptions import traktException, traktAuthException  # , traktServerBusy


class TraktAPI:

    def __init__(self, ssl_verify=True, timeout=None):

        self.session = requests.Session()
        self.verify = ssl_verify and sickbeard.TRAKT_VERIFY and certifi.where()
        self.timeout = timeout or sickbeard.TRAKT_TIMEOUT
        self.auth_url = sickbeard.TRAKT_BASE_URL
        self.api_url = sickbeard.TRAKT_BASE_URL
        self.headers = {
            'Content-Type': 'application/json',
            'trakt-api-version': '2',
            'trakt-api-key': sickbeard.TRAKT_CLIENT_ID
        }

    def trakt_token(self, trakt_pin=None, refresh=False, count=0):
   
        if 3 <= count:
            sickbeard.TRAKT_ACCESS_TOKEN = ''
            return False
        elif 0 < count:
            time.sleep(3)

        data = {
            'client_id': sickbeard.TRAKT_CLIENT_ID,
            'client_secret': sickbeard.TRAKT_CLIENT_SECRET,
            'redirect_uri': 'urn:ietf:wg:oauth:2.0:oob'
        }

        if refresh:
            data['grant_type'] = 'refresh_token'
            data['refresh_token'] = sickbeard.TRAKT_REFRESH_TOKEN
        else:
            data['grant_type'] = 'authorization_code'
            if trakt_pin:
                data['code'] = trakt_pin

        headers = {
            'Content-Type': 'application/json'
        }

        resp = self.trakt_request('oauth/token', data=data, headers=headers, url=self.auth_url, method='POST', count=count)

        if 'access_token' in resp:
            sickbeard.TRAKT_TOKEN = resp['access_token']
            if 'refresh_token' in resp:
                sickbeard.TRAKT_REFRESH_TOKEN = resp['refresh_token']
            return True
        return False

    def validate_account(self):

        resp = self.trakt_request('users/settings')

        return 'account' in resp

    def get_connected_user(self):

        if sickbeard.TRAKT_TOKEN:
            response = 'Connected to Trakt user account: %s'

            if sickbeard.TRAKT_CONNECTED_ACCOUNT and sickbeard.TRAKT_TOKEN == sickbeard.TRAKT_CONNECTED_ACCOUNT[1] and sickbeard.TRAKT_CONNECTED_ACCOUNT[0]:
                return response % sickbeard.TRAKT_CONNECTED_ACCOUNT[0]

            resp = self.trakt_request('users/settings')
            if 'user' in resp:
                sickbeard.TRAKT_CONNECTED_ACCOUNT = [resp['user']['username'], sickbeard.TRAKT_TOKEN]
                return response % sickbeard.TRAKT_CONNECTED_ACCOUNT[0]

        return 'Not connected to Trakt'

    def trakt_request(self, path, data=None, headers=None, url=None, method='GET', count=0):

        if None is sickbeard.TRAKT_TOKEN:
            logger.log(u'You must get a Trakt token. Check your Trakt settings', logger.WARNING)
            return {}

        headers = headers or self.headers
        url = url or self.api_url
        count += 1

        headers['Authorization'] = 'Bearer ' + sickbeard.TRAKT_TOKEN

        try:
            resp = self.session.request(method, url + path, headers=headers, timeout=self.timeout,
                                        data=json.dumps(data) if data else [], verify=self.verify)

            # check for http errors and raise if any are present
            resp.raise_for_status()

            # convert response to json
            resp = resp.json()
        except requests.RequestException as e:
            code = getattr(e.response, 'status_code', None)
            if not code:
                if 'timed out' in e:
                    logger.log(u'Timeout connecting to Trakt. Try to increase timeout value in Trakt settings', logger.WARNING)                      
                # This is pretty much a fatal error if there is no status_code
                # It means there basically was no response at all                    
                else:
                    logger.log(u'Could not connect to Trakt. Error: {0}'.format(e), logger.WARNING)                
            elif 502 == code:
                # Retry the request, Cloudflare had a proxying issue
                logger.log(u'Retrying trakt api request: %s' % path, logger.WARNING)
                return self.trakt_request(path, data, headers, url, method, count=count)
            elif 401 == code:
                if self.trakt_token(refresh=True, count=count):
                    sickbeard.save_config()
                    return self.trakt_request(path, data, headers, url, method, count=count)
                else:
                    logger.log(u'Unauthorized. Please check your Trakt settings', logger.WARNING)
                    raise traktAuthException()
            elif code in (500, 501, 503, 504, 520, 521, 522):
                # http://docs.trakt.apiary.io/#introduction/status-codes
                logger.log(u'Trakt may have some issues and it\'s unavailable. Try again later please', logger.WARNING)
            elif 404 == code:
                logger.log(u'Trakt error (404) the resource does not exist: %s' % url + path, logger.WARNING)
            else:
                logger.log(u'Could not connect to Trakt. Code error: {0}'.format(code), logger.ERROR)
            return {}

        # check and confirm Trakt call did not fail
        if isinstance(resp, dict) and 'failure' == resp.get('status', None):
            if 'message' in resp:
                raise traktException(resp['message'])
            if 'error' in resp:
                raise traktException(resp['error'])
            else:
                raise traktException('Unknown Error')

        return resp
