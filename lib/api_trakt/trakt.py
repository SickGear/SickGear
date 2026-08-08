import certifi
import logging
import requests
import sickgear
import time
from exceptions_helper import ex, ConnectionSkipException
from json_helper import json_dumps
from sg_helpers import get_url, try_int

from .exceptions import *

# noinspection PyUnreachableCode
if False:
    from typing import Any, AnyStr, Dict

log = logging.getLogger('api_trakt')
log.addHandler(logging.NullHandler())


class TraktAPI(object):
    max_retrys = 3

    def __init__(self, timeout=None):

        self.api_url = sickgear.TRAKT_BASE_URL
        self.headers = {'Content-Type': 'application/json',
                        'trakt-api-version': '2',
                        'trakt-api-key': sickgear.TRAKT_CLIENT_ID}
        self.session = requests.Session()
        self.timeout = timeout or sickgear.TRAKT_TIMEOUT
        self.verify = sickgear.TRAKT_VERIFY and certifi.where()

    def trakt_request(self, path, data=None, headers=None, url=None, count=0, sleep_retry=60,
                      send_oauth=None, method=None, raise_skip_exception=True, failure_monitor=True, **kwargs):
        # type: (AnyStr, Dict, Dict, AnyStr, int, int, AnyStr, AnyStr, bool, bool, Any) -> Dict

        if method not in ['GET', 'POST', None]:
        # if method not in ['GET', 'POST', 'PUT', 'DELETE', None]:
            return {}
        if None is method:
            method = ('GET', 'POST')['data' in kwargs.keys() or None is not data]
        if 'oauth/token' != path and None is send_oauth and method in ['POST']:
        # if 'oauth/token' != path and None is send_oauth and method in ['POST', 'PUT', 'DELETE']:
            return {}

        count += 1
        if count > self.max_retrys:
            return {}

        # wait before retry
        if 'users/settings' != path:
            1 < count and time.sleep(sleep_retry)

        headers = headers or self.headers
        kwargs = dict(headers=headers, timeout=self.timeout, verify=self.verify)
        if data:
            kwargs['data'] = json_dumps(data)

        url = url or self.api_url
        try:
            resp = get_url(f'{url}{path}', session=self.session, use_method=method, return_response=True,
                           raise_exceptions=True, raise_status_code=True, raise_skip_exception=raise_skip_exception,
                           failure_monitor=failure_monitor, **kwargs)

            # check for http errors and raise if any are present
            resp.raise_for_status()

            # convert response to json
            resp = resp.json()

        except requests.RequestException as e:
            code = getattr(e.response, 'status_code', None)
            if not code:
                if 'timed out' in ex(e):
                    log.warning('Timeout connecting to Trakt')
                    if count >= self.max_retrys:
                        raise TraktTimeout()
                    return self.trakt_request(path, data, headers, url, count=count, sleep_retry=sleep_retry,
                                              send_oauth=send_oauth, method=method)
                # This is pretty much a fatal error if there is no status_code
                # It means there basically was no response at all
                else:
                    log.warning('Could not connect to Trakt. Error: %s' % ex(e))
                    raise TraktException('Could not connect to Trakt. Error: %s' % ex(e))

            elif 502 == code:
                # Retry the request, Cloudflare had a proxying issue
                log.warning(f'Retrying Trakt api request: {path}')
                if count >= self.max_retrys:
                    raise TraktCloudFlareException()
                return self.trakt_request(path, data, headers, url, count=count, sleep_retry=sleep_retry,
                                          send_oauth=send_oauth, method=method)

            elif 401 == code and 'oauth/token' != path:
                raise TraktAuthException()
            elif code in (500, 501, 503, 504, 520, 521, 522):
                if count >= self.max_retrys:
                    log.warning(f'Trakt may have some issues and it\'s unavailable. Code: {code}')
                    raise TraktServerError(error_code=code)
                # http://docs.trakt.apiary.io/#introduction/status-codes
                log.warning('Trakt may have some issues and it\'s unavailable. Trying again')
                return self.trakt_request(path, data, headers, url, count=count, sleep_retry=sleep_retry,
                                          send_oauth=send_oauth, method=method)
            elif 404 == code:
                # log.debug(f'Trakt error (404) the resource does not exist: {url}{path}')
                raise TraktMethodNotExisting('Trakt error (404) the resource does not exist: %s%s' % (url, path))
            elif 429 == code:
                if count >= self.max_retrys:
                    log.warning('Trakt replied with Rate-Limiting, maximum retries exceeded.')
                    raise TraktServerError(error_code=code)
                r_headers = getattr(e.response, 'headers', None)
                if None is not r_headers:
                    wait_seconds = min(try_int(r_headers.get('Retry-After', 60), 60), 150)
                else:
                    wait_seconds = 60
                log.warning('Trakt replied with Rate-Limiting, waiting %s seconds.' % wait_seconds)
                wait_seconds = (wait_seconds, 60)[0 > wait_seconds]
                wait_seconds -= sleep_retry
                if 0 < wait_seconds:
                    time.sleep(wait_seconds)
                return self.trakt_request(path, data, headers, url, count=count, sleep_retry=sleep_retry,
                                          send_oauth=send_oauth, method=method)
            elif 423 == code:
                # locked account
                log.error('An application that is NOT SickGear has flooded the Trakt API and they have locked access'
                          ' to your account. They request you contact their support at https://support.trakt.tv/'
                          ' This is not a fault of SickGear because it does *not* sync data or send the type of data'
                          ' that triggers a Trakt access lock.'
                          ' SickGear may only send a notification on a media process completion if set up for it.')
                raise TraktLockedUserAccount()
            elif 400 == code and 'invalid_grant' in getattr(e, 'text', ''):
                raise TraktInvalidGrant('Error: invalid_grant. The provided authorization grant is invalid, expired, '
                                        'revoked, does not match the redirection URI used in the authorization request,'
                                        ' or was issued to another client.')
            elif 420 == code and 'sync/collection' in path:
                # collections are limited to 100 items
                raise TraktFreemiumLimit('Freemium account maximum items exceeded')
            else:
                log.error('Could not connect to Trakt. Code error: {0}'.format(code))
                raise TraktException('Could not connect to Trakt. Code error: %s' % code)
        except ConnectionSkipException as e:
            log.warning('Connection is skipped')
            raise e
        except ValueError as e:
            log.error(f'Value Error: {ex(e)}')
            raise TraktValueError(f'Value Error: {ex(e)}')
        except (BaseException, Exception) as e:
            log.error('Exception: %s' % ex(e))
            raise TraktException('Could not connect to Trakt. Code error: %s' % ex(e))

        # check and confirm Trakt call did not fail
        if isinstance(resp, dict) and 'failure' == resp.get('status', None):
            if 'message' in resp:
                raise TraktException(resp['message'])
            if 'error' in resp:
                raise TraktException(resp['error'])
            raise TraktException('Unknown Error')

        return resp
