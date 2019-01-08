from base64 import b64encode
from time import sleep
import logging
import random
import re
from requests.sessions import Session
from requests.models import Response
import js2py
from copy import deepcopy

try:
    from urlparse import urlparse
except ImportError:
    # noinspection PyCompatibility
    from urllib.parse import urlparse

DEFAULT_USER_AGENTS = [
    'Mozilla/5.0 (Windows NT 6.1) AppleWebKit/537.36 (KHTML, like Gecko)'
    ' Chrome/41.0.2228.0 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_10_5) AppleWebKit/537.36 (KHTML, like Gecko)'
    ' Chrome/50.0.2661.102 Safari/537.36',
    'Mozilla/5.0 (Windows NT 6.1; WOW64) AppleWebKit/537.36 (KHTML, like Gecko)'
    ' Chrome/52.0.2743.116 Safari/537.36',
    'Mozilla/5.0 (Windows NT 6.1; WOW64; rv:46.0)'
    ' Gecko/20100101 Firefox/46.0',
    'Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:41.0)'
    ' Gecko/20100101 Firefox/41.0'
]

DEFAULT_USER_AGENT = random.choice(DEFAULT_USER_AGENTS)


class CloudflareScraper(Session):
    def __init__(self, **kwargs):
        super(CloudflareScraper, self).__init__()

        if 'requests' in self.headers['User-Agent']:
            # Set a random User-Agent if no custom User-Agent has been set
            self.headers['User-Agent'] = DEFAULT_USER_AGENT

        self.delay = kwargs.pop('delay', 8)

    def request(self, method, url, *args, **kwargs):
        resp = super(CloudflareScraper, self).request(method, url, *args, **kwargs)

        # Check if anti-bot is on
        if (isinstance(resp, type(Response()))
                and resp.status_code in (503, 403)):
            if (re.search('(?i)cloudflare', resp.headers.get('Server', ''))
                    and 'jschl_vc' in resp.content
                    and 'jschl_answer' in resp.content):
                resp = self.solve_cf_challenge(resp, **kwargs)
            elif 'ddgu' in resp.content:
                resp = self.solve_ddg_challenge(resp, **kwargs)

        # Otherwise, no anti-bot detected
        return resp

    def solve_ddg_challenge(self, resp, **original_kwargs):
        sleep(self.delay)
        parsed_url = urlparse(resp.url)
        try:
            submit_url = parsed_url.scheme + ':' + re.findall('"frm"[^>]+?action="([^"]+)"', resp.text)[0]
            kwargs = {k: v for k, v in original_kwargs.items() if k not in ['hooks']}
            kwargs.setdefault('headers', {})
            kwargs.setdefault('data', dict(
                h=b64encode('%s://%s' % (parsed_url.scheme, parsed_url.hostname)),
                u=b64encode(parsed_url.path), p=b64encode(parsed_url.port or '')
            ))
            resp = self.request('POST', submit_url, **kwargs)
        except(StandardError, BaseException):
            pass
        return resp

    def solve_cf_challenge(self, resp, **original_kwargs):
        sleep(self.delay)  # Cloudflare requires a delay before solving the challenge

        body = resp.text
        parsed_url = urlparse(resp.url)
        domain = parsed_url.netloc
        submit_url = '%s://%s/cdn-cgi/l/chk_jschl' % (parsed_url.scheme, domain)

        cloudflare_kwargs = {k: v for k, v in original_kwargs.items() if k not in ['hooks']}
        params = cloudflare_kwargs.setdefault('params', {})
        headers = cloudflare_kwargs.setdefault('headers', {})
        headers['Referer'] = resp.url

        try:
            params['jschl_vc'] = re.search(r'name="jschl_vc" value="(\w+)"', body).group(1)
            params['pass'] = re.search(r'name="pass" value="(.+?)"', body).group(1)

            # Extract the arithmetic operation
            js = self.extract_js(body)

        except Exception:
            # Something is wrong with the page.
            # This may indicate Cloudflare has changed their anti-bot
            # technique. If you see this and are running the latest version,
            # please open a GitHub issue so I can update the code accordingly.
            logging.error('[!] Unable to parse Cloudflare anti-bots page.')
            raise

        # Safely evaluate the Javascript expression
        try:
            params['jschl_answer'] = str(js2py.eval_js(js) + len(domain))
        except (Exception, BaseException):
            try:
                params['jschl_answer'] = str(js2py.eval_js(js) + len(domain))
            except (Exception, BaseException):
                return

        # Requests transforms any request into a GET after a redirect,
        # so the redirect has to be handled manually here to allow for
        # performing other types of requests even as the first request.
        method = resp.request.method
        cloudflare_kwargs['allow_redirects'] = False
        redirect = self.request(method, submit_url, **cloudflare_kwargs)

        location = redirect.headers.get('Location')
        parsed_location = urlparse(location)
        if not parsed_location.netloc:
            location = '%s://%s%s' % (parsed_url.scheme, domain, parsed_location.path)
        return self.request(method, location, **original_kwargs)

    @staticmethod
    def extract_js(body):
        js = re.search(r'setTimeout\(function\(\){\s+(var '
                       's,t,o,p,b,r,e,a,k,i,n,g,f.+?\r?\n[\s\S]+?a\.value =.+?)\r?\n', body).group(1)
        js = re.sub(r'a\.value\s=\s([+]?.+?)\s?\+\s?[^.]+\.length.*', r'\1', js)
        js = re.sub(r'a\.value\s=\s(parseInt\(.+?\)).+', r'\1', js)
        js = re.sub(r'\s{3,}[a-z](?: = |\.).+', '', js)
        js = re.sub(r';\s+;', ';', js)

        # Strip characters that could be used to exit the string context
        # These characters are not currently used in Cloudflare's arithmetic snippet
        js = re.sub(r'[\n\\"]', '', js)

        if 'toFixed' not in js:
            raise ValueError('Error Cloudflare IUAM JavaScript changed, contact SickGear IRC')

        return js

    @classmethod
    def create_scraper(cls, sess=None, **kwargs):
        """
        Convenience function for creating a ready-to-go CloudflareScraper object.
        """
        scraper = cls(**kwargs)

        if sess:
            attrs = ['auth', 'cert', 'cookies', 'headers', 'hooks', 'params', 'proxies', 'data']
            for attr in attrs:
                val = getattr(sess, attr, None)
                if val:
                    setattr(scraper, attr, val)

        return scraper

    # Functions for integrating cloudflare-scrape with other applications and scripts

    @classmethod
    def get_tokens(cls, url, user_agent=None, **kwargs):
        scraper = cls.create_scraper()
        if user_agent:
            scraper.headers['User-Agent'] = user_agent

        # noinspection PyUnusedLocal
        try:
            resp = scraper.get(url, **kwargs)
            resp.raise_for_status()
        except Exception as e:
            logging.error('[%s] returned an error. Could not collect tokens.' % url)
            raise

        domain = urlparse(resp.url).netloc
        # cookie_domain = None

        for d in scraper.cookies.list_domains():
            if d.startswith('.') and d in ('.' + domain):
                cookie_domain = d
                break
        else:
            raise ValueError('Unable to find Cloudflare cookies.'
                             ' Does the site actually have Cloudflare IUAM (\'I\'m Under Attack Mode\') enabled?')

        return ({'__cfduid': scraper.cookies.get('__cfduid', '', domain=cookie_domain),
                 'cf_clearance': scraper.cookies.get('cf_clearance', '', domain=cookie_domain)
                 },
                scraper.headers['User-Agent'])

    @classmethod
    def get_cookie_string(cls, url, user_agent=None):
        """
        Convenience function for building a Cookie HTTP header value.
        """
        tokens, user_agent = cls.get_tokens(url, user_agent=user_agent, **kwargs)
        return '; '.join('='.join(pair) for pair in tokens.items()), user_agent


create_scraper = CloudflareScraper.create_scraper
get_tokens = CloudflareScraper.get_tokens
get_cookie_string = CloudflareScraper.get_cookie_string
