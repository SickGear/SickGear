from bs4 import BeautifulSoup


class BS4Parser:
    def __init__(self, *args, **kwargs):
        # list type param of "feature" arg is not currently correctly tested by bs4 (r353)
        # so for now, adjust param to provide possible values until the issue is addressed
        kwargs_new = {}
        for k, v in kwargs.items():
            if 'features' in k and isinstance(v, list):
                v = [item for item in v if item in ['html5lib', 'html.parser', 'html', 'lxml', 'xml']][0]

            kwargs_new[k] = v

        self.soup = BeautifulSoup(*args, **kwargs_new)

    def __enter__(self):
        return self.soup

    def __exit__(self, exc_ty, exc_val, tb):
        self.soup.clear(True)
        self.soup = None
