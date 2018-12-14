/** @namespace config.sortArticle */
/** @namespace config.resultsSortby */
$(document).ready(function () {

	function populateLangSelect() {
		if (!$('#nameToSearch').length)
			return;

		if (1 >= $('#indexerLangSelect').find('option').length) {

			$.getJSON(sbRoot + '/home/addShows/getIndexerLanguages', {}, function (data) {

				var resultStr = '',
					selected = ' selected="selected"',
					elIndexerLang = $('#indexerLangSelect');

				if (0 === data.results.length) {
					resultStr = '<option value="en"' + selected + '>en</option>';
				} else {
					$.each(data.results, function (index, obj) {
						resultStr += '<option value="' + obj + '"'
							+ ('' == resultStr ? selected : '')
							+ '>' + obj + '</option>';
					});
				}

				elIndexerLang.html(resultStr);
				elIndexerLang.change(function () {
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

		var elTvDatabase = $('#providedIndexer'),
			elIndexerLang = $('#indexerLangSelect'),
			tvsrcName = elTvDatabase.find('option:selected').text(),
			tvSearchSrc = 0 < tvsrcName.length ? ' on ' + tvsrcName : '';

		$('#search-results').empty().html('<img id="searchingAnim" src="' + sbRoot + '/images/loading32' + themeSpinner + '.gif" height="32" width="32" />'
			+ ' searching <span class="boldest">' + cleanseText(elNameToSearch.val(), !0) + '</span>'
			+ tvSearchSrc + ' in ' + elIndexerLang.val()
			+ '...');

		searchRequestXhr = $.ajax({
			url: sbRoot + '/home/addShows/searchIndexersForShowName',
			data: {
				'search_term': cleanseText(elNameToSearch.val(), !1),
				'lang': elIndexerLang.val(),
				'indexer': elTvDatabase.val()
			},
			timeout: parseInt($('#indexer_timeout').val(), 10) * parseInt($('#indexer_count').val(), 2) * 1000 + 15000,
			dataType: 'json',
			error: function () {
				$('#search-results').empty().html('search timed out, try again in a few mins.');
			},
			success: function (data) {
				var resultStr = '', attrs = '', checked = !1, rowType, row = 0, srcState = '',
					resultItem, resultStrBuffer = '', nBufferSize = 20, nBuffer = 0, nAll = 0;

				if (null === data.results || 0 === data.results.length) {
					resultStr += '<span class="boldest">Sorry, no results found. Try a different search.</span>';
				} else {
					var result = {
						SrcName: 0, isInDB: 1, SrcId: 2, SrcDBId: 3, SrcUrl: 4, ShowID: 5, Title: 6, TitleHtml: 7,
						Aired: 8, Network: 9, Genre: 10, Overview: 11, RelSort: 12, NewestAired: 13, OldestAired: 14, AzSort: 15 , ZaSort: 16, ImgUrl: 17
					};
					$.each(data.results, function (index, item) {
						attrs = (!1 !== item[result.isInDB] ? ' disabled="disabled"' : (!0 === checked ? '' : ' checked'));
						checked = (' checked' === attrs) ? !0 : checked;
						rowType = (0 == row % 2 ? '' : ' alt');
						row++;

						var displayShowName = cleanseText(item[result.Title], !0), showstartdate = '';

						if (null !== item[result.Aired]) {
							var startDate = new Date(item[result.Aired]);
							var today = new Date();
							showstartdate = '&nbsp;<span class="stepone-result-date">('
								+ (startDate > today ? 'will debut' : 'started')
								+ ': ' + item[result.Aired] + ')</span>';
						}

						srcState = [
							null === item[result.SrcName] ? '' : item[result.SrcName],
							!1 === item[result.isInDB] ? '' : '<span class="exists-db"><a href="' + sbRoot + item[result.isInDB] + '" target="_blank">exists in db</a></span>']
							.join(' - ').replace(/(^[\s-]+|[\s-]+$)/, '');
						resultItem = '<div class="results-item' + rowType + '" data-indb="' +  (!1 === item[result.isInDB] ? '' : '1') + '" data-sort-rel="' + item[result.RelSort] + '" data-sort-newest="' + item[result.NewestAired] + '" data-sort-oldest="' + item[result.OldestAired] + '" data-sort-az="' + item[result.AzSort] + '" data-sort-za="' + item[result.ZaSort] + '">'
							+ '<input id="whichSeries" type="radio"'
							+ ' class="stepone-result-radio"'
							+ (!1 === item[result.isInDB]
								? ' title="Add show <span style=\'color: rgb(66, 139, 202)\'>' + displayShowName + '</span>"'
								: ' title="Show exists in DB,<br><span style=\'font-weight:700\'>selection not possible</span>"')
							+ ' name="whichSeries"'
							+ ' value="' + cleanseText([item[result.SrcDBId], item[result.SrcName], item[result.ShowID], item[result.Title]].join('|'), !0) + '"'
							+ attrs
							+ ' />'
							+ '<a'
							+ ' class="stepone-result-title"'
							+ ' title="<div style=\'color: rgb(66, 139, 202)\'>' + cleanseText(item[result.TitleHtml], !0) + '</div>'
							+ (0 < item[result.Genre].length ? '<div style=\'font-weight:bold\'>(<em>' + item[result.Genre] + '</em>)</div>' : '')
							+ (0 < item[result.Network].length ? '<div style=\'font-weight:bold;font-size:0.9em;color:#888\'><em>' + item[result.Network] + '</em></div>' : '')
							+ '<img style=\'max-height:150px;float:right;margin-left:3px\' src=\'/' + item[result.ImgUrl] + '\'>'
							+ (0 < item[result.Overview].length ? '<p style=\'margin:0 0 2px\'>' + item[result.Overview] + '</p>' : '')
							+ '<span style=\'float:right;clear:both\'>Click for more</span>'
							+ '"'
							+ ' href="' + anonURL + item[result.SrcUrl] + ((data.langid && '' != data.langid) ? '&lid=' + data.langid : '') + '"'
							+ ' onclick="window.open(this.href, \'_blank\'); return !1;"'
							+ '>' + (config.sortArticle ? displayShowName : displayShowName.replace(/^((?:A(?!\s+to)n?)|The)(\s)+(.*)/i, '$3$2<span class="article">($1)</span>')) + '</a>'
							+ showstartdate
							+ ('' === srcState ? ''
								: '&nbsp;<span class="stepone-result-db grey-text">' + '[' + srcState + ']' + '</span>')
							+ '</div>' + "\n";
						if (nBuffer < nBufferSize || item[result.isInDB]) {
							resultStr += resultItem;
							if (!1 === item[result.isInDB])
								nBuffer++;
						} else {
							resultStrBuffer += resultItem;
						}
						nAll++;
					});
				}
				var selAttr = 'selected="selected" ',
					selClass = 'selected-text',
					classAttrSel = 'class="' + selClass + '" ',
					useBuffer = nBufferSize < nAll,
					defSortby = /^az/.test(config.resultsSortby) || /^za/.test(config.resultsSortby) || /^newest/.test(config.resultsSortby) || /^oldest/.test(config.resultsSortby) ? '': classAttrSel + selAttr;

				$('#search-results').html(
					'<fieldset>' + "\n" + '<legend class="legendStep" style="margin-bottom: 15px">'
						+ '<span id="count"></span>'
						+ '<span style="float:right;height:32px;line-height:1">'
						+ '<select id="results-sortby" class="form-control form-control-inline input-sm">'
						+ '<optgroup label="Sort by">'
						+ '<option ' + (/^az/.test(config.resultsSortby) ? classAttrSel + selAttr : '') + 'value="az">A to Z</option>'
						+ '<option ' + (/^za/.test(config.resultsSortby) ? classAttrSel + selAttr : '') + 'value="za">Z to A</option>'
						+ '<option ' + (/^newest/.test(config.resultsSortby) ? classAttrSel + selAttr : '') + 'value="newest">Newest aired</option>'
						+ '<option ' + (/^oldest/.test(config.resultsSortby) ? classAttrSel + selAttr : '') + 'value="oldest">Oldest aired</option>'
						+ '<option ' + defSortby + 'value="rel">Relevancy</option>'
						+ '</optgroup><optgroup label="With...">'
						+ '<option ' + (!/notop$/.test(config.resultsSortby) ? classAttrSel : '') + 'value="ontop">Exists on top</option>'
						+ '<option ' + (/notop$/.test(config.resultsSortby) ? classAttrSel : '') + 'value="notop">Exists in mix</option>'
						+ '</optgroup></select></span>'
						+ '</legend>' + "\n"
						+ '<div id="holder">'
						+ resultStr
						+ '</div>'
						+ '</fieldset>'
					);

				if (useBuffer) {
					$('#search-results-buffer').html(resultStrBuffer);
					$('#more-results').show();
					$('#more-results a').on('click', function(e, d) {
						e.preventDefault();
						$('#more-results').hide();
						$('#search-results #count').text(nAll + ' search result' + (1 === nAll ? '' : 's') + '...');
						$('#search-results-buffer .results-item').appendTo('#holder');
						container$.isotope( 'reloadItems' ).isotope(
							{sortBy: $('#results-sortby').find('option:not([value$="top"]).selected-text').val()});
						myform.loadsection(0);
					});
					$('#search-results #count').text((nBuffer + ' / ' + nAll)
						+ ' search result' + (1 === nBuffer ? '' : 's') + '...');
				} else {
					$('#search-results #count').text((0 < nBuffer ? nBuffer + (useBuffer ? ' / ' + nAll : '') : 'No')
						+ ' search result' + (1 === nAll ? '' : 's') + '...');
				}

				var container$ = $('#holder'),
					sortbySelect$ = $('#results-sortby'),
					reOrder = (function(value){
						return ($('#results-sortby').find('option[value$="notop"]').hasClass(selClass)
							? (1000 > value ? value + 1000 : value)
							: (1000 > value ? value : value - 1000))}),
					getData = (function(itemElem, sortby){
						var position = parseInt($(itemElem).attr('data-sort-' + sortby));
						return (!$(itemElem).attr('data-indb')) ? position : reOrder(position);
					});

				sortbySelect$.find('.' + selClass).each(function(){
					$(this).html('> ' + $(this).html());
				});

				container$.isotope({
					itemSelector: '.results-item',
					sortBy: sortbySelect$.find('option:not([value$="top"]).' + selClass).val(),
					layoutMode: 'masonry',
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

				sortbySelect$.on('change', function(){
					var selectedSort = String($(this).val()), sortby = selectedSort, curSortby$, curSel$, newSel$;

					curSortby$ = $(this).find('option:not([value$="top"])');
					if (/top$/.test(selectedSort)){
						sortby = curSortby$.filter('.' + selClass).val();
						curSortby$ = $(this).find('option[value$="top"]');
					}
					curSel$ = curSortby$.filter('.' + selClass);
					curSel$.html(curSel$.html().replace(/(?:>|&gt;)\s/ , '')).removeClass(selClass);

					newSel$ = $(this).find('option[value$="' + selectedSort + '"]');
					newSel$.html('&gt; ' + newSel$.html()).addClass(selClass);

					$('.results-item[data-indb="1"]').each(function(){
						$(this).attr(sortby, reOrder(parseInt($(this).attr(sortby), 10)));
					});
					$('.results-item').removeClass('alt');
					container$.isotope('updateSortData').isotope({sortBy: sortby});

					config.resultsSortby = sortby + ($(this).find('option[value$="notop"]').hasClass(selClass) ? ' notop' : '');
					$.get(sbRoot + '/config/general/saveResultPrefs', {ui_results_sortby: selectedSort});
				});

				updateSampleText();
				myform.loadsection(0);
				$('.stepone-result-radio, .stepone-result-title').each(addQTip);
			}
		});
	}

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
			if (!$('input:radio[name="whichSeries"]:checked').val()
				&& !$('input:hidden[name="whichSeries"]').val().length) {
					alert('You must choose a show to continue');
					return !1;
			}
			generate_bwlist();
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
			if ($('input:hidden[name="whichSeries"]').length && $('#fullShowPath').length) {
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

		var show_name = '',
			sep_char,
			elRadio = $('input:radio[name="whichSeries"]:checked'),
			elInput = $('input:hidden[name="whichSeries"]'),
			elScene = $('#scene'),
			elRootDirs = $('#rootDirs'),
			elFullShowPath = $('#fullShowPath'),
			idxWhichShowID = 2, idxWhichTitle = 3;

		// if they've picked a radio button then use that
		if (elRadio.length) {
			show_name = elRadio.val().split('|')[idxWhichTitle];
			elScene[0].checked = 0 <= show_scene_maps.indexOf(parseInt(elRadio.val().split('|')[idxWhichShowID], 10));
			$('#scene-maps-found').css('display', elScene.is(':checked') ? 'block' : 'None');
		}
		// if we provided a show in the hidden field, use that
		else if (elInput.length && elInput.val().length) {
			show_name = $('#providedName').val();
		}
		update_bwlist(show_name);
		var sample_text = '<p>Adding show <span class="show-name">' + cleanseText(show_name, !0) + '</span>'
			+ ('' == show_name ? 'into<br />' : '<br />into')
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
		if (show_name.length) {
			$.get(sbRoot + '/home/addShows/sanitizeFileName', {name: cleanseText(show_name, !1)}, function (data) {
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

	function update_bwlist (show_name) {

		$('#black, #white, #pool').children().remove();

		if ($('#anime').prop('checked')) {
			$('#blackwhitelist').show();
			if (show_name) {
				$.getJSON(sbRoot + '/home/fetch_releasegroups', {'show_name': cleanseText(show_name, !1)}, function (data) {
					if ('success' == data['result']) {
						var groups = [];
						$.each(data.groups, function (i, group) {
							if ('' != group.name) {
								groups.push(group.name + '#<3SG#' + ' (' + group.rating + ') ' + group.range)
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
			$('#blackwhitelist').hide();
		}
	}
});
