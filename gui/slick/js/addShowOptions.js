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
			default_wanted_begin: $('#wanted_begin').val(),
			default_wanted_latest: $('#wanted_latest').val(),
			default_flatten_folders: $('#flatten_folders').prop('checked'),
			default_scene: $('#scene').prop('checked'),
			default_subtitles: $('#subtitles').prop('checked'),
			default_anime: $('#anime').prop('checked'),
			default_tag: $('#tag').val()
		});

		new PNotify({
			title: 'Saving Defaults',
			text: 'Saving your "add show" defaults.',
			shadow: false
		});

		$(this).attr('disabled', true);
	});

	$('#statusSelect, #qualityPreset, #anyQualities, #bestQualities, #wanted_begin, #wanted_latest,'
		+ ' #flatten_folders, #scene, #subtitles, #anime, #tag').change(function() {
		$('#saveDefaultsButton').attr('disabled', false);
	});

});