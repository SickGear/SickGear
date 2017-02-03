function initActions() {
	var menu$ = $('#SubMenu');
	menu$.find('a[href*="/home/restart/"]').addClass('btn restart').html('<i class="sgicon-restart"></i>Restart');
	menu$.find('a[href*="/home/shutdown/"]').addClass('btn shutdown').html('<i class="sgicon-shutdown"></i>Shutdown');
	menu$.find('a[href*="/home/logout/"]').addClass('btn').html('<i class="sgicon-logout"></i>Logout');
	menu$.find('a:contains("Edit")').addClass('btn').html('<i class="sgicon-edit"></i>Edit');
	menu$.find('a:contains("Remove")').addClass('btn remove').html('<i class="sgicon-delete"></i>Remove');
	menu$.find('a:contains("Clear History")').addClass('btn clearhistory').html('<i class="sgicon-delete"></i>Clear History');
	menu$.find('a:contains("Trim History")').addClass('btn trimhistory').html('<i class="sgicon-trim"></i>Trim History');
	menu$.find('a[href$="/errorlogs/downloadlog/"]').addClass('btn').html('<i class="sgicon-download"></i>Download Log');
	menu$.find('a[href$="/errorlogs/clearerrors/"]').addClass('btn').html('<i class="sgicon-delete"></i>Clear Errors');
	menu$.find('a:contains("Re-scan")').addClass('btn').html('<i class="sgicon-refresh"></i>Re-scan');
	menu$.find('a:contains("Backlog Overview")').addClass('btn').html('<i class="sgicon-backlog"></i>Backlog Overview');
	menu$.find('a[href$="/home/updatePLEX/"]').addClass('btn').html('<i class="sgicon-plex"></i>Update PLEX');
	menu$.find('a:contains("Force")').addClass('btn').html('<i class="sgicon-fullupdate"></i>Force Full Update');
	menu$.find('a:contains("Rename")').addClass('btn').html('<i class="sgicon-rename"></i>Media Renamer');
	menu$.find('a[href$="/config/subtitles/"]').addClass('btn').html('<i class="sgicon-subtitles"></i>Subtitles');
	menu$.find('a[href*="/home/subtitleShow"]').addClass('btn').html('<i class="sgicon-subtitles"></i>Download Subtitles');
	menu$.find('a:contains("Anime")').addClass('btn').html('<i class="sgicon-anime"></i>Anime');
	menu$.find('a:contains("Search")').addClass('btn').html('<i class="sgicon-search"></i>Search');
	menu$.find('a:contains("Provider")').addClass('btn').html('<i class="sgicon-book"></i>Media Providers');
	menu$.find('a:contains("General")').addClass('btn').html('<i class="sgicon-config"></i>General');
	menu$.find('a:contains("Episode Status")').addClass('btn').html('<i class="sgicon-episodestatus"></i>Episode Status');
	menu$.find('a:contains("Missed Subtitle")').addClass('btn').html('<i class="sgicon-subtitles"></i>Missed Subtitles');
	menu$.find('a[href$="/config/postProcessing/"]').addClass('btn').html('<i class="sgicon-postprocess"></i>Post Processing');
	menu$.find('a[href$="/postprocess/"]').addClass('btn').html('<i class="sgicon-postprocess"></i>Process Media');
	menu$.find('a:contains("Media Search")').addClass('btn').html('<i class="sgicon-search"></i>Media Search');
	menu$.find('a:contains("Manage Torrents")').addClass('btn').html('<i class="sgicon-bittorrent"></i>Manage Torrents');
	menu$.find('a:contains("Show Processes")').addClass('btn').html('<i class="sgicon-showqueue"></i>Show Processes');
	menu$.find('a[href$="/manage/failedDownloads/"]').addClass('btn').html('<i class="sgicon-failed"></i>Failed Downloads');
	menu$.find('a:contains("Notification")').addClass('btn').html('<i class="sgicon-notification"></i>Notifications');
	menu$.find('a[href$="/home/updateEMBY/"]').addClass('btn').html('<i class="sgicon-emby"></i>Update Emby');
	menu$.find('a[href$="/home/updateKODI/"]').addClass('btn').html('<i class="sgicon-kodi"></i>Update Kodi');
	menu$.find('a[href$="/home/updateXBMC/"]').addClass('btn').html('<i class="sgicon-xbmc"></i>Update XBMC');
	menu$.find('a:contains("Update show in Emby")').addClass('btn').html('<i class="sgicon-emby"></i>Update show in Emby');
	menu$.find('a:contains("Update show in Kodi")').addClass('btn').html('<i class="sgicon-kodi"></i>Update show in Kodi');
	menu$.find('a:contains("Update show in XBMC")').addClass('btn').html('<i class="sgicon-xbmc"></i>Update show in XBMC');
}

$(document).ready(function(){
	initActions();
	$('#NAV' + topmenu).addClass('active');
	$('.dropdown-toggle').dropdownHover();
	(/undefined/i.test(document.createElement('input').placeholder)) && $('body').addClass('no-placeholders');
});
