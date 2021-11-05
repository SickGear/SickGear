from requests.exceptions import RequestException
from requests.models import Response
from requests.sessions import Session

import logging
import random
import re
import time

from _23 import b64encodestring, urlparse


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


class CloudflareError(RequestException):
    pass


class CloudflareScraper(Session):
    def __init__(self, **kwargs):
        super(CloudflareScraper, self).__init__()

        if 'requests' in self.headers['User-Agent']:
            # Set a random User-Agent if no custom User-Agent has been set
            self.headers['User-Agent'] = random.choice(DEFAULT_USER_AGENTS)
        self.cf_ua = self.headers['User-Agent']

        self.default_delay = 8
        self.delay = kwargs.pop('delay', self.default_delay)
        self.start_time = None

        self.trust_env = False

    def request(self, method, url, *args, **kwargs):
        url_solver = kwargs.pop('url_solver', None)

        if not kwargs.pop('proxy_browser', None):
            resp = super(CloudflareScraper, self).request(method, url, *args, **kwargs)
        else:
            resp = self.get_content(method, url, url_solver,
                                    user_agent=self.headers.get('User-Agent'), proxy_browser=True, **kwargs)

        if (isinstance(resp, type(Response()))
                and resp.status_code in (503, 429, 403)):
            self.start_time = time.time()
            if (re.search('(?i)cloudflare', resp.headers.get('Server', ''))
                    and b'jschl_vc' in resp.content
                    and b'jschl_answer' in resp.content):
                resp = self.solve_cf_challenge(resp, url_solver, **kwargs)
            elif b'ddgu' in resp.content:
                resp = self.solve_ddg_challenge(resp, **kwargs)

        return resp

    def wait(self):
        delay = self.delay - (time.time() - self.start_time)
        time.sleep((0, delay)[0 < delay])  # required delay before solving the challenge

    def solve_ddg_challenge(self, resp, **original_kwargs):
        parsed_url = urlparse(resp.url)
        try:
            submit_url = parsed_url.scheme + ':' + re.findall('"frm"[^>]+?action="([^"]+)"', resp.text)[0]
            kwargs = {k: v for k, v in original_kwargs.items() if k not in ['hooks']}
            kwargs.setdefault('headers', {})
            kwargs.setdefault('data', dict(
                h=b64encodestring('%s://%s' % (parsed_url.scheme, parsed_url.hostname)),
                u=b64encodestring(parsed_url.path), p=b64encodestring(parsed_url.port or '')
            ))
            self.wait()
            resp = self.request('POST', submit_url, **kwargs)
        except (BaseException, Exception):
            pass
        return resp

    def test_flaresolverr(self, url_solver):
        # test if FlareSolverr software is running
        response_test = super(CloudflareScraper, self).request('GET', url_solver)
        fs_ver = None
        if 200 == response_test.status_code and response_test.ok:
            json_data = response_test.json()
            if any([json_data.get('version')]):
                fs_ver = json_data.get('version')
        if None is fs_ver:
            raise ValueError('FlareSolverr software not found (is it running?)')
        return fs_ver

    def get_content(self, method, url, url_solver, user_agent, proxy_browser=False, **kwargs):

        url_solver = url_solver and re.sub(r'(/|v1)*$', '', url_solver) or 'http://localhost:8191'
        if not self.test_flaresolverr(url_solver):
            raise ValueError('No FlareSolverr software running %sat %s' % (('to solve Cloudflare challenge ',
                                                                            '')[proxy_browser], url_solver))
        try:
            params = {} if 'v1' not in self.test_flaresolverr(url_solver) else dict(userAgent=user_agent)
            params.update(dict(
                cmd='request.%s' % method.lower(), url=url,
                cookies=[{'name': cur_ckee.name, 'value': cur_ckee.value,
                          'domain': cur_ckee.domain, 'path': cur_ckee.path} for cur_ckee in self.cookies]))
            response = super(CloudflareScraper, self).request('POST', '%s/v1' % url_solver, json=params)
        except(BaseException, Exception) as e:
            raise ValueError('FlareSolverr software unable to %s: %r' % (('solve Cloudflare anti-bot IUAM challenge',
                                                                          'fetch content')[proxy_browser], e))
        if None is not response:
            data_json = response.json()
            result = ({}, data_json)[isinstance(data_json, (dict, list))]
            if response.ok:
                if 'ok' == result.get('status'):
                    self.cookies.clear()
                    for cur_ckee in result.get('solution', {}).get('cookies', []):
                        if cur_ckee.get('value') and cur_ckee.get('name') not in ('', None, '_gid', '_ga', '_gat'):
                            self.cookies.set(
                                cur_ckee['name'], cur_ckee['value'],
                                rest={'httpOnly': cur_ckee.get('httpOnly'), 'session': cur_ckee.get('session')},
                                **dict([(k, cur_ckee.get(k)) for k in ('expires', 'domain', 'path', 'secure')]))
                else:
                    response = None
            elif 'error' == result.get('status'):
                raise ValueError('Failure with FlareSolverr: %s' % result.get('message', 'See the FlareSolver output'))

        return response

    def solve_cf_challenge(self, resp, url_solver, **original_kwargs):
        body = resp.text
        parsed_url = urlparse(resp.url)
        domain = parsed_url.netloc

        if '/cdn-cgi/l/chk_captcha' in body or 'cf_chl_captcha' in body:
            raise CloudflareError(
                'Cloudflare captcha presented for %s, safe to ignore as this shouldn\'t happen every time, ua: %s' %
                (domain, self.cf_ua), response=resp)

        final_response = self.get_content(
                'GET', (resp.request.url, '%s://%s/' % (parsed_url.scheme, domain))['POST' == resp.request.method],
                url_solver, user_agent=resp.request.headers.get('User-Agent'))
        if None is final_response:
            raise ValueError('Failed to validate Cloudflare anti-bot IUAM challenge')

        return final_response

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

        try:
            resp = scraper.get(url, **kwargs)
            resp.raise_for_status()
        except (BaseException, Exception):
            logging.error('[%s] returned an error. Could not collect tokens.' % url)
            raise

        domain = urlparse(resp.url).netloc

        for d in scraper.cookies.list_domains():
            if d.startswith('.') and d in ('.' + domain):
                cookie_domain = d
                break
        else:
            raise ValueError('Unable to find Cloudflare cookies.'
                             ' Does the site actually have Cloudflare IUAM (\'I\'m Under Attack Mode\') enabled?')

        return (
            {'__cfduid': scraper.cookies.get('__cfduid', '', domain=cookie_domain),
             'cf_clearance': scraper.cookies.get('cf_clearance', '', domain=cookie_domain)},
            scraper.headers['User-Agent'])

    @classmethod
    def get_cookie_string(cls, url, user_agent=None, **kwargs):
        """
        Convenience function for building a Cookie HTTP header value.
        """
        tokens, user_agent = cls.get_tokens(url, user_agent=user_agent, **kwargs)
        return '; '.join(['='.join(pair) for pair in tokens.items()]), user_agent


create_scraper = CloudflareScraper.create_scraper
get_tokens = CloudflareScraper.get_tokens
get_cookie_string = CloudflareScraper.get_cookie_string
