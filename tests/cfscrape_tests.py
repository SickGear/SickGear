# -*- coding: utf-8 -*-

import os.path
import sys
import unittest

from cfscrape__init__ import challenge_responses, requested_page, url

sys.path.insert(1, os.path.abspath('../lib'))

import cfscrape


class TestCase(unittest.TestCase):

    def check_resp(self, u, **kwargs):
        scraper = cfscrape.CloudflareScraper(**kwargs)
        resp = scraper.get(u)
        self.assertEqual(resp and resp.content, requested_page)

    @challenge_responses(filename='js_challenge_10_04_2019.html', jschl_answer='18.8766915031')
    def test_js_challenge_10_04_2019(self, **kwargs):
        return self.check_resp(url, **kwargs)

    @challenge_responses(filename='js_challenge_21_03_2019.html', jschl_answer='13.0802397598')
    def test_js_challenge_21_03_2019(self, **kwargs):
        return self.check_resp(url, **kwargs)

    @challenge_responses(filename='js_challenge_13_03_2019.html', jschl_answer='38.5879578333')
    def test_js_challenge_13_03_2019(self, **kwargs):
        return self.check_resp(url, **kwargs)

    @challenge_responses(filename='js_challenge_03_12_2018.html', jschl_answer='10.66734594')
    def test_js_challenge_03_12_2018(self, **kwargs):
        return self.check_resp(url, **kwargs)

    @challenge_responses(filename='js_challenge_09_06_2016.html', jschl_answer='6648')
    def test_js_challenge_09_06_2016(self, **kwargs):
        return self.check_resp(url, **kwargs)

    @challenge_responses(filename='js_challenge_21_05_2015.html', jschl_answer='649')
    def test_js_challenge_21_05_2015(self, **kwargs):
        return self.check_resp(url, **kwargs)


if __name__ == '__main__':
    suite = unittest.TestLoader().loadTestsFromTestCase(TestCase)
    unittest.TextTestRunner(verbosity=2).run(suite)
