/*globals $, config, sbRoot, generate_bwlist*/

$(document).ready(function () {

	$.getJSON(sbRoot + '/home/addShows/getIndexerLanguages', {}, function (data) {
		var resultStr, flag, selected, current_lang_added = '';

		if (data.results.length === 0) {
			flag = ' class="flag" style="background-image:url(' + sbRoot + '/images/flags/' + config.show_lang + '.png)"';
			resultStr = '<option value="' + config.show_lang + '" selected="selected"' + flag + '>' + config.show_lang + '</option>';
		} else {
			current_lang_added = false;
			$.each(data.results, function (index, obj) {

				if (obj === config.show_lang) {
					selected = ' selected="selected"';
					current_lang_added = true;
				}
				else {
					selected = '';
				}

				flag = ' class="flag" style="background-image:url(' + sbRoot + '/images/flags/' + obj + '.png);"';
				resultStr += '<option value="' + obj + '"' + selected + flag + '>' + obj + '</option>';
			});

			if (!current_lang_added) {
				resultStr += '<option value=" ' + config.show_lang + '" selected="selected"> ' + config.show_lang + '</option>';
			}

		}
		$('#indexerLangSelectEdit').html(resultStr);

	});


	var all_exceptions = [];

	$('#location').fileBrowser({title: 'Select Show Location'});

	$('#submit').click(function () {
		all_exceptions = [];

		$('#exceptions_list').find('option').each  (function () {
			all_exceptions.push($(this).val());
		});

		$('#exceptions_list').val(all_exceptions);
		if (config.show_isanime) {
			generate_bwlist();
		}
	});

	$('#addSceneName').click(function () {
		var scene_ex = $('#SceneName').val();
		var scene_ex_season = $('#SceneNameSeason').val();
		var option = $('<option>');
		all_exceptions = [];

		$('#exceptions_list').find('option').each  (function () {
			all_exceptions.push($(this).val());
		});

		$('#SceneName').val('');
		$('#SceneNameSeason').val('');

		if ($.inArray(scene_ex_season + '|' + scene_ex, all_exceptions) > -1 || (scene_ex === '')) {
			return;
		}
		$('#SceneException').show();

		option.attr('value', scene_ex_season + '|' + scene_ex);
		if (scene_ex_season === "-1") {
			option.html('S*: ' + scene_ex);
		}
		else {
			option.html('S' + scene_ex_season + ': ' + scene_ex);
		}
		return option.appendTo('#exceptions_list');
	});

	$('#removeSceneName').click(function () {
		$('#exceptions_list').find('option:selected').remove();

		$(this).toggle_SceneException();
	});

	$.fn.toggle_SceneException = function () {
		all_exceptions = [];

		$('#exceptions_list').find('option').each  (function () {
			all_exceptions.push($(this).val());
		});

		if ('' === all_exceptions) {
			$('#SceneException').hide();
		}
		else {
			$('#SceneException').show();
		}
	};

	$(this).toggle_SceneException();


});