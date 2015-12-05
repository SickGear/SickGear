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
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with SickGear.  If not, see <http://www.gnu.org/licenses/>.

from six import moves

import sickbeard

from lib import MultipartPostHandler

try:
    import json
except ImportError:
    from lib import simplejson as json

from sickbeard.common import USER_AGENT
from sickbeard import logger
from sickbeard.exceptions import ex
from sickbeard import helpers


def sendNZB(nzb):
    """
    Sends an NZB to SABnzbd via the API.

    nzb: The NZBSearchResult object to send to SAB
    """

    # set up a dict with the URL params in it
    params = {'output': 'json'}
    if sickbeard.SAB_USERNAME is not None:
        params['ma_username'] = sickbeard.SAB_USERNAME
    if sickbeard.SAB_PASSWORD is not None:
        params['ma_password'] = sickbeard.SAB_PASSWORD
    if sickbeard.SAB_APIKEY is not None:
        params['apikey'] = sickbeard.SAB_APIKEY
    if sickbeard.SAB_CATEGORY is not None:
        params['cat'] = sickbeard.SAB_CATEGORY

    # use high priority if specified (recently aired episode)
    if nzb.priority == 1:
        params['priority'] = 1

    # if it's a normal result we just pass SAB the URL
    if nzb.resultType == 'nzb':
        params['mode'] = 'addurl'
        params['name'] = nzb.url

    # if we get a raw data result we want to upload it to SAB
    elif nzb.resultType == 'nzbdata':
        params['mode'] = 'addfile'
        multiPartParams = {'nzbfile': (nzb.name + '.nzb', nzb.extraInfo[0])}

    url = sickbeard.SAB_HOST + 'api'

    logger.log(u'Sending NZB to SABnzbd: %s' % nzb.name)
    logger.log(u'Using SABnzbd URL: %s with parameters: %s' % (url, params), logger.DEBUG)

    # if we have the URL to an NZB then we've built up the SAB API URL already so just call it
    if nzb.resultType == 'nzb':
        success, result = _sabURLOpenSimple(url, params)

    # if we are uploading the NZB data to SAB then we need to build a little POST form and send it
    elif nzb.resultType == 'nzbdata':
        headers = {'User-Agent': USER_AGENT}
        success, result = _sabURLOpenSimple(url, params=params, post_data=multiPartParams, headers=headers)

    if not success:
        return False, result

    # do some crude parsing of the result text to determine what SAB said
    if result['status']:
        logger.log(u'NZB sent to SABnzbd successfully', logger.DEBUG)
        return True
    elif 'error' in result:
        logger.log(u'NZB failed to send to SABnzbd. Return error text is: %s', logger.ERROR)
        return False
    else:
        logger.log(u'Unknown failure sending NZB to SABnzbd. Return text is: %s' % result, logger.ERROR)
        return False


def _checkSabResponse(result):
    if len(result) == 0:
        logger.log(u'No data returned from SABnzbd, NZB not sent', logger.ERROR)
        return False, 'No data from SABnzbd'

    if 'error' in result:
        logger.log(result['error'], logger.ERROR)
        return False, result['error']
    else:
        return True, result


def _sabURLOpenSimple(url, params=None, post_data=None, headers=None):
    result = helpers.getURL(url, params=params, post_data=post_data, headers=headers, json=True)
    if result is None:
        logger.log(u'No data returned from SABnzbd', logger.ERROR)
        return False, u'No data returned from SABnzbd'
    else:
        return True, result


def getSabAccesMethod(host=None, username=None, password=None, apikey=None):
    url = host + 'api'
    params = {u'mode': u'auth', u'output': u'json'}

    success, result = _sabURLOpenSimple(url, params=params)
    if not success:
        return False, result

    return True, result['auth']


def testAuthentication(host=None, username=None, password=None, apikey=None):
    """
    Sends a simple API request to SAB to determine if the given connection information is connect

    host: The host where SAB is running (incl port)
    username: The username to use for the HTTP request
    password: The password to use for the HTTP request
    apikey: The API key to provide to SAB

    Returns: A tuple containing the success boolean and a message
    """

    # build up the URL parameters
    params = {u'mode': u'queue', u'output': u'json', u'ma_username': username, u'ma_password': password, u'apikey': apikey}
    url = host + 'api'

    # send the test request
    logger.log(u'SABnzbd test URL: %s with parameters: %s' % (url, params), logger.DEBUG)
    success, result = _sabURLOpenSimple(url, params=params)
    if not success:
        return False, result

    # check the result and determine if it's good or not
    success, sabText = _checkSabResponse(result)
    if not success:
        return False, sabText

    return True, u'Success'

