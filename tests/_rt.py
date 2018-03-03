import unittest

import sys
import os.path

sys.path.insert(1, os.path.abspath('..'))
sys.path.insert(1, os.path.abspath('../lib'))

import sickbeard
from sickbeard import logger
import time

TESTDIR = os.path.abspath('.')
sickbeard.LOG_DIR = os.path.join(TESTDIR, 'Logs')
sickbeard.logger.sb_log_instance.init_logging(False)

from lib.rtorrent import RTorrent

class HelperTests(unittest.TestCase):
    host = 'scgi://localhost:32467/'
    username = password = None
    path = '/home/scouseman/torrents/tv'
    label = 'sg2'
    hash = '0B5CBDD3F9999F6015A8DCD3053CE3E288C2EDAD'

    auth = None

    def test_rtorrent(self):
        try:
            logger.log('Test case: for rTorrent (start log)')
            self.auth = RTorrent(self.host, self.username, self.password, True)

            if self.auth:
                logger.log('Details:%s %s %s, client version:%s' % (
                    self.host, self.username, self.password, self.auth._client_version_tuple))

                logger.log(self.auth._get_load_function('url', False, False))

                result = self.state(self.hash, pause=True)
                logger.log('pause: %r' % result)
                time.sleep(10)
                self.state(self.hash, pause=False)
                logger.log('resume: %r' % result)

                # logger.log(self.auth._get_conn().system.listMethods())
            else:
                logger.log('No rT Object')

        except AssertionError:
            pass

    def state(self, btih, pause=None):
        result = None

        if self.auth and None is not pause:
            torrent = self.auth.find_torrent(btih)
            logger.log('find : %r' % torrent)
            if None is torrent:
                return False

            if None is not pause:
                result = getattr(torrent, ('resume', 'pause')[pause])()

        return result

logger.log('Test case: for rTorrent (end log)')

if __name__ == '__main__':
    suite = unittest.TestLoader().loadTestsFromTestCase(HelperTests)
    unittest.TextTestRunner(verbosity=2).run(suite)
