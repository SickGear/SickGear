import sys
import warnings
warnings.filterwarnings('ignore', module=r'.*fuz.*', message='.*Sequence.*')

import time
import unittest
from os.path import abspath, dirname, join

sys.path.insert(1, abspath(join(dirname(__file__), '..')))
sys.path.insert(1, abspath(join(dirname(__file__), '..', 'lib')))

import sickgear
from sickgear.providers.thepiratebay import ThePirateBayProvider


class ValidHomeTests(unittest.TestCase):
    """ a remembered provider home is tried first only while it is still a listed home """
    home, home2, gone = 'https://thepiratebay.org/', 'https://www.thepiratebay.org/', 'https://gone-mirror.org/'

    def setUp(self):
        self.org_homes = sickgear.PROVIDER_HOMES
        sickgear.PROVIDER_HOMES = {}
        self.fetched = []
        self.provider = ThePirateBayProvider()
        self.provider.enabled = True
        self.provider.url_home = [self.home, self.home2]
        self.provider.should_skip = lambda *args, **kwargs: False
        self.provider.save_main_config = lambda *args, **kwargs: None
        self.provider.get_url = self.fake_get_url

    def tearDown(self):
        sickgear.PROVIDER_HOMES = self.org_homes

    def fake_get_url(self, url, **kwargs):
        self.fetched.append(url)
        return f'{"x" * 40} The Pirate Bay page'

    def remember(self, url, expire):
        sickgear.PROVIDER_HOMES[self.provider.get_id()] = (url, int(time.time()) + expire)

    def test_home_no_longer_listed_is_dropped(self):
        self.remember(self.gone, 60 * 60)  # a valid expiry would take the first home without a page check
        self.assertEqual(self.home, self.provider._valid_home())
        self.assertEqual([self.home], self.fetched)
        self.assertEqual(self.home, sickgear.PROVIDER_HOMES[self.provider.get_id()][0])

    def test_listed_home_is_tried_first(self):
        self.remember(self.home2, -1)
        self.assertEqual(self.home2, self.provider._valid_home())
        self.assertEqual([self.home2], self.fetched)


if '__main__' == __name__:
    suite = unittest.TestLoader().loadTestsFromTestCase(ValidHomeTests)
    unittest.TextTestRunner(verbosity=2).run(suite)
