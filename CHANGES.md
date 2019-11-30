﻿### 0.20.11 (2019-11-30 02:45:00 UTC)

* Remove redundant tvdb_api v1
* Change update Emby api
* Fix update CF IUAM handler
* Fix issue with duplicate tweets


### 0.20.10 (2019-11-25 23:45:00 UTC)

* Fix history activity hits when there are no stats
* Fix 401 authentication issues caused by Requests lib using Linux environment vars


### 0.20.9 (2019-11-24 21:35:00 UTC)

* Change improve handling of poster/banner thumb URLs


### 0.20.8 (2019-11-14 09:40:00 UTC)

* Change improve TD provider recent search performance to process new items since the previous cycle
* Change log a tip for TD users who have not improved on the default site setting "Torrents per page" 
* Change tweak hoverover highlight on menu item Shows/History for when History is the home page
* Change update tvdb_api to 3.0.0
* Change improve fetching TVDB thumbnails
* Change add new 'banner_thumb' and 'poster_thumb' direct links
* Change artwork domain to new artwork domain with fallback URLs
* Change improve handling of Plex auth failure

                                                                                                                
### 0.20.7 (2019-11-10 14:40:00 UTC)

* Fix configured Plex notification hosts that don't start with "http"
* Add exclude "Specials" when pruning with option edit show/Other/"Keep up to"


### 0.20.6 (2019-11-04 22:15:00 UTC)

* Change move config migrator earlier up in the startup phase and add capability to gracefully downgrade config file
* Remove POTuk torrent provider
* Remove WOP torrent provider


### 0.20.5 (2019-10-18 00:01:00 UTC)

* Fix order for option edit show/Other/"Keep up to"


### 0.20.4 (2019-09-10 16:30:00 UTC)

* Change improve TVChaosUK search range, and also to recognise more of its random release names in results


### 0.20.3 (2019-08-27 18:50:00 UTC)

* Fix provider LimeTorrents


### 0.20.2 (2019-08-10 00:25:00 UTC)

* Fix some missing reference issues in webserve
* Add a link 'FAQ: Episode not found / Snatch failed' to 'View Log File'
* Fix Shazbat torrent provider


### 0.20.1 (2019-08-02 20:45:00 UTC)

* Change ensure TVDb statuses display as "Continuing" on home page where applicable
* Change improve handling an enabled Emby server that becomes unreachable
* Change improve performance of parsing provider search results


### 0.20.0 (2019-07-15 21:25:00 UTC)

* Change if episode name is not known at point of rename, then use 'tba'
* Add "Use dots in show.name path" to config/General/Misc, this will only affect newly added shows
* Change displayed folder on add show page to update based on "Use dots in show.name path" setting
* Update attr 18.3.0.dev0 (55642b3) to 19.2.0.dev0 (de84609) 
* Update Beautiful Soup 4.6.3 (r475) to 4.7.1 (r497)
* Add soupsieve 1.9.1 (24859cc)
* Add functools_lru_cache (soupsieve dep) 1.5 (21e85f5)
* Update CacheControl library 0.12.5 (0fedbba) to 0.12.5 (007e8ca)    
* Update Certifi 2018.11.29 (10a1f8a) to 2019.03.09 (401100f)
* Update dateutil 2.7.5 (e954819) to 2.8.0 (c90a30c)
* Update DiskCache library 3.1.1 (05cac6a) to 3.1.1 (2649ac9)
* Update Hachoir library 2.0a3 to 2.0a6 (c102cc7)
* Update html5lib 1.1-dev (4f92357) to 1.1-dev (4b22754)
* Update IMDb-pie 5.6.3 (4220e83) to 5.6.4 (f695e87)
* Update MsgPack 0.6.0 (197e307) to 0.6.1 (737f08a)
* Update profilehooks module 1.10.1 (fdbf19d) to 1.11.0 (e17f378)
* Update pyjsparser 2.4.5 (39b468e) to 2.7.1 (5465d03)
* Update PySocks 1.6.8 (b687a34) to 1.7.0 (91dcdf0)
* Update Requests library 2.21.0 (e52932c) to 2.22.0 (aeda65b)
* Update scandir 1.9.0 (9ab3d1f) to 1.10.0 (982e6ba)
* Update Six compatibility library 1.12.0 (d927b9e) to 1.12.0 (8da94b8)
* Update Tornado Web Server 5.1.1 (cc2cf07) to 5.1.1 (a99f1471)
* Update TZlocal 1.4 to 2.0.0.dev0 (b73a692)
* Update unidecode module 1.0.22 (578cdb9) to 1.0.22 (a5045ab)
* Update urllib3 release 1.24.3 (324e47a) to 1.25.2 (49eea80)
* Update win_inet_pton 1.0.1 (934a852) to 1.1.0 (57e3558)
* Update xmltodict library 0.11.0 (79ac9a4) to 0.12.0 (f3ab7e1)
* Change sickgear.py can now be run as start up instead of SickBeard.py
* Change refactor startup functions to prevent possible latency issues with systemd
* Add startup loading page
* Change restart to use loading page
* Add upgrade messages for sickbeard, cache, and failed db upgrade processes to loading page
* Change add WorkingDirectory to systemd startup prevents startup git issue
* Change improve MagnetDLProvider latest releases search
* Add option to TVChaosUK settings, 'Send "Say thanks!"'


### 0.19.10 (2019-07-10 17:42:00 UTC)

* Fix catch error on systems with no local timezone


### 0.19.9 (2019-07-05 23:30:00 UTC)

* Change Anonymous redirect misuse of dereferer.org (was removed from SG in 2015) to nullrefer.com service


### 0.19.8 (2019-07-01 12:00:00 UTC)

* Fix the develop branch Travis build badge on GitHub homepage


### 0.19.7 (2019-06-27 12:05:00 UTC)

* Fix FF/WF display images on viewing show list


### 0.19.6 (2019-06-24 00:15:00 UTC)

* Change add rTorrent 0.9.7 compatibility
* Change improve Cloudflare connectivity


### 0.19.5 (2019-06-13 18:25:00 UTC)

* Update Js2Py 0.43 (da310bb) to 0.64 (efbfcca)
* Change update Cloudflare anti-bot handler
* Fix force reload all images and don't force reload all images for ended shows during show update


### 0.19.4 (2019-06-09 02:30:00 UTC)

* Change improve post processing checks for complete folder names


### 0.19.3 (2019-06-07 21:40:00 UTC)

* Fix "too many SQL variables" with over 999 shows when updating name cache


### 0.19.2 (2019-06-07 11:55:00 UTC)

* Change prevent post processing under a parent (or show root) folder


### 0.19.1 (2019-06-06 00:00:00 UTC)

* Change ignore word "Spanish" to not match Spanish Princess
* Remove BeyondHD torrent provider (API nuked)
* Change TVDb mappings


### 0.19.0 (2019-05-08 01:10:00 UTC)

* Update attrs 18.2.0.dev0 (c2bc831) to 18.3.0.dev0 (55642b3)
* Update CacheControl library 0.12.5 (cd91309) to 0.12.5 (0fedbba)
* Update Certifi 2018.10.15 (a462d21) to 2018.11.29 (10a1f8a)
* Update dateutil 2.7.2 (49690ee) to 2.7.5 (e954819)
* Update DiskCache library 3.0.6 (6397269) to 3.1.1 (05cac6a)
* Update html5lib 1.1-dev (e9ef538) to 1.1-dev (4f92357)
* Update idna library 2.7 (0f50bdc) to 2.8 (032fc55)
* Update MsgPack 0.5.6 (d4675be) to 0.6.0 (197e307)
* Update Requests library 2.21.0 (c452e3b) to 2.21.0 (e52932c)
* Update SimpleJSON 3.16.0 (e2a54f7) to 3.16.1 (ce75e60)
* Update Six compatibility library 1.11.0 (0b4265e) to 1.12.0 (d927b9e)
* Update urllib3 release 1.24.1 (a6ec68a) to 1.24.3 (324e47a)
* Change suppress logging false positive of bad Emby request


### 0.18.23 (2019-05-07 12:15:00 UTC)

* Fix Milkie torrent provider


### 0.18.22 (2019-05-06 19:25:00 UTC)

* Update UnRar for Windows 5.70 to 5.71 x64
* Change improve clarity for media provider search task
* Add Milkie torrent provider
* Change check manual search of illegal UNKNOWN status and change it to SKIPPED
* Change set status for shows without location
* Change set status to SKIPPED/UNAIRED when update is exited early


### 0.18.21 (2019-04-26 09:35:00 UTC)

* Change torrent client post process script to be compatible with Dash (tested with Ubuntu 18.04 LTS)


### 0.18.20 (2019-04-23 23:10:00 UTC)

* Add NinjaCentral usenet provider
* Remove Nzb.org usenet provider (r.i.p)
* Remove Milkie torrent provider (last activity > 3 months)
* Fix setting ignore/require words in webapi
* Change handle TVDb api returns None for some shows as 'seriesName'


### 0.18.19 (2019-04-19 02:00:00 UTC)

* Fix season search at provider ETTV
* Change improve IMDb id parsing


### 0.18.18 (2019-03-25 16:45:00 UTC)

* Fix "Search now" under reverse proxy configurations (credit: nojp)


### 0.18.17 (2019-03-17 08:50:00 UTC)

* Fix Cloudflare issue (affects TorrentDay and others)
* Fix provider Blutopia
* Change keep ignored status even when file exists during show update
* Change improve TVDb invalid show detection


### 0.18.16 (2019-02-26 21:15:00 UTC)

* Update UnRar for Windows 5.61 to 5.70
* Fix provider WOP 


### 0.18.15 (2019-02-21 15:30:00 UTC)

* Change improve Zooqle
* Change log bad torrent data
* Change search HorribleSubs without fansub groups
* Remove provider Anizb
* Change improve handling Trakt API response errors with watchlists
* Fix TV info source locked id check


### 0.18.14 (2019-02-11 15:10:00 UTC)

* Fix ETTV provider cache search
* Fix Snowfl provider
* Fix HorribleSubs provider single digit episode search 
* Change TokyoToshokan provider to prefer magnets and ignore invalid nyaa links
* Fix saving duplicate filename extension .nzb and .torrent


### 0.18.13 (2019-02-09 16:00:00 UTC)

* Fix Nyaa provider
* Fix HorribleSubs provider


### 0.18.12 (2019-02-07 03:55:00 UTC)

* Change improve DiskStation 6.2 connectivity and error logging
* Fix TokyoToshokan


### 0.18.11 (2019-02-03 13:50:00 UTC)

* Add hd/sd quality detection for x265 hevc (to use; remove x265 and hevc from global ignore list)
* Add prefer x265/hevc releases over x264 at equal qualities
* Fix EpisodeView Webcal link for proxy use
* Fix UI issue with /api/builder -> SickGear.Episode.SetStatus
* Change provider Rarbg


### 0.18.10 (2019-01-11 14:00:00 UTC)

* Fix using ampersand with find show search input


### 0.18.9 (2019-01-08 01:00:00 UTC)

* Change ensure utf-8 locale for Ubuntu snap
* Change remove non-release group stuff from newnab results
* Add detection of NZBHydra and NZBHydra 2 to config providers
* Remove Torrentz2


### 0.18.8 (2018-12-18 21:00:00 UTC)

* Change first run GUI defaults to enable fanart and episode view as home
* Fix an issue in the Travis CI test system used by GitHub
* Fix potential issue parsing IMDb response
* Update IMDb-pie 5.6.3 (df7411d1) to 5.6.3 (4220e83)


### 0.18.7 (2018-12-14 01:00:00 UTC)

* Fix saving NZBGet priority to Normal
* Change hide "More results" between add show searches


### 0.18.6 (2018-12-12 19:30:00 UTC)

* Change to public IMDb lists is now handled when adding a list
* Change IMDb cards view to feedback when a list has no TV shows
* Change IMDb cards view to include TV Mini Series
* Change add "list more" to list choices on IMDb cards view
* Change IMDb requests to be https


### 0.18.5 (2018-12-10 12:15:00 UTC)

* Change all nzb provider requests to 60s timeout
* Fix encode str to unicode for get_UWRatio
* Fix decode given show in add show as 'utf-8' into unicode
* Change improve UI to account for docker/snap installations
* Fix snap startup permissions issue
* Change providers on first run to be alphabetically listed and grouped usenet, torrent, anime
* Change suppress the redundant first run dateutil zoneinfo warning
* Update CFScrape 1.6.8 (be0a536) to custom 1.9.5 (be0a536)
* Update pyjsparser 2.4.5 (cd5b829) to 2.4.5 (39b468e)
* Update Js2Py 0.43 (c1442f1) to 0.43 (da310bb)
* Change it's the time of year to wear a fluffy hat


### 0.18.4 (2018-12-04 15:45:00 UTC)

* Fix "Test Emby" notifications output when there are not enough API keys for hosts
* Change About page to include current base @ version number
* Change handle when a known season is deleted from indexer but ep data is not deletable locally


### 0.18.3 (2018-12-01 17:35:00 UTC)

* Add Milkie torrent provider


### 0.18.2 (2018-11-30 21:15:00 UTC)

* Remove AlphaReign torrent provider
* Change minimise library update calls to Kodi and Plex


### 0.18.1 (2018-11-28 15:35:00 UTC)

* Fix manual search button on Daily Schedule


### 0.18.0 (2018-11-26 19:30:00 UTC)

