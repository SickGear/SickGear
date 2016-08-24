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

	var idSelect = '#imdb-accounts', idDel = '#imdb-list-del', idInput = '#imdb-url', idOnOff = '#imdb-list-onoff',
		sel = 'selected', opt = 'option', selOpt = [opt, sel].join(':'),
		elDropDown = $(idSelect), elDel = $(idDel), elInput = $(idInput), elOnOff = $(idOnOff);

	function accId() {return elDropDown.find(selOpt).val();}
	function nameList() {return elDropDown.find(selOpt).text();}
	function isAdd() {return 'new' === accId();}
	function isOff() {return 0 == nameList().indexOf('(Off) ');}
	function warnMessage(msg) { elInput.addClass('warning').prop('title', msg); }
	function all(state) {$([idSelect, idDel, idInput, idOnOff].join()).prop('disabled', 'on' == state ? !1 : !0)}
	function setOnOff() {elOnOff.val(isAdd() || isOff() ? 'Enable' : 'Disable');}
	function setLink() {
		var idView = '#view-list', idLink = '#link-list';
		return $([idView, idLink].join()).removeClass() &&
			((isAdd() || isOff()) && $(idLink).addClass('hide') || $(idView).addClass('hide')) &&
			(!isOff() && $(idLink)
				.attr('href', sbRoot + '/home/addShows/watchlist_imdb?account=' + accId())
				.attr('title', 'View ' + nameList()));
	}

	function defaultControls() {
		elDel.prop('disabled', isAdd());
		elInput.removeClass('warning')
			.val(!isAdd() && accId() || '')
			.prop('title', isAdd() ? '' : 'Select Add. Use Delete or Disable')
			.prop('readonly', !isAdd());
		setOnOff();
		setLink();
	}

	function populateSelect(jsonData) {
		/** @namespace response.accounts */
		var response = $.parseJSON(jsonData);

		if ('Success' !== response.result) {
			warnMessage(response.result);
			return !1;
		}

		elDropDown.find(opt).slice(1).remove();
		var i, l, accounts = response.accounts, options = elDropDown.get(0).options;
		for (i = 0, l = accounts.length; i < l; i = i + 2) {
			options[options.length] = new Option(accounts[i + 1] +
				(0 == accounts[i + 1].replace('(Off) ', '').toLowerCase().indexOf('your') ? '' : '\'s') + ' list', accounts[i]);
			if (0 <= $.trim(elInput.val()).indexOf(accounts[i])) {
				elDropDown.find(opt).prop(sel, !1);
				elDropDown.find('option[value="' + accounts[i] + '"]').prop(sel, sel);
				elInput.val(accounts[i]);
				elInput.prop('title', 'Select Add. Use Delete or Disable');
				setOnOff();
			}
		}
		return !0;
	}

	elDropDown.change(function() {
		defaultControls();
	});

	elDel.on('click', function(e) {
		all('off');
		$.confirm({
			'title'		: 'Remove the "' + nameList().replace('\'s', '').replace(' list', '') + '" IMDb Watchlist',
			'message'	: 'Are you sure you want to remove <span class="footerhighlight">' + nameList() + '</span> ?<br /><br />',
			'buttons'	: {
				'Yes'	: {
					'class'	: 'green',
					'action': function() {
						all('off');
						$.get(sbRoot + '/home/addShows/watchlist_imdb', {
							'action': elDel.val().toLowerCase(),
							'select': accId()})
							.done(function(response) {
								all('on'); setControls(!populateSelect(response), !1); setOnOff(); })
							.fail(function() {
								all('on'); setControls(!0, 'Invalid ID'); setOnOff(); });
					}
				},
				'No'	: {
					'class'	: 'red',
					'action': function() { e.preventDefault(); all('on'); defaultControls();}
				}
			}
		});
	});

	elOnOff.on('click', function(e) {
		var strList = $.trim(elInput.val());

		elInput.removeClass('warning');
		if (!strList) {
			warnMessage('Missing IMDb list Id or URL');
		} else {
			all('off');
			var params = {'action': elOnOff.val().toLowerCase()};
			if ('enable' == params.action)
				params.input = strList;
			else
				params.select = accId();

			$.get(sbRoot + '/home/addShows/watchlist_imdb', params)
				.done(function(data) { setControls(!populateSelect(data), !1); })
				.fail(function() { setControls(!0, 'Failed to load list'); });
		}
	});

	function setControls(resetSelect, message) {
		all('on');
		if (resetSelect) {
			if (message)
				warnMessage(message);
			var addList = '[value="new"]';
			elDropDown.find(opt).not(addList).prop(sel, !1);
			elDropDown.find(opt + addList).prop(sel, sel);
		}
		elDel.prop('disabled', isAdd());
		elInput.prop('readonly', !isAdd());
		setLink()
	}

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

	$('#showlist_tagview').on('change', function() {
		var selected = '#showlist_tagview_', target = $(selected + 'custom_config');
		target.removeClass('hidden');
		if ('custom' !== $(this).val())
			target.addClass('hidden');
		$(selected + 'standard,' + selected + 'anime,' + selected + 'custom').removeClass('hidden').addClass('hidden');
		$(selected + $(this).val()).removeClass('hidden');
	});
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
				$('#branchVersion').find('option[value=' + data['current'] + ']').attr('selected','selected');
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
	var option = $('<option>');
	option.attr('value', text[1]);
	option.html(text[0]);
	option.appendTo('#pullRequestVersion');
}

function add_option_to_branches(text) {
	var option = $('<option>');
	option.attr('value', text);
	option.html(text);
	option.appendTo('#branchVersion');
}
