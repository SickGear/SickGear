$(document).ready(function(){
	var enabler = $('.enabler'),
		viewIf = $('.viewIf');

	enabler.each(function(){
		if (!$(this).prop('checked'))
			$('#content_' + $(this).attr('id')).hide();
	});

	enabler.click(function(){
		var content_id = $('#content_' + $(this).attr('id'));
		if ($(this).prop('checked'))
			content_id.fadeIn('fast', 'linear');
		else
			content_id.fadeOut('fast', 'linear');
	});

	viewIf.each(function(){
		$(($(this).prop('checked') ? '.hide_if_' : '.show_if_') + $(this).attr('id')).hide();
	});

	viewIf.click(function(){
		var if_id = '_if_' + $(this).attr('id');
		if ($(this).prop('checked')) {
			$('.hide' + if_id).fadeOut('fast', 'linear');
			$('.show' + if_id).fadeIn('fast', 'linear');
		} else {
			$('.show' + if_id).fadeOut('fast', 'linear');
			$('.hide' + if_id).fadeIn('fast', 'linear');
		}
	});

	var ui_update_trim_zero = (function() {
		var secs = ('00' + new Date().getSeconds().toString()).slice(-2),
			elSecs = $('#trim_info_seconds'),
			elTrimZero = $('#trim_zero');
		elTrimZero.each(function() {
			var checked = $(this).prop('checked') && $('#fuzzy_dating').prop('checked');

			$('#time_presets').find('option').each(function() {
				var text = ($(this).text());
				$(this).text(checked
					? text.replace(/(\b\d+:\d\d):\d+/mg, '$1')
					: text.replace(/(\b\d+:\d\d)(?:.\d+)?/mg, '$1:' + secs));
			});
		});

		if ($('#fuzzy_dating').prop('checked'))
			if (elTrimZero.prop('checked'))
				elSecs.fadeOut('fast', 'linear');
			else
				elSecs.fadeIn('fast', 'linear');
		else
			elSecs.fadeIn('fast', 'linear');
	});

	$('#trim_zero, #fuzzy_dating').click(function() {
		ui_update_trim_zero();
	});

	ui_update_trim_zero();

	$('.datePresets').click(function(){
		var elDatePresets = $('#date_presets'),
			defaultPreset = elDatePresets.val();
		if ($(this).prop('checked') && '%x' == defaultPreset) {
			defaultPreset = '%a, %b %d, %Y';
			$('#date_use_system_default').html('1')
		} else if (!$(this).prop('checked') && '1' == $('#date_use_system_default').html())
			defaultPreset = '%x';

		elDatePresets.attr('name', 'date_preset_old');
		elDatePresets.attr('id', 'date_presets_old');

		var elDatePresets_na = $('#date_presets_na');
		elDatePresets_na.attr('name', 'date_preset');
		elDatePresets_na.attr('id', 'date_presets');

		var elDatePresets_old = $('#date_presets_old');
		elDatePresets_old.attr('name', 'date_preset_na');
		elDatePresets_old.attr('id', 'date_presets_na');

		if (defaultPreset)
			elDatePresets.val(defaultPreset)
	});

	// bind 'myForm' and provide a simple callback function
	$('#configForm').ajaxForm({
		beforeSubmit: function(){
			$('.config_submitter').each(function(){
				$(this).attr('disabled', 'disabled');
				$(this).after('<span><img src="' + sbRoot + '/images/loading16' + themeSpinner + '.gif"> Saving...</span>');
				$(this).hide();
			});
			$('.show_update_hour_value').text($('#show_update_hour').val())
		},
		success: function(response){
			setTimeout(function(){config_success(response)}, 2000);
		}
	});

	$('#api_key').click(function(){ $('#api_key').select() });
	$('#generate_new_apikey').click(function(){
		$.get(sbRoot + '/config/general/generateKey',
			function(data){
				if (data.error != undefined) {
					alert(data.error);
					return;
				}
				$('#api_key').val(data);
		});
	});

	$('#branchCheckout').click(function(){
		window.location.href = sbRoot + '/home/branchCheckout?branch=' + $('#branchVersion').val();
	});

	$('#pullRequestCheckout').click(function(){
		window.location.href = sbRoot + '/home/pullRequestCheckout?branch=' + $('#pullRequestVersion').val();
	});
	
});

function config_success(response){
	if (response == 'reload'){
		window.location.reload(true);
	}
	$('.config_submitter').each(function(){
		$(this).removeAttr('disabled');
		$(this).next().remove();
		$(this).show();
	});
	$('#email_show').trigger('notify');
}