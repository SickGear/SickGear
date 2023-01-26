/** @namespace $.SickGear.Root */
/** @namespace config.showLang */
/** @namespace config.showIsAnime */
/** @namespace config.expandIds */
/*globals $, config, sbRoot, generateAniGroupList*/

$(document).ready(function () {

	$('#location').fileBrowser({title: 'Select Show Location'});
	String.prototype.padLeft = function padLeft(length, leadingChar) {
		if (undefined === leadingChar) leadingChar = '0';
		return this.length < length ? (leadingChar + this).padLeft(length, leadingChar) : this;
	};

	function htmlFlag(lang) {
		return ' class="flag" style="background-image:url(' + $.SickGear.Root + '/images/flags/' + lang + '.png)"'
	}

	function uriFlag(lang) {
		return $.SickGear.Root + '/images/flags/' + lang + '.png'
	}

	$.getJSON($.SickGear.Root + '/add-shows/get-infosrc-languages', {}, function (data) {
		var htmlText = '', currentLangAdded = '',
			selected = ' selected="selected"', htmlSelected = '',
			elInfosrcLang = $('#infosrc-lang-select'),
			useSelect2 = 0 < data.results_ext.length, populateItem;

		if (!data.results.length && !data.results_ext.length) {
			htmlText = '<option value="' + config.showLang + '"' + selected + htmlFlag(config.showLang) + '>'
				+ config.showLang + '</option>';
		} else {
			currentLangAdded = !1;
			if (useSelect2){
				// 3 letter abbr object
				$.each(data.results_ext, function (index, obj) {

					htmlSelected = '';
					if (obj.std_abbr === config.showLang) {
						currentLangAdded = !0;
						htmlSelected = selected;
					}

					htmlText += '<option style="padding-left:25px" value="' + obj.std_abbr + '"'
								+ ' data-abbr="' + obj.abbr + '"'
								+ ' data-img="' + uriFlag(obj.std_abbr) + '"'
								+ ' data-title="' + obj.en + ' (' + obj.orig_abbr + '/' + obj.std_abbr + '/' + obj.abbr + ')' +  '"'
								+ (!!htmlSelected
									? htmlSelected + '>&gt; '
									: '>')
								+ obj.native
								+ '</option>';
				});
			} else {
				// legacy 2 letter abbr list
				$.each(data.results, function (index, strLang) {

					htmlSelected = '';
					if (strLang === config.showLang) {
						currentLangAdded = !0;
						htmlSelected = selected;
					}

					htmlText += '<option value="' + strLang + '"' + htmlSelected + htmlFlag(strLang) + '>'
						+ strLang + '</option>';
				});
			}
			if (!currentLangAdded)
				htmlText += '<option value="' + config.showLang + '" ' + selected + '>' + config.showLang + '</option>';
		}

		elInfosrcLang.html(htmlText);

		if (useSelect2) {
			populateItem = function (data) {
				if (!!data.element)
					return $('<span class="flag"'
						+ ' style="background-image:url(' + $(data.element).data('img') + ')"'
						+ ' title="' + $(data.element).data('title') + '">'
						+ data.text
						+ '</span>');
				return data.text;
			}
			elInfosrcLang.select2({templateResult: populateItem, templateSelection: populateItem, width: 162});
		}
	});

	function getExceptions() {
		var allExceptions = [];

		$('#exceptions_list').find('option').each(function () {
			allExceptions.push($(this).val());
		});

		return allExceptions
	}

	function okExit(action){
		return ('the-main' === ($('input[name="set-main"]:checked').attr('id')  || 'the-main')
			|| confirm('A "set main" change is pending\n\n' + action + ' without saving changes?'))
	}

	$('a:contains("Cancel Edit")').on('click', function () {
		if (!okExit('Cancel')) return !1;
	});

	$('#submit').on('click', function () {
		if (!okExit('Update')) return !1;
		$('#exceptions_list').val(getExceptions());
		if (config.showIsAnime)
			generateAniGroupList();
	});

	$('#addSceneName').on('click', function () {
		var elSceneName = $('#SceneName'), elSceneNameSeason = $('#SceneNameSeason'),
			sceneEx = elSceneName.val(), sceneExSeason = elSceneNameSeason.val();

		elSceneName.val('');
		elSceneNameSeason.val('');

		if (-1 < $.inArray(sceneExSeason + '|' + sceneEx, getExceptions()) || ('' === sceneEx))
			return;

		$('#SceneException').fadeIn('fast', 'linear');

		var option = $('<option>');
		if (null === sceneExSeason)
			sceneExSeason = '-1';
		option.val(sceneExSeason + '|' + sceneEx);
		option.html(('S' + ('-1' === sceneExSeason ? '*' : sceneExSeason.padLeft(2)) + ': ') + sceneEx);

		return option.appendTo($('#exceptions_list'));
	});

	$('#removeSceneName').on('click', function () {
		$('#exceptions_list').find('option:selected').remove();

		$(this).toggle_SceneException();
	});

	/** @namespace data.text */
	$('#export-alts').on('click', function (e) {
		e.preventDefault();

		var that$ = $(this);
		that$.attr('disabled', 'disabled');
		$.getJSON(sbRoot + '/config/general/export-alt', {'tvid_prodid': $('#tvid_prodid').val()},
			function (data) {
				if (data.text) {
					$.confirm({
						'title'		: 'Export names/numbers',
						'message'	: 'Copy/paste the following for export...' +
							'<div><pre style="width:95%;margin:0 auto;max-height:250px">' + data.text + '</pre></div>',
						'buttons'	: {
							'close'	: {
								'class'	: 'green',
								'action': function(){}	// Nothing to do in this case. You can as well omit the action property.
							}
						}
					});
				}
				that$.removeAttr('disabled');
		});
	});

	$.fn.toggle_SceneException = function () {
		var elSceneException = $('#SceneException');

		if (0 === getExceptions().length)
			elSceneException.fadeOut('fast', 'linear');
		else
			elSceneException.fadeIn('fast', 'linear');
	};

	$(this).toggle_SceneException();

	var elABD = $('#air_by_date'), elScene = $('#scene'), elSports = $('#sports'), elAnime = $('#anime'),
		elIdMap = $('#idmapping');

	function uncheck(el) {el.prop('checked', !1)}
	function checked(el) {return el.prop('checked')}

	function isAnime() {
		uncheck(elABD); uncheck(elSports);
		if (config.showIsAnime) { $('#anigrouplists').fadeIn('fast', 'linear'); } return !0; }
	function isScene() { uncheck(elABD); uncheck(elSports); }
	function isABD() { uncheck(elAnime); uncheck(elScene); $('#anigrouplists, #anime-options').fadeOut('fast', 'linear'); }
	function isSports() { uncheck(elAnime); uncheck(elScene); $('#anigrouplists, #anime-options').fadeOut('fast', 'linear'); }

	if (checked(elAnime)) { isAnime(); }
	if (checked(elScene)) { isScene(); }
	if (checked(elABD)) { isABD(); }
	if (checked(elSports)) { isSports(); }

	elAnime.on('click', function() {
		if (checked(elAnime))
			isAnime() && !config.showIsAnime && $('#anime-options').fadeIn('fast', 'linear');
		else
			$('#anigrouplists, #anime-options').fadeOut('fast', 'linear');
	});
	elIdMap.on('click', function() {
		var elMapOptions = $('#idmapping-options'), anim = {fast: 'linear'};
		if (checked(elIdMap))
			elMapOptions.fadeIn(anim);
		else
			elMapOptions.fadeOut(anim);
	});
	elScene.on('click', function() { isScene(); });
	elABD.on('click', function() { isABD(); });
	elSports.on('click', function() { isSports() });

	if (config.expandIds) { elIdMap.click(); }

	function undef(value) {
		return /undefined/i.test(typeof(value));
	}

	function updateSrcLinks() {

		var preventSave = !1, search = 'data-search';
		$('[id^=mid-], #source-id').each(function (i, selected) {
			var elSelected = $(selected),
				okDigits = !(/[^\d]/.test(elSelected.val()) || ('' === elSelected.val())),
				service = (('source-id' === elSelected.attr('id')) ? '#src-' + elSelected.attr('name') : '#src-' + elSelected.attr('id')),
				elLock = $('#lockid-' + service.replace(/.*?(\d+)$/, '$1')),
				elService = $(service),
				On = 'data-', Off = '', linkOnly = !1, newLink = '';

			if (okDigits) {
				if (0 < parseInt(elSelected.val(), 10)) {
					On = ''; Off = 'data-';
				} else {
					linkOnly = !0
				}
			}
			$.each(['href', 'title', 'onclick'], function(i, attr) {
				if ('n' === elService.attr(search)) {
					elService.attr(On + attr, elService.attr(Off + attr)).removeAttr(Off + attr);
				}
				if (linkOnly)
					elService.attr(attr, elService.attr(search + '-' + attr));
				elService.attr(search, linkOnly ? 'y' : 'n')
			});
			var title;
			if (('' === Off) && !linkOnly) {
				preventSave = !0;
				title = elSelected.attr('title');
				if (!/undefined/.test(title))
					elSelected.attr({'data-title': title});
				elSelected.addClass('warning').attr({title: 'Use digits (0-9)'});
				elLock.prop('disabled', !0);
			} else {
				title = elSelected.attr('data-title');
				if (!/undefined/.test(title))
					elSelected.attr({'title': title}).removeAttr('data-title');
				else
					elSelected.removeClass('warning').removeAttr('title');
				elLock.prop('disabled', !1);
				if (!undef(elService.attr('href'))) {
					if (!undef(elService.attr('data-href')) && linkOnly) {
						newLink = elService.attr(search + '-href');
					} else {
						newLink = elService.attr((undef(elService.attr('data-href')) ? '' : 'data-')
							+ 'href').replace(/(.*?)\d+/, '$1') + elSelected.val();
					}
					elService.attr('href', newLink);
				}
			}
		});
		$('#save-mapping').prop('disabled', preventSave);
	}

	$('[id^=mid-], #source-id').on('input', function() {
		updateSrcLinks();
	});

	function saveMapping(paused, markWanted) {
		var sbutton = $(this), mid = $('[id^=mid-]'), lock = $('[id^=lockid-]'),
			allf = $('[id^=mid-], [id^=lockid-], #reset-mapping, [name^=set-main]'),
			radio = $('[name^=set-main]:checked'), isMain = !radio.length || ('the-main' === radio.attr('id') && $.trim($('#source-id').val()) == $('#prodid').val()),
			panelSaveGet = $('#panel-save-get'), saveWait = $('#save-wait');

		allf.prop('disabled', !0);
		sbutton.prop('disabled', !0);
		var param = {'tvid_prodid': $('#tvid_prodid').val()};
		mid.each(function (i, selected) {
			param[$(selected).attr('id')] = $(selected).val();
		});
		lock.each(function (i, selected) {
			param[$(selected).attr('id')] = $(selected).prop('checked');
		});
		param['tvid'] = $('#tvid').val();
		if (!isMain) {
			param['m_tvid'] = radio.attr('data-tvid');
			param['m_prodid'] = $.trim(radio.closest('span').find('input:text').val());
			param['paused'] = paused ? '1' : '0';
			param['markwanted'] = markWanted ? '1' : '0';
			panelSaveGet.removeClass('show').addClass('hide');
			saveWait.removeClass('hide').addClass('show');
		}

		$.getJSON(sbRoot + '/home/save-mapping', param)
		 	.done(function (data) {
				allf.prop('disabled', !1);
				sbutton.prop('disabled', !1);
				panelSaveGet.removeClass('hide').addClass('show');
				saveWait.removeClass('show').addClass('hide');
				if (undef(data.error)) {
					$.each(data.map, function (i, item) {
						$('#mid-' + i).val(item.id);
						$('#lockid-' + i).prop('checked', -100 === item.status)
					});
					/** @namespace data.switch */
					/** @namespace data.switch.mtvid_prodid */
					if (!isMain && data.hasOwnProperty('switch') && data.switch.hasOwnProperty('Success')) {
						window.location.replace(sbRoot + '/home/view-show?tvid_prodid=' + $('#tvid_prodid').val());
						// window.location.replace(sbRoot + '/home/view-show?tvid_prodid=' + data.mtvid_prodid);
					} else if ((0 <  $('*[data-maybe-main=1]').length)
						&& (((0 === $('[name^=set-main]').length) && (0 < $('*[data-maybe-main=1]').val()))
						|| ((0 < $('[name^=set-main]').length) && (0 === $('*[data-maybe-main=1]').val())))) {
						location.reload();
					}
				}})
			.fail(function () {
				allf.prop('disabled', !1);
				sbutton.prop('disabled', !1);
			});
	}

	function resetMapping() {
		var fbutton = $(this), mid = $('[id^=mid-]'), lock = $('[id^=lockid-]'),
			allf = $('[id^=mid-], [id^=lockid-], #save-mapping, [name^=set-main]');

		allf.prop('disabled', !0);
		fbutton.prop('disabled', !0);

		var param = {'tvid_prodid': $('#tvid_prodid').val()};
		mid.each(function (i, selected) {
			param[$(selected).attr('id')] = $(selected).val();
		});

		lock.each(function (i, selected) {
			param[$(selected).attr('id')] = $(selected).prop('checked');
		});

		$.getJSON(sbRoot + '/home/force-mapping', param)
			.done(function (data) {
				allf.prop('disabled', !1);
				fbutton.prop('disabled', !1);
				if (undef(data.error)) {
					$('#the-main').prop('checked', !0).trigger('click');
					$.each(data, function (i, item) {
						$('#mid-' + i).val(item.id);
						$('#lockid-' + i).prop('checked', -100 === item.status);
					});
					updateSrcLinks();
				}})
			.fail(function () {
				allf.prop('disabled', !1);
				fbutton.prop('disabled', !1);
			});
	}

	$('#save-mapping, #reset-mapping').click(function() {
		var save = /save/i.test(this.id),
			radio = $('[name=set-main]:checked'), isMain = !radio.length || ('the-main' === radio.attr('id') && $.trim($('#source-id').val()) == $('#prodid').val()),
			newMain = (save && !isMain),
			paused = 'on' === $('#paused:checked').val(),
			extraWarn = !newMain ? '' : 'Warning: Changing the main source can produce undesirable'
				+ ' results if episodes do not match at old and new TV info sources<br /><br />'
				+ (paused ? '' : '<input type="checkbox" id="mark-wanted" style="margin-right:6px">'
					+ '<span class="red-text">Mark all added episodes Wanted to search for releases</span>'
					+ '</input><br /><br />'),
			checkAction = !newMain ? 'save ID changes' : 'change the TV info source';

		$.confirm({
			'title': save ? 'Confirm changes' : 'Get default IDs',
			'message':  extraWarn + 'Are you sure you want to ' + (save ? checkAction : 'fetch default IDs') + ' ?',
			'buttons': {
				'Yes': {
					'class': 'green',
					'action': function () {
						save ? saveMapping(paused, 'on' === $('#mark-wanted:checked').val()) : resetMapping()
					}
				},
				'No': {
					'class': 'red',
					'action': function () {}
				}
			}
		});

	});

});