* Update Beautiful Soup 4.6.0 (r449) to 4.6.3 (r475)
* Update CacheControl library 0.12.4 (bd94f7e) to 0.12.5 (cd91309)
* Update Certifi 2018.01.18 (e225253) to 2018.08.24 (8be9f89)
* Update dateutil module 2.7.2 (ff03c0f) to 2.7.2 (49690ee)
* Update feedparser 5.2.1 (5646f4c) to 5.2.1 (2b11c80)
* Update profilehooks module 1.10.0 (0ce1e29) to 1.10.1 (fdbf19d)
* Update PySocks 1.6.8 (524ceb4) to 1.6.8 (b687a34)
* Update Requests library 2.15.1 (282b01a) to 2.19.1 (2c6a842)
* Update scandir module 1.6 (c3592ee) to 1.9.0 (9ab3d1f)
* Update SimpleJSON 3.13.2 (6ffddbe) to 3.16.0 (e2a54f7)
* Update Tornado Web Server 5.0.1 (2b2a220a) to 5.1.1 (cc2cf07)
* Update unidecode module 1.0.22 (81f938d) to 1.0.22 (578cdb9)
* Update UnRar for Windows 5.60 to 5.61
* Add idna library 2.7 (0f50bdc)
* Add urllib3 release 1.23 (7c216f4)
* Change if old scandir binary module is installed, fallback to slow Python module and inform user to upgrade binary
* Change site services tester to fallback to http if error with SSL
* Change postprocessor try to use folder name when filename does not contain show name
* Change force redirects in TVMaze API to be https
* Add display first 20 results in "Add show" view with a link to display more
* Add search results sort by Z to A to "Add show" view
* Add search results sort by newest aired to "Add show" view
* Add search results sort by oldest aired to "Add show" view
* Change requirements.txt Cheetah >= 3.1.0
* Add bB torrent provider
* Add Snowfl torrent provider
* Fix manual search button on displayShow and episode view page
* Change feedback result of manual search on the clicked button image/tooltip
* Change reduce browser I/O on displayShow
* Fix displayShow bug where click holding on a season btn and then dragging away leaves 50% white
* Change Show List text "Search Show Name" to "Filter Show Name", and "Reset Search" to "Reset Filter" for clarity
* Change when getting a non existing folder, add the failed location to log messages
* Change add pulsing effect to warning indicators in navbar
* Add show search ability to menu Shows/"Add show"
* Change simplify options on final step of Add show
* Add quick set suggestion statuses in Episode Status Manager. Helpful for orphan "Snatches", or changes to "Skipped" etc.
* Change DisplayShow manual search button busy animation
* Add history view layouts to "Shows" menu
* Add a current layout indicator to "Shows"/"History" menu item
* Add the five last added shows to "Shows" menu under item "[1/2]"
* Change relabel ui "Episode Schedule" and "Episode View" to "Daily Schedule"
* Change displayShow, move table header sorting chevron images from right side of column to before text
* Change displayShow, move plotinfo from right side of name column to before the episode text
* Fix use correct columns for sorting on displayShow
* Fix sort by episode number on displayShow
* Change add images for manual search finished on displayShow to indicate completed fully (green) or low quality (bronze)
* Change improve image sizes to reduce page overhead
* Fix make release group comparison for proper/repack search case insensitive


### 0.17.15 (2018-11-24 20:30:00 UTC)

* Fix pruning large watch lists
* Add Ubuntu snap installer


### 0.17.14 (2018-11-15 08:00:00 UTC)

* Change remove required restart of SickGear after changing label or path settings for rTorrent and qBittorrent


### 0.17.13 (2018-11-08 21:12:00 UTC)

* Fix add filter to data used for alternative scene episode numbers
* Change don't enable "Scene numbering" for shows without alternative scene episode numbers
* Change label/summary of editShow/Search/"Scene numbering" to "Editable episode numbers" to improve clarity for its use
* Change improve summary of addShow/Finally/"Scene numbering"
* Change improve displayShow tooltips for editable episode number fields


### 0.17.12 (2018-10-23 19:50:00 UTC)

* Change add text search as default for old newznab without supportedParams caps parameter


### 0.17.11 (2018-10-14 18:43:00 UTC)

* Fix post process "Permission denied" caused by removing the !sync file too early in onTxComplete
* Change onTxComplete copy files logic to mitigate potential issues
* Change bump onTxComplete version to 1.1
* Change onTxComplete supported qBittorrent version is 4.13 and newer
* Change onTxComplete supported uTorrent is 2.2.1
* Add onTxComplete.bat logging to onTxComplete.log
* Fix issue with TVChaosUK


### 0.17.10 (2018-10-05 20:15:00 UTC)

* Change improve log stats for rejected items at torrent providers
* Change when a TVChaosUK response is invalid, wait then retry


### 0.17.9 (2018-10-04 15:40:00 UTC)

* Change improve TVChaosUK


### 0.17.8 (2018-10-02 13:15:00 UTC)

* Fix executing addshow form prematurely


### 0.17.7 (2018-09-26 18:30:00 UTC)

* Fix conflicting chars search with RarBG torrent provider
* Change improve Zooqle search
* Fix saving an nzb and a couple of notifs settings as disabled whose defaults were enabled


### 0.17.6 (2018-09-22 09:45:00 UTC)

* Fix propers search for Xspeeds torrent provider
* Remove BTScene and BitMeTV torrent providers


### 0.17.5 (2018-09-08 13:20:00 UTC)

* Fix error updating shows with certain paths
* Fix getting XEM absolute numbers for show
* Fix IMDb info load for redirected ids
* Fix flags on displayShow (under Linux)
* Change refactor scene numbering
* Change update LimeTorrents icon


### 0.17.4 (2018-09-01 03:00:00 UTC)

* Fix typo


### 0.17.3 (2018-09-01 02:10:00 UTC)

* Fix issue with tvdb response data


### 0.17.2 (2018-08-30 15:06:00 UTC)

* Fix Blutopia, Skytorrents, and SpeedCD torrent providers


### 0.17.1 (2018-08-29 17:37:00 UTC)

* Change replace imdb lib with imdb-pie 5.6.3 (df7411d1)
* Change handle if BTS returns no data
* Change improve hachoir error handling with bad source metadata


### 0.17.0 (2018-08-24 23:40:00 UTC)

* Add ability to set episodes to suggested statuses in Episode Status Manager. Useful for orphaned "Snatches" or to undo
  change to "Skipped", "Ignored", or "Wanted" to a previously known quality
* Change save config values only where reqd. reduces file by up to 75%
* Add 'Map an NZBGet "DestDir"' setting to config/Search/NZB Results tab (select NZBGet)
* Add TVDB, TheXem, and GitHub buttons to page History/Layout "Provider fails" that fetches a site Up/Down report
* Add bubble links to History/Provider fails when more than one provider has failures
* Add "Keep up to x most recent downloads" to Edit Show/Other
* Add "Keep up to x most recent downloads" to Manage/Bulk Change/Edit
* Change append number of downloads to keep to the number of file(s) at Display Show
* Add "Keep up to x most recent downloads" to add show finally step
* Add prune to refreshDir/rescan
* Update Tornado Web Server 5.0.1 (35a538f) to 5.0.1 (2b2a220a)
* Add HDME torrent provider
* Add HorribleSubs torrent provider
* Add ImmortalSeed torrent provider
* Add Xspeeds torrent provider
* Change consolidate provider filters into 'Only allow releases that are'
* Add provider filters, Only allow releases that are ...
  'scene releases (srrDB/predb listed)', 'or contain' text or regex,
  'non scene if no recent search results', 'non scene if no active search results',
  'not scene nuked', and 'nuked if no active search results'
* Change improve tvdb_api performance; remember if episodes are cached and reload show if not and episodes are requested
* Change remove redundant torrent URLs and improve provider loader


### 0.16.23 (2018-08-21 21:00:00 UTC)

* Fix detection of existing files
* Change add sanitize 'imdbid' field in tvdb_api v2
* Change indexer_id in imdb_info (switchIndexer)


### 0.16.22 (2018-08-18 12:30:00 UTC)

* Change TVDB data parsing for gueststars, writers and genre


### 0.16.21 (2018-07-28 14:15:00 UTC)

* Change TorrentDay
* Change TVDB API 2 to version 2.2.0


### 0.16.20 (2018-07-17 14:30:00 UTC)

* Change TorrentDay
* Fix for Emby updater when no folders are returned from API


### 0.16.19 (2018-07-05 18:10:00 UTC)

* Fix Uuid1 Python Bug, add fallback to uuid4 when uuid1 fails with ValueError https://bugs.python.org/issue32502


### 0.16.18 (2018-07-05 14:45:00 UTC)

* Fix Scenetime torrent provider
* Change disable search torrents on first installation


### 0.16.17 (2018-07-01 01:00:00 UTC)

* Update UnRar for Windows 5.50 to 5.60
* Fix API save show paused state and API exception raised when no indexer results


### 0.16.16 (2018-06-09 12:13:00 UTC)

* Fix metadata mediabrowser when no actors
* Add 'vp9' and 'av1' to ignore word list


### 0.16.15 (2018-06-03 21:24:00 UTC)

* Change garbage_name regex


### 0.16.14 (2018-06-01 15:55:00 UTC)

* Change improve IPT and RarBG providers


### 0.16.13 (2018-05-26 17:00:00 UTC)

* Change add blacklog search terms for anime PROPERS
* Fix rare case recovery after a server has been down


### 0.16.12 (2018-05-25 00:40:00 UTC)

* Fix anime parser and anime PROPER level


### 0.16.11 (2018-05-22 00:00:00 UTC)

* Fix SickGear-NG.py post processing script


### 0.16.10 (2018-05-21 23:30:00 UTC)

* Fix importing TV shows with utf8 characters in parent folders on Windows
* Fix utf8 in folders for SickGear-NG.py post processing script, script version bumped 1.5 to 1.6
* Fix incorrect logic mixing seasons
* Remove NMA notifier


### 0.16.9 (2018-05-17 15:30:00 UTC)

* Fix authorisation issue affecting some providers


### 0.16.8 (2018-05-17 02:00:00 UTC)

* Fix changing master id via search method


### 0.16.7 (2018-05-14 02:40:00 UTC)

* Fix name_parser_tests for test_extra_info_no_name


### 0.16.6 (2018-05-14 01:00:00 UTC)

* Change improve tolerance to parse a release title with a badly placed episode name
* Change improve handling tvdb_api data when adding upcoming shows with unfilled data
* Change search only once per cycle for shows with multiple episodes that air on the same day
* Fix SpeedCD


### 0.16.5 (2018-05-07 21:15:00 UTC)

* Fix HTTP 422 error when using Plex Username and Password
* Change how show URLs are made for TV info sources


### 0.16.4 (2018-05-03 12:00:00 UTC)

* Fix PiSexy torrent provider


### 0.16.3 (2018-05-02 13:55:00 UTC)

* Fix issue on displayShow


### 0.16.2 (2018-05-02 00:25:00 UTC)

* Change use copy of showObj for UI to preserve original object structs


### 0.16.1 (2018-05-01 13:20:00 UTC)

* Fix IMDb links to older shows on displayshow and editshow page


### 0.16.0 (2018-04-26 17:10:00 UTC)

* Change search show result 'exists in db' text into a link to display show page
* Change increase namecache size and fix deleting items from it when at capacity
* Change improve security with cross-site request forgery (xsrf) protection on web forms
* Change improve security by sending header flags httponly and secure with cookies
* Change improve security with DNS rebinding prevention, set "Allowed browser hostnames" at config/General/Web Interface
* Change improve test for creating self-signed SSL cert
* Change force restart when switching SSL on/off
* Change disable SSL cert verification for logins in pp-scripts
* Change hachoir targa and mpeg_ts mime parser tags so they validate
* Update backports/ssl_match_hostname 3.5.0.1 (r18) to 3.7.0.1 (r28)
* Update cachecontrol library 0.12.3 (db54c40) to 0.12.4 (bd94f7e)
* Update chardet packages 3.0.4 (9b8c5c2) to 4.0.0 (b3d867a)
* Update dateutil library 2.6.1 (2f3a160) to 2.7.2 (ff03c0f)
* Update feedparser library 5.2.1 (f1dd1bb) to 5.2.1 (5646f4c) - Uses the faster cchardet if installed
* Change Hachoir can't support PY2 so backport their PY3 to prevent a need for system dependant external binaries like mediainfo
* Update html5lib 0.99999999/1.0b9 (1a28d72) to 1.1-dev (e9ef538)
* Update IMDb 5.1 (r907) to 5.2.1dev20171113 (f640595)
* Update jquery.form plugin 3.51.0 to 4.2.2
* Update moment.js 2.17.1 to 2.21.0
* Update profilehooks 1.9.0 (de7d59b) to 1.10.0 (0ce1e29)
* Update Certifi 2017.07.27 (f808089) to 2018.01.18 (e225253)
* Update PySocks 1.6.5 (b4323df) to 1.6.8 (524ceb4)
* Update rarfile 3.0 (3e54b22) to 3.0 (2704344)
* Update Requests library 2.13.0 (fc54869) to 2.15.1 (282b01a)
* Update scandir 1.3 to 1.6 (c3592ee)
* Update SimpleJSON library 3.10.0 (c52efea) to 3.13.2 (6ffddbe)
* Update Six compatibility library 1.10.0 (r433) to 1.11.0 (68112f3)
* Update Tornado Web Server 5.0.1 (35a538f) to 5.1.dev1 (415f453)
* Update unidecode library 0.04.21 (e99b0e3) to 1.0.22 (81f938d)
* Update webencodings 0.5 (3970651) to 0.5.1 (fa2cb5d)
* Update xmltodict library 0.10.2 (375d3a6) to 0.11.0 (79ac9a4)


### 0.15.14 (2018-04-20 12:00:00 UTC)

* Change prefer modern html5lib over old to prevent display show issue on systems that fail to clean libs
* Change add un/pw for cookie support to improve SpeedCD torrent provider
* Change improve handling faults when downloading .torrent files
* Remove TorrentBytes provider
* Change remove redundant log messages for releases never to be cached removing <30% log spam
* Change remove redundant log messages for items not found in cache removing <10% log spam
* Fix marking episodes wanted due to parsing malformed non-anime release name as an anime season pack
* Change speed optimization, compile static name parser regexes once, instead of for every NameParser instance
* Change remove redundant create regexs log messages removing <10% log spam


### 0.15.13 (2018-04-18 13:50:00 UTC)

* Fix API endpoints for sg.exceptions and exceptions
* Change improve searching torrent provider BTScene


### 0.15.12 (2018-04-17 14:10:00 UTC)

* Fix ETTV torrent provider


### 0.15.11 (2018-04-16 03:20:00 UTC)

* Fix issue creating xml metadata files
* Change improve searching torrent providers AReign, EZTV, HDB, SkyT, and SCD


### 0.15.10 (2018-04-13 12:10:00 UTC)

