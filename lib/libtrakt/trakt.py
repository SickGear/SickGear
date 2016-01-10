import requests
import certifi
import json
import sickbeard
import time
import datetime
from sickbeard import logger

from exceptions import TraktException, TraktAuthException  # , TraktServerBusy


class TraktAccount:
    max_auth_fail = 9

    def __init__(self, account_id=None, token='', refresh_token='', auth_fail=0, last_fail=None, token_valid_date=None):
        self.account_id = account_id
        self._name = ''
        self.token = token
        self.refresh_token = refresh_token
        self.auth_fail = auth_fail
        self.last_fail = last_fail
        self.token_valid_date = token_valid_date

    @property
    def name(self):
        if self.token and self.active:
            if not self._name:
                try:
                    resp = TraktAPI().trakt_request('users/settings', send_oauth=self.account_id, sleep_retry=20)
                    self.reset_auth_failure()
                    if 'user' in resp:
                        self._name = resp['user']['username']
                except TraktAuthException:
                    self.inc_auth_failure()
                    self._name = ''
                except TraktException:
                    pass
        else:
            self._name = ''

        return self._name

    def reset_name(self):
        self._name = ''

    @property
    def active(self):
        return self.auth_fail < self.max_auth_fail and self.token

    @property
    def needs_refresh(self):
        return not self.token_valid_date or self.token_valid_date - datetime.datetime.now() < datetime.timedelta(days=3)

    @property
    def token_expired(self):
        return self.token_valid_date and datetime.datetime.now() > self.token_valid_date

    def reset_auth_failure(self):
        if self.auth_fail != 0:
            self.auth_fail = 0
            self.last_fail = None

    def inc_auth_failure(self):
        self.auth_fail += 1
        self.last_fail = datetime.datetime.now()

    def auth_failure(self):
        if self.auth_fail < self.max_auth_fail:
            if self.last_fail:
                time_diff = datetime.datetime.now() - self.last_fail
                if self.auth_fail % 3 == 0:
                    if time_diff > datetime.timedelta(days=1):
                        self.inc_auth_failure()
                        sickbeard.save_config()
                elif time_diff > datetime.timedelta(minutes=15):
                    self.inc_auth_failure()
                    if self.auth_fail == self.max_auth_fail or time_diff > datetime.timedelta(hours=6):
                        sickbeard.save_config()
            else:
                self.inc_auth_failure()


