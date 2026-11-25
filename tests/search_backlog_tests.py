import sys
import time
import unittest
from unittest import mock
from os.path import abspath, dirname, join

sys.path.insert(1, abspath(join(dirname(__file__), '..')))
sys.path.insert(1, abspath(join(dirname(__file__), '..', 'lib')))

import sickgear
from sickgear import search_backlog
from sickgear.providers.generic import GenericProvider


class FakeProvider(object):
    def __init__(self, provider_type, backlog=True, scheduled=True):
        self.providerType = provider_type
        self.enable_backlog = backlog
        self.enable_scheduled_backlog = scheduled

    @staticmethod
    def is_active():
        return True


class SkipWithinADayTests(unittest.TestCase):
    """ a scheduled backlog within a day of the last one goes on only for a torrent provider set for scheduled backlog,
    else it is skipped with a debug line, and it does not warn that no provider has backlog searching """

    def run_backlog(self, providers):
        lines = []
        searcher = search_backlog.BacklogSearcher.__new__(search_backlog.BacklogSearcher)
        with mock.patch.object(sickgear.providers, 'sorted_sources', return_value=providers), \
                mock.patch.object(search_backlog.BacklogSearcher, '_get_last_runtime', return_value=time.time() - 3600), \
                mock.patch.object(search_backlog.BacklogSearcher, '_get_last_backlog',
                                  side_effect=RuntimeError('the run went on')), \
                mock.patch.object(search_backlog.logger, 'warning', side_effect=lambda m: lines.append(('warning', m))), \
                mock.patch.object(search_backlog.logger, 'debug', side_effect=lambda m: lines.append(('debug', m))):
            try:
                searcher.search_backlog()
            except RuntimeError as e:
                lines.append(('run', str(e)))
        return lines

    def test_torrent_backlog_without_scheduled_is_skipped(self):
        lines = self.run_backlog([FakeProvider(GenericProvider.NZB),
                                  FakeProvider(GenericProvider.TORRENT, scheduled=False)])
        self.assertEqual([('debug', 'Last scheduled backlog run was within the last day, skipping this run.')], lines)

    def test_torrent_scheduled_backlog_goes_on(self):
        lines = self.run_backlog([FakeProvider(GenericProvider.TORRENT)])
        self.assertEqual([('run', 'the run went on')], lines)


if '__main__' == __name__:
    unittest.main()
