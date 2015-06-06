import urllib
import urlparse
import re
from feedparser import feedparser
import sickbeard

from sickbeard import logger
from sickbeard.exceptions import ex

def getFeed(url, post_data=None, request_headers=None):
    parsed = list(urlparse.urlparse(url))
    parsed[2] = re.sub("/{2,}", "/", parsed[2])  # replace two or more / with one

    if post_data:
        url += urllib.urlencode(post_data)

    try:
        feed = feedparser.parse(url, False, False, request_headers)

        if feed:
            if 'entries' in feed:
                return feed
            elif 'error' in feed.feed:
                err_code = feed.feed['error']['code']
                err_desc = feed.feed['error']['description']
                logger.log(u'RSS ERROR:[%s] CODE:[%s]' % (err_desc, err_code), logger.DEBUG)
        else:
            logger.log(u'RSS error loading url: ' + url, logger.DEBUG)

    except Exception as e:
        logger.log(u'RSS error: ' + ex(e), logger.DEBUG)