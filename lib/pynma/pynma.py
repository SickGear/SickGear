#!/usr/bin/python

from . import __version__
from xml.dom.minidom import parseString

import requests


class PyNMA(object):
    """
    http://www.notifymyandroid.com/api.jsp
    PyNMA(apikey=None, developerkey=None)
        takes 2 optional arguments:
            - (opt) apykey: a string containing 1 key or an array of keys
            - (opt) developerkey: where you can store your developer key
    """

    def __init__(self, apikey=None, developerkey=None):

        self._developerkey = None
        self.developerkey(developerkey)

        self.api_server = 'https://www.notifymyandroid.com'
        self.add_path = '/publicapi/notify'
        self.user_agent = 'PyNMA/v%s' % __version__

        key = []
        if apikey:
            key = (apikey, [apikey])[str == type(apikey)]

        self._apikey = self.uniq(key)

    @staticmethod
    def uniq(seq):
        # Not order preserving
        return list({}.fromkeys(seq).keys())

    def addkey(self, key):
        """
        Add a key (register ?)
        """
        if str == type(key):
            if key not in self._apikey:
                self._apikey.append(key)

        elif list == type(key):
            for k in key:
                if k not in self._apikey:
                    self._apikey.append(k)

    def delkey(self, key):
        """
        Removes a key (unregister ?)
        """
        if str == type(key):
            if key in self._apikey:
                self._apikey.remove(key)

        elif list == type(key):
            for k in key:
                if key in self._apikey:
                    self._apikey.remove(k)

    def developerkey(self, developerkey):
        """
        Sets the developer key (and check it has the good length)
        """
        if str == type(developerkey) and 48 == len(developerkey):
            self._developerkey = developerkey

    def push(self, application='', event='', description='', url='', content_type=None, priority=0, batch_mode=False, html=False):
        """
        Pushes a message on the registered API keys.
            takes 5 arguments:
                - (req) application: application name [256]
                - (req) event:       event name       [1000]
                - (req) description: description      [10000]
                - (opt) url:         url              [512]
                - (opt) contenttype: Content Type (act: None (plain text) or text/html)
                - (opt) priority:    from -2 (lowest) to 2 (highest) (def:0)
                - (opt) batch_mode:  call API 5 by 5 (def:False)
                - (opt) html: shortcut for content_type=text/html

            Warning: using batch_mode will return error only if all API keys are bad
            http://www.notifymyandroid.com/api.jsp
        """
        datas = {'application': application[:256].encode('utf8'),
                 'event': event[:1000].encode('utf8'),
                 'description': description[:10000].encode('utf8'),
                 'priority': priority}

        if url:
            datas['url'] = url[:2000]

        if self._developerkey:
            datas['developerkey'] = self._developerkey

        if 'text/html' == content_type or True == html:  # Currently only accepted content type
            datas['content-type'] = 'text/html'

        results = {}

        if not batch_mode:
            for key in self._apikey:
                datas['apikey'] = key
                res = self.callapi('POST', self.add_path, datas)
                results[key] = res
        else:
            datas['apikey'] = ','.join(self._apikey)
            res = self.callapi('POST', self.add_path, datas)
            results[datas['apikey']] = res

        return results

    def callapi(self, method, path, args):
        headers = {'User-Agent': self.user_agent}

        if 'POST' == method:
            headers['Content-type'] = 'application/x-www-form-urlencoded'

        try:
            resp = requests.post('%s:443%s' % (self.api_server, path), data=args, headers=headers).text
            res = self._parse_response(resp)
        except Exception as e:
            res = {'type': 'pynmaerror',
                   'code': 600,
                   'message': str(e)}
            pass

        return res

    @staticmethod
    def _parse_response(response):

        root = parseString(response).firstChild

        for elem in root.childNodes:
            if elem.TEXT_NODE == elem.nodeType:
                continue

            if 'success' == elem.tagName:
                res = dict(list(elem.attributes.items()))
                res['message'] = ''
                res['type'] = elem.tagName
                return res

            if 'error' == elem.tagName:
                res = dict(list(elem.attributes.items()))
                res['message'] = elem.firstChild.nodeValue
                res['type'] = elem.tagName
                return res
