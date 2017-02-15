import unittest

import sys
import os.path
sys.path.insert(1, os.path.abspath('..'))

from sickbeard import common


class QualityTests(unittest.TestCase):

    def check_quality_names(self, quality, cases):
        for fn in cases:
            second = common.Quality.nameQuality(fn)
            self.assertEqual(quality, second, 'fail %s != %s for case: %s' % (quality, second, fn))

    # TODO: repack / proper ? air-by-date ? season rip? multi-ep?

    def test_SDTV(self):

        self.assertEqual(common.Quality.compositeStatus(common.DOWNLOADED, common.Quality.SDTV),
                         common.Quality.statusFromName('Test.Show.S01E02-GROUP.mkv'))

        self.check_quality_names(common.Quality.SDTV, [
            'Test.Show.S01E02.PDTV.XViD-GROUP',
            'Test.Show.S01E02.PDTV.x264-GROUP',
            'Test.Show.S01E02.HDTV.XViD-GROUP',
            'Test.Show.S01E02.HDTV.x264-GROUP',
            'Test.Show.S01E02.DSR.XViD-GROUP',
            'Test.Show.S01E02.DSR.x264-GROUP',
            'Test.Show.S01E02.TVRip.XViD-GROUP',
            'Test.Show.S01E02.TVRip.x264-GROUP',
            'Test.Show.S01E02.WEBRip.XViD-GROUP',
            'Test.Show.S01E02.WEBRip.x264-GROUP',
            'Test.Show.S01E02.Web-Rip.x264.GROUP',
            'Test.Show.S01E02.WEB-DL.x264-GROUP',
            'Test.Show.S01E02.WEB-DL.AAC2.0.H.264-GROUP',
            'Test.Show.S01E02 WEB-DL H 264-GROUP',
            'Test.Show.S01E02_WEB-DL_H_264-GROUP',
            'Test.Show.S01E02.WEB-DL.AAC2.0.H264-GROUP',
            'Test.Show.S01E02.HDTV.AAC.2.0.x264-GROUP',
            'Test.Show.S01E02.HDTV.DD5.1.XViD-GROUP',
            'Test.Show.S01E02.HDTV.DD7.1.h.264-GROUP',
            'Test.Show.S01E02.WEB-DL.DD5.1.h.264-GROUP',
            'Test.Show.S01E02.WEB.h264-GROUP',
            'Test.Show.S01E02.WEB.x264-GROUP',
            'Test.Show.S01E02.WEB.h265-GROUP',
            'Test.Show.S01E02.WEB.x265-GROUP',
            'Test.Show.S01E02.WEBRip.h264-GROUP',
            'Test.Show.S01E02.WEBRip.x264-GROUP'])

    def test_SDDVD(self):
        self.check_quality_names(common.Quality.SDDVD, [
            'Test.Show.S01E02.DVDRiP.XViD-GROUP',
            'Test.Show.S01E02.DVDRiP.DiVX-GROUP',
            'Test.Show.S01E02.DVDRiP.x264-GROUP',
            'Test.Show.S01E02.DVDRip.WS.XViD-GROUP',
            'Test.Show.S01E02.DVDRip.WS.DiVX-GROUP',
            'Test.Show.S01E02.DVDRip.WS.x264-GROUP',
            'Test.Show-S01E02-Test.Dvd Rip',
            'Test.Show.S01E02.BDRIP.XViD-GROUP',
            'Test.Show.S01E02.BDRIP.DiVX-GROUP',
            'Test.Show.S01E02.BDRIP.x264-GROUP',
            'Test.Show.S01E02.BDRIP.WS.XViD-GROUP',
            'Test.Show.S01E02.BDRIP.WS.DiVX-GROUP',
            'Test.Show.S01E02.BDRIP.WS.x264-GROUP'])

    def test_HDTV(self):
        self.check_quality_names(common.Quality.HDTV, [
            'Test.Show.S01E02.720p.HDTV.x264-GROUP',
            'Test.Show.S01E02.HR.WS.PDTV.x264-GROUP',
            'Test.Show.S01E02.720p.AHDTV.x264-GROUP'])

    def test_RAWHDTV(self):
        self.check_quality_names(common.Quality.RAWHDTV, [
            'Test.Show.S01E02.720p.HDTV.DD5.1.MPEG2-GROUP',
            'Test.Show.S01E02.1080i.HDTV.DD2.0.MPEG2-GROUP',
            'Test.Show.S01E02.1080i.HDTV.H.264.DD2.0-GROUP',
            'Test Show - S01E02 - 1080i HDTV MPA1.0 H.264 - GROUP',
            'Test.Show.S01E02.1080i.HDTV.DD.5.1.h264-GROUP'])

    def test_FULLHDTV(self):
        self.check_quality_names(common.Quality.FULLHDTV, [
            'Test.Show.S01E02.1080p.HDTV.x264-GROUP',
            'Test.Show.S01E02.1080p.AHDTV.x264-GROUP'])

    def test_HDWEBDL(self):
        self.check_quality_names(common.Quality.HDWEBDL, [
            'Test.Show.S01E02.720p.WEB-DL-GROUP',
            'Test.Show.S01E02.720p.WEBRip-GROUP',
            'Test.Show.S01E02.WEBRip.720p.H.264.AAC.2.0-GROUP',
            'Test.Show.S01E02.720p.WEB-DL.AAC2.0.H.264-GROUP',
            'Test Show S01E02 720p WEB-DL AAC2 0 H 264-GROUP',
            'Test_Show.S01E02_720p_WEB-DL_AAC2.0_H264-GROUP',
            'Test.Show.S01E02.720p.WEB-DL.AAC2.0.H264-GROUP',
            'Test.Show.S01E02.720p.iTunes.Rip.H264.AAC-GROUP',
            'Test.Show.s01e02.WEBDL.720p.GROUP',
            'Test Show s01e02 WEBDL 720p GROUP',
            'Test Show S01E02 720p WEB-DL AVC-GROUP',
            'Test.Show.S01E02.WEB-RIP.720p.GROUP',
            'Test.Show.S01E02.720p.WEB.h264-GROUP',
            'Test.Show.S01E02.720p.WEB.x264-GROUP',
            'Test.Show.S01E02.720p.WEB.h265-GROUP',
            'Test.Show.S01E02.720p.WEB.x265-GROUP',
            'Test.Show.S01E02.720p.WEBRip.h264-GROUP',
            'Test.Show.S01E02.720p.WEBRip.x264-GROUP'])

    def test_FULLHDWEBDL(self):
        self.check_quality_names(common.Quality.FULLHDWEBDL, [
            'Test.Show.S01E02.1080p.WEB-DL-GROUP',
            'Test.Show.S01E02.1080p.WEBRip-GROUP',
            'Test.Show.S01E02.WEBRip.1080p.H.264.AAC.2.0-GROUP',
            'Test.Show.S01E02.WEBRip.1080p.H264.AAC.2.0-GROUP',
            'Test.Show.S01E02.1080p.iTunes.H.264.AAC-GROUP',
            'Test Show S01E02 1080p iTunes H 264 AAC-GROUP',
            'Test_Show_S01E02_1080p_iTunes_H_264_AAC-GROUP',
            'Test.Show.s01e02.WEBDL.1080p.GROUP',
            'Test Show s01e02 WEBDL 1080p GROUP',
            'Test Show S01E02 1080p WEB-DL AVC-GROUP',
            'Test.Show.S01E02.WEB-RIP.1080p.GROUP',
            'Test.Show.S01E02.1080p.WEB.h264-GROUP',
            'Test.Show.S01E02.1080p.WEB.x264-GROUP',
            'Test.Show.S01E02.1080p.WEB.h265-GROUP',
            'Test.Show.S01E02.1080p.WEB.x265-GROUP',
            'Test.Show.S01E02.1080p.WEBRip.h264-GROUP',
            'Test.Show.S01E02.1080p.WEBRip.x264-GROUP'])

    def test_HDBLURAY(self):
        self.check_quality_names(common.Quality.HDBLURAY, [
            'Test.Show.S01E02.720p.BluRay.x264-GROUP',
            'Test.Show.S01E02.720p.HDDVD.x264-GROUP',
            'Test.Show.S01E02.720p.Blu-ray.x264-GROUP'])

    def test_FULLHDBLURAY(self):
        self.check_quality_names(common.Quality.FULLHDBLURAY, [
            'Test.Show.S01E02.1080p.BluRay.x264-GROUP',
            'Test.Show.S01E02.1080p.HDDVD.x264-GROUP',
            'Test.Show.S01E02.1080p.Blu-ray.x264-GROUP',
            'Test Show S02 1080p Remux AVC FLAC 5.1'])

    def test_UHD4KWEB(self):
        self.check_quality_names(common.Quality.UHD4KWEB, [
            'Test.Show.S01E02.2160p.WEBRip.h264-GROUP',
            'Test.Show.S01E02.2160p.WEBRip.x264-GROUP',
            'Test.Show.S01E02.2160p.WEBRip.x265-GROUP'])

    def test_UNKNOWN(self):
        self.check_quality_names(common.Quality.UNKNOWN, ['Test.Show.S01E02-SiCKGEAR'])

    def test_reverse_parsing(self):
        self.check_quality_names(common.Quality.SDTV, ['Test Show - S01E02 - SD TV - GROUP'])
        self.check_quality_names(common.Quality.SDDVD, ['Test Show - S01E02 - SD DVD - GROUP'])
        self.check_quality_names(common.Quality.HDTV, ['Test Show - S01E02 - HD TV - GROUP'])
        self.check_quality_names(common.Quality.RAWHDTV, ['Test Show - S01E02 - RawHD TV - GROUP'])
        self.check_quality_names(common.Quality.FULLHDTV, ['Test Show - S01E02 - 1080p HD TV - GROUP'])
        self.check_quality_names(common.Quality.HDWEBDL, ['Test Show - S01E02 - 720p WEB-DL - GROUP'])
        self.check_quality_names(common.Quality.FULLHDWEBDL, ['Test Show - S01E02 - 1080p WEB-DL - GROUP'])
        self.check_quality_names(common.Quality.HDBLURAY, ['Test Show - S01E02 - 720p BluRay - GROUP'])
        self.check_quality_names(common.Quality.FULLHDBLURAY, ['Test Show - S01E02 - 1080p BluRay - GROUP'])
        self.check_quality_names(common.Quality.UNKNOWN, ['Test Show - S01E02 - Unknown - SiCKGEAR'])

if __name__ == '__main__':
    suite = unittest.TestLoader().loadTestsFromTestCase(QualityTests)
    unittest.TextTestRunner(verbosity=2).run(suite)
