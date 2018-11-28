/** @namespace $.SickGear.Root */
/** @namespace data.episodes */
/** @namespace ep.showindexer */
/** @namespace ep.showindexid */
/** @namespace ep.season */
/** @namespace ep.episode */
/** @namespace ep.searchstate */
/** @namespace ep.status */
/** @namespace ep.quality */
/** @namespace ep.retrystate */
/** @namespace ep.statusoverview */

var dev = !1,
	logInfo = dev ? console.info.bind(window.console) : function() {},
	logErr = dev ? console.error.bind(window.console) : function() {};

PNotify.prototype.options.maxonscreen = 5;

$(function () {

	ajaxConsumer.checkManualSearches();

});

var baseUrl = function() {
	return $.SickGear.Root;
};

var ajaxConsumer = function () {
	var that = this;
	that.timeoutId = 0;
	that.pollInterval = 0;
	logInfo('init ajaxConsumer');

	return {
		checkManualSearches : function () {
			logInfo('ajaxConsumer.checkManualSearches()');
			var showId = $('#showID').val();
			$.getJSON({
				url: baseUrl() + '/home/search_q_progress' + (/undefined/i.test(showId) ? '' : '?show=' + showId),
				timeout: 15000 // timeout request after 15 secs
			})
			.done(function (data) {
				logInfo('search_q_progress.success(data)', data);
				if (!data.episodes || 0 === data.episodes.length) {
					rowRestore();
				}
				// using 5s as a reasonable max. when updating images from historical statuses after a page refresh
				that.pollInterval = data.episodes && data.episodes.length
					? (uiUpdateComplete(data) ? 5000 : 1000) : 10000;	// 10000/0
			})
			.fail(function () {
				logErr('search_q_progress.error()');
				that.pollInterval = 30000;
			})
			.always(function (jqXHR, textStatus) {
				logInfo('search_q_progress.complete(textStatus)', '\'' + textStatus + '\'.');
				clearTimeout(that.timeoutId);
				if (that.pollInterval)
					that.timeoutId = setTimeout(ajaxConsumer.checkManualSearches, that.pollInterval);
				logInfo(that.pollInterval ? '^-- ' + that.pollInterval/1000 + 's to next work' : '^-- no more work');
				logInfo('====');
			});
		}
	};
}();

function uiUpdateComplete(data) {
	var isFinished = !0;
	$.each(data.episodes, function (name, ep) {

		var sxe = ep.season + 'x' + ep.episode,
			displayShowEp$ = $('#' + sxe),
			displayShow$ = displayShowEp$.closest('tr'),
			episodeView$ = $('[data-show-id="' + ep.showindexer + '_' + ep.showindexid + '_' + sxe + '"]'),
			link$ = (displayShow$.length ? displayShow$ : episodeView$).find('.ep-search, .ep-retry'),
			uiOptions = $.ajaxEpSearch.defaults;

		logInfo('^-- data item', name, ep.searchstate, ep.showindexid, sxe, ep.statusoverview);

		if (link$.length) {
			var htmlContent = '', imgTip, imgCls;

			switch (ep.searchstate) {
				case 'searching':
					isFinished = !1;
					imgUpdate(link$, 'Searching', uiOptions.loadingImage);
					disableLink(link$);
					uiWanted(displayShow$);
					htmlContent = '[' + ep.searchstate + ']';
					break;
				case 'queued':
					isFinished = !1;
					imgUpdate(link$, 'Queued', uiOptions.queuedImage);
					disableLink(link$);
					uiWanted(displayShow$);
					htmlContent = '[' + ep.searchstate + ']';
					break;
				case 'finished':
					var attrName = !!getAttr(link$, 'href') ? 'href' : 'data-href', href = getAttr(link$, attrName);
					if (ep.retrystate) {
						imgTip = 'Click to retry download';
						link$.attr('class', 'ep-retry').attr(attrName, href.replace('search', 'retry'));
					} else {
						imgTip = 'Click for manual search';
						link$.attr('class', 'ep-search').attr(attrName, href.replace('retry', 'search'));
					}
					if (/good|qual|snatched/i.test(ep.statusoverview)) {
						imgCls = uiOptions.imgYes;
						if (/good/i.test(ep.statusoverview))
							imgCls = uiOptions.successImage;
						else if (/qual/i.test(ep.statusoverview))
							imgCls = uiOptions.upgradeImage;
						// unhide displayshow row checkbox on success, e.g. unaired eps hide it
						displayShowEp$.removeClass('hide');
					} else {
						imgTip = 'Last manual search failed. Click to try again';
						imgCls = uiOptions.imgNo;
					}
					imgUpdate(link$, imgTip, imgCls);
					enableLink(link$);

					// update row status
					if (ep.statusoverview) {
						uiClearClass(link$.closest('tr'))
							.addClass(ep.statusoverview);
					}
					// update quality text for status column
					var rSearchTerm = /(\w+)\s\((.+?)\)/;
					htmlContent = ep.status.replace(rSearchTerm,
						'$1' + ' <span class="quality ' + ep.quality + '">' + '$2' + '</span>');

					// remove backed vars
					link$.removeAttr('data-status data-rowclass data-imgclass');
			}

			// update the status area
			link$.closest('.col-search').siblings('.col-status').html(htmlContent);
		}
	});
	return isFinished;
}

