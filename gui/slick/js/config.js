$(document).ready(function () {
	var enabler = $('.enabler'),
		viewIf = $('.viewIf');

	enabler.each(function () {
		if (!$(this).prop('checked'))
			$('#content_' + $(this).attr('id')).hide();
	});

	enabler.click(function () {
		var content_id = $('#content_' + $(this).attr('id'));
		if ($(this).prop('checked'))
			content_id.fadeIn('fast', 'linear');
		else
			content_id.fadeOut('fast', 'linear');
	});

	viewIf.each(function () {
		$(($(this).prop('checked') ? '.hide_if_' : '.show_if_') + $(this).attr('id')).hide();
	});

	viewIf.click(function () {
		var if_id = '_if_' + $(this).attr('id');
		if ($(this).prop('checked')) {
			$('.hide' + if_id).fadeOut('fast', 'linear');
			$('.show' + if_id).fadeIn('fast', 'linear');
		} else {
			$('.show' + if_id).fadeOut('fast', 'linear');
			$('.hide' + if_id).fadeIn('fast', 'linear');
		}
	});

	var ui_update_trim_zero = (function () {
		var secs = ('00' + new Date().getSeconds().toString()).slice(-2),
			elSecs = $('#trim_info_seconds'),
			elTrimZero = $('#trim_zero');
		elTrimZero.each(function () {
			var checked = $(this).prop('checked') && $('#fuzzy_dating').prop('checked');

			$('#time_presets').find('option').each(function () {
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

	$('#trim_zero, #fuzzy_dating').click(function () {
		ui_update_trim_zero();
	});

	ui_update_trim_zero();

	$('.datePresets').click(function () {
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
		beforeSubmit: function () {
			$('.config_submitter').each(function () {
				$(this).attr('disabled', 'disabled');
				$(this).after('<span><img src="' + sbRoot + '/images/loading16' + themeSpinner + '.gif"> Saving...</span>');
				$(this).hide();
			});
			$('.show_update_hour_value').text($('#show_update_hour').val())
		},
		success: function (response) {
			setTimeout(function () {config_success(response)}, 2000);
		}
	});

	$('#api_key').click(function () {$('#api_key').select()});
	$('#generate_new_apikey').click(function () {
		$.get(sbRoot + '/config/general/generateKey',
			function (data) {
				if (data.error != undefined) {
					alert(data.error);
					return;
				}
				$('#api_key').val(data);
			});
	});

	$('#branchCheckout').click(function () {
		window.location.href = sbRoot + '/home/branchCheckout?branch=' + $('#branchVersion').val();
	});

	$('#pullRequestCheckout').click(function () {
		window.location.href = sbRoot + '/home/pullRequestCheckout?branch=' + $('#pullRequestVersion').val();
	});

	fetch_branches();
	fetch_pullrequests();
});

function config_success(response) {
	if (response == 'reload') {
		window.location.reload(true);
	}
	$('.config_submitter').each(function () {
		$(this).removeAttr('disabled');
		$(this).next().remove();
		$(this).show();
	});
	$('#email_show').trigger('notify');
}

function fetch_pullrequests() {
	$.getJSON(sbRoot + '/config/general/fetch_pullrequests', function (data) {
		$('#pullRequestVersion').find('option').remove();
		if (data['result'] == 'success') {
			var pulls = [];
			$.each(data['pulls'], function (i, pull) {
				if (pull[0] != '') {
					pulls.push(pull);
				}
			});
			if (pulls.length > 0) {
				$.each(pulls, function (i, text) {
					add_option_to_pulls(text);
				});
				$('#pullRequestCheckout').removeAttr('disabled');
			} else {
				add_option_to_pulls(['No pull requests available', '']);
			}
		} else {
			add_option_to_pulls(['Failed to connect to github', '']);
		}
	});
}

function fetch_branches() {
	$.getJSON(sbRoot + '/config/general/fetch_branches', function (data) {
		$('#branchVersion').find('option').remove();
		if (data['result'] == 'success') {
			var branches = [];
			$.each(data['branches'], function (i, branch) {
				if (branch != '') {
					branches.push(branch);
				}
			});
			if (branches.length > 0) {
				$.each(branches, function (i, text) {
					add_option_to_branches(text);
				});
				$('#branchCheckout').removeAttr('disabled');
			} else {
				add_option_to_branches('No branches available');
			}
		} else {
			add_option_to_branches('Failed to connect to github');
		}
	});
}

function add_option_to_pulls(text) {
	option = $('<option>');
	option.attr('value', text[1]);
	option.html(text[0]);
	option.appendTo('#pullRequestVersion');
}

function add_option_to_branches(text) {
	option = $('<option>');
	option.attr('value', text);
	option.html(text);
	option.appendTo('#branchVersion');
}