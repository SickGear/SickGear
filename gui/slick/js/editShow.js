/** @namespace config.showLang */
/** @namespace config.showIsAnime */
/*globals $, config, sbRoot, generate_bwlist*/

$(document).ready(function () {

	$('#location').fileBrowser({title: 'Select Show Location'});

	function htmlFlag(lang) {
		return ' class="flag" style="background-image:url(' + sbRoot + '/images/flags/' + lang + '.png)"'
	}

	$.getJSON(sbRoot + '/home/addShows/getIndexerLanguages', {}, function (data) {
		var result = '', currentLangAdded = '', selected = ' selected="selected"';

		if (0 == data.results.length) {
			result = '<option value="' + config.showLang + '"' + selected + htmlFlag(config.showLang) + '>'
				+ config.showLang + '</option>';
		} else {
			currentLangAdded = !1;
			$.each(data.results, function (index, strLang) {

				var htmlSelected = '';
				if (strLang === config.showLang) {
					currentLangAdded = !0;
					htmlSelected = selected;
				}

				result += '<option value="' + strLang + '"' + htmlSelected + htmlFlag(strLang) + '>'
					+ strLang + '</option>';
			});

			if (!currentLangAdded)
				result += '<option value="' + config.showLang + '" ' + selected + '>' + config.showLang + '</option>';
		}

		$('#indexerLangSelectEdit').html(result);
	});

	function getExceptions() {
		var allExceptions = [];

		$('#exceptions_list').find('option').each(function () {
			allExceptions.push($(this).val());
		});

		return allExceptions
	}

	$('#submit').click(function () {
		$('#exceptions_list').val(getExceptions());
		if (config.showIsAnime)
			generate_bwlist();
	});

	$('#addSceneName').click(function () {
		var elSceneName = $('#SceneName'), elSceneNameSeason = $('#SceneNameSeason'),
			sceneEx = elSceneName.val(), sceneExSeason = elSceneNameSeason.val();

		elSceneName.val('');
		elSceneNameSeason.val('');

		if (-1 < $.inArray(sceneExSeason + '|' + sceneEx, getExceptions()) || ('' === sceneEx))
			return;

		$('#SceneException').fadeIn('fast', 'linear');

		var option = $('<option>');
		option.attr('value', sceneExSeason + '|' + sceneEx);
		option.html((config.showIsAnime ? 'S' + ('-1' === sceneExSeason ? '*' : sceneExSeason) + ': ' : '') + sceneEx);

		return option.appendTo($('#exceptions_list'));
	});

	$('#removeSceneName').click(function () {
		$('#exceptions_list').find('option:selected').remove();

		$(this).toggle_SceneException();
	});

	$.fn.toggle_SceneException = function () {
		var elSceneException = $('#SceneException');

		if (0 == getExceptions().length)
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
		if (config.showIsAnime) { $('#blackwhitelist').fadeIn('fast', 'linear'); } return !0; }
	function isScene() { uncheck(elABD); uncheck(elSports); }
	function isABD() { uncheck(elAnime); uncheck(elScene); $('#blackwhitelist').fadeOut('fast', 'linear'); }
	function isSports() { uncheck(elAnime); uncheck(elScene); $('#blackwhitelist').fadeOut('fast', 'linear'); }

	if (checked(elAnime)) { isAnime(); }
	if (checked(elScene)) { isScene(); }
	if (checked(elABD)) { isABD(); }
	if (checked(elSports)) { isSports() }

	elAnime.on('click', function() {
		if (checked(elAnime))
			isAnime() && !config.showIsAnime && $('#anime-options').fadeIn('fast', 'linear');
		else
			$('#blackwhitelist, #anime-options').fadeOut('fast', 'linear');
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

	function undef(value) {
		return /undefined/i.test(typeof(value));
	}

	function updateSrcLinks() {

		var preventSave = !1, search = 'data-search';
		$('[id^=mid-]').each(function (i, selected) {
			var elSelected = $(selected),
				okDigits = !(/[^\d]/.test(elSelected.val()) || ('' == elSelected.val())),
				service = '#src-' + elSelected.attr('id'),
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
				if ('n' == elService.attr(search)) {
					elService.attr(On + attr, elService.attr(Off + attr)).removeAttr(Off + attr);
				}
				if (linkOnly)
					elService.attr(attr, elService.attr(search + '-' + attr));
				elService.attr(search, linkOnly ? 'y' : 'n')
			});
			if (('' == Off) && !linkOnly) {
				preventSave = !0;
				elSelected.addClass('warning').attr({title: 'Use digits (0-9)'});
				elLock.prop('disabled', !0);
			} else {
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

	$('[id^=mid-]').on('input', function() {
		updateSrcLinks();
	});

	function saveMapping(paused, markWanted) {
		var sbutton = $(this), mid = $('[id^=mid-]'), lock = $('[id^=lockid-]'),
			allf = $('[id^=mid-], [id^=lockid-], #reset-mapping, [name^=set-master]'),
			radio = $('[name^=set-master]:checked'), isMaster = !radio.length || 'the-master' == radio.attr('id'),
			panelSaveGet = $('#panel-save-get'), saveWait = $('#save-wait');

		allf.prop('disabled', !0);
		sbutton.prop('disabled', !0);
		var param = {'show': $('#show').val()};
		mid.each(function (i, selected) {
			param[$(selected).attr('id')] = $(selected).val();
		});
		lock.each(function (i, selected) {
			param[$(selected).attr('id')] = $(selected).prop('checked');
		});
		if (!isMaster) {
			param['indexer'] = $('#indexer').val();
			param['mindexer'] = radio.attr('data-indexer');
			param['mindexerid'] = radio.attr('data-indexerid');
			param['paused'] = paused ? '1' : '0';
			param['markwanted'] = markWanted ? '1' : '0';
			panelSaveGet.removeClass('show').addClass('hide');
			saveWait.removeClass('hide').addClass('show');
		}

		$.getJSON(sbRoot + '/home/saveMapping', param)
		 	.done(function (data) {
				allf.prop('disabled', !1);
				sbutton.prop('disabled', !1);
				panelSaveGet.removeClass('hide').addClass('show');
				saveWait.removeClass('show').addClass('hide');
				if (undef(data.error)) {
					$.each(data.map, function (i, item) {
						$('#mid-' + i).val(item.id);
						$('#lockid-' + i).prop('checked', -100 == item.status)
					});
					/** @namespace data.switch */
					/** @namespace data.switch.mid */
					if (!isMaster && data.hasOwnProperty('switch') && data.switch.hasOwnProperty('Success')) {
						window.location.replace(sbRoot + '/home/displayShow?show=' + data.mid);
					} else if ((0 <  $('*[data-maybe-master=1]').length)
						&& (((0 == $('[name^=set-master]').length) && (0 < $('*[data-maybe-master=1]').val()))
						|| ((0 < $('[name^=set-master]').length) && (0 == $('*[data-maybe-master=1]').val())))) {
						location.reload();
					}
				}})
			.fail(function (data) {
				allf.prop('disabled', !1);
				sbutton.prop('disabled', !1);
			});
	}

	function resetMapping() {
		var fbutton = $(this), mid = $('[id^=mid-]'), lock = $('[id^=lockid-]'),
			allf = $('[id^=mid-], [id^=lockid-], #save-mapping, [name^=set-master]');

		allf.prop('disabled', !0);
		fbutton.prop('disabled', !0);

		var param = {'show': $('#show').val()};
		mid.each(function (i, selected) {
			param[$(selected).attr('id')] = $(selected).val();
		});

		lock.each(function (i, selected) {
			param[$(selected).attr('id')] = $(selected).prop('checked');
		});

		$.getJSON(sbRoot + '/home/forceMapping', param)
			.done(function (data) {
				allf.prop('disabled', !1);
				fbutton.prop('disabled', !1);
				if (undef(data.error)) {
					$('#the-master').prop('checked', !0).trigger('click');
					$.each(data, function (i, item) {
						$('#mid-' + i).val(item.id);
						$('#lockid-' + i).prop('checked', -100 == item.status);
					});
					updateSrcLinks();
				}})
			.fail(function (data) {
				allf.prop('disabled', !1);
				fbutton.prop('disabled', !1);
			});
	}

	$('#save-mapping, #reset-mapping').click(function() {

		var save = /save/i.test($(this).attr('id')),
			radio = $('[name=set-master]:checked'), isMaster = !radio.length || 'the-master' == radio.attr('id'),
			newMaster = (save && !isMaster),
			paused = 'on' == $('#paused:checked').val(),
			extraWarn = !newMaster ? '' : 'Warning: Changing the master source can produce undesirable'
				+ ' results if episodes do not match at old and new TV info sources<br /><br />'
				+ (paused ? '' : '<input type="checkbox" id="mark-wanted" style="margin-right:6px">'
					+ '<span class="red-text">Mark all added episodes Wanted to search for releases</span>'
					+ '</input><br /><br />'),
			checkAction = !newMaster ? 'save ID changes' : 'change the TV info source';

		$.confirm({
			'title': save ? 'Confirm changes' : 'Get default IDs',
			'message':  extraWarn + 'Are you sure you want to ' + (save ? checkAction : 'fetch default IDs') + ' ?',
			'buttons': {
				'Yes': {
					'class': 'green',
					'action': function () {
						save ? saveMapping(paused, 'on' == $('#mark-wanted:checked').val()) : resetMapping()
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