function enableLink(el$) {
	el$.attr('href', el$.attr('data-href')).removeAttr('data-href').fadeTo('fast', 1);
}

function disableLink(el$) {
	el$.attr('data-href', el$.attr('href')).removeAttr('href').fadeTo('fast', .7);
}

function getAttr(el$, name) {
	return el$.is('[' + name + ']') ? el$.attr(name) : !1;
}

function imgUpdate(link$, tip, cls) {
	link$.find('img').attr('src', '').attr('title', tip).prop('alt', '')
		.removeClass('spinner2 queued search no yes').addClass(cls);
}

function uiClearClass(el$) {
	return el$.removeClass('skipped wanted qual good unaired snatched') || el$;
}

function uiWanted(el$) {
	uiClearClass(el$).addClass('wanted');
}

function rowRestore() {
	$('a[data-status]').each(function() {
		uiClearClass($(this).closest('tr'))
			.addClass($(this).attr('data-rowclass'));
		$(this).closest('.col-search').siblings('.col-status').html($(this).attr('data-status'));
		imgUpdate($(this),
			getAttr($(this), 'data-imgtitle'),
			getAttr($(this), 'data-imgclass') || $.ajaxEpSearch.defaults.searchImage);
		$(this).removeAttr('data-status data-rowclass data-imgclass data-imgtitle');
	});
}

(function() {

	$.ajaxEpSearch = {
		defaults: {
			size:			16,
			colorRow:		!1,
			loadingImage:	'spinner2',
			queuedImage:	'queued',
			searchImage:	'search',
			successImage:	'success',
			upgradeImage:	'upgrade',
			imgNo:			'no',
			imgYes:			'yes'
		}
	};

	$.fn.ajaxEpSearch = function(uiOptions) {
		uiOptions = $.extend( {}, $.ajaxEpSearch.defaults, uiOptions);

		$('.ep-search, .ep-retry').on('click', function(event) {
			event.preventDefault();
			logInfo(($(this).hasClass('ep-search') ? 'Search' : 'Retry') + ' clicked');

			// check if we have disabled the click
			if (!!getAttr($(this), 'data-href')) {
				logInfo('Already queued, not downloading!');
				return !1;
			}

			if ($(this).hasClass('ep-retry')
				&& !confirm('Mark download as bad and retry?')) {
				return !1;
			}

			var link$ = $(this), img$ = link$.find('img'), img = ['Failed', uiOptions.imgNo], imgCls;
			// backup ui vars
			if (!!link$.closest('.col-search').length && link$.closest('.col-search').siblings('.col-status')) {
				link$.attr('data-rowclass', getAttr(link$.closest('tr'), 'class'));
				link$.attr('data-status', link$.closest('.col-search').siblings('.col-status').html().trim());
			}
			link$.attr('data-imgtitle', getAttr(img$, 'title'));
			if (imgCls = getAttr(img$, 'class')) {
				link$.attr('data-imgclass', imgCls.trim());
			}

			imgUpdate(link$, 'Loading', uiOptions.loadingImage);
			uiWanted(link$.closest('tr'));

			$.getJSON({url: baseUrl() + $(this).attr('href'), timeout: 15000})
				.done(function(data) {
					logInfo('getJSON() data...', data);

					// if failed, replace success/queued with initiated red X/No
					if ('failure' !== data.result) {
						// otherwise, queued successfully

						// update ui status
						link$.closest('.col-search').siblings('.col-status').html('[' + data.result + ']');

						// prevent further interaction
						disableLink(link$);

						img = 'queuing' === data.result
							? ['Queuing', uiOptions.queuedImage]
							: ['Searching', uiOptions.loadingImage];
					}

					// update ui image
					imgUpdate(link$, img[0], img[1]);
					ajaxConsumer.checkManualSearches();
				})
				.fail(function() { rowRestore(); });

			// prevent following the clicked link
			return !1;
		});
	};
})();
