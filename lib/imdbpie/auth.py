# -*- coding: utf-8 -*-
from __future__ import absolute_import, unicode_literals

try:
    # noinspection PyProtectedMember
    from base64 import encodebytes
except ImportError:
    from base64 import encodestring as encodebytes

from datetime import datetime
from hashlib import sha256 as sha256
from hashlib import sha1 as sha
import hmac
import json
import requests
import tempfile
import time

import diskcache
from dateutil.parser import parse
from dateutil.tz import tzutc
from six.moves.urllib.parse import urlparse, parse_qs, quote
from six import string_types, text_type

from .constants import APP_KEY, HOST, USER_AGENT, BASE_URI


class ZuluHmacAuthV3HTTPHandler(object):

    def __init__(self, host, secret_key, security_token, access_key):
        self.secret_key = secret_key
        self.host = host
        self.security_token = security_token
        self.access_key = access_key
        self._hmac_256 = self._get_hmac(ignore=True)

    def _get_hmac(self, ignore=False):
        if ignore or self._hmac_256:
            digestmod = sha256
        else:
            digestmod = sha
        return hmac.new(self.secret_key.encode('utf-8'), digestmod=digestmod)

    @staticmethod
    def canonical_headers(headers_to_sign):
        """
        Return the headers that need to be included in the StringToSign
        in their canonical form by converting all header keys to lower
        case, sorting them in alphabetical order and then joining
        them into a string, separated by newlines.
        """
        vals = sorted(['%s:%s' % (n.lower().strip(),
                                  headers_to_sign[n].strip()) for n in headers_to_sign])
        return '\n'.join(vals)

    def headers_to_sign(self, http_request):
        headers_to_sign = {'Host': self.host}
        for name, value in http_request.headers.items():
            lname = name.lower()
            if lname.startswith('x-amz'):
                headers_to_sign[name] = value
        return headers_to_sign

    def canonical_query_string(self, http_request):
        if http_request.method == 'POST':
            return ''
        qs_parts = []
        for param in sorted(http_request.params):
            value = self.get_utf8_value(http_request.params[param])
            param_ = quote(param, safe='-_.~')
            value_ = quote(value, safe='-_.~')
            qs_parts.append('{0}={1}'.format(param_, value_))
        return '&'.join(qs_parts)

    @staticmethod
    def get_utf8_value(value):
        if isinstance(value, bytes):
            value.decode('utf-8')
            return value

        if not isinstance(value, string_types):
            value = text_type(value)

        if isinstance(value, text_type):
            value = value.encode('utf-8')

        return value

    def string_to_sign(self, http_request):
        headers_to_sign = self.headers_to_sign(http_request)
        canonical_qs = self.canonical_query_string(http_request)
        canonical_headers = self.canonical_headers(headers_to_sign)
        string_to_sign = '\n'.join((
            http_request.method,
            http_request.path,
            canonical_qs,
            canonical_headers,
            '',
            http_request.body
        ))
        return string_to_sign, headers_to_sign

    def add_auth(self, req):
        """
        Add AWS3 authentication to a request.

        :type req: :class`boto.connection.HTTPRequest`
        :param req: The HTTPRequest object.
        """
        # This could be a retry.  Make sure the previous
        # authorization header is removed first.
        if 'X-Amzn-Authorization' in req.headers:
            del req.headers['X-Amzn-Authorization']
        req.headers['X-Amz-Date'] = self.formatdate(usegmt=True)
        if self.security_token:
            req.headers['X-Amz-Security-Token'] = self.security_token
        string_to_sign, headers_to_sign = self.string_to_sign(req)
        # print('StringToSign:\n%s' % string_to_sign)
        hash_value = sha256(string_to_sign.encode('utf-8')).digest()
        b64_hmac = self.sign_string(hash_value)
        s = "AWS3 AWSAccessKeyId=%s," % self.access_key
        s += "Algorithm=%s," % self.algorithm()
        s += "SignedHeaders=%s," % ';'.join(headers_to_sign)
        s += "Signature=%s" % b64_hmac
        req.headers['X-Amzn-Authorization'] = s

    def sign_string(self, string_to_sign):
        new_hmac = self._get_hmac()
        new_hmac.update(string_to_sign)
        return encodebytes(new_hmac.digest()).decode('utf-8').strip()

    def algorithm(self):
        if self._hmac_256:
            return 'HmacSHA256'
        return 'HmacSHA1'

    @staticmethod
    def formatdate(timeval=None, localtime=False, usegmt=False):
        """Returns a date string as specified by RFC 2822, e.g.:

        Fri, 09 Nov 2001 01:08:47 -0000

        Optional timeval if given is a floating point time value as accepted by
        gmtime() and localtime(), otherwise the current time is used.

        Optional localtime is a flag that when True, interprets timeval, and
        returns a date relative to the local timezone instead of UTC, properly
        taking daylight savings time into account.

        Optional argument usegmt means that the timezone is written out as
        an ascii string, not numeric one (so "GMT" instead of "+0000"). This
        is needed for HTTP, and is only used when localtime==False.
        """
        # Note: we cannot use strftime() because that honors the locale and RFC
        # 2822 requires that day and month names be the English abbreviations.
        if timeval is None:
            timeval = time.time()
        if localtime:
            now = time.localtime(timeval)
            # Calculate timezone offset, based on whether the local zone has
            # daylight savings time, and whether DST is in effect.
            if time.daylight and now[-1]:
                offset = time.altzone
            else:
                offset = time.timezone
            hours, minutes = divmod(abs(offset), 3600)
            # Remember offset is in seconds west of UTC, but the timezone is in
            # minutes east of UTC, so the signs differ.
            if offset > 0:
                sign = '-'
            else:
                sign = '+'
            zone = '%s%02d%02d' % (sign, hours, minutes // 60)
        else:
            now = time.gmtime(timeval)
            # Timezone offset is always -0000
            if usegmt:
                zone = 'GMT'
            else:
                zone = '-0000'
        return '%s, %02d %s %04d %02d:%02d:%02d %s' % (
            ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'][now[6]],
            now[2],
            ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
             'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'][now[1] - 1],
            now[0], now[3], now[4], now[5],
            zone)


