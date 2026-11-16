$(function(){

	// the options that "Save as defaults" saves, and their state when last saved
	var defaultsFields = '#statusSelect, #quality-preset, #wanted-qualities, #upgrade-qualities, #wanted_begin,'
		+ ' #wanted_latest, #tag, #pause, #scene, #subs, #flatten_folders, #anime';
	function defaultsState() {
		return $(defaultsFields).map(function() {
			return 'checkbox' === this.type ? this.checked : String($(this).val());
		}).get().join('|');
	}
	var savedDefaults = defaultsState();

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
			default_anime: $('#anime').prop('checked')
		});

		new PNotify({
			title: 'Saving Defaults',
			text: 'Saving your "add show" defaults.',
			shadow: false
		});

		savedDefaults = defaultsState();
		$(this).attr('disabled', true);
	});

	// ready to save only while an option differs from its saved state, so that a change back is nothing to save
	$(defaultsFields).change(function() {
		$('#saveDefaultsButton').attr('disabled', defaultsState() === savedDefaults);
	});

	var updateOptions = function(that$, oldlink, newlink){
		that$.val(that$.val().replace(oldlink, newlink));
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

	// "Keep up to" deletes episodes, so say so when a number is entered
	$('#prune').on('input change', function() {
		$('#prune-warn').toggle(0 < parseInt($(this).val(), 10));
	});

});
