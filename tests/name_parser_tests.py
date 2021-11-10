from __future__ import print_function
import datetime
import os.path
import test_lib as test
import sys
import unittest

sys.path.insert(1, os.path.abspath('..'))
sys.path.insert(1, os.path.abspath('../lib'))

import sickbeard
from sickbeard import name_cache, tv
from sickbeard.classes import OrderedDefaultdict
from sickbeard.name_parser import parser

sickbeard.SYS_ENCODING = 'UTF-8'

DEBUG = VERBOSE = False

simple_test_cases = {
    'standard': {
        'Mr.Show.Name.S01E02.Source.Quality.Etc-Group':
            parser.ParseResult(None, 'Mr Show Name', 1, [2], 'Source.Quality.Etc', 'Group'),
        'Show.Name.S01E02': parser.ParseResult(None, 'Show Name', 1, [2]),
        'Show Name - S01E02 - My Ep Name': parser.ParseResult(None, 'Show Name', 1, [2], 'My Ep Name'),
        'Show.1.0.Name.S01.E03.My.Ep.Name-Group':
            parser.ParseResult(None, 'Show 1.0 Name', 1, [3], 'My.Ep.Name', 'Group'),
        'Show.Name.S01E02E03.Source.Quality.Etc-Group':
            parser.ParseResult(None, 'Show Name', 1, [2, 3], 'Source.Quality.Etc', 'Group'),
        'Mr. Show Name - S01E02-03 - My Ep Name': parser.ParseResult(None, 'Mr. Show Name', 1, [2, 3], 'My Ep Name'),
        'Show.Name.S01.E02.E03': parser.ParseResult(None, 'Show Name', 1, [2, 3]),
        'Show.Name-0.2010.S01E02.Source.Quality.Etc-Group':
            parser.ParseResult(None, 'Show Name-0 2010', 1, [2], 'Source.Quality.Etc', 'Group'),
        'S01E02 Ep Name': parser.ParseResult(None, None, 1, [2], 'Ep Name'),
        'Show Name - S06E01 - 2009-12-20 - Ep Name':
            parser.ParseResult(None, 'Show Name', 6, [1], '2009-12-20 - Ep Name'),
        'Show Name - S06E01 - -30-': parser.ParseResult(None, 'Show Name', 6, [1], '30-'),
        'Show-Name-S06E01-720p': parser.ParseResult(None, 'Show-Name', 6, [1], '720p'),
        'Show-Name-S06E01-1080i': parser.ParseResult(None, 'Show-Name', 6, [1], '1080i'),
        'Show.Name.S06E01.Other.WEB-DL': parser.ParseResult(None, 'Show Name', 6, [1], 'Other.WEB-DL'),
        'Show.Name.S06E01 Some-Stuff Here': parser.ParseResult(None, 'Show Name', 6, [1], 'Some-Stuff Here'),
        'Show.Name.S01E15-11001001': parser.ParseResult(None, 'Show Name', 1, [15], None),
        'Show.Name.S01E02.Source.Quality.Etc-Group - [stuff]':
            parser.ParseResult(None, 'Show Name', 1, [2], 'Source.Quality.Etc', 'Group'),
    },

    'non_standard_multi_ep': {
        'Show Name - S01E02and03 - My Ep Name': parser.ParseResult(None, 'Show Name', 1, [2, 3], 'My Ep Name'),
        'Show Name - S01E02and03and04 - My Ep Name': parser.ParseResult(None, 'Show Name', 1, [2, 3, 4], 'My Ep Name'),
        'Show Name - S01E02to03 - My Ep Name': parser.ParseResult(None, 'Show Name', 1, [2, 3], 'My Ep Name'),
        'Show Name - S01E02&3&4 - My Ep Name': parser.ParseResult(None, 'Show Name', 1, [2, 3, 4], 'My Ep Name'),
    },

    'fov': {
        'Show_Name.1x02.Source_Quality_Etc-Group':
            parser.ParseResult(None, 'Show Name', 1, [2], 'Source_Quality_Etc', 'Group'),
        'Show Name 1x02': parser.ParseResult(None, 'Show Name', 1, [2]),
        'Show Name 1x02 x264 Test': parser.ParseResult(None, 'Show Name', 1, [2], 'x264 Test'),
        'Show Name - 1x02 - My Ep Name': parser.ParseResult(None, 'Show Name', 1, [2], 'My Ep Name'),
        'Show_Name.1x02x03x04.Source_Quality_Etc-Group':
            parser.ParseResult(None, 'Show Name', 1, [2, 3, 4], 'Source_Quality_Etc', 'Group'),
        'Show Name - 1x02-03-04 - My Ep Name': parser.ParseResult(None, 'Show Name', 1, [2, 3, 4], 'My Ep Name'),
        '1x02 Ep Name': parser.ParseResult(None, None, 1, [2], 'Ep Name'),
        'Show-Name-1x02-720p': parser.ParseResult(None, 'Show-Name', 1, [2], '720p'),
        'Show-Name-1x02-1080i': parser.ParseResult(None, 'Show-Name', 1, [2], '1080i'),
        'Show Name [05x12] Ep Name': parser.ParseResult(None, 'Show Name', 5, [12], 'Ep Name'),
        'Show.Name.1x02.WEB-DL': parser.ParseResult(None, 'Show Name', 1, [2], 'WEB-DL'),
    },

    'fov_non_standard_multi_ep': {
        'Show_Name.1x02and03and04.Source_Quality_Etc-Group':
            parser.ParseResult(None, 'Show Name', 1, [2, 3, 4], 'Source_Quality_Etc', 'Group'),
    },

    'standard_repeat': {
        'Show.Name.S01E02.S01E03.Source.Quality.Etc-Group':
            parser.ParseResult(None, 'Show Name', 1, [2, 3], 'Source.Quality.Etc', 'Group'),
        'Show.Name.S01E02.S01E03': parser.ParseResult(None, 'Show Name', 1, [2, 3]),
        'Show Name - S01E02 - S01E03 - S01E04 - Ep Name':
            parser.ParseResult(None, 'Show Name', 1, [2, 3, 4], 'Ep Name'),
        'Show.Name.S01E02.S01E03.WEB-DL': parser.ParseResult(None, 'Show Name', 1, [2, 3], 'WEB-DL'),
    },

    'fov_repeat': {
        'Show.Name.1x02.1x03.Source.Quality.Etc-Group':
            parser.ParseResult(None, 'Show Name', 1, [2, 3], 'Source.Quality.Etc', 'Group'),
        'Show.Name.1x02.1x03': parser.ParseResult(None, 'Show Name', 1, [2, 3]),
        'Show Name - 1x02 - 1x03 - 1x04 - Ep Name': parser.ParseResult(None, 'Show Name', 1, [2, 3, 4], 'Ep Name'),
        'Show.Name.1x02.1x03.WEB-DL': parser.ParseResult(None, 'Show Name', 1, [2, 3], 'WEB-DL'),
    },

    'bare': {
        'Show.Name.102.Source.Quality.Etc-Group':
            parser.ParseResult(None, 'Show Name', 1, [2], 'Source.Quality.Etc', 'Group'),
        'show.name.2010.123.source.quality.etc-group':
            parser.ParseResult(None, 'show name 2010', 1, [23], 'source.quality.etc', 'group'),
        'show.name.2010.222.123.source.quality.etc-group':
            parser.ParseResult(None, 'show name 2010.222', 1, [23], 'source.quality.etc', 'group'),
        'Show.Name.102': parser.ParseResult(None, 'Show Name', 1, [2]),
        'the.event.401.hdtv-lol': parser.ParseResult(None, 'the event', 4, [1], 'hdtv', 'lol'),
        # 'show.name.2010.special.hdtv-blah': None,
    },

    'stupid': {
        'tpz-abc102': parser.ParseResult(None, None, 1, [2], None, 'tpz'),
        'tpz-abc.102': parser.ParseResult(None, None, 1, [2], None, 'tpz'),
    },

    'no_season': {
        'Show Name - 01 - Ep Name': parser.ParseResult(None, 'Show Name', None, [1], 'Ep Name'),
        '01 - Ep Name': parser.ParseResult(None, None, None, [1], 'Ep Name'),
        'Show Name - 01 - Ep Name - WEB-DL': parser.ParseResult(None, 'Show Name', None, [1], 'Ep Name - WEB-DL'),
        'Show.Name.2015.04.19.Ep.Name.Part.2.PROPER.PDTV.x264-GROUP':
            parser.ParseResult(None, 'Show Name', release_group='GROUP', extra_info='Ep.Name.Part.2.PROPER.PDTV.x264',
                               air_date=datetime.date(2015, 4, 19)),
    },

    'no_season_general': {
        'Show.Name.E23.Source.Quality.Etc-Group':
            parser.ParseResult(None, 'Show Name', None, [23], 'Source.Quality.Etc', 'Group'),
        'Show Name - Episode 01 - Ep Name': parser.ParseResult(None, 'Show Name', None, [1], 'Ep Name'),
        'Show.Name.Part.3.Source.Quality.Etc-Group':
            parser.ParseResult(None, 'Show Name', 1, [3], 'Source.Quality.Etc', 'Group'),
        'Show.Name.Part.1.and.Part.2.Blah-Group': parser.ParseResult(None, 'Show Name', 1, [1, 2], 'Blah', 'Group'),
        'Show.Name.Part.IV.Source.Quality.Etc-Group':
            parser.ParseResult(None, 'Show Name', None, [4], 'Source.Quality.Etc', 'Group'),
        'Deconstructed.E07.1080i.HDTV.DD5.1.MPEG2-TrollHD':
            parser.ParseResult(None, 'Deconstructed', None, [7], '1080i.HDTV.DD5.1.MPEG2', 'TrollHD'),
        'Show.Name.E23.WEB-DL': parser.ParseResult(None, 'Show Name', None, [23], 'WEB-DL'),
    },

    'no_season_multi_ep': {
        'Show.Name.E23-24.Source.Quality.Etc-Group':
            parser.ParseResult(None, 'Show Name', None, [23, 24], 'Source.Quality.Etc', 'Group'),
        'Show Name - Episode 01-02 - Ep Name': parser.ParseResult(None, 'Show Name', None, [1, 2], 'Ep Name'),
        'Show.Name.E23-24.WEB-DL': parser.ParseResult(None, 'Show Name', None, [23, 24], 'WEB-DL'),
    },

    'season_only': {
        'Show.Name.S02.Source.Quality.Etc-Group':
            parser.ParseResult(None, 'Show Name', 2, [], 'Source.Quality.Etc', 'Group'),
        'Show Name Season 2': parser.ParseResult(None, 'Show Name', 2),
        'Season 02': parser.ParseResult(None, None, 2),
    },

    'scene_date_format': {
        'Show.Name.2010.11.23.Source.Quality.Etc-Group':
            parser.ParseResult(None, 'Show Name', None, [], 'Source.Quality.Etc', 'Group', datetime.date(2010, 11, 23)),
        'Show Name - 2010.11.23': parser.ParseResult(None, 'Show Name', air_date=datetime.date(2010, 11, 23)),
        'Show.Name.2010.23.11.Source.Quality.Etc-Group':
            parser.ParseResult(None, 'Show Name', None, [], 'Source.Quality.Etc', 'Group', datetime.date(2010, 11, 23)),
        'Show Name - 2010-11-23 - Ep Name':
            parser.ParseResult(None, 'Show Name', extra_info='Ep Name', air_date=datetime.date(2010, 11, 23)),
        '2010-11-23 - Ep Name': parser.ParseResult(None, extra_info='Ep Name', air_date=datetime.date(2010, 11, 23)),
        'Show.Name.2010.11.23.WEB-DL':
            parser.ParseResult(None, 'Show Name', None, [], 'WEB-DL', None, datetime.date(2010, 11, 23)),
    },

    'uk_date_format': {
        'Show.Name.23.11.2010.Source.Quality.Etc-Group':
            parser.ParseResult(None, 'Show Name', None, [], 'Source.Quality.Etc', 'Group', datetime.date(2010, 11, 23)),
        'Show Name - 23.11.2010': parser.ParseResult(None, 'Show Name', air_date=datetime.date(2010, 11, 23)),
        'Show.Name.11.23.2010.Source.Quality.Etc-Group':
            parser.ParseResult(None, 'Show Name', None, [], 'Source.Quality.Etc', 'Group', datetime.date(2010, 11, 23)),
        'Show Name - 23-11-2010 - Ep Name':
            parser.ParseResult(None, 'Show Name', extra_info='Ep Name', air_date=datetime.date(2010, 11, 23)),
        '23-11-2010 - Ep Name': parser.ParseResult(None, extra_info='Ep Name', air_date=datetime.date(2010, 11, 23)),
        'Show.Name.23.11.2010.WEB-DL':
            parser.ParseResult(None, 'Show Name', None, [], 'WEB-DL', None, datetime.date(2010, 11, 23)),
    },

    'folder_filename': {
        'Show.Name.S01.DVDRip.XviD-NOGRP/1x10 - The Episode Name.avi':
            parser.ParseResult(None, 'Show Name', 1, [10], 'The Episode Name', 'NOGRP')
    },

    'anime_ultimate': {
        '[Tsuki] Bleach - 301 [1280x720][61D1D4EE]':
            parser.ParseResult(None, 'Bleach', None, [], '1280x720', 'Tsuki', None, [301]),
        '[Tsuki] Fairy Tail - 70 [1280x720][C4807111]':
            parser.ParseResult(None, 'Fairy Tail', None, [], '1280x720', 'Tsuki', None, [70]),
        '[SGKK] Bleach 312v2 [720p MKV]':
            parser.ParseResult(None, 'Bleach', None, [], '720p MKV', 'SGKK', None, [312]),
        '[BSS-Anon] Tengen Toppa Gurren Lagann - 22-23 [1280x720][h264][6039D9AF]':
            parser.ParseResult(None, 'Tengen Toppa Gurren Lagann', None, [], '1280x720', 'BSS-Anon', None, [22, 23]),
        '[SJSUBS]_Naruto_Shippuden_-_02_[480p AAC]':
            parser.ParseResult(None, 'Naruto Shippuden', None, [], '480p AAC', 'SJSUBS', None, [2]),
        '[SFW-Chihiro] Dance in the Vampire Bund - 12 [1920x1080 Blu-ray FLAC][2F6DBC66].mkv':
            parser.ParseResult(
                None, 'Dance in the Vampire Bund', None, [], '1920x1080 Blu-ray FLAC', 'SFW-Chihiro', None, [12]),
        '[SHiN-gx] Hanasaku Iroha - 01 [1280x720 h.264 AAC][BDC36683]':
            parser.ParseResult(None, 'Hanasaku Iroha', None, [], '1280x720 h.264 AAC', 'SHiN-gx', None, [1]),
        '[SFW-Chihiro] Dance in the Vampire Bund - 02 [1920x1080 Blu-ray FLAC][C1FA0A09]':
            parser.ParseResult(
                None, 'Dance in the Vampire Bund', None, [], '1920x1080 Blu-ray FLAC', 'SFW-Chihiro', None, [2]),
        '[HorribleSubs] No. 6 - 11 [720p]':
            parser.ParseResult(None, 'No. 6', None, [], '720p', 'HorribleSubs', None, [11]),
        '[HorribleSubs] D Gray-Man - 312 (480p) [F501C9BE]':
            parser.ParseResult(None, 'D Gray-Man', None, [], '480p', 'HorribleSubs', None, [312]),
        '[SGKK] Tengen Toppa Gurren Lagann - 45-46 (720p h264) [F501C9BE]':
            parser.ParseResult(None, 'Tengen Toppa Gurren Lagann', None, [], '720p h264', 'SGKK', None, [45, 46]),
        '[Stratos-Subs]_Infinite_Stratos_-_12_(1280x720_H.264_AAC)_[379759DB]':
            parser.ParseResult(None, 'Infinite Stratos', None, [], '1280x720_H.264_AAC', 'Stratos-Subs', None, [12]),
        '[ShinBunBu-Subs] Bleach - 02-03 (CX 1280x720 x264 AAC)':
            parser.ParseResult(None, 'Bleach', None, [], 'CX 1280x720 x264 AAC', 'ShinBunBu-Subs', None, [2, 3]),
        '[Doki] Hanasaku Iroha - 03 (848x480 h264 AAC) [CB1AA73B]':
            parser.ParseResult(None, 'Hanasaku Iroha', None, [], '848x480 h264 AAC', 'Doki', None, [3]),
        '[UTW]_Fractal_-_01_[h264-720p][96D3F1BF]':
            parser.ParseResult(None, 'Fractal', None, [], 'h264-720p', 'UTW', None, [1]),
        '[a-s]_inuyasha_-_028_rs2_[BFDDF9F2]':
            parser.ParseResult(None, 'inuyasha', None, [], 'BFDDF9F2', 'a-s', None, [28]),
        '[HorribleSubs] Fairy Tail S2 - 37 [1080p]':
            parser.ParseResult(None, 'Fairy Tail S2', None, [], '1080p', 'HorribleSubs', None, [37]),
        '[HorribleSubs] Sword Art Online II - 23 [720p]':
            parser.ParseResult(None, 'Sword Art Online II', None, [], '720p', 'HorribleSubs', None, [23]),
    },

    'anime_standard': {
        '[Cthuko] Shirobako - 05v2 [720p H264 AAC][80C9B09B]':
            parser.ParseResult(None, 'Shirobako', None, [], '720p H264 AAC', 'Cthuko', None, [5]),
        '[Ayako]_Minami-ke_Okaeri_-_01v2_[1024x576 H264+AAC][B1912CD8]':
            parser.ParseResult(None, 'Minami-ke Okaeri', None, [], '1024x576 H264+AAC', 'Ayako', None, [1]),
        'Show.Name.123-11001001': parser.ParseResult(None, 'Show Name', None, [], None, None, None, [123]),
    },

    'anime_ep_quality': {
        'Show Name 09 HD': parser.ParseResult(None, 'Show Name', None, [], 'HD', None, None, [9]),
        'Show Name 09 SD': parser.ParseResult(None, 'Show Name', None, [], 'SD', None, None, [9]),
        'Show Name 09 HD720': parser.ParseResult(None, 'Show Name', None, [], 'HD720', None, None, [9]),
        'Show Name HD1080 09': parser.ParseResult(None, 'Show Name', None, [], 'HD1080', None, None, [9]),
    },

    'anime_quality_ep': {
        'Show Name HD 09': parser.ParseResult(None, 'Show Name', None, [], 'HD', None, None, [9]),
        'Show Name SD 09': parser.ParseResult(None, 'Show Name', None, [], 'SD', None, None, [9]),
        'Show Name HD720 09': parser.ParseResult(None, 'Show Name', None, [], 'HD720', None, None, [9]),
        'Show Name HD1080 09': parser.ParseResult(None, 'Show Name', None, [], 'HD1080', None, None, [9]),
    },

    'anime_ep_name': {
        '[TzaTziki]_One_Piece_279_Chopper_Man_1_[720p][8AE5F25D]':
            parser.ParseResult(None, 'One Piece', None, [], '720p', 'TzaTziki', None, [279]),
        "[ACX]Wolf's_Rain_-_04_-_Scars_in_the_Wasteland_[octavarium]_[82B7E357]":
            parser.ParseResult(None, "Wolf's Rain", None, [], 'octavarium', 'ACX', None, [4]),
        '[ACX]Black Lagoon - 02v2 - Mangrove Heaven [SaintDeath] [7481F875]':
            parser.ParseResult(None, 'Black Lagoon', None, [], 'SaintDeath', 'ACX', None, [2]),
    },

    'anime_standard_round': {
        '[SGKK] Bleach - 312v2 (1280x720 h264 AAC) [F501C9BE]':
            parser.ParseResult(None, 'Bleach', None, [], '1280x720 h264 AAC', 'SGKK', None, [312]),
    },

    'anime_slash': {
        '[SGKK] Bleach 312v1 [720p/MKV]': parser.ParseResult(None, 'Bleach', None, [], '720p', 'SGKK', None, [312]),
        '[SGKK] Bleach 312 [480p/MKV]': parser.ParseResult(None, 'Bleach', None, [], '480p', 'SGKK', None, [312])
    },

    'anime_standard_codec': {
        '[Ayako]_Infinite_Stratos_-_IS_-_07_[H264][720p][EB7838FC]':
            parser.ParseResult(None, 'Infinite Stratos', None, [], '720p', 'Ayako', None, [7]),
        '[Ayako] Infinite Stratos - IS - 07v2 [H264][720p][44419534]':
            parser.ParseResult(None, 'Infinite Stratos', None, [], '720p', 'Ayako', None, [7]),
        '[Ayako-Shikkaku] Oniichan no Koto Nanka Zenzen Suki Janain Dakara ne - 10 [LQ][h264][720p] [8853B21C]':
            parser.ParseResult(None, 'Oniichan no Koto Nanka Zenzen Suki Janain Dakara ne', None, [],
                               '720p', 'Ayako-Shikkaku', None, [10]),
        '[Tsuki] Fairy Tail - 72 [XviD][C4807111]':
            parser.ParseResult(None, 'Fairy Tail', None, [], 'C4807111', 'Tsuki', None, [72]),
        'Bubblegum Crisis Tokyo 2040 - 25 [aX] [F4E2E558]':
            parser.ParseResult(None, 'Bubblegum Crisis Tokyo 2040', None, [], 'aX', None, None, [25]),

    },

    'anime_and_normal': {
        'Bleach - s02e03 - 012 - Name & Name': parser.ParseResult(None, 'Bleach', 2, [3], None, None, None, [12]),
        'Bleach - s02e03e04 - 012-013 - Name & Name':
            parser.ParseResult(None, 'Bleach', 2, [3, 4], None, None, None, [12, 13]),
        'Bleach - s16e03-04 - 313-314': parser.ParseResult(None, 'Bleach', 16, [3, 4], None, None, None, [313, 314]),
        'Blue Submarine No. 6 s16e03e04 313-314':
            parser.ParseResult(None, 'Blue Submarine No. 6', 16, [3, 4], None, None, None, [313, 314]),
        'Bleach.s16e03-04.313-314': parser.ParseResult(None, 'Bleach', 16, [3, 4], None, None, None, [313, 314]),
        '.hack roots s01e01 001.mkv': parser.ParseResult(None, 'hack roots', 1, [1], None, None, None, [1]),
        '.hack sign s01e01 001.mkv': parser.ParseResult(None, 'hack sign', 1, [1], None, None, None, [1])

    },

    'anime_and_normal_reverse': {
        'Bleach - 012 - s02e03 - Name & Name': parser.ParseResult(None, 'Bleach', 2, [3], None, None, None, [12]),
        'Blue Submarine No. 6 - 012-013 - s02e03e04 - Name & Name':
            parser.ParseResult(None, 'Blue Submarine No. 6', 2, [3, 4], None, None, None, [12, 13]),
        '07-GHOST - 012-013 - s02e03e04 - Name & Name':
            parser.ParseResult(None, '07-GHOST', 2, [3, 4], None, None, None, [12, 13]),
        '3x3 Eyes - 012-013 - s02e03-04 - Name & Name':
            parser.ParseResult(None, '3x3 Eyes', 2, [3, 4], None, None, None, [12, 13]),
    },

    'anime_and_normal_front': {
        '165.Naruto Shippuuden.s08e014':
            parser.ParseResult(None, 'Naruto Shippuuden', 8, [14], None, None, None, [165]),
        '165-166.Naruto Shippuuden.s08e014e015':
            parser.ParseResult(None, 'Naruto Shippuuden', 8, [14, 15], None, None, None, [165, 166]),
        '165-166.07-GHOST.s08e014-015': parser.ParseResult(None, '07-GHOST', 8, [14, 15], None, None, None, [165, 166]),
        '165-166.3x3 Eyes.S08E014E015': parser.ParseResult(None, '3x3 Eyes', 8, [14, 15], None, None, None, [165, 166]),
    },

    'anime_bare_ep': {
        'Show Name 123 - 001 - Ep 1 name': parser.ParseResult(None, 'Show Name 123', None, [], None, None, None, [1]),
        'One Piece 102': parser.ParseResult(None, 'One Piece', None, [], None, None, None, [102]),
        'bleach - 010': parser.ParseResult(None, 'bleach', None, [], None, None, None, [10]),
        'Naruto Shippuden - 314v2': parser.ParseResult(None, 'Naruto Shippuden', None, [], None, None, None, [314]),
    },

    'anime_bare': {
        'Blue Submarine No. 6 104-105':
            parser.ParseResult(None, 'Blue Submarine No. 6', None, [], None, None, None, [104, 105]),
        'Samurai X: Trust & Betrayal (OVA) 001-002':
            parser.ParseResult(None, 'Samurai X: Trust & Betrayal (OVA)', None, [], None, None, None, [1, 2]),
        "[ACX]_Wolf's_Spirit_001.mkv": parser.ParseResult(None, "Wolf's Spirit", None, [], None, 'ACX', None, [1])
    }

}

