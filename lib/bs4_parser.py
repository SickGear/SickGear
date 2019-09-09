import re
from bs4 import BeautifulSoup, SoupStrainer
from six import iteritems


class BS4Parser(object):
    def __init__(self, *args, **kwargs):
        # list type param of "feature" arg is not currently correctly tested by bs4 (r353)
        # so for now, adjust param to provide possible values until the issue is addressed
        kwargs_new = {}
        for k, v in iteritems(kwargs):
            if 'features' in k and isinstance(v, list):
                v = [item for item in v if item in ['html5lib', 'html.parser', 'html', 'lxml', 'xml']][0]

            elif 'parse_only' in k:
                if isinstance(v, dict):
                    (parse_key, filter_dict), = kwargs[k].items()
                    v = SoupStrainer(parse_key, filter_dict)
                else:
                    v = SoupStrainer(v)

            elif 'preclean' in k and v:
                args = (re.sub(r'(?si)(<!--.*?-->|<style.*?</style>)', '', args[0]),) + args[1:]
                continue

            kwargs_new[k] = v

        tag, attr = [x in kwargs_new and kwargs_new.pop(x) or y for (x, y) in [('tag', 'table'), ('attr', '')]]
        if attr:
            args = (re.sub(r'(?is).*(<%(tag)s[^>]+%(attr)s[^>]*>.*</%(tag)s>).*' % {'tag': tag, 'attr': attr},
                           r'<html><head></head><body>\1</body></html>', args[0]).strip(),) + args[1:]

        self.soup = BeautifulSoup(*args, **kwargs_new)

    def __enter__(self):
        return self.soup

    def __exit__(self, exc_ty, exc_val, tb):
        self.soup.clear(True)
        self.soup = None
