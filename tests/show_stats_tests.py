import datetime
import unittest

import test_lib as test

from sickgear.common import Quality, DOWNLOADED, SNATCHED, SKIPPED, WANTED, UNAIRED, ARCHIVED
from sickgear.webserve import Home


class ShowStatsTests(test.SickbeardTestDBCase):
    """ the downloaded, snatched and total episodes of a show, the figures of the Downloads column of the show list and of
    the bulk change page """

    def add_episodes(self, tvid, prodid, *episodes):
        with test.db.DBConnection() as sg_db:
            for cur_ep, (cur_status, cur_days_ago) in enumerate(episodes, 1):
                airdate = (datetime.date.today() - datetime.timedelta(days=cur_days_ago)).toordinal()
                sg_db.action('INSERT INTO tv_episodes (indexer, showid, season, episode, airdate, status, location)'
                             ' VALUES (?, ?, 1, ?, ?, ?, ?)', [tvid, prodid, cur_ep, airdate, cur_status, ''])

    def test_counts_of_a_show(self):
        self.add_episodes(
            1, 100,
            (Quality.composite_status(DOWNLOADED, Quality.HDTV), 30),
            (Quality.composite_status(ARCHIVED, Quality.SDTV), 29),
            (Quality.composite_status(SNATCHED, Quality.HDTV), 3),
            (SKIPPED, 20),
            (WANTED, 2),
            (UNAIRED, -7))
        stat = Home.show_stats()['1:100']
        self.assertEqual((2, 1, 5), (stat['ep_downloaded'], stat['ep_snatched'], stat['ep_total']))

    def test_each_show_has_its_own_figures(self):
        self.add_episodes(1, 100, (Quality.composite_status(DOWNLOADED, Quality.HDTV), 30))
        self.add_episodes(3, 200, (WANTED, 5), (WANTED, 4))
        stats = Home.show_stats()
        self.assertEqual((1, 1), (stats['1:100']['ep_downloaded'], stats['1:100']['ep_total']))
        self.assertEqual((0, 2), (stats['3:200']['ep_downloaded'], stats['3:200']['ep_total']))


if '__main__' == __name__:
    unittest.main()
