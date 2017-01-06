/** @namespace $.SickGear.Root */
/** @namespace config.sortArticle */
/** @namespace config.homeSearchFocus */
/** @namespace config.fuzzyDating */
/** @namespace config.fuzzydate */
/** @namespace config.datePreset */
/** @namespace config.timePreset */
/** @namespace config.isPoster */
$.tablesorter.addParser({
	id:'loadingNames',
	is:function(s){
		return !1;
	},
	format:function(s){
		var name = (s.toLowerCase() || '');
		return (0 === name.indexOf('loading...')) ? name.replace('loading...', '000')
			: config.sortArticle ? name : name.replace(/^(?:(?:A(?!\s+to)n?)|The)\s(\w)/i, '$1');
	},
	type:'text'
});

$.tablesorter.addParser({
	id:'quality',
	is:function(s){
		return !1;
	},
	format:function(s){
		return s.replace('hd2160p', 23).replace('hd1080p', 22).replace('hd720p', 21).replace('hd', 20)
			.replace('sd', 10).replace('any', 1).replace('custom', 50);
	},
	type:'numeric'
});

$.tablesorter.addParser({
	id:'downloads',
	is:function(s){
		return !1;
	},
	format:function(s){
		return valueDownloads(s);
	},
	type:'numeric'
});

var valueDownloads = (function(s){
	var match = s.match(/^(\?|\d+)(?:[^/]+[^\d]+(\d+))?$/);

	if (null === match || '?' === match[1])
		return -10;

	var dlCnt = parseInt(match[1], 10), epsCnt = parseInt(match[2], 10);

	if (0 === dlCnt)
		return epsCnt;

	var perNum = parseInt(1000000000 * parseFloat(dlCnt / epsCnt), 10), finalNum = perNum;
	if (0 < finalNum)
		finalNum += dlCnt;

	return finalNum;
}),

llUpdate = (function(){
	$.ll.handleScroll();
	$('#show-list').removeClass('init');
}),

tabUpdate = (function(that, sel){
	$('#link-group' + that.id.replace('container', '')).find('.show-cnt').html(
		'[' + ($(that).find(sel).not('.filtered').length || '--') + ']');
}),

widgetRefresh = function(ctrlElId){
	// update the ui-controlgroup widget classes from DOM class states
	var widgetItems$ = $(ctrlElId + '-menu').find('.ui-menu-item');
	widgetItems$.filter('.selected').removeClass('selected');
	$(ctrlElId).find('.selected').each(function(i, elSelected){
		widgetItems$.eq(elSelected.index).addClass('selected');
	});
};

