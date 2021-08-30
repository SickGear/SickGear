/** @namespace $.SickGear.Root */
/** @namespace config.sortArticle */
/** @namespace config.resultsSortby */
/** @namespace config.searchTests */
/** @namespace config.folder */
$(document).ready(function () {

	function htmlFlag(lang) {
		return ' class="flag" style="background-image:url(' + $.SickGear.Root + '/images/flags/' + lang + '.png)"'
	}

	function populateLangSelect() {
		if (!$('#nameToSearch').length)
			return;

		if (1 >= $('#infosrc-lang-select').find('option').length) {

			$.getJSON(sbRoot + '/add-shows/get-infosrc-languages', {}, function (data) {

				var resultStr = '', flag,
					selected = ' selected="selected"',
					elInfosrcLang = $('#infosrc-lang-select');

				if (0 === data.results.length) {
					resultStr = '<option value="en"' + selected + '>&gt; en</option>';
				} else {
					$.each(data.results, function (index, obj) {
						flag = htmlFlag(obj);
						resultStr += '<option value="' + obj + '"'
							+ ('' === resultStr
								? flag.replace('"flag', '"flag selected-text') + selected + '>&gt; '
								: flag + '>')
							+ obj + '</option>';
					});
				}

				elInfosrcLang.html(resultStr);
				elInfosrcLang.change(function () {
					searchIndexers();
				});
			});
		}
	}

	function cleanseText(text, toDisplay) {
		return (!0 == toDisplay
			? text
			.replace(/["]/g, '&quot;')
			: text
			.replace(/(?:["]|&quot;)/g, '')
		);
	}

	var searchRequestXhr = null;

	function searchIndexers() {
		var elNameToSearch = $('#nameToSearch');

		if (!elNameToSearch.val().length)
			return;

		$('#more-results').hide();

		if (searchRequestXhr)
			searchRequestXhr.abort();

		var elTvDatabase = $('#provided-tvid'),
			elInfosrcLang = $('#infosrc-lang-select'),
			tvsrcName = elTvDatabase.find('option:selected').text(),
			tvSearchSrc = 0 < tvsrcName.length
				? ' <span class="boldest">' + elTvDatabase.find('option:selected').attr('data-name') + '</span>'
				: '';

		$('#search-results').empty().html('<img id="searchingAnim" src="' + sbRoot + '/images/loading32' + themeSpinner + '.gif" height="32" width="32">'
			+ ' searching '
			+ tvSearchSrc
			+ ' in <em>lang:' + elInfosrcLang.val() + '</em> <span' + htmlFlag(elInfosrcLang.val()).replace('.png)"', '.png);display:inline-block;width:16px;height:11px;margin:-2px 3px 0 0;vertical-align:middle"') + '></span>'
			+ ' for <span class="boldest">' + cleanseText(elNameToSearch.val(), !0) + '</span>'
			+ '...');

		searchRequestXhr = $.ajax({
			url: sbRoot + '/add-shows/search-tvinfo-for-showname',
			data: {
				'search_term': cleanseText(elNameToSearch.val(), !1),
				'lang': elInfosrcLang.val(),
				'search_tvid': elTvDatabase.val()
			},
			timeout: parseInt($('#indexer_timeout').val(), 10) * parseInt($('#indexer_count').val(), 2) * 1000 + 15000,
			dataType: 'json',
			error: function () {
				$('#search-results').empty().html('search timed out, try again in a few mins.');
			},
			success: function (data) {
				var resultStr = '', attrs = '', checked = !1, rowType, row = 0, srcState = '',
					resultItem, nBuffer = 0, nBufferSize = 20, nAll = 0;

				if (null === data.results || 0 === data.results.length) {
					resultStr += '<span class="boldest">Sorry, no results found. Try a different search.</span>';
				} else {
					var n = 0, result = {
						SrcName: n, isInDB: ++n, SrcId: ++n, SrcDBId: ++n, SrcSlug: ++n, SrcUrl: ++n, ShowID: ++n,
						Title: ++n, TitleHtml: ++n, Aired: ++n, AiredStr: ++n, Network: ++n, Genre: ++n,
						Language: ++n, LanguageCC: ++n, Overview: ++n, ImgUrl: ++n,
						RelSort: ++n, RelCombined : ++n, NewestAired: ++n, NewestCombined: ++n,
						OldestAired: ++n, OldestCombined: ++n, AzSort: ++n, AzCombined : ++n, ZaSort: ++n, ZaCombined: ++n,
						DirectIdMatch: ++n, RenameSuggest: ++n
					};
					$.each(data.results, function (index, item) {
						attrs = (!1 !== item[result.isInDB] ? ' disabled="disabled"' : (!0 === checked ? '' : ' checked'))
							+ ' data-rename-suggest="' + item[result.RenameSuggest] + '"';
						checked = (-1 === attrs.indexOf('checked')) ? checked : !0;
						rowType = (0 === row % 2 ? '' : ' alt');
						row++;

						var displayShowName = cleanseText(item[result.Title], !0), showstartdate = '';

						if (null !== item[result.Aired]) {
							var startDate = new Date(item[result.Aired]);
							var today = new Date();
							showstartdate = '&nbsp;<span class="stepone-result-date">('
								+ (startDate > today ? 'will debut' : 'started')
								+ ': ' + item[result.AiredStr] + ')</span>';
						}

						srcState = [
							null === item[result.SrcName] ? '' : item[result.SrcName],
							!1 === item[result.isInDB] ? '' : '<span class="exists-db"><a href="' + sbRoot + item[result.isInDB] + '" target="_blank">exists in db</a></span>']
							.join(' - ').replace(/(^[\s-]+|[\s-]+$)/, '');
						resultItem = '<div class="results-item' + ' ' + item[result.SrcSlug] + rowType + '" data-indb="' + (!1 === item[result.isInDB] ? '' : '1')
							+ '" data-sort-rel="' + item[result.RelSort] + '" data-sort-rel-combined="' + item[result.RelCombined]
							+ '" data-sort-newest="' + item[result.NewestAired] + '" data-sort-newest-combined="' + item[result.NewestCombined]
							+ '" data-sort-oldest="' + item[result.OldestAired] + '" data-sort-oldest-combined="' + item[result.OldestCombined]
							+ '" data-sort-az="' + item[result.AzSort] + '" data-sort-az-combined="' + item[result.AzCombined]
							+ '" data-sort-za="' + item[result.ZaSort] + '" data-sort-za-combined="' + item[result.ZaCombined] + '">'
							+ '<label><i></i>'
							+ '<input type="radio"'
							+ ' class="stepone-result-radio"'
							+ (!1 === item[result.isInDB]
								? ' title="Add show <span style=\'color: rgb(66, 139, 202)\'>' + displayShowName + '</span>"'
								: ' title="Show exists in DB,<br><span style=\'font-weight:700\'>selection not possible</span>"')
							+ ' name="which_series"'
							+ ' value="' + cleanseText([item[result.SrcDBId], item[result.SrcName], item[result.ShowID], item[result.Title]].join('|'), !0) + '"'
							+ attrs
							+ '></label>'
							+ '<a'
							+ ' class="stepone-result-title"'
							+ ' title="<div style=\'color: rgb(66, 139, 202)\'>' + cleanseText(item[result.TitleHtml], !0) + '</div>'
							+ (0 < item[result.LanguageCC].length && 'gb' !== item[result.LanguageCC]
								? '<div style=\'font-weight:bold;font-size:0.9em;color:#888\'><em>Language: <span' + htmlFlag(item[result.LanguageCC]).replace('.png)"', '.png);display:inline-block;width:16px;height:11px;margin:-2px 3px 0 0;vertical-align:middle"').replace(/"/g, "'") + '></span>'
								+ item[result.Language] + '</em></div>' : '')
							+ (0 < item[result.Genre].length ? '<div style=\'font-weight:bold\'>(<em>' + item[result.Genre] + '</em>)</div>' : '')
							+ (0 < item[result.Network].length ? '<div style=\'font-weight:bold;font-size:0.9em;color:#888\'><em>' + item[result.Network] + '</em></div>' : '')
							+ (item[result.ImgUrl] && '<img style=\'max-height:150px;float:right;margin-left:3px\' src=\'/' + item[result.ImgUrl] + '\'>' || '')
							+ (0 < item[result.Overview].length ? '<p style=\'margin:0 0 2px\'>' + item[result.Overview] + '</p>' : '')
							+ '<span style=\'float:right;clear:both\'>Click for more</span>'
							+ '"'
							+ ' href="' + anonURL + item[result.SrcUrl] + '"'
							+ ' onclick="window.open(this.href, \'_blank\'); return !1;"'
							+ '>' + (config.sortArticle ? displayShowName : displayShowName.replace(/^((?:A(?!\s+to)n?)|The)(\s)+(.*)/i, '$3$2<span class="article">($1)</span>')) + '</a>'
							+ showstartdate
							+ ('' === srcState ? ''
								: '&nbsp;<span class="stepone-result-db grey-text">' + '[' + srcState + ']' + '</span>')
							+ '</div>' + "\n";
						resultStr += resultItem;
						if(item[result.isInDB])
							nBufferSize++;
						if ((nBuffer < nBufferSize) || item[result.isInDB])
							nBuffer++;
						nAll++;
					});
				}
				var selAttr = 'selected="selected" ',
					selClass = 'selected-text',
					classAttrSel = 'class="' + selClass + '" ',
					defSortby = /^az/.test(config.resultsSortby) || /^za/.test(config.resultsSortby) || /^newest/.test(config.resultsSortby) || /^oldest/.test(config.resultsSortby) ? '': classAttrSel + selAttr;

				$('#search-results').addClass('collapsed').html(
					'<fieldset>' + "\n" + '<legend class="legendStep" style="margin-bottom: 15px">'
						+ '<span id="count"></span>'
						+ '<span style="float:right;height:32px;line-height:1"><span id="results-expander" style="margin-right:10px"></span>'
						+ '<select id="results-sortby" class="form-control form-control-inline input-sm">'
						+ '<optgroup label="Sort by">'
						+ '<option ' + (/^az/.test(config.resultsSortby) ? classAttrSel + selAttr : '') + 'value="az">A to Z</option>'
						+ '<option ' + (/^za/.test(config.resultsSortby) ? classAttrSel + selAttr : '') + 'value="za">Z to A</option>'
						+ '<option ' + (/^newest/.test(config.resultsSortby) ? classAttrSel + selAttr : '') + 'value="newest">Newest aired</option>'
						+ '<option ' + (/^oldest/.test(config.resultsSortby) ? classAttrSel + selAttr : '') + 'value="oldest">Oldest aired</option>'
						+ '<option ' + defSortby + 'value="rel">Relevancy</option>'
						+ '</optgroup><optgroup label="With...">'
						+ '<option ' + (!/notop$/.test(config.resultsSortby) ? classAttrSel : '') + 'value="ontop">Exists on top</option>'
						+ '<option ' + (/notop$/.test(config.resultsSortby) ? classAttrSel : '') + 'value="notop">Exists combined</option>'
						+ '<option ' + (!/nogroup/.test(config.resultsSortby) ? classAttrSel : '') + 'value="ingroup">Source grouped</option>'
						+ '<option ' + (/nogroup$/.test(config.resultsSortby) ? classAttrSel : '') + 'value="nogroup">Source combined</option>'
						+ '</optgroup></select></span>'
						+ '</legend>' + "\n"
						+ '<div id="holder">'
						+ resultStr
						+ '</div>'
						+ '</fieldset>'
					);
				function displayCount(){
					$('#count').html((nAll > nBufferSize ? nBuffer + ' of ' + nAll : (0 < nAll ? nAll : 'No'))
						+ ' result' + (1 === nAll ? '' : 's') + '...');
				}
				displayCount();
				var defaultExpander = '<i class="sgicon-arrowdown" style="margin-right:-8px; font-size:12px"></i>expand list'
				$('#results-expander').html((nAll > nBufferSize ? ' <span id="more-results" style="display:none;font-size: 0.7em">[<a href="#" style="text-decoration:none">' + defaultExpander + '</a>]</span>' : ''));
				$('#more-results').show();
				$('#more-results a').on('click', function(e, d) {
					e.preventDefault();
					var results$ = $('#search-results'), displayAction = '';
					if (results$.hasClass('collapsed')){
						displayAction = '<i class="sgicon-arrowup" style="margin-right:4px; font-size:12px"></i>collapse list';
						results$.removeClass('collapsed');
						$('#count').html('All ' + nAll + ' result' + (1 === nAll ? '' : 's'));
					} else {
						displayAction = defaultExpander;
						results$.addClass('collapsed');
						displayCount();
					}
					$('#more-results').find('a').html(displayAction);

					container$.isotope('updateSortData');
					updateResults();
					myform.loadsection(0);
				});

				var container$ = $('#holder'),
					sortbySelect$ = $('#results-sortby'),
					reOrder = (function(value){
						return ($('#results-sortby').find('option[value$="notop"]').hasClass(selClass)
							? (1000 > value ? value + 1000 : value)
							: (1000 > value ? value : value - 1000))}),
					fx = {filterData: function(){
						var results$ = $('#search-results');
						if (results$.hasClass('collapsed')){
							var itemElem = this, number = getAttr(itemElem, 'sort-' + results$.find('option:not([value$="top"],[value$="group"]).' + selClass).val());
							number -= number >= 1000 ? 1000 : 0;
							return (number < nBufferSize ) || !!getAttr(itemElem, 'indb');
						}
						return !0;
					}},
					getAttr = (function(itemElem, attr){
						var number = $(itemElem).attr('data-' + attr);
						return ('undefined' !== typeof(number)) && parseInt(number, 10) || 0;
					}),
					getData = (function(itemElem, sortby){
						var position = getAttr(itemElem, 'sort-' + sortby +
							($('#results-sortby').find('option[value$="ingroup"]').hasClass(selClass) ? '' : '-combined'));
						return (!!getAttr(itemElem, 'indb') ? reOrder(position) : position);
					});

				sortbySelect$.find('.' + selClass).each(function(){
					$(this).html('> ' + $(this).html());
				});

				function updateResults(){
					$('.results-item').removeClass('alt');
					container$.isotope({
						itemSelector: '.results-item',
						sortBy: sortbySelect$.find('option:not([value$="top"],[value$="group"]).' + selClass).val(),
						layoutMode: 'masonry',
						filter: fx['filterData'],
						getSortData: {
							az: function(itemElem){ return getData(itemElem, 'az'); },
							za: function(itemElem){ return getData(itemElem, 'za'); },
							newest: function(itemElem){ return getData(itemElem, 'newest'); },
							oldest: function(itemElem){ return getData(itemElem, 'oldest'); },
							rel: function(itemElem){ return getData(itemElem, 'rel'); }
						}
					}).on('arrangeComplete', function(event, items){
						$(items).each(function(i, item){
							if (1 === i % 2){
								$(item.element).addClass('alt');
							}
						});
					});
				}
				container$.isotope();  // must init first
				updateResults();

				sortbySelect$.on('change', function(){
					var selectedSort = String($(this).val()), sortby = selectedSort, curSortby$, curSel$, newSel$;
					curSortby$ = $(this).find('option:not([value$="top"],[value$="group"])');
					if (/(top|group)$/.test(selectedSort)){
						sortby = curSortby$.filter('.' + selClass).val();
						curSortby$ = $(this).find('option[value$="'
							+ (-1 !== selectedSort.indexOf('top') ? 'top' : 'group') + '"]');
					}
					curSel$ = curSortby$.filter('.' + selClass);
					curSel$.html(curSel$.html().replace(/(?:>|&gt;)\s/ , '')).removeClass(selClass);

					newSel$ = $(this).find('option[value$="' + selectedSort + '"]');
					newSel$.html('&gt; ' + newSel$.html()).addClass(selClass);

					$('.results-item[data-indb="1"]').each(function(){
						$(this).attr(sortby, reOrder(parseInt($(this).attr(sortby), 10)));
					});
					container$.isotope('updateSortData');
					updateResults();

					config.resultsSortby = sortby +
						($(this).find('option[value$="notop"]').hasClass(selClass) ? ' notop' : '') +
						($(this).find('option[value$="nogroup"]').hasClass(selClass) ? ' nogroup' : '');
					$.get(sbRoot + '/config/general/save-result-prefs', {ui_results_sortby: selectedSort});
				});

				updateSampleText();
				myform.loadsection(0);
				$('.stepone-result-radio, .stepone-result-title').each(addQTip);
			}
		});
	}

	function submitSearch(searchFor){
		$('#nameToSearch').val(searchFor);
		!!searchFor && $('#searchName').click();
		return !1;
	}

	$('#try-0').on('click', function(){return submitSearch('');});
	$('#try-1').on('click', function(){return submitSearch(config.searchTests[1]);});
	$('span[id^="try-"]').each(function(i, el){
		var match = $(el).attr('id').match(/try-(\d+)(-.*)$/i);
		if (!!match){
			$('#' + match[0]).on('click', function(){
				var match = $(this).attr('id').match(/try-(\d+)(-.*)$/i),
					num = parseInt(match[1], 10),
					kind = match[2],
					nextEl$ = $('span[id$="'+ (num + 1) + kind + '"]');

				$(this).closest('span[id^="try-"]').addClass('hide');
				(nextEl$.length ? nextEl$ : $('span[id$="'+ kind + '"]:first')).removeClass('hide');
				return submitSearch(config.searchTests[num]);
			});
		}
	});

	var elNameToSearch = $('#nameToSearch'),
		elSearchName = $('#searchName');

	elSearchName.click(function () { searchIndexers(); });

	if (elNameToSearch.length && elNameToSearch.val().length) {
		elSearchName.click();
	}

	$('#addShowButton, #cancelShowButton').click(function () {
		if (/cancel/.test(this.id)){
			$('input[name=cancel_form]').val('1');
		} else {
			// if they haven't picked a show don't let them submit
			if (!$('input:radio[name="which_series"]:checked').val()
				&& !$('input:hidden[name="which_series"]').val().length) {
					alert('You must choose a show to continue');
					return !1;
			}
			generateAniGroupList();
		}
		$('#addShowForm').submit();
	});

	$('#skipShowButton').click(function () {
		$('#skipShow').val('1');
		$('#addShowForm').submit();
	});

	$('#quality-preset').change(function () {
		myform.loadsection(2);
	});

	/***********************************************
	* jQuery Form to Form Wizard- (c) Dynamic Drive (www.dynamicdrive.com)
	* This notice MUST stay intact for legal use
	* Visit http://www.dynamicdrive.com/ for this script and 100s more.
	***********************************************/

	var myform = $.SickGear.myform = new FormToWizard({
		fieldsetborderwidth: 0,
		formid: 'addShowForm',
		revealfx: ['slide', 500],
		oninit: function () {
			populateLangSelect();
			updateSampleText();
			if ($('input:hidden[name="which_series"]').length && $('#fullShowPath').length) {
				goToStep(3);
			}
		}
	});

	function goToStep(num) {
		$('.step').each(function () {
			if ($.data(this, 'section') + 1 == num) {
				$(this).click();
			}
		});
	}

	elNameToSearch.focus();

	function updateSampleText() {
		if (0 === $('#displayText').length) {
			$('#cancelShowButton').attr('disabled', !1);
			$('#addShowButton').attr('disabled', 0 === $('#holder').find('.results-item').length);
			return;
		}
		// if something's selected then we have some behavior to figure out

		var showName = '',
			sep_char,
			elRadio = $('input:radio[name="which_series"]:checked'),
			elInput = $('input:hidden[name="which_series"]'),
			elScene = $('#scene'),
			elRootDirs = $('#rootDirs'),
			elFullShowPath = $('#fullShowPath'),
			idxWhichShowID = 2, idxWhichTitle = 3;

		if (!!elRadio.length) {
			$('#rename-suggest').val(elRadio.attr('data-rename-suggest'));
		}

		if (!!config.folder.length) {
			showName = config.folder;
		}
		// if they've picked a radio button then use that
		else if (elRadio.length) {
			showName = elRadio.val().split('|')[idxWhichTitle];
			elScene[0].checked = 0 <= showSceneMaps.indexOf(parseInt(elRadio.val().split('|')[idxWhichShowID], 10));
			$('#scene-maps-found').css('display', elScene.is(':checked') ? 'block' : 'None');
		}
		// if we provided a show in the hidden field, use that
		else if (elInput.length && elInput.val().length) {
			showName = $('#provided-show-name').val();
		}
		updateAniGrouplist(showName);
		var sample_text = '<p>Adding show <span class="show-name">' + cleanseText(showName, !0) + '</span>'
			+ (!showName.length ? 'into<br>' : '<br>into' + (!config.folder.length ? '' : ' user location'))
			+ ' <span class="show-dest">';

		// if we have a root dir selected, figure out the path
		if (elRootDirs.find('option:selected').length) {
			var root_dir_text = elRootDirs.find('option:selected').val();
			if (root_dir_text.indexOf('/') >= 0) {
				sep_char = '/';
			} else if (root_dir_text.indexOf('\\') >= 0) {
				sep_char = '\\';
			} else {
				sep_char = '';
			}

			if (root_dir_text.substr(sample_text.length - 1) != sep_char) {
				root_dir_text += sep_char;
			}
			root_dir_text += '<i>||</i>' + sep_char;

			sample_text += root_dir_text;
		} else if (elFullShowPath.length && elFullShowPath.val().length) {
			sample_text += elFullShowPath.val();
		} else {
			sample_text += 'unknown dir.';
		}

		sample_text += '</span></p>';

		// if we have a show name then sanitize and use it for the dir name
		if (showName.length) {
			$.get(sbRoot + '/add-shows/generate-show-dir-name', {show_name: cleanseText(showName, !1)}, function (data) {
				$('#displayText').html(sample_text.replace('||', data));
			});
		// if not then it's unknown
		} else {
			$('#displayText').html(sample_text.replace('||', '??'));
		}

		// also toggle the add show button
		if ((elRootDirs.find('option:selected').length || (elFullShowPath.length && elFullShowPath.val().length)) &&
			(elRadio.length) || (elInput.length && elInput.val().length)) {
			$('#addShowButton').attr('disabled', !1);
		} else {
			$('#addShowButton').attr('disabled', !0);
		}
	}

	$('#rootDirText').change(updateSampleText);

	$('#search-results').on('click', '.stepone-result-radio', updateSampleText);

	elNameToSearch.keydown(function (event) {
		if (event.keyCode == 13) {
			event.preventDefault();
			elSearchName.click();
		}
	});

	var addQTip = (function() {
		$(this).css('cursor', 'help');
		$(this).qtip({
			show: {
				solo: !0
			},
			position: {
				viewport: $(window),
				my: 'left center',
				adjust: {
					y: -10,
					x: 2
				}
			},
			style: {
				tip: {
					corner: !0,
					method: 'polygon'
				},
				classes: 'qtip-rounded qtip-bootstrap qtip-shadow ui-tooltip-sb'
			}
		});
	});

	$('#anime').change (function () {
		updateSampleText();
		myform.loadsection(2);
	});

	function add_option_to_pool (text) {
		var groupvalue = '', groupview = text,
			option = $('<option>'),
			match = /^(.*?)#<3SG#(.*)$/m.exec(text);

		if (match != null) {
			groupvalue = match[1];
			groupview = groupvalue + match[2];
		}
		option.val(groupvalue);
		option.html(groupview);
		option.appendTo('#pool');
	}

	function updateAniGrouplist (show_name) {

		$('#allow, #block, #pool').children().remove();

		if ($('#anime').prop('checked')) {
			$('#anigrouplists').show();
			if (show_name) {
				$.getJSON(sbRoot + '/home/fetch-releasegroups', {'show_name': cleanseText(show_name, !1)}, function (data) {
					if ('success' == data['result']) {
						var groups = [];
						$.each(data.groups, function (i, group) {
							if ('' != group.name) {
								groups.push(group.name + '#<3SG#' + ('' === group.rating ? '' : ' (' + group.rating + ') ') + group.range)
							}
						});
						if (0 < groups.length) {
							groups.sort();
							$.each(groups, function (i, text) {
								add_option_to_pool(text);
							});
						} else {
							add_option_to_pool('No groups returned from AniDB');
						}
					} else if ('fail' == data['result']) {
						if ('connect' == data['resp']) {
							add_option_to_pool('Fail:AniDB connect. Restart sg else check debug log');
						} else if ('init' == data['resp']) {
							add_option_to_pool('Did not initialise AniDB. Check debug log if reqd.');
						}
					}
			 	});
			}
		} else {
			$('#anigrouplists').hide();
		}
	}
});
