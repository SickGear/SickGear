/** @namespace $.SickGear.Root */

var dev = !1,
	logInfo = dev && console.info.bind(window.console) || function(){},
	logErr = dev && console.error.bind(window.console) || function(){};

$(function () {

	ajaxConsumer.checkLoadNotifications();

});

var baseUrl = function () {
	return $.SickGear.Root;
};

var ajaxConsumer = function () {
	var that = this;
	that.timeoutId = 0;
	that.pollInterval = 100;
	logInfo('init ajaxConsumer');

	return {
		checkLoadNotifications : function () {
			logInfo('ajaxConsumer.checkLoadNotifications()');
			$.getJSON({
				url: baseUrl() + '/get_message',
				timeout: 15000 // timeout request after 15 secs
			})
			.done(function (data) {
				uiUpdateComplete(data.message);
			})
			.fail(function (jqXHR, textStatus, errorThrown) {
				if (404 === jqXHR.status) {
					putMsg('Finished loading. Reloading page');
					location.reload();
				}
				that.pollInterval = 500;
			})
			.always(function (jqXHR, textStatus) {
				clearTimeout(that.timeoutId);
				if (that.pollInterval)
					that.timeoutId = setTimeout(ajaxConsumer.checkLoadNotifications, that.pollInterval);
				logInfo(that.pollInterval ? '^-- ' + that.pollInterval/1000 + 's to next work' : '^-- no more work');
				logInfo('====');
			});
		}
	};
}();

function putMsg(msg) {
	var loading = '.loading-step', lastStep = $(loading).filter(':last');
	if (msg !== lastStep.find('.desc').attr('data-message')){
		lastStep.after(lastStep.clone());
		lastStep.find('.spinner').hide();
		lastStep.find('.hide-yes').removeClass('hide-yes');
		$(loading).filter(':last')
			.find('.desc')
			.attr('data-message', msg)
			.text(msg + ': ');
	}
}

function uiUpdateComplete(data) {
	$.each(data, function (i, msg) {
		if (i >= $('.loading-step').length){
			putMsg(msg)
		}
	});
}
