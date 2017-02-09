/** @namespace $.SickGear.Root */
/** @namespace $.SickGear.Host */
/** @namespace $.SickGear.Port */
/** @namespace $.SickGear.UseHttps */
/** @namespace $.SickGear.PID */
/** @namespace data.msg */

var sgRoot = $.SickGear.Root,
	browserUrl = window.location.protocol + '//' + window.location.host + sgRoot,
	baseUrl = 'http' + ($.SickGear.UseHttps ? 's' : '') + '://' + $.SickGear.Host + ':'
		+ (('' == sgRoot) ? $.SickGear.Port : location.port) + sgRoot,
	isAliveUrl = sgRoot + '/home/is_alive/',
	timeoutId;
$.SickGear.numRestartWaits = 0;

function is_alive() {
	timeoutId = 0;

	//noinspection JSUnusedLocalSymbols
	$.ajax({
		'url': isAliveUrl,
		'type': 'GET',
		'dataType': 'jsonp',
		'success': function(data) {
			var resp = data.msg.toString();
			if ('nope' == resp) {
				// if initialising then just wait and try again

				$('#shut_down_message').find('.spinner,.hide-yes').removeClass();
				$('#restart_message').removeClass();
				setTimeout(is_alive, 100);

			} else if (/undefined/i.test($.SickGear.PID) || $.SickGear.PID == resp) {
				// if this is before we've even shut down then just try again later

				setTimeout(is_alive, 100);

			} else {
				// if we're ready to go then redirect to new url

				$('#restart_message').find('.spinner,.hide-yes').removeClass();
				$('#refresh_message').removeClass();
				window.location = baseUrl + '/home/';
			}
		},
		'error': function(XMLHttpRequest, textStatus, errorThrown) {
			setTimeout(is_alive, 100);
		}
	});
}

$(document).ready(function() {

	is_alive();

	//noinspection JSUnusedLocalSymbols
	$('#shut_down_message').ajaxError(function(e, jqxhr, settings, exception) {
		$.SickGear.numRestartWaits += 1;

		$('#shut_down_message').find('.spinner,.hide-yes').removeClass();

		var restart$ = $('#restart_message');
		restart$.removeClass();

		isAliveUrl = baseUrl + '/home/is_alive/';

		// If using https and the port or protocol changed, then wait 5 seconds before redirect because ajax calls will
		// fail with untrusted certs or when a http ajax request is made from https with a mixed content error.
		if ($.SickGear.UseHttps || 'https:' == window.location.protocol) {
			if (browserUrl != baseUrl) {

				timeoutId = 1;
				setTimeout(function() {
					$('#restart_message').find('.spinner,.hide-yes').removeClass();
					$('#refresh_message').removeClass();
				}, 3000);
				setTimeout(function() {
					window.location = baseUrl + '/home/'
				}, 5000);
			}
		}

		// if it is taking forever just give up
		if (90 < $.SickGear.numRestartWaits) {

			restart$.find('.spinner,.yes,.hide-no').removeClass();
			$('#restart_fail_message').removeClass();
			return;
		}

		if (0 == timeoutId) {

			timeoutId = setTimeout(is_alive, 100);
		}
	});

});
