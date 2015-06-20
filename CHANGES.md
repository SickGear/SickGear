### 0.10.0 (2015-xx-xx xx:xx:xx UTC)

* Remove EZRSS provider
* Update Tornado webserver to 4.2 (fdfaf3d)
* Update change to suppress reporting of Tornado exception error 1 to updated package (ref:hacks.txt)
* Update fix for API response header for JSON content type and the return of JSONP data to updated package (ref:hacks.txt)
* Update Requests library 2.6.2 to 2.7.0 (8b5e457)
* Update change to suppress HTTPS verification InsecureRequestWarning to updated package (ref:hacks.txt)
* Change to consolidate cache database migration code
* Change to only rebuild namecache on show update instead of on every search
* Add removal of old entries from namecache on show deletion
* Add Hallmark and specific ITV logos, remove logo of non-english Comedy Central Family
* Fix provider SCC failing to find episodes of air by date shows
* Fix provider SCC searching propers
* Fix provider SCC stop snatching releases for episodes already completed
* Fix provider SCC handle null server responses
* Change provider SCC remove 1 of 3 requests per search to save 30% time
* Remove useless webproxies from provider TPB as they fail for one reason or another
* Change provider TPB to use mediaExtensions from common instead of hard-coded private list
* Add new tld variants to provider TPB
* Add test for authenticity to provider TPB to notify of 3rd party block
* Change provider Womble's use SSL
* Change provider KAT remove dead url
* Change provider KAT to use mediaExtensions from common instead of private list
* Change provider KAT provider PEP8 and code convention cleanup
* Change refactor and code simplification for torrent providers
* Remove NextGen torrent provider
* Add Rarbg torrent provider
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

[develop changelog]
* Update Requests library 2.7.0 (ab1f493) to 2.7.0 (8b5e457)
* Update Tornado webserver from 4.2.dev1 (609dbb9) to 4.2b1 (61a16c9)
* Change reload_module call to explicit import lib/six.moves
* Change queue, httplib, cookielib and xmlrpclib to use explicit import lib/six.moves
* Change zoneinfo update/loader to be compatible with dateutil 2.4.2
* Change use metadata for zoneinfo files and remove hack of dateutil lib
* Change param item "features" passed to Beautiful Soup to prevent false +ve warning in r353


### 0.9.1 (2015-05-25 03:03:00 UTC)

* Fix erroneous multiple downloads of torrent files which causes snatches to fail under certain conditions


### 0.9.0 (2015-05-18 14:33:00 UTC)

* Update Tornado webserver to 4.2.dev1 (609dbb9)
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
* Update Tornado webserver to 4.1dev1 and add the certifi lib dependency
* Fix trending shows page from loading full size poster images
* Add "Archive on first match" to Manage, Mass Update, Edit Selected page
* Fix searching IPTorrentsProvider
* Remove travisci python 2.5 build testing


### 0.1.0 (2014-10-16 12:35:15 UTC)

* Initial release
