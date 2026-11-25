import sys
import unittest
from os.path import abspath, dirname, join

sys.path.insert(1, abspath(join(dirname(__file__), '..')))
sys.path.insert(1, abspath(join(dirname(__file__), '..', 'lib')))

from sickgear.notifiers.emby import EmbyNotifier


class CheckConfigLogTests(unittest.TestCase):
    """ a setting with more hosts than api keys is warned about once, the same setting again logs a debug line """

    def setUp(self):
        EmbyNotifier.warned_config = None
        self.lines = []
        self.client = EmbyNotifier()
        self.client._log_warning = lambda msg: self.lines.append(('warning', msg))
        self.client._log_debug = lambda msg: self.lines.append(('debug', msg))

    def levels(self):
        return [_l for _l, _ in self.lines]

    def test_same_setting_warns_once(self):
        for _ in range(3):
            self.assertEqual((False, False, 'Not enough Api keys for hosts'),
                             self.client.check_config('host1,host2', 'key1'))
        self.assertEqual(['warning', 'debug', 'debug'], self.levels())

    def test_changed_setting_warns_again(self):
        self.client.check_config('host1,host2', 'key1')
        self.client.check_config('host1', 'key1,key2')
        self.assertEqual(['warning', 'warning'], self.levels())

    def test_good_setting_then_same_bad_one_warns_again(self):
        self.client.check_config('host1,host2', 'key1')
        self.assertEqual((['host1'], ['key1'], 'OK'), self.client.check_config('host1', 'key1'))
        self.client.check_config('host1,host2', 'key1')
        self.assertEqual(['warning', 'warning'], self.levels())


if '__main__' == __name__:
    unittest.main()
