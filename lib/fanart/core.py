import requests
import re
import lib.fanart as fanart
from sickbeard.bs4_parser import BS4Parser
from .errors import ResponseFanartError


class Request(object):
    def __init__(self, apikey, tvdb_id, ws=fanart.WS.TV):
        self._apikey = apikey
        self._tvdb_id = tvdb_id
        self._ws = ws
        self._response = None
        self._web_url = 'https://fanart.tv/series/%s'
        self._assets_url = 'https://assets.fanart.tv'

    def __str__(self):
        return fanart.BASEURL % (self._ws, self._tvdb_id, self._apikey)

    def response(self):

        try:
            response = requests.get(str(self))
            rjson = response.json()
            image_type = u'showbackground'
            rhtml = self.scrape_web(image_type)
            if not isinstance(rjson, dict) and 0 == len(rhtml[image_type]):
                raise Exception(response.text)

            if 0 < len(rhtml[image_type]):
                items = {image_type: []}
                for item1 in rhtml[image_type]:
                    use_item = True
                    for k, item2 in enumerate(rjson[image_type] or []):
                        if '00' == item2['lang']:  # adjust api data of no language to a default
                            rjson[image_type][k]['lang'] = u'en'
                        if item1['id'] == item2['id']:
                            use_item = False
                            break
                    if use_item:
                        items[image_type] += [item1]
                rjson[image_type] += items[image_type]
            return rjson

        except Exception as e:
            raise ResponseFanartError(str(e))

    def scrape_web(self, image_type):
        try:
            data = requests.get(self._web_url % self._tvdb_id)
            if not data:
                return

            with BS4Parser(data.text, features=['html5lib', 'permissive']) as html:
                ul_item = html.find('ul', attrs={'class': image_type})
                if ul_item:
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
                            image_lang = u'None found'
                            if item:
                                match = re.search(r'Language:\s*(\w+)', item, re.I)
                                if match:
                                    image_lang = u'%s' % (match.group(1)[0:2:].lower(), 'en')['None' == match.group(1)]

                            if not (None is image_id or None is image_url):
                                image_urls[image_type].append({u'id': image_id, u'url': image_url, u'likes': image_likes, u'lang': image_lang})

                        return image_urls
        except Exception, e:
            pass
