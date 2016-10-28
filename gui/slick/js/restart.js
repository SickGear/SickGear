/** @namespace $.SickGear.Root */
/** @namespace $.SickGear.Host */
/** @namespace $.SickGear.Port */
/** @namespace $.SickGear.UseHttps */
/** @namespace data.msg */

var sgRoot = $.SickGear.Root,
	browserUrl = window.location.protocol + '//' + window.location.host + sgRoot,
	baseUrl = 'http' + ($.SickGear.UseHttps ? 's' : '') + '://' + $.SickGear.Host + ':'
		+ (('' == sgRoot) ? $.SickGear.Port : location.port) + sgRoot,
	isAliveUrl = sgRoot + '/home/is_alive/',
	timeoutId;
$.SickGear.currentPid = '';
$.SickGear.numRestartWaits = 0;

function is_alive() {
	timeoutId = 0;
	$.get(isAliveUrl, function(data) {

		if ('nope' == data.msg.toString()) {
			// if initialising then just wait and try again

			$('#shut_down_message').find('.spinner,.hide-yes').removeClass();
			$('#restart_message').removeClass();
			setTimeout(is_alive, 100);

		} else if ('' == $.SickGear.currentPid || $.SickGear.currentPid == data.msg) {
			// if this is before we've even shut down then just try again later

			$.SickGear.currentPid = data.msg;
			setTimeout(is_alive, 100);

		} else {
			// if we're ready to go then redirect to new url

			$('#restart_message').find('.spinner,.hide-yes').removeClass();
			$('#refresh_message').removeClass();
			window.location = baseUrl + '/home/';
		}
	}, 'jsonp');
}

$(document).ready(function() {

	is_alive();

	//noinspection JSUnusedLocalSymbols
	$('#shut_down_message').ajaxError(function(e, jqxhr, settings, exception) {
		$.SickGear.numRestartWaits += 1;

		$('#shut_down_message').find('.spinner,.hide-yes').removeClass();
		$('#restart_message').removeClass();
		isAliveUrl = baseUrl + '/home/is_alive/';

		// if https is enabled or you are currently on https and the port or protocol changed just wait 5 seconds then redirect.
		// This is because the ajax will fail if the cert is untrusted or the the http ajax request from https will fail because of mixed content error.
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

			$('#restart_message').find('.spinner,.yes,.hide-no').removeClass();
			$('#restart_fail_message').removeClass();
			return;
		}

		if (0 == timeoutId) {

			timeoutId = setTimeout(is_alive, 100);
		}
	});

});