class HTTPRequest(object):

    def __init__(self, method, protocol, host, port, path, auth_path, params, headers, body):
        """Represents an HTTP request.

        :type method: string
        :param method: The HTTP method name, 'GET', 'POST', 'PUT' etc.

        :type protocol: string
        :param protocol: The http protocol used, 'http' or 'https'.

        :type host: string
        :param host: Host to which the request is addressed. eg. abc.com

        :type port: int
        :param port: port on which the request is being sent. Zero means unset,
            in which case default port will be chosen.

        :type path: string
        :param path: URL path that is being accessed.

        :type auth_path: string or None
        :param path: The part of the URL path used when creating the
            authentication string.

        :type params: dict
        :param params: HTTP url query parameters, with key as name of
            the param, and value as value of param.

        :type headers: dict
        :param headers: HTTP headers, with key as name of the header and value
            as value of header.

        :type body: string
        :param body: Body of the HTTP request. If not present, will be None or
            empty string ('').
        """
        self.method = method
        self.protocol = protocol
        self.host = host
        self.port = port
        self.path = path
        if auth_path is None:
            auth_path = path
        self.auth_path = auth_path
        self.params = params
        # chunked Transfer-Encoding should act only on PUT request.
        if headers and 'Transfer-Encoding' in headers and \
                headers['Transfer-Encoding'] == 'chunked' and \
                self.method != 'PUT':
            self.headers = headers.copy()
            del self.headers['Transfer-Encoding']
        else:
            self.headers = headers
        self.body = body

    def __str__(self):
        return (('method:(%s) protocol:(%s) host(%s) port(%s) path(%s) '
                 'params(%s) headers(%s) body(%s)')
                % (self.method, self.protocol, self.host, self.port, self.path,
                   self.params, self.headers, self.body))


class Auth(object):

    SOON_EXPIRES_SECONDS = 60
    _CREDS_STORAGE_KEY = 'imdbpie-credentials'

    def __init__(self):
        self._cachedir = tempfile.gettempdir()

    def _get_creds(self, retry=False):
        with diskcache.Cache(directory=self._cachedir) as cache:
            try:
                return cache.get(self._CREDS_STORAGE_KEY)
            except ValueError as e:
                if not retry:
                    cache.close()
                    import encodingKludge as ek
                    import os
                    ek.ek(os.remove, ek.ek(os.path.join, self._cachedir, diskcache.core.DBNAME))
                    return self._get_creds(retry=True)
                else:
                    raise e

    def _set_creds(self, creds):
        with diskcache.Cache(directory=self._cachedir) as cache:
            cache[self._CREDS_STORAGE_KEY] = creds
        return creds

    def clear_cached_credentials(self):
        with diskcache.Cache(directory=self._cachedir) as cache:
            cache.delete(self._CREDS_STORAGE_KEY)

    def _creds_soon_expiring(self):
        creds = self._get_creds()
        if not creds:
            return creds, True
        expires_at = parse(creds['expirationTimeStamp'])
        now = datetime.now(tzutc())
        if now < expires_at:
            time_diff = expires_at - now
            if time_diff.total_seconds() < self.SOON_EXPIRES_SECONDS:
                # creds will soon expire, so renew them
                return creds, True
            return creds, False
        else:
            return creds, True

    @staticmethod
    def _get_credentials():
        url = '{0}/authentication/credentials/temporary/ios82'.format(BASE_URI)
        response = requests.post(
            url, json={'appKey': APP_KEY}, headers={'User-Agent': USER_AGENT}
        )
        response.raise_for_status()
        return json.loads(response.content.decode('utf8'))['resource']

    def get_auth_headers(self, url_path):
        creds, soon_expires = self._creds_soon_expiring()
        if soon_expires:
            creds = self._set_creds(creds=self._get_credentials())

        handler = ZuluHmacAuthV3HTTPHandler(
            host=HOST,
            secret_key=creds['secretAccessKey'],
            security_token=creds['sessionToken'], access_key=creds['accessKeyId']
        )
        parsed_url = urlparse(url_path)
        params = {
            key: val[0] for key, val in parse_qs(parsed_url.query).items()
        }
        request = HTTPRequest(
            method='GET', protocol='https', host=HOST,
            port=443, path=parsed_url.path, auth_path=None, params=params,
            headers={'User-Agent': USER_AGENT}, body=''
        )
        handler.add_auth(req=request)
        headers = request.headers

        return headers
