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
            ('Title S01E01 (1st Oct 2017)', 'Title S01E01 2017-10-01.hdtv.x264', 'SD TV'),
            ('Title - S17E07 HDTV x264 Subs', 'Title.S17E07.HDTV.x264', 'SD TV'),
            ('Title S08E08 Ep name (1 Nov 2016) [text]', 'Title S08E08 Ep name 2016-11-01 [text].hdtv.x264', 'SD TV'),
            ('Title - S02E02 (1 November 2016) [text] mp4', 'Title.S02E02 2016-11-01 [text].hdtv.x264', 'SD TV'),
            ('Title - Ep name 1of2 (31 Oct 2016) mp4', 'Title.Ep name.S01E01.2016-10-31.hdtv.x264', 'SD TV'),
            ('Title 1of2 (31 October 2016) [text] mp4', 'Title.S01E01.2016-10-31 [text].hdtv.x264', 'SD TV'),
            ('Title - Series 11 (2016) [text]', 'Title.Season 11 (2016) [text].hdtv.x264', 'SD TV'),
            ('Title - Series 123 (1976) DVDrip XviD', 'Title.Season 123 (1976).DVDrip.XviD', 'SD DVD'),
            ('Title - Series 1 (2016) [DVDRip]', 'Title.Season 1 (2016).DVDRip.x264', 'SD DVD'),
            ('Title (25 Oct 2016) [text] 720HD', 'Title 2016-10-25 [text].720p.hdtv.x264', 'HD TV'),
            ('The Title - 1of5 (31 Oct 2016) mp4', 'The Title.S01E01.2016-10-31.hdtv.x264', 'SD TV'),
            ('Title - Series 1 (2016) mp4*Series Repack*', 'Title.Season 1 (2016).Repack.hdtv.x264', 'SD TV'),
            ('Title Series 1 (2015-2016) Pack 1 of 2 [Series Repack]', 'Title.S01 Pack 1.Repack.hdtv.x264', 'SD TV'),
            ('Text... Ellipsis', 'Text... Ellipsis.hdtv.x264', 'SD TV'),
            ('Title S13E18 (23 Oct 2016) HD 720p Proper', 'Title S13E18 2016-10-23 HD.Proper.720p.hdtv.x264', 'HD TV'),
            ('Title\'s Proper Stuff - Series 1', 'Title\'s Proper Stuff.Season 1.hdtv.x264', 'SD TV'),
            ('Title - Text **PROPER** (Sep 2011) [mp3]', 'Title.Text.2011-09 [mp3].PROPER.hdtv.x264', 'SD TV'),
            ('Title S14E12 Wk 6 (29 October 2016) [PROPER]', 'Title S14E12 Wk 6 2016-10-29.PROPER.hdtv.x264', 'SD TV'),
            ('Title S02E08 text (27 Oct 2016) *Proper*', 'Title S02E08 text 2016-10-27.Proper.hdtv.x264', 'SD TV'),
            ('Title (24 Oct 2016) mp4 **PROPER**', 'Title 2016-10-24.PROPER.hdtv.x264', 'SD TV'),
            ('Title (24 October 2016) mp4 [text] *Proper*', 'Title 2016-10-24.[text].Proper.hdtv.x264', 'SD TV'),
        ]:
            results = []
            try:
                results = self.regulate_title(t[0])
            except (StandardError, Exception) as e:
                print(str(e))
            from sickbeard.common import Quality
            for result in results:
                q = Quality.qualityStrings[Quality.sceneQuality(result)]
                try:
                    assert ('%s-grp' % t[1]) not in results, 'Test failed: with: \'%s\' expected: \'%s\' got: \'%s\'' % (t[0], t[1], result)
                    assert q == t[2], 'Test failed: quality of expected: \'%s\' got:%s' % (t[2], q)
                except (StandardError, Exception) as e:
                    logger.log('%r' % e)
                    # convenience line for a breakpoint to be placed here to debug a failure
                    self.regulate_title(t[0])
                    pass
            pass
