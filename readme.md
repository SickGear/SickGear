<hr>
<div><a id="top"><img alt="SickGear" width="200" src="https://raw.githubusercontent.com/wiki/SickGear/SickGear/images/SickGearLogo.png"></a></div>
**SickGear**, a usenet and bittorrent PVR
<hr>
SickGear is Beta software.  *Please note that this software is not for the masses*.  We require you to be knowledgeable about how to use git and setup basic requirements in order to run this software.  Please use a search engine if you are unsure how to perform a task, before asking us about it! *If this is __not__ for you, then please do not use this software!*

SickGear provides management of TV shows and/or Anime, can detect wanted or episodes to upgrade and make use of downloader applications.  SickGear is proud to be a descendant of SickBeard and is honoured to be endorsed by one of its former lead developers.  

## Features include
* Stable, quality assured testing and development cycle
* Innovations that inspire imitators
* Most comprehensive selection of usenet and torrent sources
* Episode management
  * View missed and upcoming shows at a glance with "day by day" and other layouts
  * Group shows into personalised sections in a full show list view
  * Automatic and manual search for availability of wanted episodes
  * Set what episodes you want and how to receive them
  * Uses well known established index sites to gather show information
  * Searches for known alternatively named shows with a fallback to user edited names
  * Searches for known alternatively numbered episodes with a fallback to user edited numbers
  * Forward search results to a downloader program (e.g. SABNZBd, NZBGet, uTorrent, and others)
  * Save search results to a "blackhole" folder that can be periodically scanned for taking action
  * Post-process downloaded episodes into customisable layouts, with or without extra metadata
  * Advanced Failed Download Handling (FDH)
  * Overview of seasons, episodes, rating, version, airdate, episode status ([their meaning](https://github.com/SickGear/SickGear/wiki/Episode-Status))
* Subtitle management
* Notification
  * System notifiers (i.e. XBMC, Kodi, Plex)
  * Device notifiers (i.e. Growl, Prowl, Notify My Android)
  * Social (i.e. Twitter, E-mail)
* Server friendly with minimal number of calls (e.g. one request per chosen snatch, not per result)
* Let SickGear recommend trendy shows

Some of our innovative features;
* Automated search after adding a show
* Desktop notifications
* Enhanced Anime features when adding shows
* Visual percentage progress of managed episodes
* Separate Plex server and Plex client settings
* Intelligent library updates that target Plex servers that list the show of an episode
* Configurable episode status for removed media files
* Configurable default home page
* Source providers
* User Interface

## Available versions
<table><thead></thead><tbody>
<tr align="center">
  <td>Master</td><td>(most stable)</td><td><a id="top" title=""><img src="https://raw.githubusercontent.com/wiki/SickGear/SickGear/images/badge-stability.png"></a></td><td><a id="top" title=""><img src="https://raw.githubusercontent.com/wiki/SickGear/SickGear/images/badge-stable.png"></a></td>
</tr>
<tr align="center">
  <td>Development</td><td>(mostly stable)</td><td><a id="top" title="Where some imitate"><img src="https://raw.githubusercontent.com/wiki/SickGear/SickGear/images/badge-innovate.png"></a></td><td><a title="Build Status: Passing = All good!" target="_blank" href="https://travis-ci.org/SickGear/SickGear"><img src="https://travis-ci.org/SickGear/SickGear.svg?branch=develop"></a></td>
</tr>
</tbody>
</table>

## Required software
* Python 2.6+
* Cheetah 2.1.0+

## Howto

#### Install
* [Ubuntu](https://github.com/SickGear/SickGear/wiki/Install-SickGear-[1]-Ubuntu)
* [CentOS / RHEL / Fedora](https://github.com/SickGear/SickGear/wiki/Install-SickGear-[2]-CentOS-RHEL)
* [Arch Linux](https://github.com/SickGear/SickGear/wiki/Install-SickGear-[3]-Arch-Linux)
* [Synology](https://github.com/SickGear/SickGear/wiki/Install-SickGear-[4]-Synology)

#### Contribute code
Please read through our [guide](https://github.com/SickGear/SickGear/wiki/%5BHow-to%5D-Contribute-Code).  Included are directions for coding in git and how to submit pull requests.
Moreover, if your pull request is about a new feature, please try not to use more than 200 characters explaining its function.  Instead, talk to our devs in our IRC channel (link below).

#### Report issues
As reported issues can get messy, we've set up a few [guidelines](https://github.com/SickGear/SickGear/wiki/%5BHow-to%5D-Report-Issues) so that we can quickly get to the heart of the issue that is reported.  Please note that we require all the information in there! Any missing information might result in the reported issue being denied!

## Contributors

#### Core code
A huge shout out goes to the following people; MidgetSpy, zoggy, 1337, Tolstyak, Mr_Orange, Bricky, JackDandy, adam111316, Supremicus, Prinz23, and ressu (zanaga)

#### Other things, testers and QA
Also, warm thanks to tehspede, CtrlAltDefeat, vergessen (betrayed), Mike, and Rawh for their keen eye, all around help, and making sure all manner of things work as expected ( mostly! :) )

#### Provider code
Thanks also, to the unsung heroes that added source providers; Idan Gutman, Daniel Heimans, jkaberg, and Seedboy

Finally, a massive thanks to all those that remain in the shadows, the quiet ones that welcome folk to special places, we salute you for your hospitality and for tirelessly keeping up operations.

## Community
* Support
  * Please note that, aside from bug reports, we do *not* offer support.  We can offer some help, but we really need you to understand the basics of your Linux or Windows OS.  If you do not understand basics such as locating a database file, not running as root, setting up file permissions, or claiming a user derp, then we really cannot help you!
  * IRC: `irc.freenode.net` channel `#SickGear`
  * Webchat IRC: [webchat link](http://webchat.freenode.net/?channels=SickGear)

## Screenies
<table><thead></thead><tbody>
<tr align="center">
  <td><a title="Show List - Layout: Simple" href="https://raw.githubusercontent.com/wiki/SickGear/SickGear/images/screenies/showlist-simple.jpg"><img src="https://raw.githubusercontent.com/wiki/SickGear/SickGear/images/screenies/showlist-simple-t.jpg" width="200"></a></td>
  <td><a title="Show List - Layout: Banner" href="https://raw.githubusercontent.com/wiki/SickGear/SickGear/images/screenies/showlist-banner.jpg"><img src="https://raw.githubusercontent.com/wiki/SickGear/SickGear/images/screenies/showlist-banner-t.jpg" width="200"></a></td>
  <td><a title="Show List - Layout: Poster" href="https://raw.githubusercontent.com/wiki/SickGear/SickGear/images/screenies/showlist-poster.jpg"><img src="https://raw.githubusercontent.com/wiki/SickGear/SickGear/images/screenies/showlist-poster-t.jpg" width="200"></a></td>
  <td><a title="Episode View - Layout: Day by Day" href="https://raw.githubusercontent.com/wiki/SickGear/SickGear/images/screenies/episodeview-day-by-day.jpg"><img src="https://raw.githubusercontent.com/wiki/SickGear/SickGear/images/screenies/episodeview-day-by-day-t.jpg" width="200"></a></td>
  <td><a title="Episode View - Layout: List" href="https://raw.githubusercontent.com/wiki/SickGear/SickGear/images/screenies/episodeview-list.jpg"><img src="https://raw.githubusercontent.com/wiki/SickGear/SickGear/images/screenies/episodeview-list-t.jpg" width="200"></a></td>
  <td><a title="Display Show" href="https://raw.githubusercontent.com/wiki/SickGear/SickGear/images/screenies/displayshow.jpg"><img src="https://raw.githubusercontent.com/wiki/SickGear/SickGear/images/screenies/displayshow-t.jpg" width="200"></a></td>
</tr>
<tr align="center">
  <td>Show List: Simple<br />Theme: <a title="Theme Dark" href="https://raw.githubusercontent.com/wiki/SickGear/SickGear/images/screenies/showlist-simple.jpg">Dark</a>, <a title="Theme Light" href="https://raw.githubusercontent.com/wiki/SickGear/SickGear/images/screenies/showlist-simple-light.jpg">Light</a></td>
  <td>Show List: Banner<br />Theme: <a title="Theme Dark" href="https://raw.githubusercontent.com/wiki/SickGear/SickGear/images/screenies/showlist-banner.jpg">Dark</a>, <a title="Theme Light" href="https://raw.githubusercontent.com/wiki/SickGear/SickGear/images/screenies/showlist-banner-light.jpg">Light</a></td>
  <td>Show List: Poster<br />Theme: <a title="Theme Dark - Anime" href="https://raw.githubusercontent.com/wiki/SickGear/SickGear/images/screenies/showlist-poster.jpg">Dark 1</a>, <a title="Theme Dark 2" href="https://raw.githubusercontent.com/wiki/SickGear/SickGear/images/screenies/showlist-poster2.jpg">Dark 2</a></td>
  <td>Episode View: Day by Day<br />Theme: <a title="Theme Dark" href="https://raw.githubusercontent.com/wiki/SickGear/SickGear/images/screenies/episodeview-day-by-day.jpg">Dark</a>, <a title="Theme Light" href="https://raw.githubusercontent.com/wiki/SickGear/SickGear/images/screenies/episodeview-day-by-day-light.jpg">Light</a></td>
  <td>Episode View: List<br />Theme: <a title="Theme Dark" href="https://raw.githubusercontent.com/wiki/SickGear/SickGear/images/screenies/episodeview-list.jpg">Dark 1</a>, <a title="Theme Dark - Anime" href="https://raw.githubusercontent.com/wiki/SickGear/SickGear/images/screenies/episodeview-list2.jpg">Dark 2</a>, <a title="Theme Light" href="https://raw.githubusercontent.com/wiki/SickGear/SickGear/images/screenies/episodeview-list-light.jpg">Light</a></td>
  <td>Display Show<br />Theme: <a title="Theme Dark" href="https://raw.githubusercontent.com/wiki/SickGear/SickGear/images/screenies/displayshow.jpg">Dark</a>, <a title="Theme Light" href="https://raw.githubusercontent.com/wiki/SickGear/SickGear/images/screenies/displayshow-light.jpg">Light</a></td>
</tr>
</tbody>
</table>
