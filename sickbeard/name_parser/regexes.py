# Author: Nic Wolfe <nic@wolfeden.ca>
# URL: http://code.google.com/p/sickbeard/
#
# This file is part of SickGear.
#
# SickGear is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# SickGear is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with SickGear.  If not, see <http://www.gnu.org/licenses/>.

# all regexes are case insensitive

normal_regexes = [
    ('garbage_name',
     '''
     ^(?!\\bs?\\d+[ex]\\d+\\b)[a-zA-Z0-9]{3,}$
     '''
     ),
    ('standard_repeat',
     # Show.Name.S01E02.S01E03.Source.Quality.Etc-Group
     # Show Name - S01E02 - S01E03 - S01E04 - Ep Name
     r'''
     ^(?P<series_name>.+?)[. _-]+                  (?# Show_Name and separator)
     s(?P<season_num>\d+)[. _-]*                   (?# S01 and optional separator)
     e(?P<ep_num>\d+)                              (?# E02 and separator)
     ([. _-]+s(?P=season_num)[. _-]*               (?# S01 and optional separator)
     e(?P<extra_ep_num>\d+))+                      (?# E03/etc and separator)
     [. _-]*((?P<extra_info>.+?)                   (?# Source_Quality_Etc-)
     ((?<![. _-])(?<!WEB)                          (?# Make sure this is really the release group)
     -(?P<release_group>[^- ]+))?)?$               (?# Group)
     '''
     ),

    ('fov_repeat',
     # Show.Name.1x02.1x03.Source.Quality.Etc-Group
     # Show Name - 1x02 - 1x03 - 1x04 - Ep Name
     r'''
     ^(?P<series_name>.+?)[. _-]+                  (?# Show_Name and separator)
     (?P<season_num>\d+)x                          (?# 1x)
     (?P<ep_num>\d+)                               (?# 02 and separator)
     ([. _-]+(?P=season_num)x                      (?# 1x)
     (?P<extra_ep_num>\d+))+                       (?# 03/etc and separator)
     [. _-]*((?P<extra_info>.+?)                   (?# Source_Quality_Etc-)
     ((?<![. _-])(?<!WEB)                          (?# Make sure this is really the release group)
     -(?P<release_group>[^- ]+))?)?$               (?# Group)
     '''
     ),

    ('non_standard_multi_ep',
     # Show Name - S01E02&03 - My Ep Name
     # Show Name - S01E02and03 - My Ep Name
     r'''
     ^((?P<series_name>.+?)[. _-]+)?               (?# Show_Name and separator)
     s(?P<season_num>\d+)[. _-]*                   (?# S01 and optional separator)
     e(?P<ep_num>\d+)                              (?# E02 and separator)
     (([. _-]*and|&|to)                            (?# linking and/&/to)
     (?P<extra_ep_num>(?!(2160|1080|720|480)[pi])\d+))+ (?# additional E03/etc)
     [. _-]*((?P<extra_info>.+?)                   (?# Source_Quality_Etc-)
     ((?<![. _-])(?<!WEB)                          (?# Make sure this is really the release group)
     -(?P<release_group>[^- ]+))?)?$               (?# Group)
     '''
     ),

    ('standard',
     # Show.Name.S01E02.Source.Quality.Etc-Group
     # Show Name - S01E02 - My Ep Name
     # Show.Name.S01.E03.My.Ep.Name
     # Show.Name.S01E02E03.Source.Quality.Etc-Group
     # Show Name - S01E02-03 - My Ep Name
     # Show.Name.S01.E02.E03
     r'''
     ^((?P<series_name>.+?)[. _-]+)?               (?# Show_Name and separator)
     s(?P<season_num>\d+)[. _-]*                   (?# S01 and optional separator)
     e(?P<ep_num>\d+)                              (?# E02 and separator)
     (([. _-]*e|-)                                 (?# linking e/- char)
     (?P<extra_ep_num>(?!(2160|1080|720|480)[pi])\d+))* (?# additional E03/etc)
     [. _-]*((?P<extra_info>.+?)                   (?# Source_Quality_Etc-)
     ((?<![. _-])(?<!WEB)                          (?# Make sure this is really the release group)
     -(?P<release_group>[^- ]+))?)?$               (?# Group)
     '''
     ),

    ('fov_non_standard_multi_ep',
     # Show Name - 1x02and03and04 - My Ep Name
     r'''
     ^((?P<series_name>.+?)[\[. _-]+)?             (?# Show_Name and separator)
     (?P<season_num>\d+)x                          (?# 1x)
     (?P<ep_num>\d+)                               (?# 02 and separator)
     (([. _-]*and|&|to)                            (?# linking x/- char)
     (?P<extra_ep_num>
     (?!(2160|1080|720|480)[pi])(?!(?<=x)264)      (?# ignore obviously wrong multi-eps)
     \d+))+                                        (?# additional x03/etc)
     [\]. _-]*((?P<extra_info>.+?)                 (?# Source_Quality_Etc-)
     ((?<![. _-])(?<!WEB)                          (?# Make sure this is really the release group)
     -(?P<release_group>[^- ]+))?)?$               (?# Group)
     '''
     ),

    ('fov',
     # Show_Name.1x02.Source_Quality_Etc-Group
     # Show Name - 1x02 - My Ep Name
     # Show_Name.1x02x03x04.Source_Quality_Etc-Group
     # Show Name - 1x02-03-04 - My Ep Name
     r'''
     ^((?P<series_name>.+?)[\[. _-]+)?             (?# Show_Name and separator)
     (?P<season_num>\d+)x                          (?# 1x)
     (?P<ep_num>\d+)                               (?# 02 and separator)
     (([. _-]*x|-)                                 (?# linking x/- char)
     (?P<extra_ep_num>
     (?!(2160|1080|720|480)[pi])(?!(?<=x)264)      (?# ignore obviously wrong multi-eps)
     \d+))*                                        (?# additional x03/etc)
     [\]. _-]*((?P<extra_info>.+?)                 (?# Source_Quality_Etc-)
     ((?<![. _-])(?<!WEB)                          (?# Make sure this is really the release group)
     -(?P<release_group>[^- ]+))?)?$               (?# Group)
     '''
     ),

    ('scene_date_format',
     # Show.Name.2010.11.23.Source.Quality.Etc-Group
     # Show Name - 2010-11-23 - Ep Name
     r'''
     ^((?P<series_name>.+?)[. _-]+)?               (?# Show_Name and separator)
     (?P<air_year>\d{4})[. _-]+                    (?# 2010 and separator)
     (?P<air_month>\d{2})[. _-]+                   (?# 11 and separator)
     (?P<air_day>\d{2})                            (?# 23 and separator)
     [. _-]*((?P<extra_info>.+?)                   (?# Source_Quality_Etc-)
     ((?<![. _-])(?<!WEB)                          (?# Make sure this is really the release group)
     -(?P<release_group>[^- ]+))?)?$               (?# Group)
     '''
     ),

    ('uk_date_format',
     # Show.Name.23.11.2010.Source.Quality.Etc-Group
     # Show Name - 23-11-2010 - Ep Name
     # Show Name - 14-08-17 - Ep Name
     # Show Name - 14 Jan 17 - Ep Name
     r'''
     ^((?P<series_name>.+?)[. _-]+)?               (?# Show_Name and separator)
     \(?(?P<air_day>\d{2})[. _-]+                  (?# 23 and separator)
     (?P<air_month>(?:\d{2}|(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\w*))[. _-]+ (?# 11 and separator)
     (?P<air_year>(?:19|20)?\d{2})\)?              (?# 2010 and separator)
     [. _-]*((?P<extra_info>.+?)                   (?# Source_Quality_Etc-)
     ((?<![. _-])(?<!WEB)                          (?# Make sure this is really the release group)
     -(?P<release_group>[^- ]+))?)?$               (?# Group)
     '''
     ),

    ('stupid',
     # tpz-abc102
     r'''
     (?P<release_group>.+?)-\w+?[\. ]?             (?# tpz-abc)
     (?!264)                                       (?# don't count x264)
     (?P<season_num>\d{1,2})                       (?# 1)
     (?P<ep_num>\d{2})$                            (?# 02)
     '''
     ),

    ('verbose',
     # Show Name Season 1 Episode 2 Ep Name
     r'''
     ^(?P<series_name>.+?)[. _-]+                  (?# Show Name and separator)
     season[. _-]+                                 (?# season and separator)
     (?P<season_num>\d+)[. _-]+                    (?# 1)
     episode[. _-]+                                (?# episode and separator)
     (?P<ep_num>\d+)[. _-]+                        (?# 02 and separator)
     (?P<extra_info>.+)$                           (?# Source_Quality_Etc-)
     '''
     ),

    ('season_only',
     # Show.Name.S01.Source.Quality.Etc-Group
     r'''
     ^((?P<series_name>.+?)[. _-]+)?               (?# Show_Name and separator)
     s(eason[. _-])?                               (?# S01/Season 01)
     (?P<season_num>\d+)[. _-]*                    (?# S01 and optional separator)
     [. _-]*((?P<extra_info>.+?)                   (?# Source_Quality_Etc-)
     ((?<![. _-])(?<!WEB)                          (?# Make sure this is really the release group)
     -(?P<release_group>[^- ]+))?)?$               (?# Group)
     '''
     ),

    ('no_season_multi_ep',
     # Show.Name.E02-03
     # Show.Name.E02.2010
     r'''
     ^((?P<series_name>.+?)[. _-]+)?               (?# Show_Name and separator)
     (e(p(isode)?)?|part|pt)[. _-]?                (?# e, ep, episode, or part)
     (?P<ep_num>(\d+|[ivx]+))                      (?# first ep num)
     ((([. _-]+(and|&|to)[. _-]+)|-)               (?# and/&/to joiner)
     (?P<extra_ep_num>(?!(2160|1080|720|480)[pi])(\d+|[ivx]+))[. _-])            (?# second ep num)
     ([. _-]*(?P<extra_info>.+?)                   (?# Source_Quality_Etc-)
     ((?<![. _-])(?<!WEB)                          (?# Make sure this is really the release group)
     -(?P<release_group>[^- ]+))?)?$               (?# Group)
     '''
     ),

    ('no_season_general',
     # Show.Name.E23.Test
     # Show.Name.Part.3.Source.Quality.Etc-Group
     # Show.Name.Part.1.and.Part.2.Blah-Group
     r'''
     ^((?P<series_name>.+?)[. _-]+)?               (?# Show_Name and separator)
     (e(p(isode)?)?|part|pt)[. _-]?                (?# e, ep, episode, or part)
     (?P<ep_num>(\d+|([ivx]+(?=[. _-]))))          (?# first ep num)
     ([. _-]+((and|&|to)[. _-]+)?                  (?# and/&/to joiner)
     ((e(p(isode)?)?|part|pt)[. _-]?)              (?# e, ep, episode, or part)
     (?P<extra_ep_num>(?!(2160|1080|720|480)[pi])
     (\d+|([ivx]+(?=[. _-]))))[. _-])*             (?# second ep num)
     ([. _-]*(?P<extra_info>.+?)                   (?# Source_Quality_Etc-)
     ((?<![. _-])(?<!WEB)                          (?# Make sure this is really the release group)
     -(?P<release_group>[^- ]+))?)?$               (?# Group)
     '''
     ),

    ('bare',
     # Show.Name.102.Source.Quality.Etc-Group
     r'''
     ^(?P<series_name>.+?)[. _-]+                  (?# Show_Name and separator)
     (?P<season_num>\d{1,2})                       (?# 1)
     (?P<ep_num>\d{2})                             (?# 02 and separator)
     ([. _-]+(?P<extra_info>(?!\d{3}[. _-]+)[^-]+) (?# Source_Quality_Etc-)
     (-(?P<release_group>.+))?)?$                  (?# Group)
     '''
     ),

    ('no_season',
     # Show Name - 01 - Ep Name
     # 01 - Ep Name
     r'''
     ^((?P<series_name>.+?)(?:[. _-]{2,}|[. _]))?  (?# Show_Name and separator)
     (?P<ep_num>\d{1,3}(?!\d))                     (?# 01)
     (?:-(?P<extra_ep_num>\d{1,3}(?!\d)))*         (?# 02)
     (\s*(?:of)?\s*\d{1,3})?                       (?# of num eps)
     [. _-]+((?P<extra_info>.+?)                   (?# Source_Quality_Etc-)
     ((?<![. _-])(?<!WEB)                          (?# Make sure this is really the release group)
     -(?P<release_group>[^- ]+))?)?$               (?# Group)
     '''
     ),
]