class TraktAPI:
    max_retrys = 3

    def __init__(self, timeout=None):

        self.session = requests.Session()
        self.verify = sickbeard.TRAKT_VERIFY and certifi.where()
        self.timeout = timeout or sickbeard.TRAKT_TIMEOUT
        self.auth_url = sickbeard.TRAKT_BASE_URL
        self.api_url = sickbeard.TRAKT_BASE_URL
        self.headers = {'Content-Type': 'application/json',
                        'trakt-api-version': '2',
                        'trakt-api-key': sickbeard.TRAKT_CLIENT_ID}

    @staticmethod
    def build_config_string(data):
        return '!!!'.join('%s|%s|%s|%s|%s|%s' % (
            value.account_id, value.token, value.refresh_token, value.auth_fail,
            value.last_fail.strftime('%Y%m%d%H%M') if value.last_fail else '0',
            value.token_valid_date.strftime('%Y%m%d%H%M%S') if value.token_valid_date else '0') for (key, value) in data.items())

    @staticmethod
    def read_config_string(data):
        return dict((int(a.split('|')[0]), TraktAccount(
            int(a.split('|')[0]), a.split('|')[1], a.split('|')[2], int(a.split('|')[3]),
            datetime.datetime.strptime(a.split('|')[4], '%Y%m%d%H%M') if a.split('|')[4] != '0' else None,
            datetime.datetime.strptime(a.split('|')[5], '%Y%m%d%H%M%S') if a.split('|')[5] != '0' else None)) for a in data.split('!!!') if data)

    @staticmethod
    def add_account(token, refresh_token, token_valid_date):
        k = max(sickbeard.TRAKT_ACCOUNTS.keys() or [0]) + 1
        sickbeard.TRAKT_ACCOUNTS[k] = TraktAccount(account_id=k, token=token, refresh_token=refresh_token, token_valid_date=token_valid_date)
        sickbeard.save_config()
        return k

    @staticmethod
    def replace_account(account, token, refresh_token, token_valid_date, refresh):
        if account in sickbeard.TRAKT_ACCOUNTS:
            sickbeard.TRAKT_ACCOUNTS[account].token = token
            sickbeard.TRAKT_ACCOUNTS[account].refresh_token = refresh_token
            sickbeard.TRAKT_ACCOUNTS[account].token_valid_date = token_valid_date
            if not refresh:
                sickbeard.TRAKT_ACCOUNTS[account].reset_name()
            sickbeard.TRAKT_ACCOUNTS[account].reset_auth_failure()
            sickbeard.save_config()
            return True
        else:
            return False

    @staticmethod
    def delete_account(account):
        if account in sickbeard.TRAKT_ACCOUNTS:
            sickbeard.TRAKT_ACCOUNTS.pop(account)
            sickbeard.save_config()
            return True
        return False

    def trakt_token(self, trakt_pin=None, refresh=False, count=0, account=None):
        if self.max_retrys <= count:
            return False
        0 < count and time.sleep(3)

        data = {
            'client_id': sickbeard.TRAKT_CLIENT_ID,
            'client_secret': sickbeard.TRAKT_CLIENT_SECRET,
            'redirect_uri': 'urn:ietf:wg:oauth:2.0:oob'
        }

        if refresh:
            if account and account in sickbeard.TRAKT_ACCOUNTS:
                data['grant_type'] = 'refresh_token'
                data['refresh_token'] = sickbeard.TRAKT_ACCOUNTS[account].refresh_token
            else:
                return False
        else:
            data['grant_type'] = 'authorization_code'
            if trakt_pin:
                data['code'] = trakt_pin

        headers = {'Content-Type': 'application/json'}

        try:
            now = datetime.datetime.now()
            resp = self.trakt_request('oauth/token', data=data, headers=headers, url=self.auth_url,
                                      count=count, sleep_retry=0)
        except (TraktAuthException, TraktException):
            return False

        if 'access_token' in resp and 'refresh_token' in resp and 'expires_in' in resp:
            token_valid_date = now + datetime.timedelta(seconds=sickbeard.helpers.tryInt(resp['expires_in']))
            if refresh or (not refresh and account and account in sickbeard.TRAKT_ACCOUNTS):
                return self.replace_account(account, resp['access_token'], resp['refresh_token'], token_valid_date, refresh)
            else:
                return self.add_account(resp['access_token'], resp['refresh_token'], token_valid_date)
        return False

    def trakt_request(self, path, data=None, headers=None, url=None, count=0, sleep_retry=60, send_oauth=None, **kwargs):

        count += 1
        if count > self.max_retrys:
            return {}

        # wait before retry
        count > 1 and time.sleep(sleep_retry)

        headers = headers or self.headers
        if send_oauth and send_oauth in sickbeard.TRAKT_ACCOUNTS:
            if sickbeard.TRAKT_ACCOUNTS[send_oauth].active:
                if sickbeard.TRAKT_ACCOUNTS[send_oauth].needs_refresh:
                    self.trakt_token(refresh=True, count=0, account=send_oauth)
                if sickbeard.TRAKT_ACCOUNTS[send_oauth].token_expired:
                    return {}
                headers['Authorization'] = 'Bearer %s' % sickbeard.TRAKT_ACCOUNTS[send_oauth].token
            else:
                return {}

        kwargs = dict(headers=headers, timeout=self.timeout, verify=self.verify)
        if data:
            kwargs['data'] = json.dumps(data)

        url = url or self.api_url
        try:
            resp = self.session.request(('GET', 'POST')['data' in kwargs.keys()],
                                        url + path, **kwargs)

            # check for http errors and raise if any are present
            resp.raise_for_status()

            # convert response to json
            resp = resp.json()
        except requests.RequestException as e:
            code = getattr(e.response, 'status_code', None)
            if not code:
                if 'timed out' in e:
                    logger.log(u'Timeout connecting to Trakt', logger.WARNING)
                # This is pretty much a fatal error if there is no status_code
                # It means there basically was no response at all                    
                else:
                    logger.log(u'Could not connect to Trakt. Error: {0}'.format(e), logger.WARNING)                
            elif 502 == code:
                # Retry the request, Cloudflare had a proxying issue
                logger.log(u'Retrying Trakt api request: %s' % path, logger.WARNING)
                return self.trakt_request(path, data, headers, url, count=count, sleep_retry=sleep_retry, send_oauth=send_oauth)
            elif 401 == code and path != 'oauth/token':
                if send_oauth:
                    if sickbeard.TRAKT_ACCOUNTS[send_oauth].needs_refresh:
                        if self.trakt_token(refresh=True, count=count, account=send_oauth):
                            return self.trakt_request(path, data, headers, url, count=count, sleep_retry=sleep_retry, send_oauth=send_oauth)
                        else:
                            logger.log(u'Unauthorized. Please check your Trakt settings', logger.WARNING)
                            sickbeard.TRAKT_ACCOUNTS[send_oauth].auth_failure()
                            raise TraktAuthException()
                    else:
                        # sometimes the trakt server sends invalid token error even if it isn't
                        sickbeard.TRAKT_ACCOUNTS[send_oauth].auth_failure()
                        if count >= self.max_retrys:
                            raise TraktAuthException()
                        else:
                            return self.trakt_request(path, data, headers, url, count=count, sleep_retry=sleep_retry, send_oauth=send_oauth)
                else:
                    raise TraktAuthException()
            elif code in (500, 501, 503, 504, 520, 521, 522):
                # http://docs.trakt.apiary.io/#introduction/status-codes
                logger.log(u'Trakt may have some issues and it\'s unavailable. Trying again', logger.WARNING)
                self.trakt_request(path, data, headers, url, count=count, sleep_retry=sleep_retry, send_oauth=send_oauth)
            elif 404 == code:
                logger.log(u'Trakt error (404) the resource does not exist: %s' % url + path, logger.WARNING)
            else:
                logger.log(u'Could not connect to Trakt. Code error: {0}'.format(code), logger.ERROR)
            return {}

        # check and confirm Trakt call did not fail
        if isinstance(resp, dict) and 'failure' == resp.get('status', None):
            if 'message' in resp:
                raise TraktException(resp['message'])
            if 'error' in resp:
                raise TraktException(resp['error'])
            else:
                raise TraktException('Unknown Error')

        if send_oauth and send_oauth in sickbeard.TRAKT_ACCOUNTS:
            sickbeard.TRAKT_ACCOUNTS[send_oauth].reset_auth_failure()
        return resp