combination_test_cases = [
    ('/test/path/to/Season 02/03 - Ep Name.avi',
     parser.ParseResult(None, None, 2, [3], 'Ep Name'),
     ['no_season', 'season_only']),

    ('Show.Name.S02.Source.Quality.Etc-Group/tpz-sn203.avi',
     parser.ParseResult(None, 'Show Name', 2, [3], 'Source.Quality.Etc', 'Group'),
     ['stupid', 'season_only']),

    ('MythBusters.S08E16.720p.HDTV.x264-aAF/aaf-mb.s08e16.720p.mkv',
     parser.ParseResult(None, 'MythBusters', 8, [16], '720p.HDTV.x264', 'aAF'),
     ['standard']),

    ('/home/drop/storage/TV/Terminator The Sarah Connor Chronicles' +
        '/Season 2/S02E06 The Tower is Tall, But the Fall is Short.mkv',
     parser.ParseResult(None, None, 2, [6], 'The Tower is Tall, But the Fall is Short'),
     ['standard']),

    (r'/Test/TV/Jimmy Fallon/Season 2/Jimmy Fallon - 2010-12-15 - blah.avi',
     parser.ParseResult(None, 'Jimmy Fallon', extra_info='blah', air_date=datetime.date(2010, 12, 15)),
     ['scene_date_format']),

    (r'/X/30 Rock/Season 4/30 Rock - 4x22 -.avi',
     parser.ParseResult(None, '30 Rock', 4, [22]),
     ['fov']),

    ('Season 2\\Show Name - 03-04 - Ep Name.ext',
     parser.ParseResult(None, 'Show Name', 2, [3, 4], extra_info='Ep Name'),
     ['no_season', 'season_only']),

    ('Season 02\\03-04-05 - Ep Name.ext',
     parser.ParseResult(None, None, 2, [3, 4, 5], extra_info='Ep Name'),
     ['no_season', 'season_only']),
]

