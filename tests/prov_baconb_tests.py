# Tests for tvchaos
# copy these into the provider file and then do
#   self.tests()
# or run the following in the evaluation window when results are fully populated
"""
from sickbeard.common import Quality
r = [Quality.qualityStrings[Quality.sceneQuality(
    x[0]
)] for x in results]

list of results...
'\n'.join([x[0] for x in results])
store input parsed () by adding the following just before the call to regulate_title..
rtitles += [title]
and at the top of the func
rtitles = []
then when collectng results ...
rtitle:  '\n'.join(rtitles)
"""


class TvcTest:
    def __init__(self):
        pass

    def tests(self):
        for t in [
            ('showname - s02e04 [HDTV / x264 / AAC / MKV / SD]', 'showname.s02e04.[AAC.SD].HDTV.x264.MKV', 'SD TV'),
            ('showname - Season 1 [HDTV / Xvid / MP3 / AVI / 480p]', 'showname.Season 1.[MP3].480p.HDTV.Xvid.AVI', 'SD TV'),
            ('showname - Series w/ Extras [DVDRip / XviD / MP3 / AVI / SD]', 'showname.Series.w.Extras.[MP3.SD].DVDRip.XviD.AVI', 'SD DVD'),

            ('showname S03E12 [HDTV / x264 / AC3 / MKV / 720p / PROPER]', 'showname S03E12.[AC3].PROPER.720p.HDTV.x264.MKV', 'HD TV'),
            ('showname - Season 1 [WEBRip / X264 / AC3 / MKV / 720P / REPACK]', 'showname.Season 1.[AC3].REPACK.720p.WEBRip.X264.MKV', '720p WEB-DL'),

            ('showname - Season 1 [HDTV / x264 / MKV / AC3 / 720p]', 'showname.Season 1.[AC3].720p.HDTV.x264.MKV', 'HD TV'),
            ('showname - S01E01 [HDTV / x264 / AAC / MKV / 720p]', 'showname.S01E01.[AAC].720p.HDTV.x264.MKV', 'HD TV'),
            ('showname - Season 2 [HDTV / x264 / AC3 / MKV / 720p]', 'showname.Season 2.[AC3].720p.HDTV.x264.MKV', 'HD TV'),
            ('showname - Season 2 [HDTV / x264 / AC-3 / MKV / 720p]', 'showname.Season 2.[AC-3].720p.HDTV.x264.MKV', 'HD TV'),
            ('showname - Season 2 [HDTV / x264 / AC-3 / MKV / 720p / w. Subtitles]', 'showname.Season 2.[AC-3.w..Subtitles].720p.HDTV.x264.MKV', 'HD TV'),

            ('showname - Season 01 (2011) [ WEB-DL / x264 / AAC / MKV / 720p ]', 'showname.Season 01 (2011).[AAC].720p.WEB-DL.x264.MKV', '720p WEB-DL'),
            ('showname - Season 4 [WEB-DL / H.264 / AC3 / MKV / 720p]', 'showname.Season 4.[AC3].720p.WEB-DL.H.264.MKV', '720p WEB-DL'),
            ('showname - Season 4 [WEB-DL / H.264 / AC-3 / MKV / 720p]', 'showname.Season 4.[AC-3].720p.WEB-DL.H.264.MKV', '720p WEB-DL'),
            ('showname - S04E17 [WEBRIP / H264 / AAC / MKV / 720p]', 'showname.S04E17.[AAC].720p.WEBRIP.H264.MKV', '720p WEB-DL'),
            ('showname (2005) S10E10 [WEBRip / x264 / AC3 / MKV / 720p]', 'showname (2005) S10E10.[AC3].720p.WEBRip.x264.MKV', '720p WEB-DL'),
            ('showname Season 1 [WEBRip / x264 / MKV / AAC / 720p]', 'showname Season 1.[AAC].720p.WEBRip.x264.MKV', '720p WEB-DL'),
            ('showname - Season 1 [WEBRip/ x264 / DD5.1 / MKV / 720p / w. Subtitles]', 'showname.Season 1.[DD5.1.w..Subtitles].720p.WEBRip.x264.MKV', '720p WEB-DL'),
            ('showname.S01E08 [WEB-Rip/ x264 /E-AC3/MKV/1080p]', 'showname.S01E08.[E-AC3].1080p.WEB-Rip.x264.MKV', '1080p WEB-DL'),
            ('showname - Season 2 [WEB-DL / H.264 / AC-3 / MKV / 1080 / w.Subtitles]', 'showname.Season 2.[AC-3.w.Subtitles].1080p.WEB-DL.H.264.MKV', '1080p WEB-DL'),

            ('showname - Season 3 [Bluray / x264 / AC3 / MKV / 720p]', 'showname.Season 3.[AC3].720p.Bluray.x264.MKV', '720p BluRay'),
            ('showname - Season 1 [Bluray / X264 / DTS / MKV / 720p]', 'showname.Season 1.[DTS].720p.Bluray.X264.MKV', '720p BluRay'),
            ('showname - Season 1 [BluRay / x264 / DTS / MKV / 1080p]', 'showname.Season 1.[DTS].1080p.BluRay.x264.MKV', '1080p BluRay'),
            ('showname - Season 1 [BluRay / x264 / AC-3 / MKV / 1080p / w.Subtitles]', 'showname.Season 1.[AC-3.w.Subtitles].1080p.BluRay.x264.MKV', '1080p BluRay'),
        ]:
            create_test = False
            result = self.regulate_title(t[0]).replace('-NOGRP', '')
            from sickbeard.common import Quality

            q = Quality.qualityStrings[Quality.sceneQuality(result)]

            # convenience line to create the actual test data
            if create_test:
                logger.log("('%s', '%s', '%s')," % (t[0], result, q))
                continue

            try:
                assert result == t[1], 'Test failed: with: \'%s\' expected: \'%s\' got: \'%s\'' % (t[0], t[1], result)
                assert q == t[2], 'Test failed: quality of expected: \'%s\' got:%s' % (t[2], q)
            except (StandardError, Exception) as e:
                logger.log('%r' % e)
                # convenience line for a breakpoint to be placed here to debug a failure
                self.regulate_title(t[0])
                pass
            pass
