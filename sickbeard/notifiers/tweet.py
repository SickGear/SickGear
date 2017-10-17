# Author: Nic Wolfe <nic@wolfeden.ca>
# URL: http://code.google.com/p/sickbeard/
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
#  GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with SickGear.  If not, see <http://www.gnu.org/licenses/>.

from urlparse import parse_qsl

import sickbeard
from sickbeard.exceptions import ex
from sickbeard.notifiers.generic import Notifier

import lib.oauth2 as oauth
import lib.pythontwitter as twitter


class TwitterNotifier(Notifier):

    consumer_key = 'vHHtcB6WzpWDG6KYlBMr8g'
    consumer_secret = 'zMqq5CB3f8cWKiRO2KzWPTlBanYmV0VYxSXZ0Pxds0E'

    REQUEST_TOKEN_URL = 'https://api.twitter.com/oauth/request_token'
    ACCESS_TOKEN_URL = 'https://api.twitter.com/oauth/access_token'
    AUTHORIZATION_URL = 'https://api.twitter.com/oauth/authorize'
    SIGNIN_URL = 'https://api.twitter.com/oauth/authenticate'

    def get_authorization(self):

        # noinspection PyUnusedLocal
        signature_method_hmac_sha1 = oauth.SignatureMethod_HMAC_SHA1()
        oauth_consumer = oauth.Consumer(key=self.consumer_key, secret=self.consumer_secret)
        oauth_client = oauth.Client(oauth_consumer)

        self._log_debug('Requesting temp token from Twitter')

        resp, content = oauth_client.request(self.REQUEST_TOKEN_URL, 'GET')

        if '200' != resp['status']:
            self._log_error('Invalid response from Twitter requesting temp token: %s' % resp['status'])
        else:
            request_token = dict(parse_qsl(content))

            sickbeard.TWITTER_USERNAME = request_token['oauth_token']
            sickbeard.TWITTER_PASSWORD = request_token['oauth_token_secret']

            return self.AUTHORIZATION_URL + '?oauth_token=' + request_token['oauth_token']

    def get_credentials(self, key):
        request_token = dict(oauth_token=sickbeard.TWITTER_USERNAME, oauth_token_secret=sickbeard.TWITTER_PASSWORD,
                             oauth_callback_confirmed='true')

        token = oauth.Token(request_token['oauth_token'], request_token['oauth_token_secret'])
        token.set_verifier(key)

        self._log_debug('Generating and signing request for an access token using key ' + key)

        # noinspection PyUnusedLocal
        signature_method_hmac_sha1 = oauth.SignatureMethod_HMAC_SHA1()
        oauth_consumer = oauth.Consumer(key=self.consumer_key, secret=self.consumer_secret)
        self._log_debug('oauth_consumer: ' + str(oauth_consumer))
        oauth_client = oauth.Client(oauth_consumer, token)
        self._log_debug('oauth_client: ' + str(oauth_client))
        resp, content = oauth_client.request(self.ACCESS_TOKEN_URL, method='POST', body='oauth_verifier=%s' % key)
        self._log_debug('resp, content: ' + str(resp) + ',' + str(content))

        access_token = dict(parse_qsl(content))
        self._log_debug('access_token: ' + str(access_token))

        self._log_debug('resp[status] = ' + str(resp['status']))
        if '200' != resp['status']:
            self._log_error('The request for a token with did not succeed: ' + str(resp['status']))
            result = False
        else:
            self._log_debug('Your Twitter Access Token key: %s' % access_token['oauth_token'])
            self._log_debug('Access Token secret: %s' % access_token['oauth_token_secret'])
            sickbeard.TWITTER_USERNAME = access_token['oauth_token']
            sickbeard.TWITTER_PASSWORD = access_token['oauth_token_secret']
            result = True

        message = ('Key verification successful', 'Unable to verify key')[not result]
        logger.log(u'%s result: %s' % (self.name, message))
        return self._choose(message, result)

    def _notify(self, title, body, **kwargs):

        # don't use title with updates or testing, as only one str is used
        body = '::'.join(([], [sickbeard.TWITTER_PREFIX])[bool(sickbeard.TWITTER_PREFIX)]
                         + [body.replace('#: ', ': ') if 'SickGear' in title else body])

        username = self.consumer_key
        password = self.consumer_secret
        access_token_key = sickbeard.TWITTER_USERNAME
        access_token_secret = sickbeard.TWITTER_PASSWORD

        api = twitter.Api(username, password, access_token_key, access_token_secret)

        try:
            api.PostUpdate(body.encode('utf8'))
        except Exception as e:
            self._log_error(u'Error sending Tweet: ' + ex(e))
            return False

        return True


notifier = TwitterNotifier