unicode_test_cases = [
    (u'The.Big.Bang.Theory.2x07.The.Panty.Pi\xf1ata.Polarization.720p.HDTV.x264.AC3-SHELDON.mkv',
     parser.ParseResult(
         u'The.Big.Bang.Theory.2x07.The.Panty.Pi\xf1ata.Polarization.720p.HDTV.x264.AC3-SHELDON.mkv',
         u'The Big Bang Theory', 2, [7], u'The.Panty.Pi\xf1ata.Polarization.720p.HDTV.x264.AC3', u'SHELDON',
         version=-1)
     ),
    ('The.Big.Bang.Theory.2x07.The.Panty.Pi\xc3\xb1ata.Polarization.720p.HDTV.x264.AC3-SHELDON.mkv',
     parser.ParseResult(
         u'The.Big.Bang.Theory.2x07.The.Panty.Pi\xf1ata.Polarization.720p.HDTV.x264.AC3-SHELDON.mkv',
         u'The Big Bang Theory', 2, [7], u'The.Panty.Pi\xf1ata.Polarization.720p.HDTV.x264.AC3', u'SHELDON',
         version=-1)
     ),
]

failure_cases = ['7sins-jfcs01e09-720p-bluray-x264']

invalid_cases = [('The.Show.Name.111E14.1080p.WEB.x264-GROUP', 'the show name', 11, 1, False)]

