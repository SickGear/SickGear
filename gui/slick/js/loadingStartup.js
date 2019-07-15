/** @namespace $.SickGear.Root */

var dev = !1,
	logInfo = dev && console.info.bind(window.console) || function (){},
	logErr = dev && console.error.bind(window.console) || function (){};

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
	var loading = '.loading-step', lastStep$ = $(loading).filter(':last');
	if (msg !== lastStep$.attr('data-message')) {
		lastStep$.clone().insertAfter(lastStep$);

		var result$ = lastStep$.find('.result');
		lastStep$.find('.spinner').addClass('hide');
		if (!lastStep$.find('.count').text().length) {
			result$.removeClass('hide');
		} else {
			result$.addClass('hide');
		}
		lastStep$ =  $(loading).filter(':last');
		lastStep$.attr('data-message', msg);
		lastStep$.find('.desc').text(msg + ': ');
		lastStep$.find('.count').text('');
		lastStep$.find('.spinner').removeClass('hide');
		lastStep$.find('.result').addClass('hide');
	}
}

function uiUpdateComplete(data) {
	$.each(data, function (i, msg) {
		var loading = '.loading-step';
		if (i >= $(loading).length) {
			putMsg(msg.msg);
		}
		if (-1 !== msg.progress) {
			var loading$ = $(loading + '[data-message="' + msg.msg + '"]');
			loading$.find('.spinner, .result').addClass('hide');
			loading$.find('.count').text(msg.progress);
		}
	});
}
