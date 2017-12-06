/** @namespace JSONData.account_id */
/** @namespace JSONData.account_name */
/** @namespace JSONData.error_message */
/** @namespace JSONData.num_accounts */
$(document).ready(function(){
	var loading = '<img src="' + sbRoot + '/images/loading16' + themeSpinner + '.gif" height="16" width="16" />';

	$('.typelist').on('click', '.list .item a', function(){
		$(this).closest('.component-group').after(
			$('[name=' + $(this).attr('href').replace('#','') + ']').closest('.component-group')
		);
		return !1;
	});

	$('#test-growl').click(function () {
		var growlHost = $.trim($('#growl-host').val());
		var growlPassword = $.trim($('#growl-password').val());
		if (!growlHost) {
			$('#test-growl-result').html('Please fill out the necessary fields above.');
			$('#growl-host').addClass('warning');
			return;
		}
		$('#growl-host').removeClass('warning');
		$(this).prop('disabled', !0);
		$('#test-growl-result').html(loading);
		$.get(sbRoot + '/home/test_growl',
			{host: growlHost, password: growlPassword})
			.done(function (data) {
				$('#test-growl-result').html(data);
				$('#test-growl').prop('disabled', !1);
			});
	});

	$('#test-prowl').click(function () {
		var prowlApi = $.trim($('#prowl-api').val());
		var prowlPriority = $('#prowl-priority').val();
		if (!prowlApi) {
			$('#test-prowl-result').html('Please fill out the necessary fields above.');
			$('#prowl-api').addClass('warning');
			return;
		}
		$('#prowl-api').removeClass('warning');
		$(this).prop('disabled', !0);
		$('#test-prowl-result').html(loading);
		$.get(sbRoot + '/home/test_prowl',
			{prowl_api: prowlApi, prowl_priority: prowlPriority})
			.done(function (data) {
				$('#test-prowl-result').html(data);
				$('#test-prowl').prop('disabled', !1);
			});
	});

	$('#discover-emby').click(function () {
		$(this).prop('disabled', !0);
		$('#emby-host,#emby-apikey').removeClass('warning');
		$('#test-emby-result').html(loading);
		$.get(sbRoot + '/home/discover_emby')
			.done(function (data) {
				var result = 'Unable to discover a server, is one running?';
				if ('' !== data) {
					$('#emby-host').val(data);
					result = 'Server found.';
				}
				$('#test-emby-result').html(result);
				$('#discover-emby').prop('disabled', !1);
			});
	});

	$('#test-emby').click(function () {
		var host$ = $('#emby-host'), host = $.trim(host$.val());
		var apikey$ = $('#emby-apikey'), apikey = $.trim(apikey$.val());
		if (!host || !apikey) {
			$('#test-emby-result').html('Please fill out the necessary fields above.');
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
		$('#emby-host,#emby-apikey').removeClass('warning');
		$(this).prop('disabled', !0);
		$('#test-emby-result').html(loading);
		$.get(sbRoot + '/home/test_emby',
			{host: host, apikey: apikey})
			.done(function (data) {
				$('#test-emby-result').html(data);
				$('#test-emby').prop('disabled', !1);
			});
	});

	$('#test-kodi').click(function () {
		var kodiHost = $.trim($('#kodi-host').val());
		var kodiUsername = $.trim($('#kodi-username').val());
		var kodiPassword = $.trim($('#kodi-password').val());
		if (!kodiHost) {
			$('#test-kodi-result').html('Please fill out the necessary fields above.');
			$('#kodi-host').addClass('warning');
			return;
		}
		$('#kodi-host').removeClass('warning');
		$(this).prop('disabled', !0);
		$('#test-kodi-result').html(loading);
		$.get(sbRoot + '/home/test_kodi',
			{host: kodiHost, username: kodiUsername, password: kodiPassword})
			.done(function (data) {
				$('#test-kodi-result').html(data);
				$('#test-kodi').prop('disabled', !1);
			});
	});

	$('#test-xbmc').click(function () {
		var xbmcHost = $.trim($('#xbmc-host').val());
		var xbmcUsername = $.trim($('#xbmc-username').val());
		var xbmcPassword = $.trim($('#xbmc-password').val());
		if (!xbmcHost) {
			$('#test-xbmc-result').html('Please fill out the necessary fields above.');
			$('#xbmc-host').addClass('warning');
			return;
		}
		$('#xbmc-host').removeClass('warning');
		$(this).prop('disabled', !0);
		$('#test-xbmc-result').html(loading);
		$.get(sbRoot + '/home/test_xbmc',
			{host: xbmcHost, username: xbmcUsername, password: xbmcPassword})
			.done(function (data) {
				$('#test-xbmc-result').html(data);
				$('#test-xbmc').prop('disabled', !1);
			});
	});

	// show instructions for plex when enabled
	$('#use-plex').click(function() {
		if ( $(this).is(':checked') ) {
			$('.plexinfo').removeClass('hide');
		} else {
			$('.plexinfo').addClass('hide');
		}
	});
	if ($('input[id="use-plex"]').is(':checked')) {$('.plexinfo').removeClass('hide')}

	$('#test-pmc').click(function () {
		var plexHost = $.trim($('#plex-host').val());
		var plexUsername = $.trim($('#plex-username').val());
		var plexPassword = $.trim($('#plex-password').val());
		if (!plexHost) {
			$('#test-pmc-result').html('Please fill out the necessary fields above.');
			$('#plex-host').addClass('warning');
			return;
		}
		$('#plex-host').removeClass('warning');
		$(this).prop('disabled', !0);
		$('#test-pmc-result').html(loading);
		$.get(sbRoot + '/home/test_plex',
			{host: plexHost, username: plexUsername, password: plexPassword})
			.done(function (data) {
				$('#test-pmc-result').html(data);
				$('#test-pmc').prop('disabled', !1);
			});
	});

	$('#test-pms').click(function () {
		var plexServerHost = $.trim($('#plex-server-host').val());
		var plexUsername = $.trim($('#plex-username').val());
		var plexPassword = $.trim($('#plex-password').val());
		if (!plexServerHost) {
			$('#test-pms-result').html('Please fill out the necessary fields above.');
			$('#plex-server-host').addClass('warning');
			return;
		}
		$('#plex-server-host').removeClass('warning');
		$(this).prop('disabled', !0);
		$('#test-pms-result').html(loading);
		$.get(sbRoot + '/home/test_plex',
			{host: plexServerHost, username: plexUsername, password: plexPassword, server: !0})
			.done(function (data) {
				$('#test-pms-result').html(data);
				$('#test-pms').prop('disabled', !1);
			});
	});

	$('#test-boxcar2').click(function () {
		var boxcarAccesstoken = $.trim($('#boxcar2-access-token').val());
		var boxcarSound = $('#boxcar2-sound').val() || 'default';
		if (!boxcarAccesstoken) {
			$('#test-boxcar2-result').html('Please fill out the necessary fields above.');
			$('#boxcar2-access-token').addClass('warning');
			return;
		}
		$('#boxcar2-access-token').removeClass('warning');
		$(this).prop('disabled', !0);
		$('#test-boxcar2-result').html(loading);
		$.get(sbRoot + '/home/test_boxcar2',
			{access_token: boxcarAccesstoken, sound: boxcarSound})
			.done(function (data) {
				$('#test-boxcar2-result').html(data);
				$('#test-boxcar2').prop('disabled', !1);
			});
	});

	$('#test-pushover').click(function () {
		var pushover$ = $('#pushover-userkey'), pushoverUserkey = $.trim(pushover$.val()),
			pushoverApikey$ = $('#pushover-apikey'), pushoverApikey = $.trim(pushoverApikey$.val()),
			pushoverPriority = $('#pushover-priority').val(),
			pushoverDevice = $('#pushover-device').val(),
			pushoverSound = $('#pushover-sound').val(),
			testResult$ = $('#test-pushover-result');

		if (!pushoverUserkey || !pushoverApikey) {
			testResult$.html('Please fill out the necessary fields above.');
			if (!pushoverUserkey) {
				pushover$.addClass('warning');
			} else {
				pushover$.removeClass('warning');
			}
			if (!pushoverApikey) {
				pushoverApikey$.addClass('warning');
			} else {
				pushoverApikey$.removeClass('warning');
			}
			return;
		}
		$('#pushover-userkey,#pushover-apikey').removeClass('warning');
		$(this).prop('disabled', !0);
		testResult$.html(loading);
		$.get(sbRoot + '/home/test_pushover',
			{user_key: pushoverUserkey, api_key: pushoverApikey, priority: pushoverPriority,
				device: pushoverDevice, sound: pushoverSound})
			.done(function (data) {
				testResult$.html(data);
				$('#test-pushover').prop('disabled', !1);
			});
	});

	function getPushoverDevices (msg) {
		var pushoverUserkey = $.trim($('#pushover-userkey').val());
		var pushoverApikey = $.trim($('#pushover-apikey').val());
		if (!pushoverUserkey || !pushoverApikey) {
			$('#test-pushover-result').html('Please fill out the necessary fields above.');
			if (!pushoverUserkey) {
				$('#pushover-userkey').addClass('warning');
			} else {
				$('#pushover-userkey').removeClass('warning');
			}
			if (!pushoverApikey) {
				$('#pushover-apikey').addClass('warning');
			} else {
				$('#pushover-apikey').removeClass('warning');
			}
			return;
		}
		$(this).prop('disabled', !0);
		if (msg) {
			$('#test-pushover-result').html(loading);
		}
		var currentPushoverDevice = $('#pushover-device').val();
		$.get(sbRoot + '/home/get_pushover_devices',
			{user_key: pushoverUserkey, api_key: pushoverApikey})
			.done(function (data) {
				var devices = jQuery.parseJSON(data || '{}').devices;
				$('#pushover-device-list').html('');
				// add default option to send to all devices
				$('#pushover-device-list').append('<option value="all" selected="selected">-- All Devices --</option>');
				if (devices) {
					for (var i = 0; i < devices.length; i++) {
						// if a device in the list matches our current iden, select it
						if (currentPushoverDevice === devices[i]) {
							$('#pushover-device-list').append('<option value="' + devices[i] + '" selected="selected">' + devices[i] + '</option>');
						} else {
							$('#pushover-device-list').append('<option value="' + devices[i] + '">' + devices[i] + '</option>');
						}
					}
				}
				$('#get-pushoverDevices').prop('disabled', !1);
				if (msg) {
					$('#test-pushover-result').html(msg);
				}
			});

		$('#pushover-device-list').change(function () {
			$('#pushover-device').val($('#pushover-device-list').val());
			$('#test-pushover-result').html('Don\'t forget to save your new Pushover settings.');
		});
	}

	$('#get-pushoverDevices').click(function () {
		getPushoverDevices('Device list updated. Select specific device to use.');
	});

	if ($('#use-pushover').prop('checked')) {
		getPushoverDevices();
	}

	$('#test-libnotify').click(function() {
		$('#test-libnotify-result').html(loading);
		$.get(sbRoot + '/home/test_libnotify',
			function (data) { $('#test-libnotify-result').html(data); });
	});

	$('#settings-nmj').click(function() {
		if (!$('#nmj-host').val()) {
			alert('Please fill in the Popcorn IP address');
			$('#nmj-host').focus();
			return;
		}
		$('#test-nmj-result').html(loading);
		var nmjHost = $('#nmj-host').val();

		$.get(sbRoot + '/home/settings_nmj',
			{host: nmjHost},
			function (data) {
				if (null === data) {
					$('#nmj-database').removeAttr('readonly');
					$('#nmj-mount').removeAttr('readonly');
				}
				var JSONData = $.parseJSON(data);
				$('#test-nmj-result').html(JSONData.message);
				$('#nmj-database').val(JSONData.database);
				$('#nmj-mount').val(JSONData.mount);

				if (JSONData.database) {
					$('#nmj-database').attr('readonly', !0);
				} else {
					$('#nmj-database').removeAttr('readonly');
				}
				if (JSONData.mount) {
					$('#nmj-mount').attr('readonly', !0);
				} else {
					$('#nmj-mount').removeAttr('readonly');
				}
			});
	});

	$('#test-nmj').click(function () {
		var nmjHost = $.trim($('#nmj-host').val());
		var nmjDatabase = $('#nmj-database').val();
		var nmjMount = $('#nmj-mount').val();
		if (!nmjHost) {
			$('#test-nmj-result').html('Please fill out the necessary fields above.');
			$('#nmj-host').addClass('warning');
			return;
		}
		$('#nmj-host').removeClass('warning');
		$(this).prop('disabled', !0);
		$('#test-nmj-result').html(loading);
		$.get(sbRoot + '/home/test_nmj',
			{host: nmjHost, database: nmjDatabase, mount: nmjMount})
			.done(function (data) {
				$('#test-nmj-result').html(data);
				$('#test-nmj').prop('disabled', !1);
			});
	});

	$('#settings-nmjv2').click(function() {
		if (!$('#nmjv2-host').val()) {
			alert('Please fill in the Popcorn IP address');
			$('#nmjv2-host').focus();
			return;
		}
		$('#test-nmjv2-result').html(loading);
		var nmjv2Host = $('#nmjv2-host').val();
		var nmjv2Dbloc;
		var radios = document.getElementsByName('nmjv2_dbloc');
		for (var i = 0; i < radios.length; i++) {
			if (radios[i].checked) {
				nmjv2Dbloc=radios[i].value;
				break;
			}
		}

		var nmjv2Dbinstance=$('#NMJv2db-instance').val();
		$.get(sbRoot + '/home/settings_nmj2',
			{host: nmjv2Host,dbloc: nmjv2Dbloc,instance: nmjv2Dbinstance},
			function (data){
				if (null === data) {
					$('#nmjv2-database').removeAttr('readonly');
				}
				var JSONData = $.parseJSON(data);
				$('#test-nmjv2-result').html(JSONData.message);
				$('#nmjv2-database').val(JSONData.database);

				if (JSONData.database)
					$('#nmjv2-database').attr('readonly', !0);
				else
					$('#nmjv2-database').removeAttr('readonly');
			});
	});

	$('#test-nmjv2').click(function () {
		var nmjv2Host = $.trim($('#nmjv2-host').val());
		if (!nmjv2Host) {
			$('#test-nmjv2-result').html('Please fill out the necessary fields above.');
			$('#nmjv2-host').addClass('warning');
			return;
		}
		$('#nmjv2-host').removeClass('warning');
		$(this).prop('disabled', !0);
		$('#test-nmjv2-result').html(loading);
		$.get(sbRoot + '/home/test_nmj2',
			{host: nmjv2Host})
			.done(function (data) {
				$('#test-nmjv2-result').html(data);
				$('#test-nmjv2').prop('disabled', !1);
			});
	});

	$('#test-nma').click(function () {
		var nmaApi = $.trim($('#nma-api').val());
		var nmaPriority = $('#nma-priority').val();
		if (!nmaApi) {
			$('#test-nma-result').html('Please fill out the necessary fields above.');
			$('#nma-api').addClass('warning');
			return;
		}
		$('#nma-api').removeClass('warning');
		$(this).prop('disabled', !0);
		$('#test-nma-result').html(loading);
		$.get(sbRoot + '/home/test_nma',
			{nma_api: nmaApi, nma_priority: nmaPriority})
			.done(function (data) {
				$('#test-nma-result').html(data);
				$('#test-nma').prop('disabled', !1);
			});
	});

	$('#test-pushalot').click(function () {
		var pushalotAuthorizationtoken = $.trim($('#pushalot-authorizationtoken').val());
		if (!pushalotAuthorizationtoken) {
			$('#test-pushalot-result').html('Please fill out the necessary fields above.');
			$('#pushalot-authorizationtoken').addClass('warning');
			return;
		}
		$('#pushalot-authorizationtoken').removeClass('warning');
		$(this).prop('disabled', !0);
		$('#test-pushalot-result').html(loading);
		$.get(sbRoot + '/home/test_pushalot',
			{authorization_token: pushalotAuthorizationtoken})
			.done(function (data) {
				$('#test-pushalot-result').html(data);
				$('#test-pushalot').prop('disabled', !1);
			});
	});

	$('#test-pushbullet').click(function () {
		var pushbulletAccessToken = $.trim($('#pushbullet-access-token').val());
		var pushbulletDeviceIden = $('#pushbullet-device-iden').val();
		if (!pushbulletAccessToken) {
			$('#test-pushbullet-result').html('Please fill out the necessary fields above.');
			$('#pushbullet-access-token').addClass('warning');
			return;
		}
		$('#pushbullet-access-token').removeClass('warning');
		$(this).prop('disabled', !0);
		$('#test-pushbullet-result').html(loading);
		$.get(sbRoot + '/home/test_pushbullet',
			{access_token: pushbulletAccessToken, device_iden: pushbulletDeviceIden})
			.done(function (data) {
				$('#test-pushbullet-result').html(data);
				$('#test-pushbullet').prop('disabled', !1);
			});
	});

	$('#test-slack').click(function () {
		var channel = '#slack-channel', slackChannel = $(channel).val(),
			slackAsAuthed = $('#slack-as-authed').prop('checked'),
			slackBotName = $('#slack-bot-name').val(), slackIconUrl = $('#slack-icon-url').val(),
			accessToken = '#slack-access-token', slackAccessToken = $(accessToken).val();

		$(channel + ', ' + accessToken).removeClass('warning');
		if (!slackChannel || !slackAccessToken) {
			$('#test-slack-result').html('Please fill out the necessary fields above.');
			if (!slackChannel)
				$(channel).addClass('warning');
			if (!slackAccessToken)
				$(accessToken).addClass('warning');
		} else {
			$(this).prop('disabled', !0);
			$('#test-slack-result').html(loading);
			$.get(sbRoot + '/home/test_slack',
				{channel: slackChannel, as_authed: slackAsAuthed, bot_name: slackBotName,
					icon_url: slackIconUrl, access_token: slackAccessToken})
				.done(function (data) {
					$('#test-slack-result').html(data);
					$('#test-slack').prop('disabled', !1);
				});
		}
	});

	$('#test-discordapp').click(function () {
		var discordappAsAuthed = $('#discordapp-as-authed').prop('checked'),
			discordappUsername = $('#discordapp-username').val(), discordappIconUrl = $('#discordapp-icon-url').val(),
			discordappAsTts = $('#discordapp-as-tts').prop('checked'),
			accessToken = '#discordapp-access-token', discordappAccessToken = $(accessToken).val();

		$(accessToken).removeClass('warning');
		if (!discordappAccessToken) {
			$('#test-discordapp-result').html('Please fill out the necessary fields above.');
			if (!discordappAccessToken)
				$(accessToken).addClass('warning');
		} else {
			$(this).prop('disabled', !0);
			$('#test-discordapp-result').html(loading);
			$.get(sbRoot + '/home/test_discordapp',
				{as_authed: discordappAsAuthed, username: discordappUsername, icon_url: discordappIconUrl,
					as_tts: discordappAsTts, access_token: discordappAccessToken})
				.done(function (data) {
					$('#test-discordapp-result').html(data);
					$('#test-discordapp').prop('disabled', !1);
				});
		}
	});

	$('#test-gitter').click(function () {
		var gitterRoom = $('#gitter-room').val(),
			accessToken = '#gitter-access-token', gitterAccessToken = $(accessToken).val();

		$(accessToken).removeClass('warning');
		if (!gitterAccessToken) {
			$('#test-gitter-result').html('Please fill out the necessary fields above.');
			if (!gitterAccessToken)
				$(accessToken).addClass('warning');
		} else {
			$(this).prop('disabled', !0);
			$('#test-gitter-result').html(loading);
			$.get(sbRoot + '/home/test_gitter',
				{room_name: gitterRoom, access_token: gitterAccessToken})
				.done(function (data) {
					$('#test-gitter-result').html(data);
					$('#test-gitter').prop('disabled', !1);
				});
		}
	});

	function getPushbulletDevices (msg) {
		var pushbulletAccessToken = $.trim($('#pushbullet-access-token').val());
		if (!pushbulletAccessToken) {
			$('#test-pushbullet-result').html('Please fill out the necessary fields above.');
			$('#pushbullet-access-token').addClass('warning');
			return;
		}
		$(this).prop('disabled', !0);
		if (msg) {
			$('#test-pushbullet-result').html(loading);
		}
		var currentPushbulletDevice = $('#pushbullet-device-iden').val();
		$.get(sbRoot + '/home/get_pushbullet_devices',
			{access_token: pushbulletAccessToken})
			.done(function (data) {
				var devices = jQuery.parseJSON(data || '{}').devices;
				var error = jQuery.parseJSON(data || '{}').error;
				$('#pushbullet-device-list').html('');
				if (devices) {
				// add default option to send to all devices
				$('#pushbullet-device-list').append('<option value="" selected="selected">-- All Devices --</option>');
					for (var i = 0; i < devices.length; i++) {
						// only list active device targets
						if (!0 === devices[i].active) {
							// if a device in the list matches our current iden, select it
							if (currentPushbulletDevice === devices[i].iden) {
								$('#pushbullet-device-list').append('<option value="' + devices[i].iden + '" selected="selected">' + devices[i].manufacturer + ' ' + devices[i].nickname + '</option>');
							} else {
								$('#pushbullet-device-list').append('<option value="' + devices[i].iden + '">' + devices[i].manufacturer + ' ' + devices[i].nickname + '</option>');
							}
						}
					}
				}
				$('#get-pushbulletDevices').prop('disabled', !1);
				if (msg) {
					if (error.message) {
						$('#test-pushbullet-result').html(error.message);
					} else {
						$('#test-pushbullet-result').html(msg);
					}
				}
			});

		$('#pushbullet-device-list').change(function () {
			$('#pushbullet-device-iden').val($('#pushbullet-device-list').val());
			$('#test-pushbullet-result').html('Don\'t forget to save your new Pushbullet settings.');
		});
	}

	$('#get-pushbulletDevices').click(function () {
		getPushbulletDevices('Device list updated. Select specific device to use.');
	});

	if ($('#use-pushbullet').prop('checked')) {
		getPushbulletDevices();
	}

	$('#twitter-step1').click(function() {
		$('#test-twitter-result').html(loading);
		$.get(sbRoot + '/home/twitter_step1',
			function (data) {window.open(data); })
			.done(function () { $('#test-twitter-result').html('<b>Step1:</b> Confirm Authorization'); });
	});

	$('#twitter-step2').click(function () {
		var twitterKey = $.trim($('#twitter-key').val());
		if (!twitterKey) {
			$('#test-twitter-result').html('Please fill out the necessary fields above.');
			$('#twitter-key').addClass('warning');
			return;
		}
		$('#twitter-key').removeClass('warning');
		$('#test-twitter-result').html(loading);
		$.get(sbRoot + '/home/twitter_step2',
			{key: twitterKey},
			function (data) { $('#test-twitter-result').html(data); });
	});

	$('#test-twitter').click(function() {
		$.get(sbRoot + '/home/test_twitter',
			function (data) { $('#test-twitter-result').html(data); });
	});

	var elTraktAuth = $('#trakt-authenticate'), elTraktAuthResult = $('#trakt-authentication-result');

	function traktSendAuth(){
		var elAccountSelect = $('#trakt-accounts'), strCurAccountId = elAccountSelect.find('option:selected').val(),
			elTraktPin = $('#trakt-pin'), strPin = $.trim(elTraktPin.val());

		elTraktAuthResult.html(loading);

		$.get(sbRoot + '/home/trakt_authenticate',
			{pin: strPin, account: strCurAccountId})
			.done(function(data) {
				elTraktAuth.prop('disabled', !1);
				elTraktPin.val('');

				var JSONData = $.parseJSON(data);

				elTraktAuthResult.html('Success' === JSONData.result
					? JSONData.result + ' account: ' + JSONData.account_name
					: JSONData.result + ' ' + JSONData.error_message);

				if ('Success' === JSONData.result) {
					var elUpdateRows = $('#trakt-collection').find('tr');
					if ('new' === strCurAccountId) {
						elAccountSelect.append($('<option>', {value: JSONData.account_id, text: JSONData.account_id + ' - '  + JSONData.account_name + ' (ok)'}));

						if ('Connect New Pin' === elUpdateRows.eq(0).find('th').last().text()) {
							elUpdateRows.eq(0).find('th').last().html('Account');
							elUpdateRows.eq(1).find('th').last().html(JSONData.account_name);
							elUpdateRows.eq(1).find('th').last().addClass('tid-' + JSONData.account_id);
							elUpdateRows.has('td').each(function(nRow) {
								var elCells = $(this).find('td');
								if (!(nRow % 2)) {
									var IdLoc = 'update-trakt-' + JSONData.account_id + '-' + elCells.eq(0).find('span').attr('data-loc');
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
									var IdLoc = 'update-trakt-' + JSONData.account_id + '-' + elCells.eq(0).find('span').attr('data-loc');
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
		var elTraktPin = $('#trakt-pin');

		elTraktPin.removeClass('warning');
		if (!$.trim(elTraktPin.val())) {
			elTraktPin.addClass('warning');
			elTraktAuthResult.html('Please enter a required PIN above.');
		} else {
			var elAccountSelect = $('#trakt-accounts'), elSelected = elAccountSelect.find('option:selected');
			$(this).prop('disabled', !0);
			if ('new' !== elSelected.val()) {
				$.confirm({
					'title'		: 'Replace Trakt Account',
					'message'	: 'Are you sure you want to replace <span class="footerhighlight">' + elSelected.text() + '</span> ?<br /><br />',
					'buttons'	: {
						'Yes'	: {
							'class'	: 'green',
							'action': function() {
									traktSendAuth();
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
				traktSendAuth();
			}
		}
	});

	$('#trakt-accounts').change(function() {
		$('#trakt-delete').prop('disabled', 'new' === $('#trakt-accounts').val());
	});

	$('#trakt-delete').click(function(e) {
		var elAccountSelect = $('#trakt-accounts'), elSelected = elAccountSelect.find('option:selected'), that = $(this);

		that.prop('disabled', !0);
		$.confirm({
			'title'		: 'Remove Trakt Account',
			'message'	: 'Are you sure you want to remove <span class="footerhighlight">' + elSelected.text() + '</span> ?<br /><br />',
			'buttons'	: {
				'Yes'	: {
					'class'	: 'green',
					'action': function() {
						$.get(sbRoot + '/home/trakt_delete',
							{accountid: elSelected.val()})
							.done(function(data) {
								that.prop('disabled', !1);
								var JSONData = $.parseJSON(data);
								if ('Success' === JSONData.result) {
									var elCollection = $('#trakt-collection'), elUpdateRows = elCollection.find('tr'),
										header = elCollection.find('th[class*="tid-' + JSONData.account_id + '"]'),
										numAcc = parseInt(JSONData.num_accounts, 10);

									elUpdateRows.eq(0).find('th').last().html(!numAcc && '<i>Connect New Pin</i>' ||
										(1 < numAcc ? 'Trakt accounts' : 'Account'));
									elUpdateRows.find('th[colspan]').attr('colspan', 1 < numAcc ? numAcc : 1);

									!numAcc && header.html('..') || header.remove();

									var elInputs = elUpdateRows.find('input[id*=update-trakt-' + JSONData.account_id + ']');
									!numAcc && elInputs.parent().html('..') || elInputs.parent().remove();

									elUpdateRows.find('td[colspan]').each(function() {
										$(this).attr('colspan', (numAcc ? 1 + numAcc : 2))
									});

									elSelected.remove();
									$('#trakt-accounts').change();

									elTraktAuthResult.html('Deleted account: ' + JSONData.account_name);
								}
							});
					}
				},
				'No'	: {
					'class'	: 'red',
					'action': function() {
						e.preventDefault();
						$('#trakt-accounts').change();
					}
				}
			}
		});
	});

	function loadShowNotifyLists() {
		$.get(sbRoot + '/home/load_show_notify_lists', function (data) {
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
				el = $('#email-show');
				el.html('<option value="-1">-- Select show --</option>'
					+ html.join('\n'));

				$('#show-email-list').val('');

				el.change(function () {
					$('#show-email-list').val(
						$(this).find('option[value="' + $(this).val() + '"]').attr('data'))
				});
			}
		});
	}
	// Load the per show notify lists everytime this page is loaded
	loadShowNotifyLists();

	// Update the internal data struct anytime settings are saved to the server
	$('#email-show').bind('notify', function () { loadShowNotifyLists(); });

	$('#save-show-email').click(
		function(){
			var show = $('#email-show').val();
			if ('-1' === show) {
				$('#test-email-result').html('No show selected for save.');
				return
			}
			$.post(sbRoot + '/home/save_show_email', {
				show: show,
				emails: $('#show-email-list').val()},
				function (data){
					// Reload the per show notify lists to reflect changes
					loadShowNotifyLists();
					var result = $.parseJSON(data),
						show = $('#email-show').find('option[value="' + result.id + '"]').text();
					$('#test-email-result').html(result.success
						? 'Success. Notify list updated for show "' + show + '". Click below to test.'
						: 'Error saving notify list for show %s' % show);
				});
		});

	$('#test-email').click(function () {
		var status, host, port, tls, from, user, pwd, err, to;
		status = $('#test-email-result');
		status.html(loading);
		host = $('#email-host').val();
		host = host.length > 0 ? host : null;
		port = $('#email-port').val();
		port = port.length > 0 ? port : null;
		tls = $('#email-tls').attr('checked') !== undefined ? 1 : 0;
		from = $('#email-from').val();
		from = from.length > 0 ? from : 'root@localhost';
		user = $('#email-user').val().trim();
		pwd = $('#email-password').val();
		err = [];
		if (null === host) {
			err.push('SMTP server hostname');
		}
		if (null === port) {
			err.push('SMTP server host port');
		} else if (null === port.match(/^\d+$/) || parseInt(port, 10) > 65535) {
			err.push('SMTP server host port must be between 0 and 65535');
		}
		if (0 < err.length) {
			status.html('Required: ' + err.join(', '));
		} else {
			to = prompt('Enter an email address to send the test to:', '');
			if (null === to || 0 === to.length || null === to.match(/.*@.*/)) {
				status.html('Required: A valid address for email test');
			} else {
				$.get(sbRoot + '/home/test_email',
					{host:host, port:port, smtp_from:from, use_tls:tls, user:user, pwd:pwd, to:to},
					function(msg) {$('#test-email-result').html(msg);});
			}
		}
	});

});
