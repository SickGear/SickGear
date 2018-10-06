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

import datetime
import re

import sickbeard
from lib.six import moves
from base64 import standard_b64encode
from common import Quality
from sickbeard import logger
from sickbeard.helpers import tryInt
from sickbeard.providers.generic import GenericProvider


def test_nzbget(host, use_https, username, password):

    result = False
    if not host:
        msg = 'No NZBGet host found. Please configure it'
        logger.log(msg, logger.ERROR)
        return result, msg, None

    url = 'http%(scheme)s://%(username)s:%(password)s@%(host)s/xmlrpc' % {
        'scheme': ('', 's')[use_https], 'host': re.sub('(?:https?://)?(.*?)/?$', r'\1', host),
        'username': username, 'password': password}
    rpc_client = moves.xmlrpc_client.ServerProxy(url)
    try:
        msg = 'Success. Connected'
        if rpc_client.writelog('INFO', 'SickGear connected as a test'):
            logger.log(msg, logger.DEBUG)
        else:
            msg += ', but unable to send a message'
            logger.log(msg, logger.ERROR)
        result = True
        logger.log(u'NZBGet URL: %s' % url, logger.DEBUG)

    except moves.http_client.socket.error:
        msg = 'Please check NZBGet host and port (if it is running). NZBGet is not responding to these values'
        logger.log(msg, logger.ERROR)

    except moves.xmlrpc_client.ProtocolError as e:
        if 'Unauthorized' == e.errmsg:
            msg = 'NZBGet username or password is incorrect'
            logger.log(msg, logger.ERROR)
        else:
            msg = 'Protocol Error: %s' % e.errmsg
            logger.log(msg, logger.ERROR)

    return result, msg, rpc_client


def send_nzb(nzb):
    result = False
    add_to_top = False
    nzbget_prio = 0

    authed, auth_msg, rpc_client = test_nzbget(
        sickbeard.NZBGET_HOST, sickbeard.NZBGET_USE_HTTPS, sickbeard.NZBGET_USERNAME, sickbeard.NZBGET_PASSWORD)

    if not authed:
        return authed

    dupekey = ''
    dupescore = 0
    # if it aired recently make it high priority and generate DupeKey/Score
    for curEp in nzb.episodes:
        if '' == dupekey:
            dupekey = 'SickGear-%s%s' % (
                sickbeard.indexerApi(curEp.show.indexer).config.get('dupekey', ''), curEp.show.indexerid)
        dupekey += '-%s.%s' % (curEp.season, curEp.episode)

        if datetime.date.today() - curEp.airdate <= datetime.timedelta(days=7) or \
                datetime.date.fromordinal(1) >= curEp.airdate:
            add_to_top = True
            nzbget_prio = sickbeard.NZBGET_PRIORITY

    if Quality.UNKNOWN != nzb.quality:
        dupescore = nzb.quality * 100

    dupescore += (0, 9 + nzb.properlevel)[0 < nzb.properlevel]

    nzbcontent64 = None
    if 'nzbdata' == nzb.resultType:
        data = nzb.get_data()
        if not data:
            return False
        nzbcontent64 = standard_b64encode(data)
    elif 'Anizb' == nzb.provider.name and 'nzb' == nzb.resultType:
        gen_provider = GenericProvider('')
        data = gen_provider.get_url(nzb.url)
        if None is data:
            return result
        nzbcontent64 = standard_b64encode(data)

    logger.log(u'Sending NZB to NZBGet: %s' % nzb.name)

    try:
        # Find out if nzbget supports priority (Version 9.0+), old versions beginning with a 0.x will use the old cmd
        nzbget_version_str = rpc_client.version()
        nzbget_version = tryInt(nzbget_version_str[:nzbget_version_str.find('.')])

        # v13+ has a combined append method that accepts both (url and content)
        # also the return value has changed from boolean to integer
        # (Positive number representing NZBID of the queue item. 0 and negative numbers represent error codes.)
        if 13 <= nzbget_version:
            nzbget_result = rpc_client.append(
                '%s.nzb' % nzb.name, (nzbcontent64, nzb.url)[None is nzbcontent64], sickbeard.NZBGET_CATEGORY,
                nzbget_prio, False, False, dupekey, dupescore, 'score') > 0

        elif 12 == nzbget_version:
            if nzbcontent64 is not None:
                nzbget_result = rpc_client.append('%s.nzb' % nzb.name, sickbeard.NZBGET_CATEGORY,
                                                  nzbget_prio, False, nzbcontent64, False, dupekey, dupescore, 'score')
            else:
                nzbget_result = rpc_client.appendurl('%s.nzb' % nzb.name, sickbeard.NZBGET_CATEGORY,
                                                     nzbget_prio, False, nzb.url, False, dupekey, dupescore, 'score')
        elif 0 == nzbget_version:
            if nzbcontent64 is not None:
                nzbget_result = rpc_client.append('%s.nzb' % nzb.name, sickbeard.NZBGET_CATEGORY,
                                                  add_to_top, nzbcontent64)
            else:
                if 'nzb' == nzb.resultType:
                    gen_provider = GenericProvider('')
                    data = gen_provider.get_url(nzb.url)
                    if None is data:
                        return result

                    nzbcontent64 = standard_b64encode(data)
                nzbget_result = rpc_client.append('%s.nzb' % nzb.name, sickbeard.NZBGET_CATEGORY,
                                                  add_to_top, nzbcontent64)
        else:
            if nzbcontent64 is not None:
                nzbget_result = rpc_client.append('%s.nzb' % nzb.name, sickbeard.NZBGET_CATEGORY,
                                                  nzbget_prio, False, nzbcontent64)
            else:
                nzbget_result = rpc_client.appendurl('%s.nzb' % nzb.name, sickbeard.NZBGET_CATEGORY,
                                                     nzbget_prio, False, nzb.url)

        if nzbget_result:
            logger.log(u'NZB sent to NZBGet successfully', logger.DEBUG)
            result = True
        else:
            logger.log(u'NZBGet could not add %s to the queue' % ('%s.nzb' % nzb.name), logger.ERROR)
    except(StandardError, Exception):
        logger.log(u'Connect Error to NZBGet: could not add %s to the queue' % ('%s.nzb' % nzb.name), logger.ERROR)

    return result
