### 0.12.0 (2016-xx-xx xx:xx:xx UTC)

* Add strict Python version check (equal to, or higher than 2.7.9 and less than 3.0), **exit** if incorrect version
* Update unidecode library 0.04.11 to 0.04.18 (fd57cbf)
* Update xmltodict library 0.9.2 (579a005) to 0.9.2 (eac0031)
* Update Tornado Web Server 4.3.dev1 (1b6157d) to 4.4.dev1 (c2b4d05)
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
  Mass Update, Add with Browse and from Existing views
* Add Emby notifier to config/Notifications
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
* Add ILT torrent provider
* Add Fano torrent provider
* Add BTScene torrent provider
* Add Extratorrent provider
* Add Limetorrents provider
* Add nCore torrent provider
* Add Torrentz2 provider
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
* Add indicator for public access search providers
* Change improve probability selecting most seeded release
* Change add the TorrentDay x265 category to search
* Add smart logic to reduce api hits to newznab server types and improve how nzbs are downloaded
* Add newznab smart logic to avoid missing releases when there are a great many recent releases
* Change improve performance by using newznab server advertised capabilities
* Change config/providers newznab to display only non-default categories
* Change use scene season for wanted segment in backlog if show is scene numbering
* Change combine Manage Searches / Backlog Search / Limited and Full to Force
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

[develop changelog]
* Change send nzb data to NZBGet for Anizb instead of url
* Change revert test_common.py include file placement so Travis builds don't fail
* Fix Nyaa and TT torrent providers
* Change PrivateHD torrent provider
* Fix Add from Trakt
* Change unpack files once only in auto post processing copy mode
* Fix data logger for clients
* Change handle when a torrent provider goes down and its urls are cleared
* Add handler for when rar files can not be opened during post processing
* Fix join clean up


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
* Change displayShow page episode colours when a minimum quality is met with "End upgrade on first match"
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
* Change to only show option "End upgrade on first match" on edit show page if quality custom is selected
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