* Change accept theTVDB Url in addshow search field
* Change Nzb.org usenet provider add config scene only/nuked
* Change SpeedCD torrent provider improve copy/paste cookie support
* Change BTScene, LimeTorrents, SkyTorrents, Torlock, Torrentz, TPB torrent providers
* Add AlphaReign, EZTV torrent providers


### 0.15.9 (2018-04-07 20:45:00 UTC)

* Fix metadata show not found
* Change when adding a show, display show title instead of '[]'


### 0.15.8 (2018-04-07 00:14:00 UTC)

* Change improve tvinfo source meta handling for cases where server is either down, or no results are returned


### 0.15.7 (2018-04-06 13:30:00 UTC)

* Change improve metadata handler during postprocessing when tvinfo source is down
* Fix Torrentz2 filter spam


### 0.15.6 (2018-04-05 01:20:00 UTC)

* Fix cf algorythm


### 0.15.5 (2018-04-04 21:10:00 UTC)

* Remove GFT torrent provider


### 0.15.4 (2018-04-03 16:10:00 UTC)

* Fix Torrentleech provider


### 0.15.3 (2018-03-28 16:55:00 UTC)

* Fix clicking next and previous show buttons on macOS Safari


### 0.15.2 (2018-03-28 01:45:00 UTC)

* Fix search for wanted when adding new show


### 0.15.1 (2018-03-23 22:30:00 UTC)

* Fix overwriting repack where renamed filename has '-' in title
* Fix Growl display correct message on test notification success + change notification icon


### 0.15.0 (2018-03-22 00:00:00 UTC)

* Add showRSS torrent provider
* Add choice to delete watched episodes from a list of played media at Kodi, Emby, and/or Plex,
  instructions at Shows/History/Layout/"Watched"
* Add installable SickGear Kodi repository containing addon "SickGear Watched State Updater"
* Change add Emby setting for watched state scheduler at Config/Notifications/Emby/"Update watched interval"
* Change add Plex setting for watched state scheduler at Config/Notifications/Plex/"Update watched interval"
* Change add map parent folder setting at Notifications for Emby, Kodi, and Plex
* Add API cmd=sg.updatewatchedstate, instructions for use are linked to in layout "Watched" at /history
* Change history page table filter input values are saved across page refreshes
* Change history page table filter inputs, accept values like "dvd or web" to only display both
* Change history page table filter inputs, press 'ESC' key inside a filter input to reset it
* Add provider activity stats to Shows/History/Layout/ drop down
* Change move provider failures table from Manage/Media Search to Shows/History/Layout/Provider fails
* Change sort provider failures by most recent failure, and with paused providers at the top
* Add SickGear-NZBGet dedicated post processing script, see.. \autoProcessTV\SickGear-NG\INSTALL.txt
* Add non standard multi episode name parsing e.g. S01E02and03 and 1x02and03and04
* Change overhaul and add API functions
* Change API version... start with 10
* Change set application response header to 'SickGear' + add API version
* Change return timezone (of network) in API
* Add indexer to calls
* Add SickGear Command tip for old SickBeard commands
* Add warning old sickbeard API calls only support tvdb shows
* Add "tvdbid" fallback only for sickbeard calls
* Add listcommands
* Add list of all commands (old + new) in listcommand page at the beginning
* Change hide 'listcommands' command from commands list, since it needs the API builder CSS + is html not json
* Add missing help in webapi
* Add episode info: absolute_number, scene_season, scene_episode, scene_absolute_number
* Add fork to SB command
* Add sg
* Add sg.activatescenenumbering
* Add sg.addrootdir
* Add sg.checkscheduler
* Add sg.deleterootdir
* Add sg.episode
* Add sg.episode.search
* Add sg.episode.setstatus
* Add sg.episode.subtitlesearch
* Add sg.exceptions
* Add sg.forcesearch
* Add sg.future
* Add sg.getdefaults
* Add sg.getindexericon
* Add sg.getindexers to list all indexers
* Add sg.getmessages
* Add sg.getnetworkicon
* Add sg.getrootdirs
* Add sg.getqualities
* Add sg.getqualitystrings
* Add sg.history
* Add sg.history.clear
* Add sg.history.trim
* Add sg.listtraktaccounts
* Add sg.listignorewords
* Add sg.listrequiedwords
* Add sg.logs
* Add sg.pausebacklog
* Add sg.postprocess
* Add sg.ping
* Add sg.restart
* Add sg.searchqueue
* Add sg.searchtv to search all indexers
* Add sg.setexceptions
* Add sg.setignorewords
* Add sg.setrequiredwords
* Add sg.setscenenumber
* Add sg.show
* Add sg.show.addexisting
* Add sg.show.addnew
* Add sg.show.cache
* Add sg.show.delete
* Add sg.show.getbanner
* Add sg.show.getfanart
* Add sg.show.getposter
* Add sg.show.getquality
* Add sg.show.listfanart
* Add sg.show.ratefanart
* Add sg.show.seasonlist
* Add sg.show.seasons
* Add sg.show.setquality
* Add sg.show.stats
* Add sg.show.refresh
* Add sg.show.pause
* Add sg.show.update
* Add sg.shows
* Add sg.shows.browsetrakt
* Add sg.shows.forceupdate
* Add sg.shows.queue
* Add sg.shows.stats
* Change sickbeard to sickgear
* Change sickbeard_call to property
* Change sg.episode.setstatus allow setting of quality
* Change sg.history, history command output
* Change sg.searchtv to list of indexers
* Add uhd4kweb to qualities
* Add upgrade_once to add existing shows
* Add upgrade_once to add new show
* Add upgrade_once to show quality settings (get/set)
* Add 'ids' to Show + Shows
* Add ids to coming eps + get tvdb id from ids
* Add 'status_str' to coming eps
* Add 'local_datetime' to comming eps + runtime
* Add X-Filename response header to getbanner, getposter
* Add X-Fanartname response header for sg.show.getfanart
* Change remove some non-release group stuff from newnab results


### 0.14.9 (2018-03-19 13:10:00 UTC)

* Change remove dead tor caches and stop searching episodes that have a magnet saved
* Change AlphaRatio provider freeleech mode; prevent spoiling user ratio from ambiguous filtered results


### 0.14.8 (2018-03-13 22:00:00 UTC)

* Fix changing status from "Skipped" to "Wanted" in Manage/Episode Status


### 0.14.7 (2018-03-12 21:30:00 UTC)

* Add DrunkenSlug usenet provider
* Fix PiSexy torrent provider


### 0.14.6 (2018-03-05 15:40:00 UTC)

* Fix config/notifications Trakt "inactive" status not displayed when it should be
* Fix saving multiple account "Update collection" selection at config/notifications Trakt


### 0.14.5 (2018-02-23 22:15:00 UTC)

* Remove NZB.is usenet provider
* Remove HD4Free torrent provider
* Fix config/notifications/Pushover priority selector
* Fix sending notification on snatch or download to Kodi/Emby


### 0.14.4 (2018-02-18 23:55:00 UTC)

* Change relax strict mode from subtitle languages and show unknown.png flag for 'Undetermined' subtitle languages
* Add Paramount Network icon


### 0.14.3 (2018-02-13 13:00:00 UTC)

* Change improve thetvdb api response handling


### 0.14.2 (2018-02-07 16:00:00 UTC)

* Change add handling for where requesting disk freespace is denied permission on some Linux distros


### 0.14.1 (2018-02-03 22:40:00 UTC)

* Change terminology around the custom quality selection to improve clarity
* Change restrict changing custom download qualities to reasonable selections
* Add upgrade to quality selections on Add show page and Import existing show page


### 0.14.0 (2018-02-01 02:30:00 UTC)

* Change improve core scheduler logic
* Change improve media process to parse anime format 'Show Name 123 - 001 - Ep 1 name'
* Add free space stat (if obtainable) of parent folder(s) to footer
* Add option "Display disk free" to general config/interface page (default enabled)
* Add a provider error table to page Manage/Media Search
* Add failure handling, skip provider for x hour(s) depending on count of failures
* Add detection of Too Many Requests (Supporting providers UC and BTN)
* Add footer icon button to switch time layouts
* Add performance gains for proper search by integrating it into recent search
* Add the once per day proper finder time to footer, this process catches any propers missed during recent searches
* Add ability to differentiate webdl/rip sources so overwriting propers is always done from the same source (e.g. AMZN)
* Change layout of quality custom to improve clarity
* Change tweak text of SD DVD to include BD/BR
* Change TBy prov add UHD cat


### 0.13.15 (2018-01-26 10:30:00 UTC)

* Fix save on config general


### 0.13.14 (2018-01-25 16:20:00 UTC)

* Add config/general/web interface/send security headers (default enabled)
* Fix usenet_crawler cache mode results
* Fix omgwtf test of invalid auth, issue when enabling propers, and updating cache
* Fix unicode shownames when searching
* Add season specific naming exceptions to nzb + btn


### 0.13.13 (2018-01-19 00:45:00 UTC)

* Fix setting episode status when testing for if it should be deleted
* Restrict setting newly added old episodes to WANTED to the last 90 days, older are set to SKIPPED


### 0.13.12 (2018-01-16 01:10:00 UTC)

* Remove provider TorrentVault


### 0.13.11 (2018-01-15 17:35:00 UTC)

* Fix issue fetching data in a rare case


### 0.13.10 (2018-01-08 17:20:00 UTC)

* Fix "Upgrade once" for wanted qualities


### 0.13.9 (2018-01-02 15:45:00 UTC)

* Fix marking episode as to upgrade


### 0.13.8 (2017-12-27 15:45:00 UTC)

* Fix HD4Free provider


### 0.13.7 (2017-12-27 03:00:00 UTC)

* Add log message for not found on indexer when adding a new show
* Fix upgrade once ARCHIVED setting by postProcessor
* Fix determination of is_first_best_match
* Fix BTScene and Lime
* Add ETTV torrent provider
* Add PotUK torrent provider


### 0.13.6 (2017-12-13 01:50:00 UTC)

* Change improve multi episode release search
* Change improve usage of the optional regex library


### 0.13.5 (2017-12-11 21:45:00 UTC)

* Change delete unused html5lib files that can cause issue with search providers


### 0.13.4 (2017-12-11 16:45:00 UTC)

* Fix MediaBrowser Season##\metadata


### 0.13.3 (2017-12-10 20:30:00 UTC)

* Fix metadata Season Posters and Banners
* Change restore fetching metadata episode thumbs


### 0.13.2 (2017-12-08 19:00:00 UTC)

* Fix tools menu on Chrome mobile browser


### 0.13.1 (2017-12-07 15:30:00 UTC)

* Fix wanted episodes


### 0.13.0 (2017-12-06 12:40:00 UTC)

* Change don't fetch caps for disabled nzb providers
* Change recent search to use centralised title and URL parser for newznab
* Add display unaired season 1 episodes of a new show in regular and pro I view modes
* Change improve page load time when loading images
* Update isotope library 2.2.2 to 3.0.1
* Add lazyload package 3.0.0 (2e318b1)
* Add webencodings 0.5 (3970651) to assist parsing legacy web content
* Change improve add show search results by comparing search term to an additional unidecoded result set
* Change webserver startup to correctly use xheaders in reverse proxy or load balance set-ups
* Update backports_abc 0.4 to 0.5
* Update Beautiful Soup 4.4.0 (r397) to 4.6.0 (r449)
* Update cachecontrol library 0.11.5 to 0.12.3 (db54c40)
* Update Certifi 2015.11.20.1 (385476b) to 2017.07.27 (f808089)
* Update chardet packages 2.3.0 (d7fae98) to 3.0.4 (9b8c5c2)
* Update dateutil library 2.4.2 (d4baf97) to 2.6.1 (2f3a160)
* Update feedparser library 5.2.0 (8c62940) to 5.2.1 (f1dd1bb)
* Update html5lib 0.99999999/1.0b9 (46dae3d) to (1a28d72)
* Update IMDb 5.1dev20160106 to 5.1 (r907)
* Update moment.js 2.15.1 to 2.17.1
* Update PNotify library 2.1.0 to 3.0.0 (175af26)
* Update profilehooks 1.8.2.dev0 (ee3f1a8) to 1.9.0 (de7d59b)
* Update rarfile to 3.0 (3e54b22)
* Update Requests library 2.9.1 (a1c9b84) to 2.13.0 (fc54869)
* Update SimpleJSON library 3.8.1 (6022794) to 3.10.0 (c52efea)
* Update Six compatibility library 1.10.0 (r405) to 1.10.0 (r433)
* Update socks from SocksiPy 1.0 to PySocks 1.6.5 (b4323df)
* Update Tornado Web Server 4.5.dev1 (92f29b8) to 4.5.1 (79b2683)
* Update unidecode library 0.04.18 to 0.04.21 (e99b0e3)
* Update xmltodict library 0.9.2 (eac0031) to 0.10.2 (375d3a6)
* Update Bootstrap 3.2.0 to 3.3.7
* Update Bootstrap Hover Dropdown 2.0.11 to 2.2.1
* Update imagesloaded 3.1.8 to 4.1.1
* Update jquery.cookie 1.0 (21349d9) to JS-Cookie 2.1.3 (c1aa987)
* Update jquery.cookiejar 1.0.1 to 1.0.2
* Update jQuery JSON 2.2 (c908771) to 2.6 (2339804)
* Update jquery.form plugin 3.35.0 to 3.51.0 (6bf24a5)
* Update jQuery SelectBoxes 2.2.4 to 2.2.6
* Update jquery-tokeninput 1.60 to 1.62 (9c36e19)
* Update jQuery-UI 1.10.4 to 1.12.1 - minimum supported IE is 8
* Update jQuery UI Touch Punch 0.2.2 to 0.2.3
* Update qTip 2.2.1 to 2.2.2
* Update tablesorter 2.17.7 to 2.28.5
* Update jQuery 1.8.3 to 2.2.4
* Add one time run to start up that deletes troublemaking compiled files
* Fix reload of homepage after restart in some browsers
* Add detection of '1080p Remux' releases as fullhdbluray
* Add "Perform search tasks" to Config/Media Providers/Options
* Change improve clarity of enabled providers on Config/Media Providers
* Add option to limit WebDL propers to original release group under Config/Search/Media Search
* Change add IPv4 config option when enabling IPv6.
* Add autoProcessTV/onTxComplete.bat to improve Windows clients Deluge, qBittorrent, Tranmission, and uTorrent
* Add Blutopia torrent provider
* Add MagnetDL torrent provider
* Add SceneHD torrent provider
* Add Skytorrents torrent provider
* Add TorrentVault torrent provider
* Add WorldOfP2P torrent provider
* Change do not have shows checked by default on import page. To re-enable import shows checked by default,
  1) On config page 'Save' 2) Stop SG 3) Find 'import_default_checked_shows' in config.ini and set '1' 4) Start SG
