$(document).ready(function(){
	var loading = '<img src="' + sbRoot + '/images/loading16' + themeSpinner + '.gif" height="16" width="16" />';

	$('#testGrowl').click(function () {
		var growl_host = $.trim($('#growl_host').val());
		var growl_password = $.trim($('#growl_password').val());
		if (!growl_host) {
			$('#testGrowl-result').html('Please fill out the necessary fields above.');
			$('#growl_host').addClass('warning');
			return;
		}
		$('#growl_host').removeClass('warning');
		$(this).prop('disabled', true);
		$('#testGrowl-result').html(loading);
		$.get(sbRoot + '/home/testGrowl', {'host': growl_host, 'password': growl_password})
			.done(function (data) {
				$('#testGrowl-result').html(data);
				$('#testGrowl').prop('disabled', false);
			});
	});

	$('#testProwl').click(function () {
		var prowl_api = $.trim($('#prowl_api').val());
		var prowl_priority = $('#prowl_priority').val();
		if (!prowl_api) {
			$('#testProwl-result').html('Please fill out the necessary fields above.');
			$('#prowl_api').addClass('warning');
			return;
		}
		$('#prowl_api').removeClass('warning');
		$(this).prop('disabled', true);
		$('#testProwl-result').html(loading);
		$.get(sbRoot + '/home/testProwl', {'prowl_api': prowl_api, 'prowl_priority': prowl_priority})
			.done(function (data) {
				$('#testProwl-result').html(data);
				$('#testProwl').prop('disabled', false);
			});
	});

	$('#discover-emby').click(function () {
		$(this).prop('disabled', !0);
		$('#emby_host,#emby_apikey').removeClass('warning');
		$('#testEMBY-result').html(loading);
		$.get(sbRoot + '/home/discover_emby')
			.done(function (data) {
				var result = 'Unable to discover a server, is one running?';
				if ('' != data) {
					$('#emby_host').val(data);
					result = 'Server found.';
				}
				$('#testEMBY-result').html(result);
				$('#discover-emby').prop('disabled', !1);
			});
	});

	$('#testEMBY').click(function () {
		var host$ = $('#emby_host'), host = $.trim(host$.val());
		var apikey$ = $('#emby_apikey'), apikey = $.trim(apikey$.val());
		if (!host || !apikey) {
			$('#testEMBY-result').html('Please fill out the necessary fields above.');
			if (!host) {
				host$.addClass('warning');
			} else {
				host$.removeClass('warning');
			}
			if (!apikey) {
				apikey$.addClass('warning');
			} else {
				apikey$.removeClass('warning');
			}
			return;
		}
		$('#emby_host,#emby_apikey').removeClass('warning');
		$(this).prop('disabled', !0);
		$('#testEMBY-result').html(loading);
		$.get(sbRoot + '/home/testEMBY', {'host': host, 'apikey': apikey})
			.done(function (data) {
				$('#testEMBY-result').html(data);
				$('#testEMBY').prop('disabled', !1);
			});
	});

	$('#testKODI').click(function () {
		var kodi_host = $.trim($('#kodi_host').val());
		var kodi_username = $.trim($('#kodi_username').val());
		var kodi_password = $.trim($('#kodi_password').val());
		if (!kodi_host) {
			$('#testKODI-result').html('Please fill out the necessary fields above.');
			$('#kodi_host').addClass('warning');
			return;
		}
		$('#kodi_host').removeClass('warning');
		$(this).prop('disabled', true);
		$('#testKODI-result').html(loading);
		$.get(sbRoot + '/home/testKODI', {'host': kodi_host, 'username': kodi_username, 'password': kodi_password})
			.done(function (data) {
				$('#testKODI-result').html(data);
				$('#testKODI').prop('disabled', false);
			});
	});

	$('#testXBMC').click(function () {
		var xbmc_host = $.trim($('#xbmc_host').val());
		var xbmc_username = $.trim($('#xbmc_username').val());
		var xbmc_password = $.trim($('#xbmc_password').val());
		if (!xbmc_host) {
			$('#testXBMC-result').html('Please fill out the necessary fields above.');
			$('#xbmc_host').addClass('warning');
			return;
		}
		$('#xbmc_host').removeClass('warning');
		$(this).prop('disabled', true);
		$('#testXBMC-result').html(loading);
		$.get(sbRoot + '/home/testXBMC', {'host': xbmc_host, 'username': xbmc_username, 'password': xbmc_password})
			.done(function (data) {
				$('#testXBMC-result').html(data);
				$('#testXBMC').prop('disabled', false);
			});
	});

	// show instructions for plex when enabled
	$('#use_plex').click(function() {
		if ( $(this).is(':checked') ) {
			$('.plexinfo').removeClass('hide');
		} else {
			$('.plexinfo').addClass('hide');
		}
	});
	if ($('input[id="use_plex"]').is(':checked')) {$('.plexinfo').removeClass('hide')}

	$('#testPMC').click(function () {
		var plex_host = $.trim($('#plex_host').val());
		var plex_username = $.trim($('#plex_username').val());
		var plex_password = $.trim($('#plex_password').val());
		if (!plex_host) {
			$('#testPMC-result').html('Please fill out the necessary fields above.');
			$('#plex_host').addClass('warning');
			return;
		}
		$('#plex_host').removeClass('warning');
		$(this).prop('disabled', true);
		$('#testPMC-result').html(loading);
		$.get(sbRoot + '/home/testPMC', {'host': plex_host, 'username': plex_username, 'password': plex_password})
			.done(function (data) {
				$('#testPMC-result').html(data);
				$('#testPMC').prop('disabled', false);
			});
	});

	$('#testPMS').click(function () {
		var plex_server_host = $.trim($('#plex_server_host').val());
		var plex_username = $.trim($('#plex_username').val());
		var plex_password = $.trim($('#plex_password').val());
		if (!plex_server_host) {
			$('#testPMS-result').html('Please fill out the necessary fields above.');
			$('#plex_server_host').addClass('warning');
			return;
		}
		$('#plex_server_host').removeClass('warning');
		$(this).prop('disabled', true);
		$('#testPMS-result').html(loading);
		$.get(sbRoot + '/home/testPMS', {'host': plex_server_host, 'username': plex_username, 'password': plex_password})
			.done(function (data) {
				$('#testPMS-result').html(data);
				$('#testPMS').prop('disabled', false);
			});
	});

	$('#testBoxcar2').click(function () {
		var boxcar2_accesstoken = $.trim($('#boxcar2_accesstoken').val());
		var boxcar2_sound = $('#boxcar2_sound').val() || 'default';
		if (!boxcar2_accesstoken) {
			$('#testBoxcar2-result').html('Please fill out the necessary fields above.');
			$('#boxcar2_accesstoken').addClass('warning');
			return;
		}
		$('#boxcar2_accesstoken').removeClass('warning');
		$(this).prop('disabled', true);
		$('#testBoxcar2-result').html(loading);
		$.get(sbRoot + '/home/testBoxcar2', {'accesstoken': boxcar2_accesstoken, 'sound': boxcar2_sound})
			.done(function (data) {
				$('#testBoxcar2-result').html(data);
				$('#testBoxcar2').prop('disabled', false);
			});
	});

	$('#testPushover').click(function () {
		var pushover_userkey = $.trim($('#pushover_userkey').val());
		var pushover_apikey = $.trim($('#pushover_apikey').val());
		var pushover_priority = $("#pushover_priority").val();
		var pushover_device = $("#pushover_device").val();
		var pushover_sound = $("#pushover_sound").val();
		if (!pushover_userkey || !pushover_apikey) {
			$('#testPushover-result').html('Please fill out the necessary fields above.');
			if (!pushover_userkey) {
				$('#pushover_userkey').addClass('warning');
			} else {
				$('#pushover_userkey').removeClass('warning');
			}
			if (!pushover_apikey) {
				$('#pushover_apikey').addClass('warning');
			} else {
				$('#pushover_apikey').removeClass('warning');
			}
			return;
		}
		$('#pushover_userkey,#pushover_apikey').removeClass('warning');
		$(this).prop('disabled', true);
		$('#testPushover-result').html(loading);
		$.get(sbRoot + '/home/testPushover', {'userKey': pushover_userkey, 'apiKey': pushover_apikey, 'priority': pushover_priority, 'device': pushover_device, 'sound': pushover_sound})
			.done(function (data) {
				$('#testPushover-result').html(data);
				$('#testPushover').prop('disabled', false);
			});
	});

	function get_pushover_devices (msg) {
		var pushover_userkey = $.trim($('#pushover_userkey').val());
		var pushover_apikey = $.trim($('#pushover_apikey').val());
		if (!pushover_userkey || !pushover_apikey) {
			$('#testPushover-result').html('Please fill out the necessary fields above.');
			if (!pushover_userkey) {
				$('#pushover_userkey').addClass('warning');
			} else {
				$('#pushover_userkey').removeClass('warning');
			}
			if (!pushover_apikey) {
				$('#pushover_apikey').addClass('warning');
			} else {
				$('#pushover_apikey').removeClass('warning');
			}
			return;
		}
		$(this).prop('disabled', true);
		if (msg) {
			$('#testPushover-result').html(loading);
		}
		var current_pushover_device = $('#pushover_device').val();
		$.get(sbRoot + "/home/getPushoverDevices", {'userKey': pushover_userkey, 'apiKey': pushover_apikey})
			.done(function (data) {
				var devices = jQuery.parseJSON(data || '{}').devices;
				$('#pushover_device_list').html('');
				// add default option to send to all devices
				$('#pushover_device_list').append('<option value="all" selected="selected">-- All Devices --</option>');
				if (devices) {
					for (var i = 0; i < devices.length; i++) {
						// if a device in the list matches our current iden, select it
						if (current_pushover_device == devices[i]) {
							$('#pushover_device_list').append('<option value="' + devices[i] + '" selected="selected">' + devices[i] + '</option>');
						} else {
							$('#pushover_device_list').append('<option value="' + devices[i] + '">' + devices[i] + '</option>');
						}
					}
				}
				$('#getPushoverDevices').prop('disabled', false);
				if (msg) {
					$('#testPushover-result').html(msg);
				}
			});

		$('#pushover_device_list').change(function () {
			$('#pushover_device').val($('#pushover_device_list').val());
			$('#testPushover-result').html('Don\'t forget to save your new Pushover settings.');
		});
	}

	$('#getPushoverDevices').click(function () {
		get_pushover_devices('Device list updated. Select specific device to use.');
	});

	if ($('#use_pushover').prop('checked')) {
		get_pushover_devices();
	}

	$('#testLibnotify').click(function() {
		$('#testLibnotify-result').html(loading);
		$.get(sbRoot + '/home/testLibnotify',
			function (data) { $('#testLibnotify-result').html(data); });
	});

	$('#settingsNMJ').click(function() {
		if (!$('#nmj_host').val()) {
			alert('Please fill in the Popcorn IP address');
			$('#nmj_host').focus();
			return;
		}
		$('#testNMJ-result').html(loading);
		var nmj_host = $('#nmj_host').val();

		$.get(sbRoot + '/home/settingsNMJ', {'host': nmj_host},
			function (data) {
				if (data === null) {
					$('#nmj_database').removeAttr('readonly');
					$('#nmj_mount').removeAttr('readonly');
				}
				var JSONData = $.parseJSON(data);
				$('#testNMJ-result').html(JSONData.message);
				$('#nmj_database').val(JSONData.database);
				$('#nmj_mount').val(JSONData.mount);

				if (JSONData.database) {
					$('#nmj_database').attr('readonly', true);
				} else {
					$('#nmj_database').removeAttr('readonly');
				}
				if (JSONData.mount) {
					$('#nmj_mount').attr('readonly', true);
				} else {
					$('#nmj_mount').removeAttr('readonly');
				}
			});
	});

	$('#testNMJ').click(function () {
		var nmj_host = $.trim($('#nmj_host').val());
		var nmj_database = $('#nmj_database').val();
		var nmj_mount = $('#nmj_mount').val();
		if (!nmj_host) {
			$('#testNMJ-result').html('Please fill out the necessary fields above.');
			$('#nmj_host').addClass('warning');
			return;
		}
		$('#nmj_host').removeClass('warning');
		$(this).prop('disabled', true);
		$('#testNMJ-result').html(loading);
		$.get(sbRoot + '/home/testNMJ', {'host': nmj_host, 'database': nmj_database, 'mount': nmj_mount})
			.done(function (data) {
				$('#testNMJ-result').html(data);
				$('#testNMJ').prop('disabled', false);
			});
	});

	$('#settingsNMJv2').click(function() {
		if (!$('#nmjv2_host').val()) {
			alert('Please fill in the Popcorn IP address');
			$('#nmjv2_host').focus();
			return;
		}
		$('#testNMJv2-result').html(loading);
		var nmjv2_host = $('#nmjv2_host').val();
		var nmjv2_dbloc;
		var radios = document.getElementsByName('nmjv2_dbloc');
		for (var i = 0; i < radios.length; i++) {
			if (radios[i].checked) {
				nmjv2_dbloc=radios[i].value;
				break;
			}
		}

		var nmjv2_dbinstance=$('#NMJv2db_instance').val();
		$.get(sbRoot + '/home/settingsNMJv2', {'host': nmjv2_host,'dbloc': nmjv2_dbloc,'instance': nmjv2_dbinstance},
		function (data){
			if (data == null) {
				$('#nmjv2_database').removeAttr('readonly');
			}
			var JSONData = $.parseJSON(data);
			$('#testNMJv2-result').html(JSONData.message);
			$('#nmjv2_database').val(JSONData.database);

			if (JSONData.database)
				$('#nmjv2_database').attr('readonly', true);
			else
				$('#nmjv2_database').removeAttr('readonly');
		});
	});

	$('#testNMJv2').click(function () {
		var nmjv2_host = $.trim($('#nmjv2_host').val());
		if (!nmjv2_host) {
			$('#testNMJv2-result').html('Please fill out the necessary fields above.');
			$('#nmjv2_host').addClass('warning');
			return;
		}
		$('#nmjv2_host').removeClass('warning');
		$(this).prop('disabled', true);
		$('#testNMJv2-result').html(loading);
		$.get(sbRoot + '/home/testNMJv2', {'host': nmjv2_host})
			.done(function (data) {
				$('#testNMJv2-result').html(data);
				$('#testNMJv2').prop('disabled', false);
			});
	});

	$('#testNMA').click(function () {
		var nma_api = $.trim($('#nma_api').val());
		var nma_priority = $('#nma_priority').val();
		if (!nma_api) {
			$('#testNMA-result').html('Please fill out the necessary fields above.');
			$('#nma_api').addClass('warning');
			return;
		}
		$('#nma_api').removeClass('warning');
		$(this).prop('disabled', true);
		$('#testNMA-result').html(loading);
		$.get(sbRoot + '/home/testNMA', {'nma_api': nma_api, 'nma_priority': nma_priority})
			.done(function (data) {
				$('#testNMA-result').html(data);
				$('#testNMA').prop('disabled', false);
			});
	});

	$('#testPushalot').click(function () {
		var pushalot_authorizationtoken = $.trim($('#pushalot_authorizationtoken').val());
		if (!pushalot_authorizationtoken) {
			$('#testPushalot-result').html('Please fill out the necessary fields above.');
			$('#pushalot_authorizationtoken').addClass('warning');
			return;
		}
		$('#pushalot_authorizationtoken').removeClass('warning');
		$(this).prop('disabled', true);
		$('#testPushalot-result').html(loading);
		$.get(sbRoot + '/home/testPushalot', {'authorizationToken': pushalot_authorizationtoken})
			.done(function (data) {
				$('#testPushalot-result').html(data);
				$('#testPushalot').prop('disabled', false);
			});
	});

	$('#testPushbullet').click(function () {
		var pushbullet_access_token = $.trim($('#pushbullet_access_token').val());
		var pushbullet_device_iden = $('#pushbullet_device_iden').val();
		if (!pushbullet_access_token) {
			$('#testPushbullet-result').html('Please fill out the necessary fields above.');
			$('#pushbullet_access_token').addClass('warning');
			return;
		}
		$('#pushbullet_access_token').removeClass('warning');
		$(this).prop('disabled', true);
		$('#testPushbullet-result').html(loading);
		$.get(sbRoot + '/home/testPushbullet', {'accessToken': pushbullet_access_token, 'device_iden': pushbullet_device_iden})
			.done(function (data) {
				$('#testPushbullet-result').html(data);
				$('#testPushbullet').prop('disabled', false);
			});
	});

	function get_pushbullet_devices (msg) {
		var pushbullet_access_token = $.trim($('#pushbullet_access_token').val());
		if (!pushbullet_access_token) {
			$('#testPushbullet-result').html('Please fill out the necessary fields above.');
			$('#pushbullet_access_token').addClass('warning');
			return;
		}
		$(this).prop("disabled", true);
		if (msg) {
			$('#testPushbullet-result').html(loading);
		}
		var current_pushbullet_device = $('#pushbullet_device_iden').val();
		$.get(sbRoot + '/home/getPushbulletDevices', {'accessToken': pushbullet_access_token})
			.done(function (data) {
				var devices = jQuery.parseJSON(data || '{}').devices;
				var error = jQuery.parseJSON(data || '{}').error;
				$('#pushbullet_device_list').html('');
				if (devices) {
				// add default option to send to all devices
				$('#pushbullet_device_list').append('<option value="" selected="selected">-- All Devices --</option>');
					for (var i = 0; i < devices.length; i++) {
						// only list active device targets
						if (devices[i].active == true) {
							// if a device in the list matches our current iden, select it
							if (current_pushbullet_device == devices[i].iden) {
								$('#pushbullet_device_list').append('<option value="' + devices[i].iden + '" selected="selected">' + devices[i].manufacturer + ' ' + devices[i].nickname + '</option>');
							} else {
								$('#pushbullet_device_list').append('<option value="' + devices[i].iden + '">' + devices[i].manufacturer + ' ' + devices[i].nickname + '</option>');
							}
						}
					}
				}
				$('#getPushbulletDevices').prop('disabled', false);
				if (msg) {
					if (error.message) {
						$('#testPushbullet-result').html(error.message);
					} else {
						$('#testPushbullet-result').html(msg);
					}
				}
			});

		$('#pushbullet_device_list').change(function () {
			$('#pushbullet_device_iden').val($('#pushbullet_device_list').val());
			$('#testPushbullet-result').html('Don\'t forget to save your new Pushbullet settings.');
		});
	}

	$('#getPushbulletDevices').click(function () {
		get_pushbullet_devices('Device list updated. Select specific device to use.');
	});

	if ($('#use_pushbullet').prop('checked')) {
		get_pushbullet_devices();
	}

	$('#twitterStep1').click(function() {
		$('#testTwitter-result').html(loading);
		$.get(sbRoot + '/home/twitterStep1', function (data) {window.open(data); })
			.done(function () { $('#testTwitter-result').html('<b>Step1:</b> Confirm Authorization'); });
	});

	$('#twitterStep2').click(function () {
		var twitter_key = $.trim($('#twitter_key').val());
		if (!twitter_key) {
			$('#testTwitter-result').html('Please fill out the necessary fields above.');
			$('#twitter_key').addClass('warning');
			return;
		}
		$('#twitter_key').removeClass('warning');
		$('#testTwitter-result').html(loading);
		$.get(sbRoot + '/home/twitterStep2', {'key': twitter_key},
			function (data) { $('#testTwitter-result').html(data); });
	});

	$('#testTwitter').click(function() {
		$.get(sbRoot + '/home/testTwitter',
			function (data) { $('#testTwitter-result').html(data); });
	});

	var elTraktAuth = $('#trakt-authenticate'), elTraktAuthResult = $('#trakt-authentication-result');

	function trakt_send_auth(){
		var elAccountSelect = $('#trakt_accounts'), strCurAccountId = elAccountSelect.find('option:selected').val(),
			elTraktPin = $('#trakt_pin'), strPin = $.trim(elTraktPin.val());

		elTraktAuthResult.html(loading);

		$.get(sbRoot + '/home/trakt_authenticate', {'pin': strPin, 'account': strCurAccountId})
			.done(function(data) {
				elTraktAuth.prop('disabled', !1);
				elTraktPin.val('');

				var JSONData = $.parseJSON(data);

				elTraktAuthResult.html('Success' == JSONData.result
					? JSONData.result + ' account: ' + JSONData.account_name
					: JSONData.result + ' ' + JSONData.error_message);

				if ('Success' == JSONData.result) {
					var elUpdateRows = $('#trakt-collection').find('tr');
					if ('new' == strCurAccountId) {
						elAccountSelect.append($('<option>', {value: JSONData.account_id, text: JSONData.account_id + ' - '  + JSONData.account_name + ' (ok)'}));

						if ('Connect New Pin' == elUpdateRows.eq(0).find('th').last().text()) {
							elUpdateRows.eq(0).find('th').last().html('Account');
							elUpdateRows.eq(1).find('th').last().html(JSONData.account_name);
							elUpdateRows.eq(1).find('th').last().addClass('tid-' + JSONData.account_id);
							elUpdateRows.has('td').each(function(nRow) {
								var elCells = $(this).find('td');
								if (!(nRow % 2)) {
									var IdLoc = 'update_trakt_' + JSONData.account_id + '_' + elCells.eq(0).find('span').attr('data-loc');
									elCells.last().html('<input type="checkbox" id="' + IdLoc + '" name="' + IdLoc + '">');
								} else {
									elCells.attr('colspan', 1);
								}
							});
						}
						else
						{
							elUpdateRows.eq(0).find('th').last().html('Trakt accounts');
							elUpdateRows.eq(0).find('th').last().attr('colspan', 1 + parseInt(elUpdateRows.eq(0).find('th').last().attr('colspan'), 10));
							elUpdateRows.eq(1).find('th').last().after('<th>' + JSONData.account_name + '</th>');
							elUpdateRows.eq(1).find('th').last().addClass('tid-' + JSONData.account_id);
							elUpdateRows.has('td').each(function(nRow) {
								var elCells = $(this).find('td');
								if (!(nRow % 2)) {
									var IdLoc = 'update_trakt_' + JSONData.account_id + '_' + elCells.eq(0).find('span').attr('data-loc');
									elCells.last().after('<td class="opt"><input type="checkbox" id="' + IdLoc + '" name="' + IdLoc + '"></td>');
								} else {
									elCells.attr('colspan', 1 + parseInt(elCells.attr('colspan'), 10));
								}
							});
						}
					}
					else
					{
						elAccountSelect.find('option[value=' + strCurAccountId + ']').html(JSONData.account_id + ' - '  + JSONData.account_name + ' (ok)');
						elUpdateRows.eq(1).find('th[class*="tid-' + JSONData.account_id + '"]').text(JSONData.account_name);
					}
				}
			});
	}

	elTraktAuth.click(function(e) {
		var elTraktPin = $('#trakt_pin');

		elTraktPin.removeClass('warning');
		if (!$.trim(elTraktPin.val())) {
			elTraktPin.addClass('warning');
			elTraktAuthResult.html('Please enter a required PIN above.');
		} else {
			var elAccountSelect = $('#trakt_accounts'), elSelected = elAccountSelect.find('option:selected');
			$(this).prop('disabled', !0);
			if ('new' != elSelected.val()) {
				$.confirm({
					'title'		: 'Replace Trakt Account',
					'message'	: 'Are you sure you want to replace <span class="footerhighlight">' + elSelected.text() + '</span> ?<br /><br />',
					'buttons'	: {
						'Yes'	: {
							'class'	: 'green',
							'action': function() {
									trakt_send_auth();
								}
						},
						'No'	: {
							'class'	: 'red',
							'action': function() {
								e.preventDefault();
								elTraktAuth.prop('disabled', !1);
							}
						}
					}
				});
			}
			else
			{
				trakt_send_auth();
			}
		}
	});

	$('#trakt_accounts').change(function() {
		$('#trakt-delete').prop('disabled', 'new' == $('#trakt_accounts').val());
	});

	$('#trakt-delete').click(function(e) {
		var elAccountSelect = $('#trakt_accounts'), elSelected = elAccountSelect.find('option:selected'), that = $(this);

		that.prop('disabled', !0);
		$.confirm({
			'title'		: 'Remove Trakt Account',
			'message'	: 'Are you sure you want to remove <span class="footerhighlight">' + elSelected.text() + '</span> ?<br /><br />',
			'buttons'	: {
				'Yes'	: {
					'class'	: 'green',
					'action': function() {
						$.get(sbRoot + '/home/trakt_delete', {'accountid': elSelected.val()})
							.done(function(data) {
								that.prop('disabled', !1);
								var JSONData = $.parseJSON(data);
								if ('Success' == JSONData.result) {
									var elCollection = $('#trakt-collection'), elUpdateRows = elCollection.find('tr'),
										header = elCollection.find('th[class*="tid-' + JSONData.account_id + '"]'),
										num_acc = parseInt(JSONData.num_accounts, 10);

									elUpdateRows.eq(0).find('th').last().html(!num_acc && '<i>Connect New Pin</i>' ||
										(1 < num_acc ? 'Trakt accounts' : 'Account'));
									elUpdateRows.find('th[colspan]').attr('colspan', 1 < num_acc ? num_acc : 1);

									!num_acc && header.html('..') || header.remove();

									var elInputs = elUpdateRows.find('input[id*=update_trakt_' + JSONData.account_id + ']');
									!num_acc && elInputs.parent().html('..') || elInputs.parent().remove();

									elUpdateRows.find('td[colspan]').each(function() {
										$(this).attr('colspan', (num_acc ? 1 + num_acc : 2))
									});

									elSelected.remove();
									$('#trakt_accounts').change();

									elTraktAuthResult.html('Deleted account: ' + JSONData.account_name);
								}
							});
					}
				},
				'No'	: {
					'class'	: 'red',
					'action': function() {
						e.preventDefault();
						$('#trakt_accounts').change();
					}
				}
			}
		});
	});

	function load_show_notify_lists() {
		$.get(sbRoot + '/home/loadShowNotifyLists', function (data) {
			var list, html, item, len= 0, el;
			list = $.parseJSON(data);
			html = [];
			for (item in list) {
				for (var k in list[item]) {
					if ($.isArray(list[item][k])) {
						len += list[item][k].length;
						html.push('\t<optgroup label="' + k + '">');
						for (var show in list[item][k]) {
							html.push('\t\t<option value="' + list[item][k][show].id + '"'
								+ ' data="' + list[item][k][show].list + '"'
								+ '>' + list[item][k][show].name + '</option>');
						}
						html.push('\t</optgroup>');
					}
				}
			}

			if (len) {
				el = $('#email_show');
				el.html('<option value="-1">-- Select show --</option>'
					+ html.join('\n'));

				$('#show_email_list').val('');

				el.change(function () {
					$('#show_email_list').val(
						$(this).find('option[value="' + $(this).val() + '"]').attr('data'))
				});
			}
		});
	}
	// Load the per show notify lists everytime this page is loaded
	load_show_notify_lists();

	// Update the internal data struct anytime settings are saved to the server
	$('#email_show').bind('notify', function () { load_show_notify_lists(); });

	$('#save_show_email').click(
		function(){
			var show = $('#email_show').val();
			if ('-1' == show) {
				$('#testEmail-result').html('No show selected for save.');
				return
			}
			$.post(sbRoot + '/home/save_show_email', {
				show: show,
				emails: $('#show_email_list').val()},
				function (data){
					// Reload the per show notify lists to reflect changes
					load_show_notify_lists();
					var result = $.parseJSON(data),
						show = $('#email_show').find('option[value="' + result.id + '"]').text();
					$('#testEmail-result').html(result.success
						? 'Success. Notify list updated for show "' + show + '". Click below to test.'
						: 'Error saving notify list for show %s' % show);
				});
		});

	$('#testEmail').click(function () {
		var status, host, port, tls, from, user, pwd, err, to;
		status = $('#testEmail-result');
		status.html(loading);
		host = $('#email_host').val();
		host = host.length > 0 ? host : null;
		port = $('#email_port').val();
		port = port.length > 0 ? port : null;
		tls = $('#email_tls').attr('checked') !== undefined ? 1 : 0;
		from = $('#email_from').val();
		from = from.length > 0 ? from : 'root@localhost';
		user = $('#email_user').val().trim();
		pwd = $('#email_password').val();
		err = [];
		if (null == host) {
			err.push('SMTP server hostname');
		}
		if (null == port) {
			err.push('SMTP server host port');
		} else if (null == port.match(/^\d+$/) || parseInt(port, 10) > 65535) {
			err.push('SMTP server host port must be between 0 and 65535');
		}
		if (0 < err.length) {
			status.html('Required: ' + err.join(', '));
		} else {
			to = prompt('Enter an email address to send the test to:', '');
			if (null == to || 0 == to.length || null == to.match(/.*@.*/)) {
				status.html('Required: A valid address for email test');
			} else {
				$.get(sbRoot + '/home/testEmail',
					{host:host, port:port, smtp_from:from, use_tls:tls, user:user, pwd:pwd, to:to},
					function(msg) {$('#testEmail-result').html(msg);});
			}
		}
	});

});
