$.tablesorter.addParser({
	id: 'loadingNames',
	is: function (s) {
		return false;
	},
	format: function (s) {
		if (s.indexOf('Loading...') === 0) {
			return s.replace('Loading...', '000');
		} else if (config.sortArticle) {
			return (s || '');
		} else {
			return (s || '').replace(/^(?:(?:A(?!\s+to)n?)|The)\s(\w)/i, '$1');
		}
	},
	type: 'text'
});

$.tablesorter.addParser({
	id: 'quality',
	is: function (s) {
		return false;
	},
	format: function (s) {
		return s.replace('hd1080p', 5).replace('hd720p', 4).replace('hd', 3).replace('sd', 2).replace('any', 1).replace('custom', 7);
	},
	type: 'numeric'
});

$(document).ready(function () {
	if (config.homeSearchFocus) {
		$('#search_show_name').focus();
	}

	if (config.fuzzyDating) {
		fuzzyMoment({
			dtInline: config.isPoster,
			containerClass: config.fuzzydate,
			dateHasTime: !1,
			dateFormat: config.datePreset,
			timeFormat: config.timePreset,
			trimZero: config.trimZero
		});
	}

	$('div[id^="progressbar"]').each(function (k, v) {
		var progress = parseInt($(this).siblings('span[class="sort-data"]').attr('data-progress'), 10), elId = '#' + $(this).attr('id'), v = 80;
		$(elId).progressbar({value: progress});
		if (progress < 80) {
			v = progress >= 40 ? 60 : (progress >= 20 ? 40 : 20);
		}
		$(elId + ' > .ui-progressbar-value').addClass('progress-' + v);
	});

	$('img#network').on('error', function () {
		$(this).parent().text($(this).attr('alt'));
		$(this).remove();
	});

	if (config.isPoster) {
		$('.container').each(function (i, obj) {
			$(obj).isotope({
				itemSelector: '.show',
				sortBy: config.posterSortby,
				sortAscending: config.posterSortdir,
				layoutMode: 'masonry',
				masonry: {
					columnWidth: 12,
					isFitWidth: true
				},
				getSortData: {
					name: function (itemElem) {
						var name = $(itemElem).attr('data-name');
						if (config.sortArticle) {
							return (name || '');
						} else {
							return (name || '').replace(/^(?:(?:A(?!\s+to)n?)|The)\s(\w)/i, '$1');
						}
					},
					date: function (itemElem) {
						var date = $(itemElem).attr('data-date');
						return date.length && parseInt(date, 10) || Number.POSITIVE_INFINITY;
					},
					network: '[data-network]',
					progress: function (itemElem) {
						var progress = $(itemElem).children('.sort-data').attr('data-progress');
						return progress.length && parseInt(progress, 10) || Number.NEGATIVE_INFINITY;
					}
				}
			});

			$('#postersort').on('change', function () {
				var sortValue = this.value;
				$(obj).isotope({sortBy: sortValue});
				$.get(this.options[this.selectedIndex].getAttribute('data-sort'));
			});

			$('#postersortdirection').on('change', function () {
				var sortDirection = this.value;
				sortDirection = sortDirection == 'true';
				$(obj).isotope({sortAscending: sortDirection});
				$.get(this.options[this.selectedIndex].getAttribute('data-sort'));
			});
		});
	} else {
		$('.tablesorter').each(function (i, obj) {
			$(obj).has('tbody tr').tablesorter({
				sortList: [[5, 1], [1, 0]],
				textExtraction: {
					0: function (node) {
						return $(node).find('span').text().toLowerCase();
					},
					2: function (node) {
						return $(node).find('span').text().toLowerCase();
					},
					3: function (node) {
						return $(node).find('span').text().toLowerCase();
					},
					4: function (node) {
						return $(node).find('span').attr('data-progress');
					},
					5: function (node) {
						return $(node).find('i').attr('alt');
					}
				},
				widgets: ['saveSort', 'zebra', 'stickyHeaders', 'filter'],
				headers: {
					0: {sorter: 'isoDate'},
					1: {sorter: 'loadingNames'},
					3: {sorter: 'quality'},
					4: {sorter: 'eps'}
				},
				widgetOptions: {
					filter_columnFilters: false,
					filter_reset: '.resetshows'
				},
				sortStable: true
			});
		});
	}
});