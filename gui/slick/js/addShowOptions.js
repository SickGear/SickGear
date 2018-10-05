$(function(){

	$('#saveDefaultsButton').click(function() {
		var anyQualArray = [], bestQualArray = [];

		$('#wanted-qualities option:selected').each(function(i, d) {
			anyQualArray.push($(d).val());
		});
		$('#upgrade-qualities option:selected').each(function(i, d) {
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

	$('#statusSelect, #quality-preset, #wanted-qualities, #upgrade-qualities, #wanted_begin, #wanted_latest,'
		+ ' #flatten_folders, #scene, #subtitles, #anime, #tag').change(function() {
		$('#saveDefaultsButton').attr('disabled', false);
	});

	var updateOptions = function(that$, oldlink, newlink){
		that$.html(that$.html().replace(oldlink, newlink));
		if (!(/undefined/i.test(typeof $.SickGear.myform))){
			$.SickGear.myform.loadsection(2);
		}
	};
	$('#moreless-options-addshow').on('click', function(e){
		e.stopPropagation();
		e.preventDefault();
		var that$ = $(this), el$ = $('#options-addshow');
		if ('none' === el$.css('display')){
			el$.fadeIn('fast', 'linear', function(){
				updateOptions(that$, 'More', 'Less');
			});
		} else {
			el$.fadeOut('fast', 'linear', function(){
				updateOptions(that$, 'Less', 'More');
			});
		}
		return !1;
	});

});