extra_info_no_name_tests = [('The Show Name', [('Episode 302', 3, 2)],
                             'The.Show.Name.S03E02.REPACK.Episode.302.720p.AMZN.WEBRip.DDP5.1.x264-GROUP',
                             'REPACK.720p.AMZN.WEBRip.DDP5.1.x264'),
                            ('The Show Name', [('Episode 302', 3, 2)],
                             'The.Show.Name.S03E02.Episode.302.REPACK.720p.AMZN.WEBRip.DDP5.1.x264-GROUP',
                             'REPACK.720p.AMZN.WEBRip.DDP5.1.x264'),
                            ('The Show Name', [('Episode 302', 3, 2)],
                             'The.Show.Name.S03E02.Episode.302.REPACK.720p.AMZN.WEBRip.DDP5.1.x264-GROUP',
                             'REPACK.720p.AMZN.WEBRip.DDP5.1.x264'),
                            ('The Show Name', [('Episode 302', 3, 2)],
                             'The.Show.Name.S03E02.REPACK.720p.AMZN.WEBRip.DDP5.1.x264-GROUP',
                             'REPACK.720p.AMZN.WEBRip.DDP5.1.x264'),
                            ('The Show Name', [('Episode 302', 3, 2)],
                             'The.Show.Name.S03E02.720p.AMZN.WEBRip.DDP5.1.x264-GROUP',
                             '720p.AMZN.WEBRip.DDP5.1.x264'),
                            ('The Show Name', [('Episode 302', 3, 2), ('Name 2', 3, 3)],
                             'The.Show.Name.S03E02E03.720p.AMZN.WEBRip.DDP5.1.x264-GROUP',
                             '720p.AMZN.WEBRip.DDP5.1.x264'),
                            ('The Show Name', [('Episode 302', 3, 2), ('Name 2', 3, 3)],
                             'The.Show.Name.S03E02E03.Episode.302.Name.2.720p.AMZN.WEBRip.DDP5.1.x264-GROUP',
                             '720p.AMZN.WEBRip.DDP5.1.x264'),
                            ('The Show Name', [('Episode 302', 3, 2), ('Name 2', 3, 3)],
                             'The.Show.Name.S03E02E03.REPACK.Episode.302.Name.2.720p.AMZN.WEBRip.DDP5.1.x264-GROUP',
                             'REPACK.720p.AMZN.WEBRip.DDP5.1.x264'),
                            ('The Show Name', [('Episode 302', 3, 2), ('Name 2', 3, 3)],
                             'The.Show.Name.S03E02E03.Episode.302.Name.2.REPACK.720p.AMZN.WEBRip.DDP5.1.x264-GROUP',
                             'REPACK.720p.AMZN.WEBRip.DDP5.1.x264'),
                            ]

