# coding=utf-8
import unittest

import sys
import os.path
sys.path.append(os.path.abspath('..'))

import sickbeard
# from sickbeard.helpers import get_wanted
from sickbeard import logger
TESTDIR = os.path.abspath('.')
sickbeard.LOG_DIR = os.path.join(TESTDIR, 'Logs')
sickbeard.logger.sb_log_instance.init_logging(False)

class HelperTests(unittest.TestCase):
    """
    searchIndexersForShowName() search test terms (add show search)

    chäos;head
    luksusfælden
    pokémon
    """

    def test_get_wanted(self):

        return
        sickbeard.DATA_DIR = u'I:\\_Incoming\\downloaders\\usenet\\sick-beard\\git\\DataSG'
        just_select = True
        exclude = False

        logger.log('Unbreakable Kimmy Schmidt')
        show_id = 281593
        get_wanted(show_id, 3, True, just_select, exclude)
        get_wanted(show_id, 3, False, just_select, exclude)
        get_wanted(show_id, -1, True, just_select, exclude)
        get_wanted(show_id, -1, False, just_select, exclude)

        logger.log('Hoc')
        show_id = 262980
        get_wanted(show_id, 3, True, just_select, exclude)
        get_wanted(show_id, 3, False, just_select, exclude)
        get_wanted(show_id, -1, True, just_select, exclude)
        get_wanted(show_id, -1, False, just_select, exclude)

        logger.log('Powers 2015')
        show_id = 286943
        get_wanted(show_id, 3, True, just_select, exclude)
        get_wanted(show_id, 3, False, just_select, exclude)
        get_wanted(show_id, -1, True, just_select, exclude)
        get_wanted(show_id, -1, False, just_select, exclude)

        logger.log('Broke Girls')
        show_id = 248741
        get_wanted(show_id, 3, True, just_select, exclude)
        get_wanted(show_id, 3, False, just_select, exclude)
        get_wanted(show_id, -1, True, just_select, exclude)
        get_wanted(show_id, -1, False, just_select, exclude)

if __name__ == '__main__':
    suite = unittest.TestLoader().loadTestsFromTestCase(HelperTests)
    unittest.TextTestRunner(verbosity=2).run(suite)
