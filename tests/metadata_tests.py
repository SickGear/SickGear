import sys
import unittest
from os.path import abspath, dirname, join
from unittest import mock

sys.path.insert(1, abspath(join(dirname(__file__), '..')))
sys.path.insert(1, abspath(join(dirname(__file__), '..', 'lib')))

from sickgear.indexermapper import MapStatus
from sickgear.metadata import generic
from sickgear.metadata.generic import GenericMetadata
from tvinfo_base.base import TVINFO_TVDB, TVINFO_TVMAZE


class ValidShowTests(unittest.TestCase):
    """ a show that a tv info source does not return is logged with the name of that source, a warning for the source
    of the show and for an id the user locked, a debug line for another source, which only gives images """

    def check(self, tvid, status=MapStatus.NONE):
        lines = []
        show_obj = mock.Mock(tvid=TVINFO_TVMAZE, ids={TVINFO_TVDB: {'id': 457634, 'status': status}})
        show_obj.name = "The Captive's War"
        with mock.patch.object(generic.logger, 'warning', side_effect=lambda m: lines.append(('warning', m))), \
                mock.patch.object(generic.logger, 'debug', side_effect=lambda m: lines.append(('debug', m))):
            self.assertFalse(GenericMetadata._valid_show(None, show_obj, tvid))
        return lines

    def test_own_source(self):
        self.assertEqual([('warning', "Show The Captive's War not found on TVmaze")], self.check(None))

    def test_other_source(self):
        self.assertEqual([('debug', "Show The Captive's War not found on TheTVDB")], self.check(TVINFO_TVDB))

    def test_other_source_locked_id(self):
        self.assertEqual([('warning', "Show The Captive's War not found on TheTVDB, for the locked id 457634")],
                         self.check(TVINFO_TVDB, MapStatus.NO_AUTOMATIC_CHANGE))


if '__main__' == __name__:
    unittest.main()