anime_regexes = [
    ('anime_ultimate',
     r'''
     ^(?:\[(?P<release_group>.+?)\][ ._-]*)
     (?P<series_name>.+?)[ ._-]+
     (?P<ep_ab_num>\d{1,4})
     (-(?P<extra_ab_ep_num>\d{1,4}))?[ ._-]+?
     (?:v(?P<version>[0-9]))?
     (?:[\w\.]*)
     (?:(?:(?:[\[\(])(?P<extra_info>\d{3,4}[xp]?\d{0,4}[\.\w\s-]*)(?:[\]\)]))|(?:\d{3,4}[xp]))
     (?:[ ._]?\[(?P<crc>\w+)\])?
     .*?
     '''
     ),

    ('anime_standard',
     # [Group Name] Show Name.13-14
     # [Group Name] Show Name - 13-14
     # Show Name 13-14
     # [Group Name] Show Name.13
     # [Group Name] Show Name - 13
     # Show Name 13
     r'''
     ^(\[(?P<release_group>.+?)\][ ._-]*)?         (?# Release Group and separator)
     (?P<series_name>.+?)[ ._-]+                   (?# Show_Name and separator)
     (?P<ep_ab_num>\d{1,4})                        (?# E01)
     (-(?P<extra_ab_ep_num>\d{1,4}))?              (?# E02)
     (v(?P<version>[0-9]))?                        (?# version)
     [ ._-]+\[(?P<extra_info>\d{3,4}[xp]?\d{0,4}.+?)\] (?# Source_Quality_Etc-)
     (\[(?P<crc>\w{8})\])?                         (?# CRC)
     .*?                                           (?# Separator and EOL)
     '''
     ),

    ('anime_standard_round',
     # [Stratos-Subs]_Infinite_Stratos_-_12_(1280x720_H.264_AAC)_[379759DB]
     # [ShinBunBu-Subs] Bleach - 02-03 (CX 1280x720 x264 AAC)
     r'''
     ^(\[(?P<release_group>.+?)\][ ._-]*)?         (?# Release Group and separator)
     (?P<series_name>.+?)[ ._-]+                   (?# Show_Name and separator)
     (?P<ep_ab_num>\d{1,4})                        (?# E01)
     (-(?P<extra_ab_ep_num>\d{1,4}))?              (?# E02)
     (v(?P<version>[0-9]))?                        (?# version)
     [ ._-]+\((?P<extra_info>(CX[ ._-]?)?\d{3,4}[xp]?\d{0,4}[\.\w\s-]*)\) (?# Source_Quality_Etc-)
     (\[(?P<crc>\w{8})\])?                         (?# CRC)
     .*?                                           (?# Separator and EOL)
     '''
     ),

    ('anime_ep_quality',
     # Show Name 09 HD
     # Show Name 09 HD1234
     # Show Name 09 SD
     r'''
     ^(\[(?P<release_group>.+?)\][ ._-]*)?         (?# Release Group and separator)
     (?P<series_name>.+?)[ ._-]+                   (?# Show_Name and separator)
     (?P<ep_ab_num>\d{1,4})                        (?# E01)
     (-(?P<extra_ab_ep_num>\d{1,4}))?              (?# E02)
     .*
     (v(?P<version>[0-9]))?                        (?# version)
     [ ._-]+(?P<extra_info>[sh]d\d{0,4}.*?)        (?# Source_Quality_Etc-)
     (\[(?P<crc>\w{8})\])?                         (?# CRC)
     .*?                                           (?# Separator and EOL)
     '''
     ),

    ('anime_quality_ep',
     # Show Name HD 09
     # Show Name HD1234 09
     # Show Name SD 09
     r'''
     ^(\[(?P<release_group>.+?)\][ ._-]*)?         (?# Release Group and separator)
     (?P<series_name>.+?)[ ._-]+                   (?# Show_Name and separator)
     (?P<extra_info>[sh]d\d{0,4}.*?)[ ._-]+        (?# Source_Quality_Etc-)
     (\[(?P<crc>\w{8})\])?                         (?# CRC)
     (?P<ep_ab_num>\d{1,4})                        (?# E01)
     (-(?P<extra_ab_ep_num>\d{1,4}))?              (?# E02)
     .*
     (v(?P<version>[0-9]))?                        (?# version)
     .*?                                           (?# Separator and EOL)
     '''
     ),

    ('anime_slash',
     # [SGKK] Bleach 312v1 [720p/MKV]
     r'''
     ^(\[(?P<release_group>.+?)\][ ._-]*)?         (?# Release Group and separator)
     (?P<series_name>.+?)[ ._-]+                   (?# Show_Name and separator)
     (?P<ep_ab_num>\d{1,4})                        (?# E01)
     (-(?P<extra_ab_ep_num>\d{1,4}))?              (?# E02)
     (v(?P<version>[0-9]))?                        (?# version)
     [ ._-]+\[(?P<extra_info>\d{3,4}p)             (?# Source_Quality_Etc-)
     (\[(?P<crc>\w{8})\])?                         (?# CRC)
     .*?                                           (?# Separator and EOL)
     '''
     ),

    ('anime_standard_codec',
     # [Ayako]_Infinite_Stratos_-_IS_-_07_[H264][720p][EB7838FC]
     # [Ayako] Infinite Stratos - IS - 07v2 [H264][720p][44419534]
     # [Ayako-Shikkaku] Oniichan no Koto Nanka Zenzen Suki Janain Dakara ne - 10 [LQ][h264][720p] [8853B21C]
     r'''
     ^(\[(?P<release_group>.+?)\][ ._-]*)?         (?# Release Group and separator)
     (?P<series_name>.+?)[ ._]*                    (?# Show_Name and separator)
     ([ ._-]+-[ ._-]+[A-Z]+[ ._-]+)?[ ._-]+        (?# this will kick me in the butt one day)
     (?P<ep_ab_num>\d{1,4})                        (?# E01)
     (-(?P<extra_ab_ep_num>\d{1,4}))?              (?# E02)
     (v(?P<version>[0-9]))?                        (?# version)
     ([ ._-](\[\w{1,2}\])?\[[a-z][.]?\w{2,4}\])?   (?# codec)
     [ ._-]*\[(?P<extra_info>(\d{3,4}[xp]?\d{0,4})?[\.\w\s-]*)\] (?# Source_Quality_Etc-)
     (\[(?P<crc>\w{8})\])?                         (?# CRC)
     .*?                                           (?# Separator and EOL)
     '''
     ),

    ('anime_and_normal',
     # Bleach - s16e03-04 - 313-314
     # Bleach.s16e03-04.313-314
     # Bleach s16e03e04 313-314
     r'''
     ^(\[(?P<release_group>.+?)\][ ._-]*)?
     (?P<series_name>.+?)[ ._-]+                   (?# start of string and series name and non optional separator)
     [sS](?P<season_num>\d+)[. _-]*                (?# S01 and optional separator)
     [eE](?P<ep_num>\d+)                           (?# episode E02)
     (([. _-]*e|-)                                 (?# linking e/- char)
     (?P<extra_ep_num>\d+))*                       (?# additional E03/etc)
     ([ ._-]{2,}|[ ._]+)                           (?# if "-" is used to separate at least something else has to be)
                                                   (?# there ->{2,}  "s16e03-04-313-314" wouldn't make sense any way)
     (?<!H.)(?P<ep_ab_num>\d{1,4})(?!0p)           (?# absolute number)
     (-(?P<extra_ab_ep_num>\d{1,4}))*              (?# "-" as separator and additional absolute number, all optional)
     (v(?P<version>[0-9]))?                        (?# the version e.g. "v2")
     .*?
     '''
     ),

    ('anime_and_normal_x',
     # Bleach - s16e03-04 - 313-314
     # Bleach.s16e03-04.313-314
     # Bleach s16e03e04 313-314
     r'''
     ^(?P<series_name>.+?)[ ._-]+                  (?# start of string and series name and non optional separator)
     (?P<season_num>\d+)[. _-]*                    (?# S01 and optional separator)
     [xX](?P<ep_num>\d+)                           (?# episode E02)
     (([. _-]*e|-)                                 (?# linking e/- char)
     (?P<extra_ep_num>\d+))*                       (?# additional E03/etc)
     ([ ._-]{2,}|[ ._]+)                           (?# if "-" is used to separate at least something else has to be)
                                                   (?# there ->{2,} "s16e03-04-313-314" wouldn't make sense any way)
     (?<!H.)(?P<ep_ab_num>\d{1,4})(?!0p)           (?# absolute number)
     (-(?P<extra_ab_ep_num>\d{1,4}))*              (?# "-" as separator and additional absolute number, all optional)
     (v(?P<version>[0-9]))?                        (?# the version e.g. "v2")
     .*?
     '''
     ),

    ('anime_and_normal_reverse',
     # Bleach - 313-314 - s16e03-04
     r'''
     ^(?P<series_name>.+?)[ ._-]+                  (?# start of string and series name and non optional separator)
     (?<!H.)(?P<ep_ab_num>\d{1,4})(?!0p)           (?# absolute number)
     (-(?P<extra_ab_ep_num>\d{1,4}))*              (?# "-" as separator and additional absolute number, all optional)
     (v(?P<version>[0-9]))?                        (?# the version e.g. "v2")
     ([ ._-]{2,}|[ ._]+)                           (?# if "-" is used to separate at least something else has to be)
                                                   (?# there ->{2,} "s16e03-04-313-314" wouldn't make sense any way)
     [sS](?P<season_num>\d+)[. _-]*                (?# S01 and optional separator)
     [eE](?P<ep_num>\d+)                           (?# episode E02)
     (([. _-]*e|-)                                 (?# linking e/- char)
     (?P<extra_ep_num>\d+))*                       (?# additional E03/etc)
     .*?
     '''
     ),

    ('anime_and_normal_front',
     # 165.Naruto Shippuuden.s08e014
     r'''
     ^(?<!H.)(?P<ep_ab_num>\d{1,4})(?!0p)          (?# start of string and absolute number)
     (-(?P<extra_ab_ep_num>\d{1,4}))*              (?# "-" as separator and additional absolute number, all optional)
     (v(?P<version>[0-9]))?[ ._-]+                 (?# the version e.g. "v2")
     (?P<series_name>.+?)[ ._-]+
     [sS](?P<season_num>\d+)[. _-]*                (?# S01 and optional separator)
     [eE](?P<ep_num>\d+)
     (([. _-]*e|-)                                 (?# linking e/- char)
     (?P<extra_ep_num>\d+))*                       (?# additional E03/etc)
     .*?
     '''
     ),

    ('anime_ep_name',
     r'''
     ^(?:\[(?P<release_group>.+?)\][ ._-]*)
     (?P<series_name>.+?)[ ._-]+
     (?<!H.)(?P<ep_ab_num>\d{1,4})(?!0p)
     (-(?P<extra_ab_ep_num>\d{1,4}))*[ ._-]*?
     (?:v(?P<version>[0-9])[ ._-]+?)?
     (?:.+?[ ._-]+?)?
     \[(?P<extra_info>\w+)\][ ._-]?
     (?:\[(?P<crc>\w{8})\])?
     .*?
     '''
     ),

    ('anime_bare_ep',
     # One Piece - 102
     # Show Name 123 - 001
     r'''
     ^(?:\[(?P<release_group>.+?)\][ ._-]*)?
     (?P<series_name>.+?)[ ._-]+[ ._-]{2,}         (?# Show_Name and min 2 char separator)
     (?<!H.)(?P<ep_ab_num>\d{1,4})(?!0p)           (?# 1/001, while avoiding H.264 and 1080p from being matched)
     (-(?P<extra_ab_ep_num>\d{1,4}))*[ ._-]*       (?# 2/002)
     (?:v(?P<version>[0-9]))?                      (?# v2)
     '''
     ),

    ('anime_bare',
     # [ACX]_Wolf's_Spirit_001.mkv
     r'''
     ^(\[(?P<release_group>.+?)\][ ._-]*)?
     (?P<series_name>.+?)[ ._-]+                   (?# Show_Name and separator)
     (?<!H.)(?P<ep_ab_num>\d{3})(?!0p)             (?# E01, while avoiding H.264 and 1080p from being matched)
     (-(?P<extra_ab_ep_num>\d{3}))*                (?# E02)
     (v(?P<version>[0-9]))?                        (?# v2)
     .*?                                           (?# Separator and EOL)
     '''
     ),

    ('standard',
     # Show.Name.S01E02.Source.Quality.Etc-Group
     # Show Name - S01E02 - My Ep Name
     # Show.Name.S01.E03.My.Ep.Name
     # Show.Name.S01E02E03.Source.Quality.Etc-Group
     # Show Name - S01E02-03 - My Ep Name
     # Show.Name.S01.E02.E03
     r'''
     ^((?P<series_name>.+?)[. _-]+)?               (?# Show_Name and separator)
     s(?P<season_num>\d+)[. _-]*                   (?# S01 and optional separator)
     e(?P<ep_num>\d+)                              (?# E02 and separator)
     (([. _-]*e|-)                                 (?# linking e/- char)
     (?P<extra_ep_num>(?!(2160|1080|720|480)[pi])\d+))* (?# additional E03/etc)
     [. _-]*((?P<extra_info>.+?)                   (?# Source_Quality_Etc-)
     ((?<![. _-])(?<!WEB)                          (?# Make sure this is really the release group)
     -(?P<release_group>[^- ]+))?)?$               (?# Group)
     '''
     ),
]
