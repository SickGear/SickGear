/** @namespace $.SickGear.Root */
/** @namespace $.SickGear.history.isCompact */
/** @namespace $.SickGear.history.isTrashit */
/** @namespace $.SickGear.history.useSubtitles */
/** @namespace $.SickGear.history.layoutName */
/*
 2017 Jason Mulligan <jason.mulligan@avoidwork.com>
 @version 3.5.11
*/
!function(i){function e(i){var e=arguments.length>1&&void 0!==arguments[1]?arguments[1]:{},n=[],d=0,r=void 0,a=void 0,s=void 0,f=void 0,u=void 0,l=void 0,v=void 0,B=void 0,c=void 0,p=void 0,y=void 0,m=void 0,x=void 0,g=void 0;if(isNaN(i))throw new Error("Invalid arguments");return s=!0===e.bits,y=!0===e.unix,a=e.base||2,p=void 0!==e.round?e.round:y?1:2,m=void 0!==e.spacer?e.spacer:y?"":" ",g=e.symbols||e.suffixes||{},x=2===a?e.standard||"jedec":"jedec",c=e.output||"string",u=!0===e.fullform,l=e.fullforms instanceof Array?e.fullforms:[],r=void 0!==e.exponent?e.exponent:-1,B=Number(i),v=B<0,f=a>2?1e3:1024,v&&(B=-B),(-1===r||isNaN(r))&&(r=Math.floor(Math.log(B)/Math.log(f)))<0&&(r=0),r>8&&(r=8),0===B?(n[0]=0,n[1]=y?"":t[x][s?"bits":"bytes"][r]):(d=B/(2===a?Math.pow(2,10*r):Math.pow(1e3,r)),s&&(d*=8)>=f&&r<8&&(d/=f,r++),n[0]=Number(d.toFixed(r>0?p:0)),n[1]=10===a&&1===r?s?"kb":"kB":t[x][s?"bits":"bytes"][r],y&&(n[1]="jedec"===x?n[1].charAt(0):r>0?n[1].replace(/B$/,""):n[1],o.test(n[1])&&(n[0]=Math.floor(n[0]),n[1]=""))),v&&(n[0]=-n[0]),n[1]=g[n[1]]||n[1],"array"===c?n:"exponent"===c?r:"object"===c?{value:n[0],suffix:n[1],symbol:n[1]}:(u&&(n[1]=l[r]?l[r]:b[x][r]+(s?"bit":"byte")+(1===n[0]?"":"s")),n.join(m))}var o=/^(b|B)$/,t={iec:{bits:["b","Kib","Mib","Gib","Tib","Pib","Eib","Zib","Yib"],bytes:["B","KiB","MiB","GiB","TiB","PiB","EiB","ZiB","YiB"]},jedec:{bits:["b","Kb","Mb","Gb","Tb","Pb","Eb","Zb","Yb"],bytes:["B","KB","MB","GB","TB","PB","EB","ZB","YB"]}},b={iec:["","kibi","mebi","gibi","tebi","pebi","exbi","zebi","yobi"],jedec:["","kilo","mega","giga","tera","peta","exa","zetta","yotta"]};e.partial=function(i){return function(o){return e(o,i)}},"undefined"!=typeof exports?module.exports=e:"function"==typeof define&&define.amd?define(function(){return e}):i.filesize=e}("undefined"!=typeof window?window:global);

function rowCount(){
	var output$ = $('#row-count');
	if(!output$.length)
		return;

	var tbody$ = $('#tbody'),
		nRows = tbody$.find('tr').length,
		compacted = tbody$.find('tr.hide').length,
		compactedFiltered = tbody$.find('tr.filtered.hide').length,
		filtered = tbody$.find('tr.filtered').length;
	output$.text((filtered
		? nRows - (filtered + compacted - compactedFiltered) + ' / ' + nRows + ' filtered'
		: nRows) + (1 === nRows ? ' row' : ' rows'));
}