* Add Nyaa (.si) torrent provider
* Add Trakt watchlist to Add show/Trakt Cards
* Change revoke application access at Trakt when account is deleted in SG
* Add persistent hide/unhide cards to Add show/Trakt and Add show/IMDb Cards
* Change simplify dropdowns at all Add show/Cards
* Change cosmetic title on shutdown
* Change use TVDb API v2
* Change improve search for PROPERS
* Change catch show update task errors
* Change simplify and update FreeBSD init script
* Change only use newznab Api key if needed
* Change editshow saving empty scene exceptions
* Change improve TVDB data handling
* Change improve post processing by using more snatch history data
* Change show update, don't delete any ep in DB if eps are not returned from indexer
* Change prevent unneeded error message during show update
* Change improve performance, don't fetch episode list when retrieving a show image
* Change don't remove episodes from DB with status: SNATCHED, SNATCHED_PROPER, SNATCHED_BEST, DOWNLOADED, ARCHIVED, IGNORED
* Change add additional episode removal protections for TVDb_api v2
* Change filter SKIPPED items from episode view
* Change improve clarity of various error message by including relevant show name
* Change extend WEB PROPER release group check to ignore SD releases
* Change increase performance by reducing TVDb API requests with a global token
* Change make indexer lookup optional in NameParser, and deactivate during searches
* Change improve newnab autoselect categories
* Change add nzb.org BoxSD and BoxHD categories
* Change post processor, ignore symlinks found in process_dir
* Change file modify date of episodes older than 1970 can be changed to airdate, log warning on set fail
* Add new parameter 'poster' to indexer api
* Add optional tvdb_api load season image: lINDEXER_API_PARMS['seasons'] = True
* Add optional tvdb_api load season wide image: lINDEXER_API_PARMS['seasonwides'] = True
* Add Fuzzywuzzy 0.15.1 to sort search results
* Change remove search results filtering from tv info source
* Change suppress startup warnings for Fuzzywuzzy and Cheetah libs
* Change show search, add options to choose order of search results
* Add option to sort search results by 'A to Z' or 'First aired'
* Add option to sort search results by 'Relevancy' using Fuzzywuzzy lib
* Change search result anchor text uses SORT_ARTICLE setting for display
* Change existing shows in DB are no longer selectable in result list
* Change add image to search result item hover over
* Change improve image load speed on browse Trakt/IMDb/AniDB pages
* Add a changeable master Show ID when show no longer found at TV info source due to an ID change
* Add guiding links to assist user to change TV Info Source ID
* Add "Shows with abandoned master IDs" to Manage/Show Processes Page to link shows that can have their show IDs
  adjusted in order to sustain TV info updates
* Add "Shows from defunct TV info sources" to Manage/Show Processes page to link shows that can be switched to a
  different default TV info source
* Add shows not found at a TV info source for over 7 days will only be retried once a week
* Change prevent showing 'Mark download as bad and retry?' dialog when status doesn't require it
* Add warn icon indicator of abandoned IDs to "Manage" menu bar and "Manage/Show Processes" menu item
* Add shows that have no replacement ID can be ignored at "Manage/Show Processes", the menu bar warn icon hides if all are ignored
* Change FreeBSD initscript to use command_interpreter
* Add Slack notifier to Notifications config/Social
* Change allow Cheetah template engine version 2 and newer
* Change improve handling of relative download links from providers
* Change enable TorrentBytes provider
* Change after SG is updated, don't attempt to send a Plex client notifications if there is no client host set
* Add file name to possible names in history lookup post processing
* Add garbage name handling to name parser
* Change overhaul Notifications, add Notifier Factory and DRY refactoring
* Notifiers are now loaded into memory on demand
* Add bubble links to Notifications config tabs
* Add Discordapp notifier to Notifications config/Social
* Add Gitter notifier to Notifications config/Social
* Change order of notifiers in Notifications config tabs
* Remove Pushalot notifier
* Remove XBMC notifier
* Change a link to include webroot for "plot overview for this ended show"
* Change Bulk Changes and Notifications save to be web_root setting aware
* Change subtitle addons no longer need to be saved before Search Subtitles is enabled as a
  forbidden action to reuse an exited FindSubtitles thread is no longer attempted
* Fix tools menu not opening for some browsers
* Change overhaul handling of PROPERS/REPACKS/REAL
* Add restriction to allow only same release group for repacks
* Change try all episode names with 'real', 'repack', 'proper'
* Add tip to search settings/media search about improved matching with optional regex library
* Change use value of "Update shows during hour" in General Settings straight after it is saved instead of after restart
* Change add tips for what to use for Growl notifications on Windows
* Change if a newly added show is not found on indexer, remove already created empty folder
* Change parse 1080p Bluray AVC/VC1 to a quality instead of unknown
* Add quality tag to archived items, improve displayShow/"Change selected episodes to"
* Use to prevent "Update to" on those select episodes while preserving the downloaded quality
* Change group "Downloaded" status qualities into one section
* Add "Downloaded/with archived quality" to set shows as downloaded using quality of archived status
* Add "Archived with/downloaded quality" to set shows as archived using quality of downloaded status
* Add "Archived with/default (min. initial quality of show here)"
* Change when settings/Post Processing/File Handling/Status of removed episodes/Set Archived is enabled, set status and quality accordingly
* Add downloaded and archived statuses to Manage/Episode Status
* Add quality pills to Manage/Episode Status
* Change Manage/Episode Status season output format to be more readable


### 0.12.37 (2017-11-12 10:35:00 UTC)

* Change improve .nzb handling


### 0.12.36 (2017-11-01 11:45:00 UTC)

* Change qBittorent to handle the change to its API success/fail response


### 0.12.35 (2017-10-27 20:30:00 UTC)

* Change and add some network logos


### 0.12.34 (2017-10-25 15:20:00 UTC)

* Change improve TVChaos parser


### 0.12.33 (2017-10-12 13:00:00 UTC)

* Change improve handling of torrent auth failures


### 0.12.32 (2017-10-11 02:05:00 UTC)

* Change improve PA torrent access


### 0.12.31 (2017-10-06 22:30:00 UTC)

* Change improve handling of connection failures for metadata during media processing


### 0.12.30 (2017-09-29 00:20:00 UTC)

* Fix Media Providers/Custom Newznab tab action 'Delete' then 'Save Changes'
* Fix enforce value API expects for paused show flag


### 0.12.29 (2017-09-17 09:00:00 UTC)

* Fix provider nCore
* Change .torrent checker due to files created with qB 3.3.16 (affects nCore and NBL)


### 0.12.28 (2017-08-26 18:15:00 UTC)

* Change prevent indexer specific release name parts from fudging search logic


### 0.12.27 (2017-08-22 19:00:00 UTC)

* Update to UnRar 5.50 release


### 0.12.26 (2017-08-20 13:05:00 UTC)

* Fix infinite loop loading network_timezones
* Change add optional "stack_size" setting as integer to config.ini under "General" stanza
* Change prevent too many retries when loading network timezones, conversions, and zoneinfo in a short time
* Update to UnRar 5.50 beta 6


### 0.12.25 (2017-06-19 23:35:00 UTC)

* Remove provider SceneAccess


### 0.12.24 (2017-07-31 20:42:00 UTC)

* Fix copy post process method on posix


### 0.12.23 (2017-07-18 16:55:00 UTC)

* Remove obsolete tvrage_api lib


### 0.12.22 (2017-07-13 20:20:00 UTC)

* Fix "Server failed to return anything useful" when should be using cached .torrent file
* Fix displayShow 'Unaired' episode rows change state where appropriate
* Change displayShow to stop requiring an airdate for checkboxes


### 0.12.21 (2017-06-19 23:35:00 UTC)

* Change provider Bit-HDTV user/pass to cookie


### 0.12.20 (2017-06-14 22:00:00 UTC)

* Change send info now required by qBittorrent 3.13+ clients


### 0.12.19 (2017-05-20 10:30:00 UTC)

* Remove provider Freshon.tv


### 0.12.18 (2017-05-15 23:00:00 UTC)

* Change thexem, remove tvrage from xem


### 0.12.17 (2017-05-15 22:10:00 UTC)

* Remove provider ExtraTorrent
* Change thexem tvrage mappings are deprecated, data fetch disabled


### 0.12.16 (2017-05-05 16:40:00 UTC)

* Fix multiple SpeedCD cookie


### 0.12.15 (2017-05-04 00:40:00 UTC)

* Remove provider Nyaa
* Change improve RSS validation (particularly for anime)
* Change improve support for legacy magnet encoding


### 0.12.14 (2017-05-02 17:10:00 UTC)

* Change provider Transmithe.net is now Nebulance


### 0.12.13 (2017-04-23 18:50:00 UTC)

* Change add filter for thetvdb show overview
* Change remove SpeedCD 'inspeed_uid' cookie requirement


### 0.12.12 (2017-03-30 03:15:00 UTC)

* Change search of SpeedCD, TVChaos and parse of TorrentDay


### 0.12.11 (2017-03-17 02:00:00 UTC)

* Change SpeedCD to cookie auth as username/password is not reliable
* Change Usenet-Crawler media provider icon


### 0.12.10 (2017-03-12 16:00:00 UTC)

* Change refactor client for Deluge 1.3.14 compatibility
* Change ensure IPT authentication is valid before use


### 0.12.9 (2017-02-24 18:40:00 UTC)

* Fix issue saving custom NewznabProviders


### 0.12.8 (2017-02-19 13:50:00 UTC)

* Change BTN API hostname


### 0.12.7 (2017-02-17 15:00:00 UTC)

* Change accept lists in JSON responses
* Change do not log error for empty BTN un/pw in most cases
* Change BTN to only try API once when doing alternative name searches
* Change when API fails, warn users as a tip that they can configure un/pw


### 0.12.6 (2017-02-17 03:48:00 UTC)

* Change skip episodes that have no wanted qualities
* Change download picked .nzb file on demand and not before
* Change improve provider title processing
* Change improve handling erroneous JSON responses
* Change improve find show with unicode characters
* Change improve results for providers Omgwtf, SpeedCD, Transmithenet, Zoogle
* Change validate .torrent files that contain optional header data
* Fix case where an episode status was not restored on failure
* Add raise log error if no wanted qualities are found
* Change add un/pw to Config/Media providers/Options for BTN API graceful fallback (can remove Api key for security)
* Change only download torrent once when using blackhole
* Add Cloudflare module 1.6.8 (be0a536) to handle specific CF connections
* Add Js2Py 0.43 (c1442f1) Cloudflare dependency
* Add pyjsparser 2.4.5 (cd5b829) Js2Py dependency
* Remove Torrentshack


### 0.12.5 (2017-01-16 16:22:00 UTC)

* Change TD search URL
* Fix saving Media Providers when either Search NZBs/Torrents is disabled


### 0.12.4 (2016-12-31 00:50:00 UTC)

* Remove Wombles nzb provider


### 0.12.3 (2016-12-27 15:20:00 UTC)

* Add UK date format handling to name parser


### 0.12.2 (2016-12-20 16:00:00 UTC)

* Change Rarbg and IPT urls


### 0.12.1 (2016-12-19 12:00:00 UTC)

* Fix image scan log for show titles that contain "%"


### 0.12.0 (2016-12-19 03:00:00 UTC)

* Add strict Python version check (equal to, or higher than 2.7.9 and less than 3.0), **exit** if incorrect version
* Update unidecode library 0.04.11 to 0.04.18 (fd57cbf)
* Update xmltodict library 0.9.2 (579a005) to 0.9.2 (eac0031)
* Update Tornado Web Server 4.3.dev1 (1b6157d) to 4.5.dev1 (92f29b8)
* Update change to suppress reporting of Tornado exception error 1 to updated package (ref:hacks.txt)
* Change API response header for JSON content type and the return of JSONP data
* Remove redundant MultipartPostHandler
* Update Beautiful Soup 4.4.0 (r390) to 4.4.0 (r397)
* Update backports/ssl_match_hostname 3.4.0.2 to 3.5.0.1 (r18)
* Update cachecontrol library 0.11.2 to 0.11.5
* Update Certifi to 2015.11.20.1 (385476b)
* Update chardet packages 2.3.0 (26982c5) to 2.3.0 (d7fae98)
* Update dateutil library 2.4.2 (083f666) to 2.4.2 (d4baf97)
* Update Hachoir library 1.3.4 (r1383) to 1.3.4 (r1435)
* Update html5lib 0.999 to 0.99999999/1.0b9 (46dae3d)
* Update IMDb 5.0 to 5.1dev20160106
* Update moment.js 2.6 to 2.15.1
* Update PNotify library 2.0.1 to 2.1.0
* Update profilehooks 1.4 to 1.8.2.dev0 (ee3f1a8)
* Update Requests library 2.7.0 (5d6d1bc) to 2.9.1 (a1c9b84)
* Update SimpleJSON library 3.8.0 (a37a9bd) to 3.8.1 (6022794)
* Update Six compatibility library 1.9.0 (r400) to 1.10.0 (r405)
* Add backports_abc 0.4
* Add singledispatch 3.4.0.3
* Change refactor email notifier
* Change emails to Unicode aware
* Add force episode recent search to API
* Change process episodes with utf8 dir and nzb names, handle failed episodes without a dir, add log output streaming
* Change move dateutil-zoneinfo.tar.gz file to data files /cache
* Change handle all Hachoir library parser errors and replace its Unicode enforcement
* Allow episode status "Skipped" to be changed to "Downloaded"
* Allow found "Skipped" episode files to be set "Unknown" quality
* Add CPU throttling preset "Disabled" to config/General/Advanced Settings
* Change overhaul Kodi notifier and tidy up config/notification/KodiNotifier ui
* Add passthru of param "post_json" to Requests() "json" in helpers.getURL
* Add search show Name to Show List Layout: Poster
* Change indicate when not sorting with article by dimming ("The", "A", "An") on Show List, Episode, History,
  Bulk Change, Add with Browse and from Existing views
