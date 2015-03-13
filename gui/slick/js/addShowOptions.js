$(document).ready(function(){

	$('#saveDefaultsButton').click(function() {
		var anyQualArray = [], bestQualArray = [];

		$('#anyQualities option:selected').each(function(i, d) {
			anyQualArray.push($(d).val());
		});
		$('#bestQualities option:selected').each(function(i, d) {
			bestQualArray.push($(d).val());
		});

		$.get(sbRoot + '/config/general/saveAddShowDefaults', {
			default_status: $('#statusSelect').val(),
			any_qualities: anyQualArray.join(','),
			best_qualities: bestQualArray.join(','),
			default_wanted_begin: $('#wanted-begin').val(),
			default_wanted_latest: $('#wanted-latest').val(),
			default_flatten_folders: $('#flatten_folders').prop('checked'),
			default_scene: $('#scene').prop('checked'),
			default_subtitles: $('#subtitles').prop('checked'),
			default_anime: $('#anime').prop('checked')
		});

		new PNotify({
			title: 'Saving Defaults',
			text: 'Saving your "add show" defaults.',
			shadow: false
		});

		$(this).attr('disabled', true);
	});

	$('#statusSelect, #qualityPreset, #anyQualities, #bestQualities, #wanted-begin, #wanted-latest,'
		+ ' #flatten_folders, #scene, #subtitles, #anime').change(function() {
		$('#saveDefaultsButton').attr('disabled', false);
	});

});