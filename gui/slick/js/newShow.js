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
			.replace(/Pokémon/, 'Pokemon')
			.replace(/(?:["]|&quot;)/g, '')
		);
	}

	var searchRequestXhr = null;

	function searchIndexers() {
		var elNameToSearch = $('#nameToSearch');

		if (!elNameToSearch.val().length)
			return;

		if (searchRequestXhr)
			searchRequestXhr.abort();

		var elTvDatabase = $('#providedIndexer'),
			elIndexerLang = $('#indexerLangSelect');

		$('#searchResults').empty().html('<img id="searchingAnim" src="' + sbRoot + '/images/loading32' + themeSpinner + '.gif" height="32" width="32" />'
			+ ' searching <span class="boldest">' + cleanseText(elNameToSearch.val(), !0) + '</span>'
			+ ' on ' + elTvDatabase.find('option:selected').text() + ' in ' + elIndexerLang.val()
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
				$('#searchResults').empty().html('search timed out, try again or try another database');
			},
			success: function (data) {
				var resultStr = '', checked = '', rowType, row = 0;

				if (0 === data.results.length) {
					resultStr += '<span class="boldest">Sorry, no results found. Try a different search.</span>';
				} else {
					var idxSrcDB = 0, idxSrcDBId = 1, idxSrcUrl = 2, idxShowID = 3, idxTitle = 4, idxTitleHtml = 5,
						idxDate = 6, idxNetwork = 7, idxGenres = 8, idxOverview = 9;
					$.each(data.results, function (index, obj) {
						checked = (0 == row ? ' checked' : '');
						rowType = (0 == row % 2 ? '' : ' class="alt"');
						row++;

						var display_show_name = cleanseText(obj[idxTitle], !0), showstartdate = '';

						if (null !== obj[idxDate]) {
							var startDate = new Date(obj[idxDate]);
							var today = new Date();
							showstartdate = '&nbsp;<span class="stepone-result-date">('
								+ (startDate > today ? 'will debut' : 'started')
								+ ': ' + obj[idxDate] + ')</span>';
						}
						resultStr += '<div' + rowType + '>'
							+ '<input id="whichSeries" type="radio"'
							+ ' class="stepone-result-radio"'
							+ ' title="Add show <span style=\'color: rgb(66, 139, 202)\'>' + display_show_name + '</span>"'
							+ ' name="whichSeries"'
							+ ' value="' + cleanseText([obj[idxSrcDBId], obj[idxSrcDB], obj[idxShowID], obj[idxTitle]].join('|'), !0) + '"'
							+ checked
							+ ' />'
							+ '<a'
							+ ' class="stepone-result-title"'
							+ ' title="<div style=\'color: rgb(66, 139, 202)\'>' + cleanseText(obj[idxTitleHtml], !0) + '</div>'
							+ (0 < obj[idxGenres].length ? '<div style=\'font-weight:bold\'>(<em>' + obj[idxGenres] + '</em>)</div>' : '')
							+ (0 < obj[idxNetwork].length ? '<div style=\'font-weight:bold;font-size:0.9em;color:#888\'><em>' + obj[idxNetwork] + '</em></div>' : '')
							+ (0 < obj[idxOverview].length ? '<p style=\'margin:0 0 2px\'>' + obj[idxOverview] + '</p>' : '')
							+ '<span style=\'float:right\'>Click for more</span>'
							+ '"'
							+ ' href="' + anonURL + obj[idxSrcUrl] + obj[idxShowID] + ((data.langid && '' != data.langid) ? '&lid=' + data.langid : '') + '"'
							+ ' onclick="window.open(this.href, \'_blank\'); return false;"'
							+ '>' + display_show_name + '</a>'
							+ showstartdate
							+ (null == obj[idxSrcDB] ? ''
								: '&nbsp;<span class="stepone-result-db grey-text">' + '[' + obj[idxSrcDB] + ']' + '</span>')
							+ '</div>' + "\n";
					});
				}
				$('#searchResults').html(
					'<fieldset>' + "\n" + '<legend class="legendStep" style="margin-bottom: 15px">'
						+ (0 < row ? row : 'No')
						+ ' search result' + (1 == row ? '' : 's') + '...</legend>' + "\n"
						+ resultStr
						+ '</fieldset>'
					);
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

	$('#addShowButton').click(function () {
		// if they haven't picked a show don't let them submit
		if (!$('input:radio[name="whichSeries"]:checked').val()
			&& !$('input:hidden[name="whichSeries"]').val().length) {
				alert('You must choose a show to continue');
				return false;
		}
		generate_bwlist();
		$('#addShowForm').submit();
	});

	$('#skipShowButton').click(function () {
		$('#skipShow').val('1');
		$('#addShowForm').submit();
	});

	$('#qualityPreset').change(function () {
		myform.loadsection(2);
	});

	/***********************************************
	* jQuery Form to Form Wizard- (c) Dynamic Drive (www.dynamicdrive.com)
	* This notice MUST stay intact for legal use
	* Visit http://www.dynamicdrive.com/ for this script and 100s more.
	***********************************************/

	var myform = new FormToWizard({
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
			$('#scene-maps-found').css('display', elScene.is(':checked') ? 'inline' : 'None');
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
			$('#addShowButton').attr('disabled', false);
		} else {
			$('#addShowButton').attr('disabled', true);
		}
	}

	$('#rootDirText').change(updateSampleText);

	$('#searchResults').on('click', '.stepone-result-radio', updateSampleText);

	elNameToSearch.keyup(function (event) {
		if (event.keyCode == 13) {
			elSearchName.click();
		}
	});

	var addQTip = (function() {
		$(this).css('cursor', 'help');
		$(this).qtip({
			show: {
				solo: true
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
					corner: true,
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
		option.attr('value', groupvalue);
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