dupe_shows = [('The Show Name', (2, 1), 1990, [('Episode 302', 3, 2)],
               'The.Show.Name.S03E02.REPACK.Episode.302.720p.AMZN.WEBRip.DDP5.1.x264-GROUP'),
              ('The Show Name', (2, 2), 1995, [('Episode 302', 3, 2)],
               'The.Show.Name.S03E02.REPACK.Episode.302.720p.AMZN.WEBRip.DDP5.1.x264-GROUP'),
]

dupe_shows_test = [('The.Show.Name.S03E02.REPACK.Episode.302.720p.AMZN.WEBRip.DDP5.1.x264-GROUP', (2, 1), 1990)]

ep_name_test = [
    {'parse_name': 'Show.Name.S01E15-11001001',
     'parse_result': parser.ParseResult(None, 'Show Name', 1, [15], None),
     'show_obj': {'name': 'Show Name', 'prodid': 223, 'tvid': 1,
                  'episodes': [{'season': 1, 'number': 15, 'name': '11001001'}]
                  }
     },
    {'parse_name': 'Show Name - s07e42e43e44 720p WEB-DL',
     'parse_result': parser.ParseResult(None, 'Show Name', 7, [42, 43, 44], '720p WEB-DL'),
     'show_obj': {'name': 'Show Name', 'prodid': 12, 'tvid': 1,
                  'episodes': [{'season': 7, 'number': 42, 'name': '80\'s Episode'}]
                  }
     },
]


