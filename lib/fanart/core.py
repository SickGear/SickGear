import requests
import re
import lib.fanart as fanart
from bs4_parser import BS4Parser
from exceptions_helper import ex
from .errors import ResponseFanartError


class Request(object):
    def __init__(self, apikey, tvdb_id, ws=fanart.WS.TV, types=None):
        self._apikey = apikey
        self._tvdb_id = tvdb_id
        self._ws = ws
        self._types = types
        self._response = None
        self._web_url = 'https://fanart.tv/series/%s'
        self._assets_url = 'https://assets.fanart.tv'

    def __str__(self):
        return fanart.BASEURL % (self._ws, self._tvdb_id, self._apikey)

    def response(self):

        try:
            response = requests.get(str(self))
            rjson = response.json()
            image_type = self._types or u'showbackground'
            rhtml = self.scrape_web(image_type)
            if not isinstance(rjson, dict) and 0 == len(rhtml[image_type]):
                raise Exception(response.text)

            if not isinstance(rjson, dict):
                rjson = {image_type: []}

            if 0 != len(rhtml[image_type]):
                rjson_ids = map(lambda i: i['id'], rjson[image_type])
                for item in filter(lambda i: i['id'] not in rjson_ids, rhtml[image_type]):
                    rjson[image_type] += [item]

            for item in rjson[image_type]:
                item['lang'] = item.get('lang', '').lower()
                if item.get('lang') in ('00', ''):  # adjust data of no language to a default 'en (default)'
                    item['lang'] = u'en (default)'

            return rjson

        except (BaseException, Exception) as e:
            raise ResponseFanartError(ex(e))

    def scrape_web(self, image_type):
        try:
            data = requests.get(self._web_url % self._tvdb_id)
            if not data:
                return

            with BS4Parser(data.text, parse_only=dict(ul={'class': 'artwork %s' % image_type})) as ul_item:
                li_items = ul_item('li')
                if li_items:
                    image_urls = {image_type: []}
                    for li_item in li_items:
                        image_id = None
                        item = li_item.find('a', attrs={'class': 'download'}).get('href')
                        if item:
                            match = re.search(r'image=(\d+)', item, re.I)
                            if match:
                                image_id = u'%s' % match.group(1)

                        item = li_item.find('a', attrs={'rel': image_type}).get('href')
                        image_url = (u'%s%s' % (self._assets_url, item), None)[None is item]

                        item = li_item.find('div', attrs={'class': 'votes'}).get_text()
                        image_likes = (item, 0)[None is item]

                        item = li_item.find('div', attrs={'class': 'metrics'}).get_text()
                        image_lang = u'en (default)'
                        if item:
                            match = re.search(r'Language:\s*(\w+)', item, re.I)
                            if match:
                                image_lang = u'%s' % (match.group(1)[0:2], 'en')['None' == match.group(1)]

                        if not (None is image_id or None is image_url):
                            image_urls[image_type].append({u'id': image_id, u'url': image_url,
                                                           u'likes': image_likes, u'lang': image_lang})

                    return image_urls
        except (BaseException, Exception):
            pass
