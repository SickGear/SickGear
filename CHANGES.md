### 0.5.0 (2014-12-14 13:55:00 UTC)

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
