# coding=utf-8
#
# This file is part of SickGear.
#

import feedparser

from exceptions_helper import ex
from sickgear import logger


class RSSFeeds(object):
    def __init__(self, provider=None):
        self.provider = provider

    def get_feed(self, url, **kwargs):

        if self.provider:
            success, err_msg = self.provider.check_auth_cookie()
            if not success:
                return
            response = self.provider.get_url(url, **kwargs)
            if not self.provider.should_skip() and response:
                try:
                    data = feedparser.parse(response)
                    data['rq_response'] = self.provider.session.response
                    if data and 'entries' in data:
                        return data

                    if data and 'error' in data.feed:
                        err_code = data.feed['error']['code']
                        err_desc = data.feed['error']['description']
                        logger.debug(f'RSS error:[{err_desc}] code:[{err_code}]')
                    else:
                        logger.debug(f'RSS error loading url: {url}')

                except (BaseException, Exception) as e:
                    logger.debug(f'RSS error: {ex(e)}')