* Add Emby notifier to config/Notifications
* Use a subprocess and cp for copying files on posix systems to preserve file metadata
* Fix alternative unicode show names from breaking search
* Change show update, set shows with newly added airdate or existing episodes with future or never dates, to "Wanted"
* Fix rare NameParser case where numeric episode name was parsed as episode number
* Change improve management of Transmission config/Search/Torrent Search "Downloaded files location"
* Add network logos ABC News 24 and Chiller
* Update network logos to their current logo
* Remove redundant Adult Swim logos
* Add scene qualities WEB.h264 to SDTV, 720p.WEB.h264 to WEB DL 720p, and 1080p.WEB.h264 to WEB DL 1080p
* Change improve handling when provider PiSexy is missing expected data
* Change Show List second level sort criteria
* Change Show List sort Next Ep, and restore sort on Downloads
* Add sort by quality to Poster layout
* Change +n snatches to links on all Show List layouts
* Change adding show processing to be highest priority
* Use timezones to check unaired status during show update/adding
* Fix syntax error causing renamer to error out
* Change storing metadata nfo vars from int to strings to resolve lxml type exceptions that don't occur with etree
* Add visual indicator for upcoming or started shows on Add Browse Shows
* Add IMDb Watchlists to 'View' drop down on the 'Add from IMDb' page
* Add 5 decades of 'IMDb Popular' selections to 'View' drop down on 'Add from... Browse Shows'
* Add 'Other Services' to 'View' drop down on 'Add from... Browse Shows'
* Add enable, disable and delete public IMDb watchlists to Config/General/Interface with a default 'SickGear' list
* Change ensure English data from IMDb
* Change prevent duplicate show ids from presenting items on 'Add from... Browse Shows'
* Change add 'nocache' kwarg to helpers.getURL to facilitate non-cached requests
* Change instantly use saved value from Search Settings/Episode Search/"Check propers every" instead of after a restart
* Change include OSError system messages in file system failure logs during post process
* Fix find associated meta files to prevent orphan episode images
* Add HD4Free torrent provider
* Change validate and improve specific Torrent provider connections, IPT, SCC, TPB, TB, TD, TT
* Change refactor cache for torrent providers to reduce code
* Change improve search category selection BMTV, FSH, FF, TB
* Change identify more SD release qualities
* Change update SpeedCD, MoreThan, TVChaosuk
* Change only create threads for providers needing a recent search instead of for all enabled
* Add 4489 as experimental value to "Recent search frequency" to use provider freqs instead of fixed width for all
* Change remove some logging cruft
* Fix post processing "Force already processed" processing only the first of multiple files
* Add FileList torrent provider
* Add provider Anizb
* Change TorrentDay to use its 2.x interface
* Add button 'Discover' Emby server to notifications
* Add Bit-HDTV torrent provider
* Add PrivateHD torrent provider
* Add Zooqle torrent provider
* Add 2160p UHD 4K WEB quality
* Add DigitalHive torrent provider
* Add RevTT torrent provider
* Add PTF torrent provider
* Add Fano torrent provider
* Add BTScene torrent provider
* Add Extratorrent provider
* Add Limetorrents provider
* Add HD-Torrents provider
* Add nCore torrent provider
* Add TorLock provider
* Add Torrentz2 provider
* Add freeleech options to fano, freshon, hdspace, phd, ptf providers
* Change SceneTime to cookie auth
* Change improve parser tolerance for torrent providers
* Change disable TorrentBytes provider, over 90s for a response is not good
* Remove Usenet-Crawler provider
* Change CPU throttling on General Config/Advanced to "Disabled" by default for new installs
* Change provider OMGWTFNZBS api url and auto reject nuked releases
* Change Search Provider page to load torrent settings only when Search torrents is enabled in Search Settings
* Add "Order" table column and list failed from newest to oldest wherever possible on Manage Failed Downloads
* Add number of items shown to Manage Failed Downloads table footer and indicate if number of shown items is limited
* Add sorting to "Provider" column and fix sorting of "Remove" column on Manage Failed Downloads
* Fix "Limit" drop down on Manage Failed Downloads
* Change nzbs.org anime search category and fix newznab anime backlog search
* Change improve nzbgeek search response
* Change use query search at 6box (id search fails)
* Change "Add New Show" results sorted newest show to oldest from top
* Change add show genre, network, and overview to "Add New Show" results
* Change improve highlight of shows found in database in "Add New Show" results
* Change use full first aired date where available in "Add New Show" results
* Change prevent duplicate results in "Add New Show"
* Add qBitTorrent to Search Settings/Torrent Search
* Add "Test NZBGet" client to Search Settings/NZB Search/NZBGet
* Change include x265 category when searching IPT provider
* Change init.systemd to use python2 binary and recommended installation paths
* Change improve handling of SIGINT CTRL+C, SIGINT CTRL+BREAK(Windows) and SIGTERM
* Change add three IPTorrents fallback urls
* Change remove one dead and add three fallback magnet torcaches for blackhole use
* Change increase delay between requests to nnab servers to over 2 seconds
* Change set Specials to status "Skipped" not "Wanted" during show updates
* Change improve debug log message for CloudFlare response that indicate website is offline
* Add handling for 'part' numbered new releases and also for specific existing 'part' numbered releases
* Add detection of password protected rars with config/Post Processing/'Unpack downloads' enabled
* Change post process to cleanup filenames with config/Post Processing/'Unpack downloads' enabled
* Change post process to join incrementally named (i.e. file.001 to file.nnn) split files
* Change replace unrar2 lib with rarfile 3.0 and UnRAR.exe 5.40 freeware
* Change post process "Copy" to delete redundant files after use
* Add indicator for public access media providers
* Change improve probability selecting most seeded release
* Change add the TorrentDay x265 category to search
* Add smart logic to reduce api hits to newznab server types and improve how nzbs are downloaded
* Add newznab smart logic to avoid missing releases when there are a great many recent releases
* Change improve performance by using newznab server advertised capabilities
* Change config/providers newznab to display only non-default categories
* Change use scene season for wanted segment in backlog if show is scene numbering
* Change combine Media Search / Backlog Search / Limited and Full to Force
* Change consolidate limited and full backlog
* Change config / Search / Backlog search frequency to instead spread backlog searches over a number of days
* Change migrate minimum used value for search frequency into new minimum 7 for search spread
* Change restrict nzb providers to 1 backlog batch run per day
* Add to Config/Search/Unaired episodes/Allow episodes that are released early
* Add to Config/Search/Unaired episodes/Use specific api requests to search for early episode releases
* Add use related ids for newznab searches to increase search efficiency
* Add periodic update of related show ids
* Change terminology Edit Show/"Post processing" tab name to "Other"
* Add advanced feature "Related show IDs" to Edit Show/Other used for finding episodes and TV info
* Add search info source image links to those that have zero id under Edit Show/Other/"Related show IDs"
* Add "set master" button to Edit Show/Other/"Related show IDs" for info source that can be changed
* Change displayShow terminology "Indexers" to "Links" to cover internal and web links
* Change add related show info sources on displayShow page
* Change don't display "temporarily" defunct TVRage image link on displayShow pages unless it is master info source
* Change if a defunct info source is the master of a show then present a link on displayShow to edit related show IDs
* Change simplify the next backlog search run time display in the page footer
* Change try ssl when fetching data thetvdb, imdb, trakt, scene exception
* Change improve reliability to Trakt notifier by using show related id support
* Change improve config/providers newznab categories layout
* Change show loaded log message at start up and include info source
* Change if episode has no airdate then set status to unaired (was skipped)
* Fix only replace initial quality releases from the upgrade to list
* Change optimise TheTVDB processes, 40% to 66% saved adding new and existing shows, 40% to 50% saved per show update
* Change improve shows with more episodes gain largest reductions in time spent processing
* Change when using "Add new show" reduce search time outs
* Change always allow incomplete show data
* Remove redundant config/general/"Allow incomplete show data"
* Fix status reset of a snatched, downloaded, or archived episode when its date is set to never (no date) on the info
  source and there is no media file
* Change only show unaired episodes on Manage/Backlog Overview and Manage/Episode Status where relevant
* Change locally cache Trakt/IMDb/Anime show cards
* Change allow pp to replace files with a repack or proper of same quality
* Fix ensure downloaded eps are not shown on episode view
* Fix allow propers to pp when show marked upgrade once
* Fix never set episodes without airdate to wanted
* Change improve getting the local timezone information
* Change hachoir_parser to close input stream if no parser is found e.g. due to file corruption
* Change improve fault tolerance of Hachoir jpeg parser
* Change reduce time taken to parse avi RIFF metadata during post processing and other times
* Change avi metadata extraction is more fault tolerant and the chance of hanging due to corrupt avi files is reduced
* Change fuzzyMoment to handle air dates before ~1970 on display show page
* Change limit availability of fuzzy date functions on General Config/Interface to English locale systems
* Add Plex notifications secure connect where available (PMS 1.1.4.2757 and newer with username and password)
* Add if all torrent caches fail, save magnets from RARBG and TPB as files for clients (or plugins) that now support it
* Add advice to logs if all caches fail to switch to direct client connect instead of the basic blackhole method
* Add search setting "Disable auto full backlog"
* Change improve performance and reduce start up time
* Fix button "Checkout branch" when stuck on disabled
* Add 'Download Log' to 'Logs & Errors' page
* Change consolidate shutdown with restart, improve systemd support, bring order to on-init globals
* Change speed improvement in finding needed categories/qualities (sd, hd, uhd)
* Change add guidance when using the "unknown" quality selection
* Change prevent browser auto completing password fields on config pages
* Change refresh page when torrent providers are enabled/disabled
* Change only display Search Settings/"Usenet retention" if Search NZBs is enabled
* Change sab API request to prevent naming mismatch
* Change update rTorrent systems
* Change logger to properly cleanup used resources
* Add fanart to Episodes View, Display Show, and Edit Show page
* Add path used for fanart images <Cache Dir>/images/fanart (<Cache Dir> value on Help page)
* Add populate images when the daily show updater is run with default maximum 3 images per show
* Change force full update in a show will replace existing images with new
* Add "Maximum fanart image files per show to cache" to config General/Interface
* Add fanart livepanel to lower right of Episodes View and Display Show page
* Add highlight panel red on Episodes view until button is clicked a few times
* Add flick through multiple background images on Episodes View and Display Show page
* Add persistent move poster image to right hand side or hide on Display Show page (multi-click the eye)
* Add persistent translucency of background images on Episodes View and Display Show page
* Add persistent fanart rating to avoid art completely, random display, random from a group, or display fave always
* Add persistent views of the show detail on Display Show page
* Add persistent views on Episodes View
* Add persistent button to collapse and expand card images on Episode View/Layout daybyday
* Add non persistent "Open gear" and "Backart only" image views to Episodes View and Display Show page
* Add "smart" selection of fanart image to display on Episode view
* Change insert [!] and change text shade of ended shows in drop down show list on Display Show page
* Change button graphic for next and previous show of show list on Display Show page
* Add logic to hide some livepanel buttons until artwork becomes available or in other circumstances
* Add "(Ended)" where appropriate to show title on Display Show page
* Change use tense for label "Airs" or "Aired" depending on if show ended
* Change display "No files" instead of "0 files" and "Upgrade once" instead of "End upgrade on first match"
* Add persistent button to newest season to "Show all" episodes
* Add persistent button to all shown seasons to "Hide most" episodes
* Add button to older seasons to toggle "Show Season n" or "Show Specials" with "Hide..." episodes
* Add season level status counts next to each season header on display show page
* Add sorting to season table headers on display show page
* Add filename and size to quality badge on display show page, removed its redundant "downloaded" text
* Remove redundant "Add show" buttons
* Change combine the NFO and TBN columns into a single Meta column
* Change reduce screen estate used by episode numbers columns
* Change improve clarity of text on Add Show page
* Change rename Edit show/"Post-Processing" tab to "Other"
* Add "Reset fanart ratings" to show Edit/Other tab
* Add fanart keys guide to show Edit/Other tab
* Change add placeholder tip to "Alternative release name(s)" on show Edit
* Change add placeholder tip to search box on shows Search
* Change hide Anime tips on show Edit when selecting its mutually exclusive options
* Change label "End upgrade on first match" to "Upgrade once" on show Edit
* Change improve performance rendering displayShow
* Add total episodes to start of show description (excludes specials if those are hidden)
* Add "Add show" actions i.e. "Search", "Trakt cards", "IMDb cards", and "Anime" to Shows menu
* Add "Import (existing)" action to Tools menu
* Change SD quality from red to dark green, 2160p UHD 4K is red
* Change relocate the functions of Logs & Errors to the right side Tools menu -> View Log File
* Add warning indicator to the Tools menu in different colour depending on error count (green through red)
* Change View Log error item output from reversed to natural order
* Change View Log File add a typeface and some colour to improve readability
* Change View Log File/Errors only display "Clear Errors" button when there are errors to clear
* Change improve performance of View Log File
* Change fanart images to not use cache as cache is not required
* Change rename "Manual Post-Processing" menu item to "Process Media"
* Change rename "Search Providers" -> "Media Providers"
* Change rename "Manage Searches" -> "Media Search"
* Change rename "Episode Status Management" -> "Episode Status"
* Change rename "Mass Update" -> "Bulk Change"
* Change indicate default home on "Shows Menu"
* Change relocate "Episodes" menu to "Shows"/"Episode Schedule"
* Change relocate "History" menu to "Shows"/"History"
* Change remove restart/shutdown buttons from "Show List"
* Change remove superfluous buttons from all submenus


### 0.11.16 (2016-10-16 17:30:00 UTC)

* Change ensure a cache.db table does exist on migration


### 0.11.15 (2016-09-13 19:50:00 UTC)

* Add rollback capability to undo database changes made during tests


### 0.11.14 (2016-07-25 03:10:00 UTC)

* Fix BeyondHD torrent provider


### 0.11.13 (2016-07-21 20:30:00 UTC)

* Remove KAT torrent provider


