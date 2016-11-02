function initActions() {
	$('#SubMenu a[href*="/home/restart/"]').addClass('btn restart').html('<i class="sgicon-restart"></i>Restart');
	$('#SubMenu a[href*="/home/shutdown/"]').addClass('btn shutdown').html('<i class="sgicon-shutdown"></i>Shutdown');
	$('#SubMenu a[href*="/home/logout/"]').addClass('btn').html('<i class="sgicon-logout"></i>Logout');
	$('#SubMenu a:contains("Edit")').addClass('btn').html('<i class="sgicon-edit"></i>Edit');
	$('#SubMenu a:contains("Remove")').addClass('btn remove').html('<i class="sgicon-delete"></i>Remove');
	$('#SubMenu a:contains("Clear History")').addClass('btn clearhistory').html('<i class="sgicon-delete"></i>Clear History');
	$('#SubMenu a:contains("Trim History")').addClass('btn trimhistory').html('<i class="sgicon-trim"></i>Trim History');
	$('#SubMenu a[href$="/errorlogs/downloadlog/"]').addClass('btn').html('<i class="sgicon-download"></i>Download Log');
	$('#SubMenu a[href$="/errorlogs/clearerrors/"]').addClass('btn').html('<i class="sgicon-delete"></i>Clear Errors');
	$('#SubMenu a:contains("Re-scan")').addClass('btn').html('<i class="sgicon-refresh"></i>Re-scan');
	$('#SubMenu a:contains("Backlog Overview")').addClass('btn').html('<i class="sgicon-backlog"></i>Backlog Overview');
	$('#SubMenu a[href$="/home/updatePLEX/"]').addClass('btn').html('<i class="sgicon-plex"></i>Update PLEX');
	$('#SubMenu a:contains("Force")').addClass('btn').html('<i class="sgicon-fullupdate"></i>Force Full Update');
	$('#SubMenu a:contains("Rename")').addClass('btn').html('<i class="sgicon-rename"></i>Media Renamer');
	$('#SubMenu a[href$="/config/subtitles/"]').addClass('btn').html('<i class="sgicon-subtitles"></i>Search Subtitles');
	$('#SubMenu a[href*="/home/subtitleShow"]').addClass('btn').html('<i class="sgicon-subtitles"></i>Download Subtitles');
	$('#SubMenu a:contains("Anime")').addClass('btn').html('<i class="sgicon-anime"></i>Anime');
	$('#SubMenu a:contains("Settings")').addClass('btn').html('<i class="sgicon-search"></i>Search Settings');
	$('#SubMenu a:contains("Provider")').addClass('btn').html('<i class="sgicon-search"></i>Search Providers');
	$('#SubMenu a:contains("General")').addClass('btn').html('<i class="sgicon-config"></i>General');
	$('#SubMenu a:contains("Episode Status")').addClass('btn').html('<i class="sgicon-episodestatus"></i>Episode Status Management');
	$('#SubMenu a:contains("Missed Subtitle")').addClass('btn').html('<i class="sgicon-subtitles"></i>Missed Subtitles');
	$('#SubMenu a[href$="/home/addShows/"]').addClass('btn').html('<i class="sgicon-addshow"></i>Add Show');
	$('#SubMenu a:contains("Processing")').addClass('btn').html('<i class="sgicon-postprocess"></i>Post-Processing');
	$('#SubMenu a:contains("Manage Searches")').addClass('btn').html('<i class="sgicon-search"></i>Manage Searches');
	$('#SubMenu a:contains("Manage Torrents")').addClass('btn').html('<i class="sgicon-bittorrent"></i>Manage Torrents');
	$('#SubMenu a:contains("Show Queue Overview")').addClass('btn').html('<i class="sgicon-showqueue"></i>Show Queue Overview');
	$('#SubMenu a[href$="/manage/failedDownloads/"]').addClass('btn').html('<i class="sgicon-failed"></i>Failed Downloads');
	$('#SubMenu a:contains("Notification")').addClass('btn').html('<i class="sgicon-notification"></i>Notifications');
	$('#SubMenu a[href$="/home/updateEMBY/"]').addClass('btn').html('<i class="sgicon-emby"></i>Update Emby');
	$('#SubMenu a[href$="/home/updateKODI/"]').addClass('btn').html('<i class="sgicon-kodi"></i>Update Kodi');
	$('#SubMenu a[href$="/home/updateXBMC/"]').addClass('btn').html('<i class="sgicon-xbmc"></i>Update XBMC');
	$('#SubMenu a:contains("Update show in Emby")').addClass('btn').html('<i class="sgicon-emby"></i>Update show in Emby');
	$('#SubMenu a:contains("Update show in Kodi")').addClass('btn').html('<i class="sgicon-kodi"></i>Update show in Kodi');
	$('#SubMenu a:contains("Update show in XBMC")').addClass('btn').html('<i class="sgicon-xbmc"></i>Update show in XBMC');
}

$(document).ready(function(){
	initActions();
	$('#NAV' + topmenu).addClass('active');
	$('.dropdown-toggle').dropdownHover();
});
