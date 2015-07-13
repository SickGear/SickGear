# coding=utf-8
#
# This file is part of SickGear.
#

from feedparser import feedparser

from sickbeard import helpers, logger
from sickbeard.exceptions import ex


class RSSFeeds:

    def __init__(self, provider=None):

        self.provider = provider

    def _check_auth_cookie(self):

        if self.provider:
            return self.provider.check_auth_cookie()
        return True

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