### 0.11.12 (2016-06-20 02:20:00 UTC)

* Change improve importing show list sickbeard.db files


### 0.11.11 (2016-04-05 19:20:00 UTC)

* Add support for SD mkv container


### 0.11.10 (2016-03-17 19:00:00 UTC)

* Fix dbs that should not have been imported to work


### 0.11.9 (2016-03-17 12:30:00 UTC)

* Fix for import of very rare db structure


### 0.11.8 (2016-03-16 12:50:00 UTC)

* Fix ensures internal buffer of a downloaded file is written to disk


### 0.11.7 (2016-03-06 12:30:00 UTC)

* Fix Torrenting provider


### 0.11.6 (2016-02-18 23:10:00 UTC)

* Fix saving config General/Interface/Date style (save again to repopulate blank dates on the Showlist view)


### 0.11.5 (2016-02-01 19:40:00 UTC)

* Fix refresh handling of Skipped and Ignored items
* Fix issue entering scene numbers


### 0.11.4 (2016-01-31 11:30:00 UTC)

* Fix issue setting some custom name patterns on the "Config/Post Processing/Episode Naming" tab
* Remove Strike torrent provider
* Add network icons


### 0.11.3 (2016-01-16 20:00:00 UTC)

* Fix Search Settings display fail
* Add Audience, Channel 5 (UK), Five US, Fox Channel, FreeForm, Global, HBO Canada, Keshet, More4, Rooster Teeth, TF1,
  Toon Disney, WE tv, XBox Video
* Change BET network logo
* Change provider TB icon
* Delete 3fm and redundant network logo


### 0.11.2 (2016-01-14 21:10:00 UTC)

* Fix issue with "Add Existing Shows" on new installations


### 0.11.1 (2016-01-12 22:20:00 UTC)

* Fix handling non-numeric IMDb popular ratings


### 0.11.0 (2016-01-10 22:30:00 UTC)

* Change to only refresh scene exception data for shows that need it
* Change reduce aggressive use of scene numbering that was overriding user preference where not needed
* Change set "Scene numbering" checkbox and add text to the label tip in third step of add "New Show" if scene numbers
  are found for the selected show in the search results of the first step
* Change label text on edit show page to highlight when manual numbering and scene numbers are available
* Fix disabling "Scene numbering" of step three in add "New Show" was ignored when scene episode number mappings exist
* Fix don't use scene episode number mappings everywhere when "Scene numbering" is disabled for a show
* Fix width of legend underlining on the third step used to bring other display elements into alignment
* Change when downloading magnet or nzb files, verify the file in cache dir and then move to blackhole
* Fix small cosmetic issue to correctly display "full backlog" date
* Add search crawler exclusions
* Fix saving default show list group on add new show options page
* Remove legacy anime split home option from anime settings tab (new option located in general/interface tab)
* Remove "Manage Torrents"
* Update Beautiful Soup 4.3.2 to 4.4.0 (r390)
* Update dateutil library to 2.4.2 (083f666)
* Update chardet packages to 2.3.0 (26982c5)
* Update Hachoir library 1.3.3 to 1.3.4 (r1383)
* Change configure quiet option in Hachoir to suppress warnings (add ref:hacks.txt)
* Add parse media content to determine quality before making final assumptions during re-scan, update, pp
* Add a postprocess folder name validation
* Update Requests library to 2.7.0 (5d6d1bc)
* Update SimpleJSON library 3.7.3 to 3.8.0 (a37a9bd)
* Update Tornado Web Server 4.2 to 4.3.dev1 (1b6157d)
* Update isotope library 2.0.1 to 2.2.2
* Update change to suppress reporting of Tornado exception error 1 to updated package (ref:hacks.txt)
* Update fix for API response header for JSON content type and the return of JSONP data to updated package (ref:hacks.txt)
* Update TvDB API library 1.09 with changes up to (35732c9) and some pep8 and code cleanups
* Fix post processing season pack folders
* Fix saving torrent provider option "Seed until ratio" after recent refactor
* Change white text in light theme on Manage / Episode Status Management page to black for better readability
* Change displayShow page episode colours when a minimum quality is met with "Upgrade once"
* Add seed time per provider for torrent clients that support seed time per torrent, i.e. currently only uTorrent
* Remove seed time display for Transmission in config/Torrent Search page because the torrent client doesn't support it
* Add PreToMe torrent provider
* Add SceneTime torrent provider
* Change TtN provider to parse new layout
* Improve recognition of SD quality
* Fix halting in mid flow of Add Existing Show which resulted in failure to scan statuses and filesizes
* Change default de-referrer url to blank
* Change javascript urls in templates to allow proper caching
* Change downloads to prevent cache misfiring with "Result is not a valid torrent file"
* Add BitMeTV torrent provider
* Add Torrenting provider
* Add FunFile torrent provider
* Add TVChaosUK torrent provider
* Add HD-Space torrent provider
* Add Shazbat torrent provider
* Remove unnecessary call to indexers during nameparsing
* Change disable ToTV due to non-deletable yet reported hacker BTC inbox scam and also little to no new content listings
* Fix Episode View KeyError: 'state-title' failure for shows without a runtime
* Update py-unrar2 library 99.3 to 99.6 (2fe1e98)
* Fix py-unrar2 on unix to handle different date formats output by different unrar command line versions
* Fix Add and Edit show quality selection when Quality 'Custom' is used
* Fix add existing shows from folders that contain a plus char
* Fix post process issue where items in history were processed out of turn
* Change increase frequency of updating show data
* Remove Animenzb provider
* Change increase the scope and number of non release group text that is identified and removed
* Add general config setting to allow adding incomplete show data
* Change to throttle connection rate on thread initiation for adba library
* Change default manage episodes selector to Snatched episodes if items exist else Wanted on Episode Status Manage page
* Change snatched row colour on Episode Status Manage page to match colour used on the show details page
* Change replace trakt with libtrakt for API v2
* Change improve robustness of Trakt communications
* Change Trakt notification config to use PIN authentication with the service
* Add multiple Trakt account support to Config/Notifications/Social
* Add setting to Trakt notification to update collection with downloaded episode info
* Change trakt notifier logo
* Remove all other Trakt deprecated API V1 service features pending reconsideration
* Change increase show search capability when using plain text and also add TVDB id, IMDb id and IMDb url search
* Change improve existing show page and the handling when an attempt to add a show to an existing location
* Change consolidate Trakt Trending and Recommended views into an "Add From Trakt" view which defaults to trending
* Change Add from Trakt/"Shows:" with Anticipated, New Seasons, New Shows, Popular, Recommendations, and Trending views
* Change Add from Trakt/"Shows:" with Most Watched, Played, and Collected during the last month and year on Trakt
* Change add season info to "Show: Trakt New Seasons" view on the Add from Trakt page
* Change increase number of displayed Trakt shows to 100
* Add genres and rating to all Trakt shows
* Add AniDb Random and Hot to Add Show page
* Add IMDb Popular to Add Show page
* Add version to anime renaming pattern
* Add Code Climate configuration files
* Change move init-scripts to single folder
* Change sickbeard variables to sickgear variables in init-scripts
* Change improve the use of multiple plex servers
* Change move JS code out of home template and into dedicated file
* Change remove branch from window title
* Change move JS code out of inc_top template and into dedicated file
* Change cleanup torrent providers
* Change utilise tvdbid for searching usenet providers
* Add setting to provider BTN to Reject Blu-ray M2TS releases
* Remove jsonrpclib library
* Change consolidate global and per show ignore and require words functions
* Change "Require word" title and notes on Config Search page to properly describe its functional logic
* Add regular expression capability to ignore and require words by starting wordlist with "regex:"
* Add list shows with custom ignore and require words under the global counterparts on the Search Settings page
* Fix failure to search for more than one selected wanted episode
* Add notice for users with Python 2.7.8 or below to update to latest Python
* Change position of parsed qualities to the start of log lines
* Change to always display branch and commit hash on 'Help & Info' page
* Add option to create season search exceptions from editShow page
* Change sab to use requests library
* Add "View Changes" to tools menu
* Change disable connection attempts and remove UI references to the TVRage info source
* Change to simplify xem id fetching
* Fix issue on Add Existing Shows page where shows were listed that should not have been
* Change get_size helper to also handle files
* Change improve handling of a bad email notify setting
* Fix provider MTV download URL
* Change give provider OMGWTFNZBS more time to respond
* Change file browser to permit manually entering a path
* Fix updating Trakt collection from Unix


### 0.10.0 (2015-08-06 11:05:00 UTC)

* Remove EZRSS provider
* Update Tornado Web Server to 4.2 (fdfaf3d)
* Update change to suppress reporting of Tornado exception error 1 to updated package (ref:hacks.txt)
* Update fix for API response header for JSON content type and the return of JSONP data to updated package (ref:hacks.txt)
* Update Requests library 2.6.2 to 2.7.0 (8b5e457)
* Update change to suppress HTTPS verification InsecureRequestWarning to updated package (ref:hacks.txt)
* Change to consolidate cache database migration code
* Change to only rebuild namecache on show update instead of on every search
* Change to allow file moving across partition
* Add removal of old entries from namecache on show deletion
* Add Hallmark and specific ITV logos, remove logo of non-english Comedy Central Family
* Fix provider TD failing to find episodes of air by date shows
* Fix provider SCC failing to find episodes of air by date shows
* Fix provider SCC searching propers
* Fix provider SCC stop snatching releases for episodes already completed
* Fix provider SCC handle null server responses
* Change provider SCC remove 1 of 3 requests per search to save 30% time
* Change provider SCC login process to use General Config/Advanced/Proxy host setting
* Change provider SCD PEP8 and code convention cleanup
* Change provider HDB code simplify and PEP8
* Change provider IPT only decode unicode search strings
* Change provider IPT login process to use General Config/Advanced/Proxy host setting
* Change provider TB logo icon used on Config/Search Providers
* Change provider TB PEP8 and code convention cleanup
* Change provider TB login process to use General Config/Advanced/Proxy host setting
* Remove useless webproxies from provider TPB as they fail for one reason or another
* Change provider TPB to use mediaExtensions from common instead of hard-coded private list
* Add new tld variants to provider TPB
* Add test for authenticity to provider TPB to notify of 3rd party block
* Change provider TD logo icon used on Config/Search Providers
* Change provider TD login process to use General Config/Advanced/Proxy host setting
* Change provider BTN code simplify and PEP8
* Change provider BTS login process to use General Config/Advanced/Proxy host setting
* Change provider FSH login process to use General Config/Advanced/Proxy host setting
* Change provider RSS torrent code to use General Config/Advanced/Proxy host setting, simplify and PEP8
* Change provider Wombles's PEP8 and code convention cleanup
* Change provider Womble's use SSL
* Change provider KAT remove dead url
* Change provider KAT to use mediaExtensions from common instead of private list
* Change provider KAT provider PEP8 and code convention cleanup
* Change refactor and code simplification for torrent and newznab providers
* Change refactor SCC to use torrent provider simplification and PEP8
* Change refactor SCD to use torrent provider simplification
* Change refactor TB to use torrent provider simplification and PEP8
* Change refactor TBP to use torrent provider simplification and PEP8
* Change refactor TD to use torrent provider simplification and PEP8
* Change refactor TL to use torrent provider simplification and PEP8
* Change refactor BTS to use torrent provider simplification and PEP8
* Change refactor FSH to use torrent provider simplification and PEP8
* Change refactor IPT to use torrent provider simplification and PEP8
* Change refactor KAT to use torrent provider simplification and PEP8
* Change refactor TOTV to use torrent provider simplification and PEP8
* Remove HDTorrents torrent provider
* Remove NextGen torrent provider
* Add Rarbg torrent provider
* Add MoreThan torrent provider
* Add AlphaRatio torrent provider
* Add PiSexy torrent provider
* Add Strike torrent provider
* Add TorrentShack torrent provider
* Add BeyondHD torrent provider
* Add GFTracker torrent provider
* Add TtN torrent provider
* Add GTI torrent provider
* Fix getManualSearchStatus: object has no attribute 'segment'
* Change handling of general HTTP error response codes to prevent issues
* Add handling for CloudFlare custom HTTP response codes
* Fix to correctly load local libraries instead of system installed libraries
* Update PyNMA to hybrid v1.0
* Change first run after install to set up the main db to the current schema instead of upgrading
* Change don't create a backup from an initial zero byte main database file, PEP8 and code tidy up
* Fix show list view when no shows exist and "Group show lists shows into" is set to anything other than "One Show List"
* Fix fault matching air by date shows by using correct episode/season strings in find search results
* Change add 'hevc', 'x265' and some langs to Config Search/Episode Search/Ignore result with any word
* Change NotifyMyAndroid to its new web location
* Update feedparser library 5.1.3 to 5.2.0 (8c62940)
* Remove feedcache implementation and library
* Add coverage testing and coveralls support
* Add py2/3 regression testing for exception clauses
* Change py2 exception clauses to py2/3 compatible clauses
* Change py2 print statements to py2/3 compatible functions
* Change py2 octal literals into the new py2/3 syntax
* Change py2 iteritems to py2/3 compatible statements using six library
* Change py2 queue, httplib, cookielib and xmlrpclib to py2/3 compatible calls using six
* Change py2 file and reload functions to py2/3 compatible open and reload_module functions
* Change Kodi notifier to use requests as opposed to urllib
* Change to consolidate scene exceptions and name cache code
* Change check_url function to use requests instead of httplib library
* Update Six compatibility library 1.5.2 to 1.9.0 (8a545f4)
* Update SimpleJSON library 2.0.9 to 3.7.3 (0bcdf20)
* Update xmltodict library 0.9.0 to 0.9.2 (579a005)
* Update dateutil library 2.2 to 2.4.2 (a6b8925)
* Update ConfigObj library 4.6.0 to 5.1.0 (a68530a)
* Update Beautiful Soup to 4.3.2 (r353)
* Update jsonrpclib library r20 to (b59217c)
* Change cachecontrol library to ensure cache file exists before attempting delete
* Fix saving root dirs
* Change pushbullet from urllib2 to requests
* Change to make pushbullet error messages clearer
* Change pyNMA use of urllib to requests (ref:hacks.txt)
* Change Trakt url to fix baseline uses (e.g. add from trending)
* Fix edit on show page for shows that have anime enabled in mass edit
* Fix issue parsing items in ToktoToshokan provider
* Change to only show option "Upgrade once" on edit show page if quality custom is selected
* Change label "Show is grouped in" in edit show page to "Show is in group" and move the section higher
* Fix post processing of anime with version tags
* Change accept SD titles that contain audio quality
* Change readme.md