class EpisodeNameCases(unittest.TestCase):
    def test_ep_numbering(self):
        for e_t in ep_name_test:
            sickbeard.showList = []
            sickbeard.showDict = {}
            name_cache.nameCache = {}
            for s in [TVShowTest(name=e_t['show_obj']['name'], prodid=e_t['show_obj']['prodid'],
                                 tvid=e_t['show_obj']['tvid'])]:
                sickbeard.showList.append(s)
                sickbeard.showDict[s.sid_int] = s
                for e_o in e_t['show_obj']['episodes']:
                    e_obj = TVEpisodeTest(e_o['name'])
                    e_obj.season = e_o['season']
                    e_obj.episode = e_o['number']
                    s.sxe_ep_obj.setdefault(e_obj.season, {})[e_obj.episode] = e_obj
            name_cache.addNameToCache(e_t['show_obj']['name'], tvid=e_t['show_obj']['tvid'],
                                      prodid=e_t['show_obj']['prodid'])
            try:
                res = parser.NameParser(True).parse(e_t['parse_name'])
            except (BaseException, Exception):
                res = None
            self.assertEqual(res, e_t['parse_result'])


class InvalidCases(unittest.TestCase):

    def _test_invalid(self, rls_name, show_name, prodid, tvid, is_anime):
        sickbeard.showList = []
        sickbeard.showDict = {}
        for s in [TVShowTest(name=rls_name, prodid=prodid, tvid=tvid, is_anime=is_anime)]:
            sickbeard.showList.append(s)
            sickbeard.showDict[s.sid_int] = s
        name_cache.addNameToCache(show_name, tvid=tvid, prodid=prodid)
        invalidexception = False
        try:
            _ = parser.NameParser(True).parse(rls_name)
        except (parser.InvalidNameException, parser.InvalidShowException):
            invalidexception = True
        self.assertEqual(invalidexception, True)

    def test_invalid(self):
        for (rls_name, show_name, prodid, tvid, is_anime) in invalid_cases:
            self._test_invalid(rls_name, show_name, prodid, tvid, is_anime)


class UnicodeTests(unittest.TestCase):

    def _test_unicode(self, name, result):
        result.which_regex = ['fov']
        parse_result = parser.NameParser(True, testing=True).parse(name)
        self.assertEqual(parse_result, result, msg=name)

        # this shouldn't raise an exception
        void = repr(str(parse_result))
        void += ''

    def test_unicode(self):
        self.longMessage = True
        for (name, result) in unicode_test_cases:
            self._test_unicode(name, result)


class FailureCaseTests(unittest.TestCase):
    @staticmethod
    def _test_name(name):
        np = parser.NameParser(True)
        try:
            parse_result = np.parse(name)
        except (parser.InvalidNameException, parser.InvalidShowException):
            return True

        if VERBOSE:
            print('Actual: ', parse_result.which_regex, parse_result)
        return False

    def test_failures(self):
        for name in failure_cases:
            self.assertTrue(self._test_name(name))


class ComboTests(unittest.TestCase):
    def _test_combo(self, name, result, which_regexes):

        if VERBOSE:
            print()
            print('Testing', name)

        np = parser.NameParser(True)

        try:
            test_result = np.parse(name)
        except parser.InvalidShowException:
            return False

        if DEBUG:
            print(test_result, test_result.which_regex)
            print(result, which_regexes)

        self.assertEqual(test_result, result)
        for cur_regex in which_regexes:
            self.assertTrue(cur_regex in test_result.which_regex)
        self.assertEqual(len(which_regexes), len(test_result.which_regex))

    def test_combos(self):

        for (name, result, which_regexes) in combination_test_cases:
            # Normalise the paths. Converts UNIX-style paths into Windows-style
            # paths when test is run on Windows.
            self._test_combo(os.path.normpath(name), result, which_regexes)


