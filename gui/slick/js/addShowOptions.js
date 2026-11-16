$(function(){

	$('#saveDefaultsButton').click(function() {
		var anyQualArray = [], bestQualArray = [];

		$('#wanted-qualities option:selected').each(function(i, d) {
			anyQualArray.push($(d).val());
		});
		$('#upgrade-qualities option:selected').each(function(i, d) {
			bestQualArray.push($(d).val());
		});

		$.get(sbRoot + '/config/general/save-add-show-defaults', {
			default_status: $('#statusSelect').val(),
			any_qualities: anyQualArray.join(','),
			// a preset has no upgrade qualities, its upgrade list is only a start point for Custom
			best_qualities: parseInt($('#quality-preset').val(), 10) ? '' : bestQualArray.join(','),
			default_wanted_begin: $('#wanted_begin').val(),
			default_wanted_latest: $('#wanted_latest').val(),
			default_tag: $('#tag').val(),
			default_pause: $('#pause').prop('checked'),
			default_scene: $('#scene').prop('checked'),
			default_subs: $('#subs').prop('checked'),
			default_flatten_folders: $('#flatten_folders').prop('checked'),
			default_anime: $('#anime').prop('checked'),
			default_prune: $('#prune').val()
		});

		new PNotify({
			title: 'Saving Defaults',
			text: 'Saving your "add show" defaults.',
			shadow: false
		});

		$(this).attr('disabled', true);
	});

	$('#statusSelect, #quality-preset, #wanted-qualities, #upgrade-qualities, #wanted_begin, #wanted_latest, #tag,'
		+ ' #pause, #scene, #subs, #flatten_folders, #anime, #prune').change(function() {
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
				el$.css('opacity', 1);
			});
		} else {
			el$.fadeOut('fast', 'linear', function(){
				updateOptions(that$, 'Less', 'More');
				el$.css('opacity', 0);
			});
		}
		return !1;
	});

});