### 0.9.1 (2015-05-25 03:03:00 UTC)

* Fix erroneous multiple downloads of torrent files which causes snatches to fail under certain conditions


### 0.9.0 (2015-05-18 14:33:00 UTC)

* Update Tornado Web Server to 4.2.dev1 (609dbb9)
* Update change to suppress reporting of Tornado exception error 1 to updated package as listed in hacks.txt
* Update fix for API response header for JSON content type and the return of JSONP data to updated package as listed in hacks.txt
* Change network names to only display on top line of Day by Day layout on Episode View
* Reposition country part of network name into the hover over in Day by Day layout
* Update Requests library 2.4.3 to 2.6.2 (ff71b25)
* Update change to suppress HTTPS verification InsecureRequestWarning to updated package as listed in hacks.txt
* Remove listed hacks.txt record for check that SSLv3 is available because issue was addressed by vendor
* Update chardet packages 2.2.1 to 2.3.0 (ff40135)
* Update cachecontrol library 0.9.3 to 0.11.2
* Change prevent wasted API hit where show and exception names create a duplicate sanitised year
* Add FAILED status indication to Snatched column of History compact
* Add ARCHIVED status release groups to Downloaded column of History compact
* Update root certificates to release dated 2015.04.28
* Add ToTV provider
* Fix poster URL on Add Show/Add From Trending page
* Fix Backlog scheduler initialization and change backlog frequency from minutes to days
* Change to consolidate and tidy some provider code
* Fix restore table row colours on the Manage/Episode Status Management page
* Add option "Unaired episodes" to config/Search Settings/Episode Search
* Change reduce time to search recent result list by searching only once for a best result
* Fix replacing episodes that have a lower quality than what is selected in the initial and archive quality list
* Fix to include episodes marked Failed in the recent and backlog search processes
* Fix display of search status for an alternative release after episode is manually set to "Failed" on the Display Show page
* Change handle more varieties of media quality
* Change to prevent another scheduled search when one of the same type is already running
* Change travis to new container builds for faster unit testing
* Add handling for shows that do not have a total number of episodes
* Add support for country network image files to the Show List view
* Add General Config/Interface/"Group show list shows into:"... to divide shows into groups on the Show List page
* Change Show List progress bar code, smaller page load, efficient use of js render engine
* Change values used for date sorting on home page and episode view for improved compatibility with posix systems
* Change response handling in downloaders to simplify logic
* Change reduce html payload across page template files
* Change to post process files ordered largest to smallest and tidied PP logging output
* Add "then trash subdirs and files" to the Process method "Move" on the manual post process page
* Add using show scene exceptions with post processing
* Change URL of scene exceptions file for TVRage indexer
* Change overhaul processTV into a thread safe class
* Change postProcessor and processTV to PEP8 standards
* Change overhaul Manual Post-Processing page in line with layout style and improve texts
* Change Force Processes enabled, only the largest video file of many will be processed instead of all files
* Change visual ui of Postprocessing results to match the logs and errors view
* Change remove ugly printing of episode object during PP seen in external apps like sabnzbd
* Change to streamline output toward actual work done instead of showing all vars
* Change pp report items from describing actions about to happen to instead detail the actual outcome of actions
* Add clarity to the output of a successful post process but with some issues rather than "there were problems"
* Add a conclusive bottom line to the pp result report
* Change helpers doctests to unittests
* Add Search Queue Overview page
* Add expandable search queue details on the Manage Searches page
* Fix failed status episodes not included in next_episode search function
* Change prevent another show update from running if one is already running
* Change split Force backlog button on the Manage Searches page into: Force Limited, Force Full
* Change refactor properFinder to be part of the search
* Change improve threading of generic_queue, show_queue and search_queue
* Change disable the Force buttons on the Manage Searches page while a search is running
* Change staggered periods of testing and updating of all shows "ended" status up to 460 days
* Change "Archive" to "Upgrade to" in Edit show and other places and improve related texts for clarity
* Fix history consolidation to only update an episode status if the history disagrees with the status


### 0.8.3 (2015-04-25 08:48:00 UTC)

* Fix clearing of the provider cache


### 0.8.2 (2015-04-19 06:45:00 UTC)

* Fix IPTorrents provider search strings and URL for new site changes


### 0.8.1 (2015-04-15 04:16:00 UTC)

* Fix season pack search errors


### 0.8.0 (2015-04-13 14:00:00 UTC)

* Change Wombles to use tv-dvd section
* Add requirements file for pip (port from midgetspy/sick-beard)
* Remove unused libraries fuzzywuzzy and pysrt
* Change webserve code to a logical layout and PEP8
* Add text to explain params passed to extra scripts on Config/Post Processing
* Remove unused SickBeardURLOpener and AuthURLOpener classes
* Update Pushbullet notifier (port from midgetspy/sickbeard)
* Change startup code cleanup and PEP8
* Change authentication credentials to display more securely on config pages
* Add a "Use as default home page" selector to General Config/Interface/User Interface
* Add option to the third step of "Add Show" to set episodes as wanted from the first and latest season, this triggers
  a backlog search on those episodes after the show is added
* Change to improve the integrity of the already post processed video checker
* Add Kodi notifier and metadata
* Add priority, device, and sound support to Pushover notifier (port from midgetspy/sickbeard)
* Fix updating of pull requests
* Add hidden cache debug page
* Change autoProcessTV scripts python code quotes from " -> '
* Add expand all button to Episode Status Management
* Add Unknown status query to Episode Status Management
* Fix Episode Status Management error popup from coming up when show is selected without expanding
* Add BET network logo
* Change "Force Backlog" button for paused shows on Backlog Overview page to "Paused" indicator
* Remove unused force variable from code and PEP8
* Change browser, bs4 parser and classes code to PEP8 standards
* Change common and config code to PEP8 standards
* Change database code to PEP8 standards
* Change general config's branches and pull request list generation for faster page loading
* Add PlayStation Network logo
* Change layout of Recent Search code
* Change naming of SEARCHQUEUE threads for shorter log lines
* Fix Recent Search running status on Manage Searches page
* Change to no longer require restart with the "Scan and post process" option on page config/Post Processing
* Add validation when using Release Group token on page config Post Processing/Episode Naming/Name pattern/Custom
* Change to simplify and reduce logging output of Recent-Search and Backlog processes
* Hide year, runtime, genre tags, country flag, or status if lacking valid data to display
* Remove redundant CSS color use (all browsers treat 3 identical digits as 6, except for possibly in gradients)
* Remove whitespace and semi-colon redundancy from CSS shedding 4.5kb
* Add show names to items listed during startup in the loading from database phase
* Add "Enable IMDb info" option to config/General/Interface
* Change to not display IMDb info on UI when "Enable IMDb info" is disabled
* Change genre tags on displayShow page to link to IMDb instead of Trakt
* Change to reduce the time taken to "Update shows" with show data
* Change to stop updating the IMDb info on edit, and during the scheduled daily update for every show
* Change to update the IMDb info for a show after snatching an episode for it
* Add IMDb lookup to "Update" action on Manage/Mass Update page
* Fix updating of scene exception name cache after adding exceptions on Editshow page
* Change log rotation to occur at midnight
* Change to keep a maximum of 7 log files
* Add automatic compression of old log files
* Change overhaul menu and button icons
* Add "Status of removed episodes" to apply (or not) a preferred status to episodes whose files are detected as removed.
  "Archived" can now be set so that removed episodes still count toward download completion stats. See setting on page
  config/Post Processing/File Handling
* Remove redundant "Skip remove detection" from the config/Post Processing/File Handling page
* Change to highlight the current selected item in combos on page config/Post Processing
* Change the episodes downloaded stat to display e.g. 2843 / 2844 as 99.9% instead of rounding to 100%
* Change 'never' episode row color away from blue on Display Show page when indexer airdate is not defined
* Add tint to archived episode row colour to differentiate it from downloaded episodes on the Display Show page
* Add indication of shows with never aired episodes on Episode Overview page
* Add "Collapse" button and visuals for Expanding... and Collapsing... states
* Add the number of episodes marked with the status being queried to Episode Overview page
* Add indication of shows with never aired episodes on Episode Overview page
* Change to separate "Set as wanted" to prevent disaster selection on Episode Overview page
* Remove restriction to not display snatched eps link in footer on Episode Overview page
* Change the shows episodes count text colour to visually separete from year numbers at the end of show names
* Change to add clarity to the subtitle and other columns on the Mass Update page
* Change to improve clarity with "Recent search" and "Limited backlog" on the Config/Search Settings page
* Change vertical alignment of input fields to be inline with text
* Add tooltips to explain why any the 6 action columns are disabled when required on the Mass Update page
* Change to reclaimed screen estate by hiding unused columns on the Mass Update page
* Change order of option on Mass Edit page to be inline with show edit page
* Fix release group not recognised from manually downloaded filename
* Change to gracefully handle some "key not found" failures when TVDB or TVRage return "Not Found" during show updates
* Change no longer stamp files where airdates are never
* Change overhaul displayShow to ready for new features
* Add section for show plot to displayShow
* Add option to view show background on displayShow (transparent and opaque) for when background downloading is added (disabled)
* Add option to collapse seasons and leave current season open on displayShow (disabled)
* Add filesize to episode location qtip on displayShow
* Change selected options from editShow will only show when enabled now on displayShow
* Change some label tags to fit with edit show page on displayShow
* Fix handle when a show in db has all episodes removed from indexer on displayShow
* Add the name of show that will be displayed to the hover of the Prev/Next show buttons on displayShow
* Add hover tooltips for nfo and tbn columns for browsers that use the title attr on displayShow
* Change Special link moved from "Season" line to "Specials" line on displayShow
* Change code re-factored in readiness for live option switching, clean up and add closures of html tables
* Add show overview from indexers to the database
* Fix case where start year or runtime is not available to display show
* Add "File logging level" to General Config/Advanced Settings
* Fix saving of Sort By/Next Episode in Layout Poster on Show List page
* Change improve backlog search
* Change only add valid items to save to DB
* Change provider cache storage structure
* Add handling for failed cache database upgrades
* Fix XEM Exceptions in case of bad data from XEM
* Change order of snatched provider images to chronological on History layout compact and add ordinal indicators in the tooltips


### 0.7.2 (2015-03-10 17:05:00 UTC)

* Fix Add From Trending page (indexer_id can be "None" which causes white screen when clicking "Add Show")


### 0.7.1 (2015-03-10 17:00:00 UTC)

* Fix error page when clicking "Add Recommended"
* Remove failed Anime options from "Add Existing Show"


### 0.7.0 (2015-03-04 06:00:00 UTC)

* Fix slow database operations (port from midgetspy/sickbeard)
* Add TVRage network name standardization
* Remove recent and backlog search at start up options from GUI
* Change recent and backlog search at start up default value to false
* Change recent search to occur 5 minutes after start up
* Change backlog search to occur 10 minutes after start up
* Change UI footer to display time left until a backlog search
* Remove obsolete tvtorrents search provider
* Change light and dark theme css to only hold color information
* Fix incorrect class names in a couple of templates
* Change anime release groups to in memory storage for lowered latency
* Change adjust menu delay and hover styling
* Fix provider list color
* Add handling of exceptional case with missing network name (NoneType) in Episode View
* Fix black and white list initialization on new show creation
* Add select all and clear all buttons to testRename template
* Fix displayShow topmenu variable to point to a valid menu item
* Change displayShow scene exception separator to a comma for neater appearance
* Remove non english subtitle providers
* Fix rename of excluded metadata
* Change corrected spelling & better clarified various log messages
* Change minor PEP8 tweaks in sab.py
* Add api disabled error code for newznab providers
* Add support for a proxy host PAC url on the General Config/Advanced Settings page
* Add proxy request url parsing to enforce netloc only matching which prevents false positives when url query parts contain FQDNs
* Add scroll into view buttons when overdues shows are available on the Episodes page/DayByDay layout
* Add scroll into view buttons when future shows are available on the Episodes page/DayByDay layout
* Add qTips to episode names on the Episodes page/DayByDay layout
* Change Episodes page/List layout qtips to prepend show title to episode plot
* Change Episodes page/DayByDay layout qtips to prepend show title to episode plot
* Change Episodes page/DayByDay layout cards to display show title in a qtip when there is no plot
* Change position of "[paused]" text to top right of a card on the Episodes page/DayByDay layout
* Add "On Air until" text and overdue/on air colour bars to show episode states on the Episodes page/DayByDay layout
* Change The Pirate Bay url back as it's now back up and oldpiratebay hasn't been updated for weeks
* Remove duplicate thepiratebay icon
* Change to ensure uTorrent API parameters are ordered for uT 2.2.1 compatibility
* Remove defunct boxcar notifier
* Add sound selection for boxcar2 notifier
* Change boxcar2 notifier to use updated api scheme
* Update the Plex notifier from a port at midgetspy/sickbeard
* Add support for multiple server hosts to the updated Plex server notifier
* Change Plex Media Server settings section for multi server(s) and improve the layout in the config/notifications page
* Add logic to Plex notifier to update a single server where its TV section path matches the downloaded show. All server
  libraries are updated if no single server has a download path match.