class BasicTests(unittest.TestCase):
    def _test_folder_file(self, section, verbose=False):
        if VERBOSE or verbose:
            print('Running', section, 'tests')
        for cur_test_base in simple_test_cases[section]:
            cur_test_dir, cur_test_file = cur_test_base.split('/')
            if VERBOSE or verbose:
                print('Testing dir: %s file: %s' % (cur_test_dir, cur_test_file))

            result = simple_test_cases[section][cur_test_base]
            show_obj = TVShowTest(name=result.series_name)
            np = parser.NameParser(testing=True, show_obj=show_obj)

            if not result:
                self.assertRaises(parser.InvalidNameException, np.parse, cur_test_file)
                return
            else:
                test_result = np.parse(cur_test_file)

            test_result.release_group = result.release_group

            try:
                # self.assertEqual(test_result.which_regex, [section])
                self.assertEqual(test_result, result)
            except (BaseException, Exception):
                print('air_by_date:', test_result.is_air_by_date, 'air_date:', test_result.air_date)
                print('anime:', test_result.is_anime, 'ab_episode_numbers:', test_result.ab_episode_numbers)
                print(test_result)
                print(result)
                raise

    def _test_names(self, np, section, transform=None, verbose=False):

        if VERBOSE or verbose:
            print('Running', section, 'tests')
        for cur_test_base in simple_test_cases[section]:
            if transform:
                cur_test = transform(cur_test_base)
            else:
                cur_test = cur_test_base
            if VERBOSE or verbose:
                print('Testing', cur_test)

            result = simple_test_cases[section][cur_test_base]
            if not result:
                self.assertRaises(parser.InvalidNameException, np.parse, cur_test)
                return
            else:
                test_result = np.parse(cur_test)

            try:
                # self.assertEqual(test_result.which_regex, [section])
                self.assertEqual(test_result, result)
            except (BaseException, Exception):
                print('air_by_date:', test_result.is_air_by_date, 'air_date:', test_result.air_date)
                print('anime:', test_result.is_anime, 'ab_episode_numbers:', test_result.ab_episode_numbers)
                print(test_result)
                print(result)
                raise

    def test_standard_names(self):
        np = parser.NameParser(False, testing=True)
        self._test_names(np, 'standard')

    def test_standard_repeat_names(self):
        np = parser.NameParser(False, testing=True)
        self._test_names(np, 'standard_repeat')

    def test_non_standard_multi_ep_names(self):
        np = parser.NameParser(False, testing=True)
        self._test_names(np, 'non_standard_multi_ep')

    def test_fov_names(self):
        np = parser.NameParser(False, testing=True)
        self._test_names(np, 'fov')

    def test_fov_repeat_names(self):
        np = parser.NameParser(False, testing=True)
        self._test_names(np, 'fov_repeat')

    def test_fov_non_standard_multi_ep_names(self):
        np = parser.NameParser(False, testing=True)
        self._test_names(np, 'fov_non_standard_multi_ep')

    def test_bare_names(self):
        np = parser.NameParser(False, testing=True)
        self._test_names(np, 'bare')

    def test_stupid_names(self):
        np = parser.NameParser(False, testing=True)
        self._test_names(np, 'stupid')

    def test_no_season_names(self):
        np = parser.NameParser(False, testing=True)
        self._test_names(np, 'no_season')

    def test_no_season_general_names(self):
        np = parser.NameParser(False, testing=True)
        self._test_names(np, 'no_season_general')

    def test_no_season_multi_ep_names(self):
        np = parser.NameParser(False, testing=True)
        self._test_names(np, 'no_season_multi_ep')

    def test_season_only_names(self):
        np = parser.NameParser(False, testing=True)
        self._test_names(np, 'season_only')

    def test_scene_date_format_names(self):
        np = parser.NameParser(False, testing=True)
        self._test_names(np, 'scene_date_format')

    def test_uk_date_format_names(self):
        np = parser.NameParser(False, testing=True)
        self._test_names(np, 'uk_date_format')

    def test_standard_file_names(self):
        np = parser.NameParser(testing=True)
        self._test_names(np, 'standard', lambda x: x + '.avi')

    def test_standard_repeat_file_names(self):
        np = parser.NameParser(testing=True)
        self._test_names(np, 'standard_repeat', lambda x: x + '.avi')

    def test_fov_file_names(self):
        np = parser.NameParser(testing=True)
        self._test_names(np, 'fov', lambda x: x + '.avi')

    def test_fov_repeat_file_names(self):
        np = parser.NameParser(testing=True)
        self._test_names(np, 'fov_repeat', lambda x: x + '.avi')

    def test_bare_file_names(self):
        np = parser.NameParser(testing=True)
        self._test_names(np, 'bare', lambda x: x + '.avi')

    def test_stupid_file_names(self):
        np = parser.NameParser(testing=True)
        self._test_names(np, 'stupid', lambda x: x + '.avi')

    def test_no_season_file_names(self):
        np = parser.NameParser(testing=True)
        self._test_names(np, 'no_season', lambda x: x + '.avi')

    def test_no_season_general_file_names(self):
        np = parser.NameParser(testing=True)
        self._test_names(np, 'no_season_general', lambda x: x + '.avi')

    def test_no_season_multi_ep_file_names(self):
        np = parser.NameParser(testing=True)
        self._test_names(np, 'no_season_multi_ep', lambda x: x + '.avi')

    def test_season_only_file_names(self):
        np = parser.NameParser(testing=True)
        self._test_names(np, 'season_only', lambda x: x + '.avi')

    def test_scene_date_format_file_names(self):
        np = parser.NameParser(testing=True)
        self._test_names(np, 'scene_date_format', lambda x: x + '.avi')

    def test_folder_filename(self):
        self._test_folder_file('folder_filename')

    def test_combination_names(self):
        pass

    def test_anime_ultimate(self):
        np = parser.NameParser(False, TVShowTest(is_anime=True), testing=True)
        self._test_names(np, 'anime_ultimate')

    def test_anime_standard(self):
        np = parser.NameParser(False, TVShowTest(is_anime=True), testing=True)
        self._test_names(np, 'anime_standard')

    def test_anime_ep_quality(self):
        np = parser.NameParser(False, TVShowTest(is_anime=True), testing=True)
        self._test_names(np, 'anime_ep_quality')

    def test_anime_quality_ep(self):
        np = parser.NameParser(False, TVShowTest(is_anime=True), testing=True)
        self._test_names(np, 'anime_quality_ep')

    def test_anime_ep_name(self):
        np = parser.NameParser(False, TVShowTest(is_anime=True), testing=True)
        self._test_names(np, 'anime_ep_name')

    def test_anime_slash(self):
        np = parser.NameParser(False, TVShowTest(is_anime=True), testing=True)
        self._test_names(np, 'anime_slash')

    def test_anime_codec(self):
        np = parser.NameParser(False, TVShowTest(is_anime=True), testing=True)
        self._test_names(np, 'anime_standard_codec')

    def test_anime_and_normal(self):
        np = parser.NameParser(False, TVShowTest(is_anime=True), testing=True)
        self._test_names(np, 'anime_and_normal')

    def test_anime_and_normal_reverse(self):
        np = parser.NameParser(False, TVShowTest(is_anime=True), testing=True)
        self._test_names(np, 'anime_and_normal_reverse')

    def test_anime_and_normal_front(self):
        np = parser.NameParser(False, TVShowTest(is_anime=True), testing=True)
        self._test_names(np, 'anime_and_normal_front')

    def test_anime_bare_ep(self):
        np = parser.NameParser(False, TVShowTest(is_anime=True), testing=True)
        self._test_names(np, 'anime_bare_ep')

    def test_anime_bare(self):
        np = parser.NameParser(False, TVShowTest(is_anime=True), testing=True)
        self._test_names(np, 'anime_bare')


