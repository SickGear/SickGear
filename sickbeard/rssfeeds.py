# coding=utf-8
#
# This file is part of SickGear.
#

import re
import requests
import requests.cookies
from feedparser import feedparser

from sickbeard import helpers, logger
from sickbeard.exceptions import ex


class RSSFeeds:

    def __init__(self, provider=None):

        self.provider = provider

    def _check_auth_cookie(self):

        if self.provider and hasattr(self.provider, 'cookies'):
            cookies = self.provider.cookies

            if not re.match('^(\w+=\w+[;\s]*)+$', cookies):
                return False

            cj = requests.utils.add_dict_to_cookiejar(self.provider.session.cookies,
                                                      dict([x.strip().split('=') for x in cookies.split(';')
                                                            if x != ''])),
            for item in cj:
                if not isinstance(item, requests.cookies.RequestsCookieJar):
                    return False

        return True

    def check_cookie(self):

        if self._check_auth_cookie():
            return True, None

        return False, 'Cookies not correctly formatted key=value pairs e.g. uid=xx;pass=yy): ' + self.provider.cookies

    def get_feed(self, url, request_headers=None):

        if not self._check_auth_cookie():
            return

        session = None
        if self.provider and hasattr(self.provider, 'session'):
            session = self.provider.session

        response = helpers.getURL(url, headers=request_headers, session=session)
        if not response:
            return

        try:
            feed = feedparser.parse(response)
            if feed and 'entries' in feed:
                return feed

            if feed and 'error' in feed.feed:
                err_code = feed.feed['error']['code']
                err_desc = feed.feed['error']['description']
                logger.log(u'RSS ERROR:[%s] CODE:[%s]' % (err_desc, err_code), logger.DEBUG)
            else:
                logger.log(u'RSS error loading url: ' + url, logger.DEBUG)

        except Exception as e:
            logger.log(u'RSS error: ' + ex(e), logger.DEBUG)