* Change the ui notifications to show the Plex Media Server(s) actioned for library updating
* Fix issue where PMS text wasn't initialised on the config/notifications page and added info about Plex clients
* Add ability to test Plex Server(s) on config/notifications page
* Add percentage of episodes downloaded to footer and remove double spaces in text
* Fix SSL authentication on Synology stations
* Change IPT urls to reduce 301 redirection
* Add detection of file-system having no support for link creation (e.g. Unraid shares)
* Add catch exceptions when unable to cache a requests response
* Update PNotify to latest master (2014-12-25) for desktop notifications
* Add desktop notifications
* Change the AniDB provider image for a sharper looking version
* Change to streamline iCal function and make it handle missing network names
* Change when picking a best result to only test items that have a size specifier against the failed history
* Add anime release groups to add new show options page
* Add setting "Update shows during hour" to General Config/Misc
* Add max-width to prevent ui glitch on Pull request and Branch Version selectors on config/General/Advanced and change <input> tags to html5
* Change order of some settings on Config/General/Interface/Web Interface and tweak texts
* Change overhaul UI of editShow and anime release groups, refactor and simplify code
* Change list order of option on the right of the displayShow page to be mostly inline with the order of options on editShow
* Change legend wording and text colour on the displayShow page
* Add output message if no release group results are available
* Add cleansing of text used in the processes to a add a show
* Add sorting of AniDB available group results
* Add error handling and related UI feedback to reflect result of AniDB communications
* Change replace HTTP auth with a login page
* Change to improve webserve code
* Add logout menu item with confirmation
* Add 404 error page
* Change SCC URLs to remove redirection overhead
* Change TorrentBytes login parameter in line with site change
* Change FreshOnTv login parameter and use secure URLs, add logging of Cloudflare blocking and prevent vacant cookie tracebacks
* Change TPB webproxy list and add SSL variants
* Add YTV network logo
* Remove defunct Fanzub provider


### 0.6.4 (2015-02-10 20:20:00 UTC)

* Fix issue where setting the status for an episode that doesn't need a db update fails


### 0.6.3 (2015-02-10 05:30:00 UTC)

* Change KickAssTorrents URL


### 0.6.2 (2015-01-21 23:35:00 UTC)

* Fix invalid addition of trailing slash to custom torrent RSS URLs


### 0.6.1 (2015-01-20 14:00:00 UTC)

* Fix snatching from TorrentBytes provider


### 0.6.0 (2015-01-18 05:05:00 UTC)

* Add network logos BBC Canada, Crackle, El Rey Network, SKY Atlantic, and Watch
* Change Yahoo! screen network logo
* Add and update Discovery Network's channel logos
* Add A&E Network International/Scripps Networks International channel logos
* Remove non required duplicate network logos
* Add lowercase PM to the General Config/Interface/Time style selection
* Change General Config/Interface/Trim zero padding to Trim date and time, now handles 2:00 pm > 2 pm
* Fix trim zero of military time hour to not use 12 hr time
* Change ThePirateBay to use oldpiratebay as a temporary fix
* Change Search Settings/Torrent/Deluge option texts for improved understanding
* Fix Womble's Index searching (ssl disabled for now, old categories are the new active ones again)
* Fix Add From Trending Show page to work with Trakt changes
* Add anime unit test cases (port from lad1337/sickbeard)
* Fix normal tv show regex (port from midgetspy/sickbeard)
* Fix anime regex (port from lad1337/sickbeard)
* Add pull request checkout option to General Config/Advanced Settings
* Add BTN api call parameter debug logging
* Fix anime searches on BTN provider
* Change replace "Daily-Search" with "Recent-Search"
* Add daily search to recent search renaming to config migration code
* Fix 'NoneType' object is not iterable in trakt module
* Add log message for when trakt does not return a watchlist
* Change Coming Episodes calendar view to a fluid layout, change episode layout design, and add day and month in column headers
* Add isotope plug-in to Coming Episodes calendar view to enable sort columns by Date, Network, and Show name
* Add imagesLoaded plug-in to prevent layout breakage by calling isotope to update content after a page auto-refresh
* Change Coming Episodes to "Episodes" page (API endpoint is not renamed)
* Add coming episodes to episode view renaming to config migration code
* Change Layout term "Calender" to "Day by Day" on Episodes page
* Fix saving of sort modes to config file on Episodes page
* Add qTip episode plots to "Day by Day" on Episodes page
* Add article sorting to networks on Episodes page
* Add toggle sort direction and multidimensional sort to isotope on Episodes page
* Add text "[paused]" where appropriate to shows on layout Day by Day on Episodes page
* Change Epsiodes page auto refresh from 10 to 30 mins
* Add UI tweaks
* Fix progress bars disappearing on home page


### 0.5.0 (2014-12-21 11:40:00 UTC)

* Fix searches freezing due to unescaped ignored or required words
* Add failed database to unit tests tear down function
* Fix purging of database files in tear down function during unit tests
* Add ability to auto focus Search Show box on Home page and control this option via General Config/Interface
* Change some provider images. Add a few new images
* Remove redundant Coming Eps template code used in the old UI
* Change update Plex notifier (port from SickBeard)
* Change Plex notifications to allow authenticated library updates (port from mmccurdy07/Sick-Beard)
* Change Config/Notifications/Plex logo and description (adapted port from mmccurdy07/Sick-Beard)
* Add ability for CSS/JS to target a specific page and layout
* Remove legacy sickbeard updater and build automation code
* Fix multiple instances of SG being able to start
* Fix garbled text appearing during startup in console
* Fix startup code order and general re-factoring (adapted from midgetspy/Sick-Beard)
* Add database migration code
* Change KickassTorrents provider URLs
* Fix missing Content-Type headers for posters and banners
* Remove config Backup & Restore
* Fix article removal for sorting on Display Show, and API pages
* Fix visual positioning of sprites on Config page
* Fix missing navbar gradients for all browsers
* Update qTip2 to v2.2.1
* Overhaul all Add Show pages
* Fix Display Show next/previous when show list is split
* Change Display Show next/previous when show list is not split to loop around
* Fix SQL statements that have dynamic table names to use proper syntax
* Fix port checking code preventing startup directly after a SG restart
* Add a link from the footer number of snatched to episode snatched overview page. The link to the
  Episode Overview page is available on all pages except on the Episode Overview page
* Change the default state for all check boxes on the Episode Overview page to not checked
* Add validation to Go button to ensure at least one item is checked on Episode Overview page
* Add highlight to current status text in header on Episode Overview page
* Fix table alignment on homepage
* Fix duplicate entries in cache database
* Fix network sorting on home page
* Fix restart issue
* Fix to use new TorrentDay URLs
* Fix typo in menu item Manage/Update XBMC


### 0.4.0 (2014-12-04 10:50:00 UTC)

* Change footer stats to not add newlines when copy/pasting from them
* Remove redundant references from Config/Help & Info
* Fix poster preview on small poster layout
* Change overhaul Config/Anime to be in line with General Configuration
* Change descriptions and layout on Config/Anime page
* Remove output of source code line when warnings highlight libraries not used with IMDb
* Add dropdown on Add Trending Shows to display all shows, shows not in library, or shows in library
* Change Help and Info icon sprites to color and text of Arguments if unused
* Change sharper looking heart image on the Add Show page
* Change Add Show on Add Trending Show page to use the full Add New Show flow
* Fix adding shows with titles that contain "&" on Add Trending Show page
* Fix unset vars on Add New Shows page used in the Add Existing Shows context
* Remove unneeded datetime convert from Coming Episodes page
* Fix the log output of the limited backlog search for episodes missed
* Remove unsupported t411 search provider
* Remove obsolete Animezb search provider
* Add option to treat anime releases that lack a quality tag as HDTV instead of "unknown"
* Remove old version checking code that no longer applies to SickGear's release system
* Fix pnotify notifications going full page
* Change overhaul Config Post Processing to be in line with General Configuration
* Change rearrange Config Post Processing items into sections for easier use
* Fix CSS overriding link colors on config pages
* Change Config Post Processing texts and descriptions throughout
* Fix Config Post Processing info icons in "Naming Legends"
* Change Config Post Processing naming sample lines to be more available
* Add Config Post Processing failed downloads Sabnzbd setup guide
* Fix Config Post Processing "Anime name pattern" custom javascript validation
* Add check that SSLv3 is available before use by requests lib
* Update Requests library 2.3.0 to 2.4.3 (9dc6602)
* Change suppress HTTPS verification InsecureRequestWarning as many sites use self-certified certificates
* Fix API endpoint Episode.SetStatus to "Wanted"
* Change airdateModifyStamp to handle hour that is "00:00"
* Fix a handler when ShowData is not available in TVDB and TVRage APIs
* Fix a handler when EpisodeData is not available in TVDB and TVRage APIs
* Add TVRage "Canceled/Ended" as "Ended" status to sort on Simple Layout of Show List page
* Fix qtips on Display Show and Config Post Processing
* Fix glitch above rating stars on Display Show page
* Change overhaul Config/Search Providers
* Change Config/Search Providers texts and descriptions
* Fix display when no providers are visible on Config/Search Providers
* Fix failing "Search Settings" link that is shown on Config/Search Providers when Torrents Search is not enabled
* Fix failing "Providers" link on Config/Search Settings/Episode Search
* Change case of labels in General Config/Interface/Timezone
* Split enabled from not enabled providers in the Configure Provider drop down on the Providers Options tab
* Fix typo on General Config/Misc
* Fix Add Trending Shows "Not In library" now filters tvrage added shows
* Add a hover over text "In library" on Add Trending Shows to display tv database show was added from
* Fix reduces time API endpoint Shows takes to return results
* Fix Coming Eps Page to include shows +/- 1 day for time zone corrections
* Fix season jumping dropdown menu for shows with over 15 seasons on Display Show
* Fix article sorting for Coming Eps, Manage, Show List, Display Show, API, and Trending Shows pages


### 0.3.1 (2014-11-19 16:40:00 UTC)

* Fix failing travis test


### 0.3.0 (2014-11-12 14:30:00 UTC)

* Change logos, text etc. branding to SickGear
* Add Bootstrap for UI features
* Change UI to resize fluidly on different display sizes, fixes the issue where top menu items would disappear on smaller screens
* Add date formats "dd/mm/yy", "dd/mm/yyyy", "day, dd/mm/yy" and "day, dd/mm/yyyy"
* Remove imdb watchlist feature from General Configuration/"Misc" tab as it wasn't ready for prime time
* Change rename tab General Configuration/"Web Interface" to "Interface"
* Add "User Interface" section to the General Configuration/"Interface" tab
* Change combine "Date and Time" and "Theme" tab content to "User Interface" section
* Add field in Advanced setting for a custom remote name used to populate branch versions
* Change theme name "original" to "light"
* Change text wording on all UI options under General Configuration
* Change reduce over use of capitals on all General Configuration tabs
* Change streamline UI layout, mark-up and some CSS styling on General Configuration tabs
* Fix imdb and three other images rejected by IExplorer because they were corrupt. Turns out that they were .ico files renamed to either .gif or .png instead of being properly converted
* Change cleanup Subtitles Search settings text, correct quotations, use spaces for code lines, tabs for html
* Add save sorting options automatically on Show List/Layout Poster
* Change clarify description for backlog searches option on provider settings page
* Fix sort mode "Next Episode" on Show List/Layout:Poster with show statuses that are Paused, Ended, and Continuing as they were random
* Fix sort of tvrage show statuses "New" and "Returning" on Show List/Layout:Simple by changing status column text to "Continuing"
* Add dark spinner to "Add New Show" (searching indexers), "Add existing shows" (Loading Folders), Coming Eps and all config pages (when saving)
* Change Config/Notifications test buttons to stop and highlight input fields that lack required values
* Change Test Plex Media Server to Test Plex Client as it only tests the client and not the server
* Change style config_notifications to match new config_general styling
* Change style config_providers to match new config_general styling
* Change move Providers Priorities qtip options to a new Search Providers/Provider Options tab
* Remove superfish-1.4.8.js and supersubs-0.2b.js as they are no longer required with new UI
* Change overhaul Config Search Settings in line with General Configuration
* Fix error when a show folder is deleted outside of SickGear
* Change combine the delete button function into the remove button on the display show page
* Change other small UI tweaks
* Fix keyerrors on backlog overview preventing the page to load
* Fix exception raised when converting 12pm to 24hr format and handle 12am when setting file modify time (e.g. used during PP)
* Fix proxy_indexers setting not loading from config file
* Add subtitle information to the cmd show and cmd shows api output
* Remove http login requirement for API when an API key is provided
* Change API now uses Timezone setting at General Config/Interface/User Interface at relevant endpoints
* Fix changing root dirs on the mass edit page
* Add use trash (or Recycle Bin) for selected actions on General Config/Misc/Send to trash
* Add handling for when deleting a show and the show folder no longer exists
* Fix Coming Episodes/Layout Calender/View Paused and tweak its UI text
* Made all init scripts executable
* Fix invalid responses when using sickbeard.searchtvdb api command
* Fixes unicode issues during searches on newznab providers when rid mapping occur
* Fix white screen of death when trying to add a show that is already in library on Add Show/Add Trending Show page
* Add show sorting options to Add Show/Add Trending Show page
* Add handler for when Trakt returns no results for Add Show/Add Trending Show page
* Fix image links when anchor child images are not found at Trakt on Add Show/Add Trending Show page
* Add image to be used when Trakt posters are void on Add Show/Add Trending Show page
* Fix growl registration not sending SickGear an update notification registration
* Add an anonymous redirect builder for external links
* Update xbmc link to Kodi at Config Notifications
* Fix missing url for kickasstorrents in config_providers
* Fix post processing when using tvrage indexer and mediabrowser metadata generation
* Change reporting failed network_timezones.txt updates from an error to a warning
* Fix missing header and "on <missing text>" when network is none and Layout "Poster" with Sort By "Network" on coming episodes page
* Change how the "local/network" setting is handled to address some issues
* Remove browser player from Config General and Display Shows page


### 0.2.2 (2014-11-12 08:25:00 UTC)

* Change updater URLs to reflect new repository location


### 0.2.1 (2014-10-22 06:41:00 UTC)

* Fix HDtorrents provider screen scraping


### 0.2.0 (2014-10-21 12:36:50 UTC)

* Fix for failed episodes not counted in total
* Fix for custom newznab providers with leading integer in name
* Add checkbox to control proxying of indexers
* Fix crash on general settings page when git output is None
* Add subcentre subtitle provider
* Add return code from hardlinking error to log
* Fix ABD regex for certain filenames
* Change miscellaneous UI fixes
* Update Tornado Web Server to 4.1dev1 and add the certifi lib dependency
* Fix trending shows page from loading full size poster images
* Add "Archive on first match" to Manage, Mass Update, Edit Selected page
* Fix searching IPTorrentsProvider
* Remove travisci python 2.5 build testing


### 0.1.0 (2014-10-16 12:35:15 UTC)

* Initial release
