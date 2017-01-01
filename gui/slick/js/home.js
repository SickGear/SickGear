/** @namespace config.sortArticle */
/** @namespace config.homeSearchFocus */
/** @namespace config.fuzzyDating */
/** @namespace config.fuzzydate */
/** @namespace config.datePreset */
/** @namespace config.timePreset */
/** @namespace config.isPoster */
/** @namespace config.posterSortby */
/** @namespace config.posterSortdir */
$.tablesorter.addParser({
	id: 'loadingNames',
	is: function (s) {
		return !1;
	},
	format: function (s) {
		var name = (s.toLowerCase() || '');
		return (0 == name.indexOf('loading...')) ? name.replace('loading...', '000')
			: config.sortArticle ? name : name.replace(/^(?:(?:A(?!\s+to)n?)|The)\s(\w)/i, '$1');
	},
	type: 'text'
});

$.tablesorter.addParser({
	id: 'quality',
	is: function (s) {
		return !1;
	},
	format: function (s) {
		return s.replace('hd1080p', 22).replace('hd720p', 21).replace('hd', 20)
			.replace('sd', 10).replace('any', 1).replace('custom', 50);
	},
	type: 'numeric'
});

$.tablesorter.addParser({
	id: 'downloads',
	is: function (s) {
		return !1;
	},
	format: function(s) {
		return valueDownloads(s);
	},
	type: 'numeric'
});

var valueDownloads = (function(s){
	var match = s.match(/^(\?|\d+)(?:[^/]+[^\d]+(\d+))?$/);

	if (null == match || '?' == match[1])
		return -10;

	var dlCnt = parseInt(match[1], 10), epsCnt = parseInt(match[2], 10);

	if (0 == dlCnt)
		return epsCnt;

	var perNum = parseInt(1000000000 * parseFloat(dlCnt / epsCnt), 10), finalNum = perNum;
	if (0 < finalNum)
		finalNum += dlCnt;

	return finalNum;
}),

llUpdate = (function(){
	$.ll.handleScroll();
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
		var progress = parseInt($(this).siblings('span[class="sort-data"]').attr('data-progress'), 10),
			elId = '#' + $(this).attr('id');
		v = 80;
		$(elId).progressbar({value: progress});
		if (progress < v) {
			v = progress >= 40 ? 60 : (progress >= 20 ? 40 : 20);
		}
		$(elId + ' > .ui-progressbar-value').addClass('progress-' + v);
	});

	if (config.isPoster) {
		$('.container').each(function (i, obj) {
			var sortCriteria;
			switch (config.posterSortby) {
				case 'date':
					sortCriteria = ['date', 'name', 'network', 'progress'];
					break;
				case 'network':
					sortCriteria = ['network', 'name', 'date', 'progress'];
					break;
				case 'progress':
					sortCriteria = ['progress', 'name', 'date', 'network'];
					break;
				case 'quality':
					sortCriteria = ['quality', 'name', 'date', 'network', 'progress'];
					break;
				default:
					sortCriteria = ['name', 'date', 'network', 'progress'];
					break;
			}

			$(obj).one('layoutComplete', llUpdate);
			$(obj).isotope({
				itemSelector: '.show-card',
				sortBy: sortCriteria,
				sortAscending: config.posterSortdir,
				layoutMode: 'masonry',
				masonry: {
					columnWidth: 188,
					isFitWidth: !0,
					gutter: 12
				},
				getSortData: {
					name: function (itemElem) {
						var name = $(itemElem).attr('data-name').toLowerCase() || '';
						return config.sortArticle ? name : name.replace(/^(?:(?:A(?!\s+to)n?)|The)\s(\w)/i, '$1');
					},
					date: function (itemElem) {
						var date = $(itemElem).attr('data-date');
						return date.length && parseInt(date, 10) || Number.POSITIVE_INFINITY;
					},
					network: function (itemElem) {
						return $(itemElem).attr('data-network').toLowerCase()
								.replace(/^(.*?)\W*[(]\w{2,3}[)]|1$/i, '$1') || '';
					},
					progress: function (itemElem) {
						var progress = $(itemElem).find('.show-dlstats').text();
						return valueDownloads(progress);
					},
					quality: function (itemElem) {
						return $(itemElem).find('.show-quality').text().toLowerCase();
					}
				}
			});

			$('#postersort').on('change', function () {
				var sortValue = this.value;
				$(obj).one('layoutComplete', llUpdate);
				$(obj).isotope({sortBy: sortValue});
				$.get(this.options[this.selectedIndex].getAttribute('data-sort'));
			});

			$('#postersortdirection').on('change', function () {
				var sortDirection = this.value;
				sortDirection = sortDirection == 'true';
				$(obj).one('layoutComplete', llUpdate);
				$(obj).isotope({sortAscending: sortDirection});
				$.get(this.options[this.selectedIndex].getAttribute('data-sort'));
			});
		});

		$('#search_show_name').on('input', function() {
			var obj = $('.container');
			obj.one('layoutComplete', llUpdate);
			obj.isotope({
				filter: function () {
					return 0 <= $(this).attr('data-name').toLowerCase().indexOf(
							$('#search_show_name').val().toLowerCase());
				}
			});
		});
	} else {
		$('.tablesorter').each(function (i, obj) {
			$(obj).has('tbody tr').tablesorter({
				sortList: [[5, 1], [1, 0]],
				textExtraction: {
					0: function (node) {
						return $(node).find('span.sort-data').text();
					},
					2: function (node) {
						return $(node).find('span.sort-data').text().toLowerCase();
					},
					3: function (node) {
						return $(node).find('span').text().toLowerCase();
					},
					4: function (node) {
						return $(node).find('.progressbarText').text();
					},
					5: function (node) {
						return $(node).find('i').attr('alt');
					}
				},
				widgets: ['saveSort', 'zebra', 'stickyHeaders', 'filter'],
				headers: {
					1: {sorter: 'loadingNames'},
					3: {sorter: 'quality'},
					4: {sorter: 'downloads'}
				},
				widgetOptions: {
					filter_columnFilters: !1
				},
				sortStable: !0
			});
			$.tablesorter.filter.bindSearch($(obj), $('.search'));
		});
	}
	$('.resetshows').click(function() {
		var input = $('#search_show_name');
		if ('' !== input.val()){
			input.val('').trigger('input').change();
			if (config.homeSearchFocus)
				input.focus();
		}
	});
});