$(document).ready(function() {

	var extraction = {0: function(node) {
			var dataSort = $(node).find('div[data-sort]').attr('data-sort')
				|| $(node).find('span[data-sort]').attr('data-sort');
			return !dataSort ? dataSort : dataSort.toLowerCase();}},
		tbody$ = $('#tbody'),
		headers = {},
		layoutName = '' + $.SickGear.history.layoutName;

	if ('detailed' === layoutName) {

		jQuery.extend(extraction, {
			4: function (node) {
				return $(node).find('span').text().toLowerCase();
			}
		});

		jQuery.extend(headers, {4: {sorter: 'quality'}});

	} else if ('compact' === layoutName) {

		jQuery.extend(extraction, {
			1: function (node) {
				return $(node).find('span[data-sort]').attr('data-sort').toLowerCase();
			},
			2: function (node) {
				return $(node).attr('provider').toLowerCase();
			},
			5: function (node) {
				return $(node).attr('quality').toLowerCase();
			}
		});

		var disable = {sorter: !1}, qualSort = {sorter: 'quality'};
		jQuery.extend(headers, $.SickGear.history.useSubtitles ? {4: disable, 5: qualSort} : {3: disable, 4: qualSort});

	} else if (-1 !== layoutName.indexOf('watched')) {

		jQuery.extend(extraction, {
			3: function(node) {
				return $(node).find('span[data-sort]').attr('data-sort');
			},
			5: function(node) {
				return $(node).find('span[data-sort]').attr('data-sort');
			},
			6: function (node) {
				return $(node).find('input:checked').length;
			}
		});

		jQuery.extend(headers, {4: {sorter: 'quality'}});

		rowCount();
	} else if (-1 !== layoutName.indexOf('compact_stats')) {
		jQuery.extend(extraction, {
			3: function (node) {
				return $(node).find('div[data-sort]').attr('data-sort');
			}
		});

	}

	var isWatched = -1 !== $('select[name="HistoryLayout"]').val().indexOf('watched'),
		options = {
			widgets: ['zebra', 'filter'],
			widgetOptions : {
				filter_hideEmpty: !0, filter_matchType : {'input': 'match', 'select': 'match'},
				filter_resetOnEsc: !0, filter_saveFilters: !0, filter_searchDelay: 300
			},
			sortList: isWatched ? [[1, 1], [0, 1]] : [0, 1],
			textExtraction: extraction,
			headers: headers},
		stateLayoutDate = function(table$, glyph$){table$.toggleClass('event-age');glyph$.toggleClass('age date');};

	if(isWatched){
		jQuery.extend(options, {
			selectorSort: '.tablesorter-header-inside',
			headerTemplate: '<div class="tablesorter-header-inside" style="margin:0 -8px 0 -4px">{content}{icon}</div>',
			onRenderTemplate: function(index, template){
				if(0 === index){
					template = '<i id="watched-date" class="icon-glyph date add-qtip" title="Change date layout" style="float:left;margin:4px -14px 0 2px"></i>'
						+ template;
				}
				return template;
			},
			onRenderHeader: function(){
				var table$ = $('#history-table'), glyph$ = $('#watched-date');
				if($.tablesorter.storage(table$, 'isLayoutAge')){
					stateLayoutDate(table$, glyph$);
				}
				$(this).find('#watched-date').on('click', function(){
					stateLayoutDate(table$, glyph$);
					$.tablesorter.storage(table$, 'isLayoutAge', table$.hasClass('event-age'));
					return !1;
				});
			}
		});
	}

	$('#history-table').tablesorter(options).bind('filterEnd', function(){
		rowCount();
	});

	$('#limit').change(function(){
		window.location.href = $.SickGear.Root + '/history/?limit=' + $(this).val()
	});

	$('#show-watched-help').click(function () {
		$('#watched-help').fadeToggle('fast', 'linear');
		$.get($.SickGear.Root + '/history/toggle-help');
	});

	var addQTip = (function(){
		$(this).css('cursor', 'help');
		$(this).qtip({
			show: {solo:true},
			position: {viewport:$(window), my:'left center', adjust:{y: -10, x: 2}},
			style: {tip: {corner:true, method:'polygon'}, classes:'qtip-dark qtip-rounded qtip-shadow'}
		});
	});
	$('.add-qtip').each(addQTip);

	$.SickGear.sumChecked = (function(){
		var dedupe = [], sum = 0, output;

		$('.del-check:checked').each(function(){
			if ($(this).closest('tr').find('.tvShow .strike-deleted').length)
				return;
			var pathFile = $(this).closest('tr').attr('data-file');
			if (-1 === jQuery.inArray(pathFile, dedupe)) {
				dedupe.push(pathFile);
				output = $(this).closest('td').prev('td.size').find('span[data-sort]').attr('data-sort');
				sum = sum + parseInt(output, 10);
			}
		});
		$('#del-watched').attr('disabled', !dedupe.length && !$('#tbody').find('tr').find('.tvShow .strike-deleted').length);

		output = filesize(sum, {symbols: {B: 'Bytes'}});
		$('#sum-size').text(/\s(MB)$/.test(output) ? filesize(sum, {round:1})
			: /^1\sB/.test(output) ? output.replace('Bytes', 'Byte') : output);
	});
	$.SickGear.sumChecked();

	var className='.del-check', lastCheck = null, check, found;
	tbody$.on('click', className, function(ev){
		if(!lastCheck || !ev.shiftKey){
			lastCheck = this;
		} else {
			check = this; found = 0;
			$('#tbody').find('> tr:visible').find(className).each(function(){
				if (2 === found)
					return !1;
				if (1 === found)
					this.checked = lastCheck.checked;
				found += (1 && (this === check || this === lastCheck));
			});
		}
		$(this).closest('table').trigger('update');
		$.SickGear.sumChecked();
	});

	function updown(data){
		var result = ': <span class="grey-text">failed to test site, oh the irony!</span>';

		if(!(/undefined/i.test(data))) {
			// noinspection JSUnresolvedVariable
			var resp = data.last_down;

			if (!(/undefined/i.test(resp))) {
				result = ': <span class="grey-text"> yes it\'s <span class="box-green">up</span> and was last down ' + resp + ' ago</span>';
			} else {
				// noinspection JSUnresolvedVariable
				resp = data.down_for;
				if (!(/undefined/i.test(resp))) {
					result = ': <span class="red-text">no, it\'s been <span class="box-red">down</span> for ~' + resp + '</span>';
				}
			}
		}

		return result;
	}

	function check_site(clicked){
		var that = $(clicked), el$=$(that.parent());
		that.attr('disabled', !0);
		$.ajax({
			url: $.SickGear.Root + '/history/check-site/?site_name=' + el$.attr('data-check'),
			type: 'GET',
			dataType: 'json',
			complete: function (data) {
				// noinspection JSUnresolvedVariable
				el$.find('.result').html(updown(data.responseJSON));
				el$.find('a').show();
				that.attr('disabled', !1);
			}
		});
	}

	$.each(['tvdb', 'thexem', 'github'], function(i, el_id){
		$('#check-' + el_id).find('input').click(function(){
			check_site(this);
		});
	});

	$('.shows-less').click(function(){
		var table$ = $(this).nextAll('table:first');
		table$ = table$.length ? table$ : $(this).parent().nextAll('table:first');
		table$.hide();
		$(this).hide();
		$(this).prevAll('input:first').show();
	});
	$('.shows-more').click(function(){
		var table$ = $(this).nextAll('table:first');
		table$ = table$.length ? table$ : $(this).parent().nextAll('table:first');
		table$.show();
		$(this).hide();
		$(this).nextAll('input:first').show();
	});

	$('.provider-retry').click(function () {
		$(this).addClass('disabled');
		var match = $(this).attr('id').match(/^(.+)-btn-retry$/);
		$.ajax({
			url: $.SickGear.Root + '/manage/search-tasks/retry-provider?provider=' + match[1],
			type: 'GET',
			complete: function () {
				window.location.reload(true);
			}
		});
	});

	$('.provider-failures').tablesorter({widgets : ['zebra'],
		headers : { 0:{sorter:!1}, 1:{sorter:!1}, 2:{sorter:!1}, 3:{sorter:!1}, 4:{sorter:!1}, 5:{sorter:!1} }
	});

	$('.provider-fail-parent-toggle').click(function(){
		$(this).closest('tr').nextUntil('tr:not(.tablesorter-childRow)').find('td').toggle();
		return !1;
	});

	// Make table cell focusable
	// http://css-tricks.com/simple-css-row-column-highlighting/
	var focus$ = $('.focus-highlight');
	if (focus$.length){
		focus$.find('td, th')
			.attr('tabindex', '1')
			// add touch device support
			.on('touchstart', function(){
				$(this).focus();
		});
	}
});
