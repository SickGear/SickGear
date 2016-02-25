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

	var elABD = $('#air_by_date'), elScene = $('#scene'), elSports = $('#sports'), elAnime = $('#anime');

	function uncheck(el){el.prop('checked', !1)}
	function checked(el){return el.prop('checked')}

	function isAnime(){
		uncheck(elABD); uncheck(elSports);
		if (config.showIsAnime){ $('#blackwhitelist').fadeIn('fast', 'linear'); } return !0; }
	function isScene(){ uncheck(elABD); uncheck(elSports); }
	function isABD(){ uncheck(elAnime); uncheck(elScene); $('#blackwhitelist').fadeOut('fast', 'linear'); }
	function isSports(){ uncheck(elAnime); uncheck(elScene); $('#blackwhitelist').fadeOut('fast', 'linear'); }

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
	elScene.on('click', function() { isScene(); });
	elABD.on('click', function() { isABD(); });
	elSports.on('click', function() { isSports() });

});
