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

import emby
import kodi
import xbmc
import plex
import nmj
import nmjv2
import synoindex
import synologynotifier
import pytivo
import trakt

import growl
import prowl
from . import libnotify
import pushover
import boxcar2
import nma
import pushalot
import pushbullet

import tweet
from lib import libtrakt
import emailnotify

# home theater / nas
emby_notifier = emby.EmbyNotifier()
kodi_notifier = kodi.KodiNotifier()
xbmc_notifier = xbmc.XBMCNotifier()
plex_notifier = plex.PLEXNotifier()
nmj_notifier = nmj.NMJNotifier()
nmjv2_notifier = nmjv2.NMJv2Notifier()
synoindex_notifier = synoindex.synoIndexNotifier()
synology_notifier = synologynotifier.synologyNotifier()
pytivo_notifier = pytivo.pyTivoNotifier()
# devices
growl_notifier = growl.GrowlNotifier()
prowl_notifier = prowl.ProwlNotifier()
libnotify_notifier = libnotify.LibnotifyNotifier()
pushover_notifier = pushover.PushoverNotifier()
boxcar2_notifier = boxcar2.Boxcar2Notifier()
nma_notifier = nma.NMA_Notifier()
pushalot_notifier = pushalot.PushalotNotifier()
pushbullet_notifier = pushbullet.PushbulletNotifier()
# social
twitter_notifier = tweet.TwitterNotifier()
trakt_notifier = trakt.TraktNotifier()
email_notifier = emailnotify.EmailNotifier()

notifiers = [
    libnotify_notifier,  # Libnotify notifier goes first because it doesn't involve blocking on network activity.
    kodi_notifier,
    xbmc_notifier,
    plex_notifier,
    nmj_notifier,
    nmjv2_notifier,
    synoindex_notifier,
    synology_notifier,
    pytivo_notifier,
    growl_notifier,
    prowl_notifier,
    pushover_notifier,
    boxcar2_notifier,
    nma_notifier,
    pushalot_notifier,
    pushbullet_notifier,
    twitter_notifier,
    trakt_notifier,
    email_notifier,
]


def notify_download(ep_name):
    for n in notifiers:
        n.notify_download(ep_name)


def notify_subtitle_download(ep_name, lang):
    for n in notifiers:
        n.notify_subtitle_download(ep_name, lang)


def notify_snatch(ep_name):
    for n in notifiers:
        n.notify_snatch(ep_name)


def notify_git_update(new_version=''):
    for n in notifiers:
        n.notify_git_update(new_version)