class TVShowTest(tv.TVShow):
    # noinspection PyMissingConstructor
    def __init__(self, is_anime=False, name='', prodid=1, tvid=1, year=1990):
        self._anime = is_anime
        self._name = name
        self._startyear = year
        self.unique_name = name
        self.tvid = tvid
        self.prodid = prodid
        self.sid_int = self.create_sid(self.tvid, self.prodid)
        self.sxe_ep_obj = {}

    def __str__(self):
        return '%s (%s)' % (self._name, self.startyear)


class TVEpisodeTest(tv.TVEpisode):
    # noinspection PyMissingConstructor
    def __init__(self, name=''):
        self._name = name
        self._tvid = 1
        self._indexer = 1
        self.tvid = 1
        self._epid = 1
        self._indexerid = 1
        self._season = -1
        self._episode = -1
        self.epid = 1


class DupeNameTests(test.SickbeardTestDBCase):

    def tearDown(self):
        super(DupeNameTests, self).tearDown()
        sickbeard.showList = []
        sickbeard.showDict = {}
        name_cache.nameCache = {}

    def test_dupe_names(self):
        sickbeard.showList = []
        sickbeard.showDict = {}
        name_cache.nameCache = {}
        for case in dupe_shows:
            tvs = TVShowTest(False, case[0], case[1][1], case[1][0], case[2])
            for e in case[3]:
                tvs.sxe_ep_obj.setdefault(e[1], {}).update({e[2]: TVEpisodeTest(e[0])})

            sickbeard.showList.append(tvs)
            sickbeard.showDict[tvs.sid_int] = tvs
        sickbeard.webserve.Home.make_showlist_unique_names()

        for case in dupe_shows_test:
            for cache_check in range(6):
                should_get_show = cache_check in (1, 3, 4)
                should_find = cache_check in (1, 3, 4)
                show_obj = should_get_show and sickbeard.helpers.find_show_by_id({case[1][0]: case[1][1]})
                if 3 == cache_check:
                    show_obj = [so for so in sickbeard.showList if so != show_obj][0]
                np = parser.NameParser(show_obj=show_obj)
                try:
                    result = np.parse(case[0])
                except sickbeard.name_parser.parser.InvalidShowException:
                    if not should_find:
                        continue
                    self.assertTrue(False, msg='Failed to find show')
                if not should_find:
                    self.assertTrue(False, msg='Found show, when it should fail')
                self.assertEqual((show_obj.tvid, show_obj.prodid), (result.show_obj.tvid, result.show_obj.prodid))


class ExtraInfoNoNameTests(test.SickbeardTestDBCase):
    def setUp(self):
        super(ExtraInfoNoNameTests, self).setUp()
        self.oldregex = parser.regex

    def tearDown(self):
        super(ExtraInfoNoNameTests, self).tearDown()
        parser.regex = self.oldregex

    def test_extra_info_no_name(self):
        for i in range(2):
            if 1 == i:
                if None is parser.regex:
                    # only retest if regex lib is installed, now test re lib
                    continue
                parser.regex = None
            for case in extra_info_no_name_tests:
                tvs = TVShowTest(False, case[0], 2, 1)
                for e in case[1]:
                    tvs.sxe_ep_obj.setdefault(e[1], {}).update({e[2]: TVEpisodeTest(e[0])})

                sickbeard.showList = [tvs]
                sickbeard.showDict = {tvs.sid_int: tvs}
                name_cache.nameCache = {}
                name_cache.buildNameCache()

                np = parser.NameParser()
                r = np.parse(case[2], cache_result=False)
                n_ep = r.extra_info_no_name()
                self.assertEqual(n_ep, case[3])


class OrderedDefaultdictTests(unittest.TestCase):

    def test_ordereddefaultdict(self):

        d = OrderedDefaultdict()
        d['key1'] = 'test_item1'
        d['key2'] = 'test_item2'
        d['key3'] = 'test_item3'
        self.assertEqual('key1', d.first_key())
        del d['key1']
        d['key4'] = 'test_item4'
        d.move_to_end('key2')
        self.assertEqual('test_item2', d['key2'])
        self.assertEqual('key2', d.last_key())
        _ = 'end'


if '__main__' == __name__:
    suite = unittest.TestLoader().loadTestsFromTestCase(OrderedDefaultdictTests)
    unittest.TextTestRunner(verbosity=2).run(suite)

    if 1 < len(sys.argv):
        suite = unittest.TestLoader().loadTestsFromName('name_parser_tests.BasicTests.test_' + sys.argv[1])
    else:
        suite = unittest.TestLoader().loadTestsFromTestCase(BasicTests)
    unittest.TextTestRunner(verbosity=2).run(suite)

    suite = unittest.TestLoader().loadTestsFromTestCase(ComboTests)
    unittest.TextTestRunner(verbosity=2).run(suite)

    suite = unittest.TestLoader().loadTestsFromTestCase(UnicodeTests)
    unittest.TextTestRunner(verbosity=2).run(suite)

    suite = unittest.TestLoader().loadTestsFromTestCase(FailureCaseTests)
    unittest.TextTestRunner(verbosity=2).run(suite)

    suite = unittest.TestLoader().loadTestsFromTestCase(InvalidCases)
    unittest.TextTestRunner(verbosity=2).run(suite)

    suite = unittest.TestLoader().loadTestsFromTestCase(ExtraInfoNoNameTests)
    unittest.TextTestRunner(verbosity=2).run(suite)

    suite = unittest.TestLoader().loadTestsFromTestCase(EpisodeNameCases)
    unittest.TextTestRunner(verbosity=2).run(suite)