$(document).ready(function(){
	$('#layout').on('selectmenuchange', function(){
		location.href = this.options[this.selectedIndex].value;
	});

	if (config.homeSearchFocus){
		$('#search_show_name').focus();
	}

	if (config.fuzzyDating){
		fuzzyMoment({
			dtInline:config.isPoster,
			containerClass:config.fuzzydate,
			dateHasTime:!1,
			dateFormat:config.datePreset,
			timeFormat:config.timePreset,
			trimZero:config.trimZero
		});
	}

	$('div[id^="progressbar"]').each(function(k, v){
		var progress = parseInt($(this).siblings('span[class="sort-data"]').attr('data-progress'), 10),
			elId = '#' + $(this).attr('id');
		v = 80;
		$(elId).progressbar({value:progress});
		if (progress < v){
			v = progress >= 40 ? 60 : (progress >= 20 ? 40 : 20);
		}
		$(elId + ' > .ui-progressbar-value').addClass('progress-' + v);
	});

	if (config.isPoster){

		$.sgConfig = config;

		$('#card-sort').on('selectmenuselect', function(event, ui){
			var sortBy = this.value, criteria, ctrlElId = '#' + this.id, elOptions$;
			event.preventBubble = !0;

			// update DOM ctrl
			if (0 !== sortBy.indexOf('order')) {
				criteria = {sortBy: sortBy};
				elOptions$ = $(this).find('option').not('option[value^="order"], option[disabled]');
			} else {
				criteria = {sortAscending: 'order-asc' === sortBy};
				elOptions$ = $(this).find('option[value^="order"]');
			}
			elOptions$.filter('.selected').removeClass('selected');
			ui.item.element.addClass('selected');
			widgetRefresh(ctrlElId);

			$.each(['.ui-tab.ui-state-active', '.ui-tab:not(.ui-state-active)'], function(){
				$('#config-components').find(this.toString()).each(function(){
					$('#' + $(this).attr('aria-controls').replace('core-component-group', 'container'))
						.one('layoutComplete', llUpdate).isotope(criteria);
				});
			});
			$.get(this.options[this.selectedIndex].getAttribute('data-sort'));
		});

		$.sgInitIsoTope = (function() {
			var sortCriteria;
			switch ($('#card-sort').find('.selected').not('option[value^="order"]').val()){
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

			$('.container').each(function(i, obj){
				var page = $('#show-list'),
					width = (page.hasClass('widescape') || page.hasClass('widetrait'))
						? 235 : page.hasClass('tallscape') ? 125 : 188;
				$(obj).one('layoutComplete', llUpdate).isotope({
					itemSelector:'.show-card',
					sortBy:sortCriteria,
					sortAscending:'order-asc' === $('#card-sort').find('option[value^="order"].selected').val(),
					layoutMode:'masonry',
					masonry:{
						columnWidth: width,
						isFitWidth:!0,
						gutter:12
					},
					getSortData:{
						name:function(itemElem){
							var name = $(itemElem).attr('data-name').toLowerCase() || '';
							return $.sgConfig.sortArticle ? name : name.replace(/^(?:(?:A(?!\s+to)n?)|The)\s(\w)/i, '$1');
						},
						date:function(itemElem){
							var date = $(itemElem).attr('data-date');
							return date.length && parseInt(date, 10) || Number.POSITIVE_INFINITY;
						},
						network:function(itemElem){
							return $(itemElem).attr('data-network').toLowerCase()
									.replace(/^(.*?)\W*[(]\w{2,3}[)]|1$/i, '$1') || '';
						},
						progress:function(itemElem){
							var progress = $(itemElem).find('.show-dlstats').text();
							return valueDownloads(progress);
						},
						quality:function(itemElem){
							return $(itemElem).find('.show-quality').text().toLowerCase();
						}
					}
				});
			});
		});
		$.sgInitIsoTope();

		$.sgRepaint = (function(that){
			var states$ = $('#show-list');

			if (!(/undefined/i.test(that)))
				states$.removeClass('widescape smallscape widetrait tallscape').addClass(that.value);

			var	img = states$.hasClass('smallscape') || states$.hasClass('widescape') || states$.hasClass('tallscape')
					? ['poster', 'banner'] : ['banner', 'poster'],
				old = img[0] + '_thumb', repl = img[1] + '_thumb',
				cachedImg = $.SickGear.Root + '/images/' + repl + '.jpg';

			$.each(['.ui-tab.ui-state-active', '.ui-tab:not(.ui-state-active)'], function(){
				$('#config-components').find(this.toString()).each(function(){
					var c$ = $('#' + $(this).attr('aria-controls').replace('core-component-group','container'));

					c$.isotope('destroy');

					var image$ = c$.find('.show-image');

					$.each(image$.find('img[data-original*="' + old + '"]'), function() {
						$(this).attr('data-original', $(this).attr('data-original').replace(old, repl));
					});

					$.each(image$.find('img[src*="' + old + '"]'), function() {
						$(this).attr('data-src-new', $(this).attr('src').replace(old, repl));
						$(this).attr('src', cachedImg);
					});

					var img$ = image$.find('img[src*="' + cachedImg + '"]');
					$.each(img$, function() {
						$(this).attr('src', $(this).attr('data-src-new')).removeAttr('data-src-new');
					});

					$.sgInitIsoTope();
				});
			});

			if (!(/undefined/i.test(that)))
				$.get(that.options[that.selectedIndex].getAttribute('data-state'));

			return !1;
		});
		$('#flexible').on('selectmenuchange', function(){$.sgRepaint(this)});
		$.sgRepaint();

		$('#search_show_name').on('input', $.debounce(400, function(){
			$('.container').one('layoutComplete', llUpdate).isotope({
				filter:function(){
					var filtered = new RegExp(
						$('.regex').attr('data-regex').replace('*', $('#search_show_name').val()), 'i')
						.test($(this).attr('data-name') || '');
					$(this).removeClass('filtered');
					if (!filtered)
						$(this).addClass('filtered');

					$('#config-components').find('.container').each(function(){
						tabUpdate(this, '.show-card');
					});
					return filtered;
				}
			});
		}));
	} else {
		$('.tablesorter').each(function(i, obj){
			$(obj).has('tbody tr').tablesorter({
				sortList:[[5, 1], [1, 0]],
				textExtraction:{
					0:function(node){
						return $(node).find('span.sort-data').text();
					},
					2:function(node){
						return $(node).find('span.sort-data').text().toLowerCase();
					},
					3:function(node){
						return $(node).find('span').text().toLowerCase();
					},
					4:function(node){
						return $(node).find('.progressbarText').text();
					},
					5:function(node){
						return $(node).find('i').attr('alt');
					}
				},
				widgets:['saveSort', 'zebra', 'stickyHeaders', 'filter'],
				headers:{
					1:{sorter:'loadingNames'},
					3:{sorter:'quality'},
					4:{sorter:'downloads'}
				},
				widgetOptions:{
					filter_columnFilters:!1
				},
				sortStable:!0
			}).bind('sortEnd filterEnd', function(e){
				llUpdate();
				'filterEnd' === e.type && tabUpdate(this, 'tr.odd, tr.even');
			});
			$.tablesorter.filter.bindSearch($(obj), $('.search'));
		});
	}

	llUpdate();

	var inputTrigger = (function(reset){
		var input$ = $('#search_show_name');
		if ('' !== input$.val() || (!(/undefined/i.test(reset)) && reset)){
			input$.trigger('input').change();
			if (config.homeSearchFocus)
				input$.focus();
		}
	});

	$('.regex').click(function(){
		var icon = $(this).button('option', 'icon'),
			state = 'ui-icon-star' === icon ? ['ui-icon-arrowthickstop-1-w', '^*']
				: 'ui-icon-arrowthickstop-1-e' === icon ? ['ui-icon-star', '*']
					: ['ui-icon-arrowthickstop-1-e', '*$'];
		$(this).button({'icon': state[0]}).attr('data-regex', state[1]);
		inputTrigger();
	});

	$('.resetshows').click(function(){
		var input$ = $('#search_show_name');
		if ('' !== input$.val()){
			input$.val('');
			inputTrigger(!0);
		}
	});

	var tabs$ = $('#config-components');
	tabs$.on('tabsactivate', function(){
		$('.container').one('layoutComplete', llUpdate).isotope('layout');
		$('.tablesorter').trigger('update');
		llUpdate();
	});

	tabs$.find('.ui-tabs-nav').sortable({
		axis: 'x',
		stop: function (e, ui) {
			$('#config-components').tabs('refresh');

			var tabTexts=[];
			ui.item.parent().find('li').each(function(){
				tabTexts.push($(this).text())
			});
			$.get($.SickGear.Root + '/home/set_tab_layout/?tabs=' + tabTexts.join('|||'))
		}
	});

});
