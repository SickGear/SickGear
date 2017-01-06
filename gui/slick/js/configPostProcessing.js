$(document).ready(function () {

	// http://stackoverflow.com/questions/2219924/idiomatic-jquery-delayed-event-only-after-a-short-pause-in-typing-e-g-timew
	var typewatch = (function () {
		var timer = 0;
		return function (callback, ms) {
			clearTimeout(timer);
			timer = setTimeout(callback, ms);
		};
	})();

	function israr_supported() {
		$.get(sbRoot + '/config/postProcessing/isRarSupported',
			function (data) {
				if (data === "supported") {
				} else {
					var el$ = $('#unpack');
					el$.qtip('option', {
						'content.text': 'Unrar Executable not found.',
						'style.classes': 'qtip-red qtip-rounded qtip-shadow'
					});
					el$.qtip('toggle', !0);
					el$.css('background-color', '#FFFFDD');
				}
			});
	}

	function fill_examples() {
		var pattern = $('#naming_pattern').val();
		var multi = $('#naming_multi_ep').find(':selected').val();

		$.get(sbRoot + '/config/postProcessing/testNaming', {pattern: pattern},
			function (data) {
				var el$ = $('#naming_example_div');
				if (data) {
					$('#naming_example').text(data + '.ext');
					el$.show();
				} else {
					el$.hide();
				}
			});

		$.get(sbRoot + '/config/postProcessing/testNaming', {pattern: pattern, multi: multi},
			function (data) {
				if (data) {
					$('#naming_example_multi').text(data + '.ext');
					$('#naming_example_multi_div').show();
				} else {
					$('#naming_example_multi_div').hide();
				}
			});

		$.get(sbRoot + '/config/postProcessing/isNamingValid', {pattern: pattern, multi: multi},
			function (data) {
				var el$ = $('#naming_pattern');
				if (data === "invalid") {
					el$.qtip('option', {
						'content.text': 'This pattern is invalid.',
						'style.classes': 'qtip-red qtip-rounded qtip-shadow'
					});
					el$.qtip('toggle', !0);
					el$.css('background-color', '#FFDDDD');
				} else if (data === "seasonfolders") {
					el$.qtip('option', {
						'content.text': 'This pattern would be invalid without the folders, using it will force "Flatten" off for all shows.',
						'style.classes': 'qtip-red qtip-rounded qtip-shadow'
					});
					el$.qtip('toggle', !0);
					el$.css('background-color', '#FFFFDD');
				} else {
					el$.qtip('option', {
						'content.text': 'This pattern is valid.',
						'style.classes': 'qtip-green qtip-rounded qtip-shadow'
					});
					el$.qtip('toggle', !1);
					el$.css('background-color', '#FFFFFF');
				}
			});

	}

	function fill_abd_examples() {
		if (!$('#naming_custom_abd').is(':checked'))
			return;
		var pattern = $('#naming_abd_pattern').val();

		$.get(sbRoot + '/config/postProcessing/testNaming', {pattern: pattern, abd: 'True'},
			function (data) {
				var el$ = $('#naming_abd_example_div');
				if (data) {
					$('#naming_abd_example').text(data + '.ext');
					el$.show();
				} else {
					el$.hide();
				}
			});

		$.get(sbRoot + '/config/postProcessing/isNamingValid', {pattern: pattern, abd: 'True'},
			function (data) {
				var el$ = $('#naming_abd_pattern');
				if (data === "invalid") {
					el$.qtip('option', {
						'content.text': 'This pattern is invalid.',
						'style.classes': 'qtip-red qtip-rounded qtip-shadow'
					});
					el$.qtip('toggle', !0);
					el$.css('background-color', '#FFDDDD');
				} else if (data === "seasonfolders") {
					el$.qtip('option', {
						'content.text': 'This pattern would be invalid without the folders, using it will force "Flatten" off for all shows.',
						'style.classes': 'qtip-red qtip-rounded qtip-shadow'
					});
					el$.qtip('toggle', !0);
					el$.css('background-color', '#FFFFDD');
				} else {
					el$.qtip('option', {
						'content.text': 'This pattern is valid.',
						'style.classes': 'qtip-green qtip-rounded qtip-shadow'
					});
					el$.qtip('toggle', !1);
					el$.css('background-color', '#FFFFFF');
				}
			});

	}

	function fill_sports_examples() {
		if (!$('#naming_custom_sports').is(':checked'))
			return;
		var pattern = $('#naming_sports_pattern').val();

		$.get(sbRoot + '/config/postProcessing/testNaming', {pattern: pattern, sports: 'True'},
			function (data) {
				if (data) {
					$('#naming_sports_example').text(data + '.ext');
					$('#naming_sports_example_div').show();
				} else {
					$('#naming_sports_example_div').hide();
				}
			});

		$.get(sbRoot + '/config/postProcessing/isNamingValid', {pattern: pattern, sports: 'True'},
			function (data) {
				var el$ = $('#naming_sports_pattern');
				if (data === "invalid") {
					el$.qtip('option', {
						'content.text': 'This pattern is invalid.',
						'style.classes': 'qtip-red qtip-rounded qtip-shadow'
					});
					el$.qtip('toggle', !0);
					el$.css('background-color', '#FFDDDD');
				} else if (data === "seasonfolders") {
					el$.qtip('option', {
						'content.text': 'This pattern would be invalid without the folders, using it will force "Flatten" off for all shows.',
						'style.classes': 'qtip-red qtip-rounded qtip-shadow'
					});
					el$.qtip('toggle', !0);
					el$.css('background-color', '#FFFFDD');
				} else {
					el$.qtip('option', {
						'content.text': 'This pattern is valid.',
						'style.classes': 'qtip-green qtip-rounded qtip-shadow'
					});
					el$.qtip('toggle', !1);
					el$.css('background-color', '#FFFFFF');
				}
			});

	}

	function fill_anime_examples() {
		if (!$('#naming_custom_anime').is(':checked'))
			return;
		var pattern = $('#naming_anime_pattern').val();
		var multi = $('#naming_anime_multi_ep').find(':selected').val();
		var anime_type = $('input[name="naming_anime"]:checked').val();

		$.get(sbRoot + '/config/postProcessing/testNaming', {pattern: pattern, anime: 'True', anime_type: anime_type},
			function (data) {
				if (data) {
					$('#naming_example_anime').text(data + '.ext');
					$('#naming_example_anime_div').show();
				} else {
					$('#naming_example_anime_div').hide();
				}
			});

		$.get(sbRoot + '/config/postProcessing/testNaming', {pattern: pattern, multi: multi, anime: 'True', anime_type: anime_type},
			function (data) {
				if (data) {
					$('#naming_example_multi_anime').text(data + '.ext');
					$('#naming_example_multi_anime_div').show();
				} else {
					$('#naming_example_multi_anime_div').hide();
				}
			});

		$.get(sbRoot + '/config/postProcessing/isNamingValid', {pattern: pattern, multi: multi, anime: 'True', anime_type: anime_type},
			function (data) {
				var el$ = $('#naming_anime_pattern');
				if (data === "invalid") {
					el$.qtip('option', {
						'content.text': 'This pattern is invalid.',
						'style.classes': 'qtip-red qtip-rounded qtip-shadow'
					});
					el$.qtip('toggle', !0);
					el$.css('background-color', '#FFDDDD');
				} else if (data === "seasonfolders") {
					el$.qtip('option', {
						'content.text': 'This pattern would be invalid without the folders, using it will force "Flatten" off for all shows.',
						'style.classes': 'qtip-red qtip-rounded qtip-shadow'
					});
					el$.qtip('toggle', !0);
					el$.css('background-color', '#FFFFDD');
				} else {
					el$.qtip('option', {
						'content.text': 'This pattern is valid.',
						'style.classes': 'qtip-green qtip-rounded qtip-shadow'
					});
					el$.qtip('toggle', !1);
					el$.css('background-color', '#FFFFFF');
				}
			});
	}

	function setup_naming() {
		// if it is a custom selection then show the text box
		var el$ = $('#name_presets');
		if (el$.find(':selected').val() === "Custom...") {
			$('#naming_custom').show();
		} else {
			$('#naming_custom').hide();
			$('#naming_pattern').val(el$.find(':selected').attr('id'));
		}
		fill_examples();
	}

	function setup_abd_naming() {
		// if it is a custom selection then show the text box
		var el$ = $('#name_abd_presets');
		if (el$.find(':selected').val() === 'Custom...') {
			$('#naming_abd_custom').show();
		} else {
			$('#naming_abd_custom').hide();
			$('#naming_abd_pattern').val(el$.find(':selected').attr('id'));
		}
		fill_abd_examples();
	}

	function setup_sports_naming() {
		// if it is a custom selection then show the text box
		var el$ = $('#name_sports_presets');
		if (el$.find(':selected').val() === 'Custom...') {
			$('#naming_sports_custom').show();
		} else {
			$('#naming_sports_custom').hide();
			$('#naming_sports_pattern').val(el$.find(':selected').attr('id'));
		}
		fill_sports_examples();
	}

	function setup_anime_naming() {
		// if it is a custom selection then show the text box
		var el$ = $('#name_anime_presets');
		if (el$.find(':selected').val() === "Custom...") {
			$('#naming_anime_custom').show();
		} else {
			$('#naming_anime_custom').hide();
			$('#naming_anime_pattern').val(el$.find(':selected').attr('id'));
		}
		fill_anime_examples();
	}

	$('#unpack').change(function () {
		if(this.checked) {
			israr_supported();
		} else {
			$('#unpack').qtip('toggle', !1);
		}
	});

	$('#name_presets').change(function () {
		setup_naming();
	});

	$('#name_abd_presets').change(function () {
		setup_abd_naming();
	});

	$('#naming_custom_abd').change(function () {
		setup_abd_naming();
	});

	$('#name_sports_presets').change(function () {
		setup_sports_naming();
	});

	$('#naming_custom_sports').change(function () {
		setup_sports_naming();
	});

	$('#name_anime_presets').change(function () {
		setup_anime_naming();
	});

	$('#naming_custom_anime').change(function () {
		setup_anime_naming();
	});

	$('input[name="naming_anime"]').click(function(){
		setup_anime_naming();
	});

	$('#naming_multi_ep').change(fill_examples);
	var el$ = $('#naming_pattern');
	el$.focusout(fill_examples);
	el$.keyup(function () {
		typewatch(function () {
			fill_examples();
		}, 500);
	});

	$('#naming_anime_multi_ep').change(fill_anime_examples);
	var naming_anime_pattern$ = $('#naming_anime_pattern');
	naming_anime_pattern$.focusout(fill_anime_examples);
	naming_anime_pattern$.keyup(function () {
		typewatch(function () {
			fill_anime_examples();
		}, 500);
	});

	el$ = $('#naming_abd_pattern');
	el$.focusout(fill_examples);
	el$.keyup(function () {
		typewatch(function () {
			fill_abd_examples();
		}, 500);
	});

	el$ = $('#naming_sports_pattern');
	el$.focusout(fill_examples);
	el$.keyup(function () {
		typewatch(function () {
			fill_sports_examples();
		}, 500);
	});

	naming_anime_pattern$.focusout(fill_examples);
	naming_anime_pattern$.keyup(function () {
		typewatch(function () {
			fill_anime_examples();
		}, 500);
	});

	$('#show_extra_params').click(function () {
		$('#extra_params').toggle();
	});
	$('#show_naming_key').click(function () {
		$('#naming_key').toggle();
	});
	$('#show_naming_abd_key').click(function () {
		$('#naming_abd_key').toggle();
	});
	$('#show_naming_sports_key').click(function () {
		$('#naming_sports_key').toggle();
	});
	$('#show_naming_anime_key').click(function () {
		$('#naming_anime_key').toggle();
	});
	$('#do_custom').click(function () {
		var el$ = $('#naming_pattern');
		el$.val($('#name_presets').find(':selected').attr('id'));
		$('#naming_custom').show();
		el$.focus();
	});
	setup_naming();
	setup_abd_naming();
	setup_sports_naming();
	setup_anime_naming();


	// -- start of metadata options div toggle code --
	$('#metadataType').on('change keyup', function () {
		$(this).showHideMetadata();
	});

	$.fn.showHideMetadata = function () {
		$('.metadataDiv').each(function () {
			var targetName = $(this).attr('id');
			var selectedTarget = $('#metadataType').find(':selected').val();

			if (selectedTarget === targetName) {
				$(this).show();
			} else {
				$(this).hide();
			}
		});
	};
	//initialize to show the div
	$(this).showHideMetadata();
	// -- end of metadata options div toggle code --

	$('.metadata_checkbox').click(function () {
		$(this).refreshMetadataConfig(!1);
	});

	$.fn.refreshMetadataConfig = function (first) {

		var cur_most = 0;
		var cur_most_provider = '';

		$('.metadataDiv').each(function () {
			var generator_name = $(this).attr('id');

			var config_arr = [],
				show_metadata = $('#' + generator_name + '_show_metadata').prop('checked'),
				episode_metadata = $('#' + generator_name + '_episode_metadata').prop('checked'),
				fanart = $('#' + generator_name + '_fanart').prop('checked'),
				poster = $('#' + generator_name + '_poster').prop('checked'),
				banner = $('#' + generator_name + '_banner').prop('checked'),
				episode_thumbnails = $('#' + generator_name + '_episode_thumbnails').prop('checked'),
				season_posters = $('#' + generator_name + '_season_posters').prop('checked'),
				season_banners = $('#' + generator_name + '_season_banners').prop('checked'),
				season_all_poster = $('#' + generator_name + '_season_all_poster').prop('checked'),
				season_all_banner = $('#' + generator_name + '_season_all_banner').prop('checked');

			config_arr.push(show_metadata ? '1' : '0');
			config_arr.push(episode_metadata ? '1' : '0');
			config_arr.push(fanart ? '1' : '0');
			config_arr.push(poster ? '1' : '0');
			config_arr.push(banner ? '1' : '0');
			config_arr.push(episode_thumbnails ? '1' : '0');
			config_arr.push(season_posters ? '1' : '0');
			config_arr.push(season_banners ? '1' : '0');
			config_arr.push(season_all_poster ? '1' : '0');
			config_arr.push(season_all_banner ? '1' : '0');

			var cur_num = 0;
			for (var i = 0; i < config_arr.length; i++) {
				cur_num += parseInt(config_arr[i]);
			}
			if (cur_num > cur_most) {
				cur_most = cur_num;
				cur_most_provider = generator_name;
			}

			$("#" + generator_name + "_eg_show_metadata").attr('class', show_metadata ? 'enabled' : 'disabled');
			$("#" + generator_name + "_eg_episode_metadata").attr('class', episode_metadata ? 'enabled' : 'disabled');
			$("#" + generator_name + "_eg_fanart").attr('class', fanart ? 'enabled' : 'disabled');
			$("#" + generator_name + "_eg_poster").attr('class', poster ? 'enabled' : 'disabled');
			$("#" + generator_name + "_eg_banner").attr('class', banner ? 'enabled' : 'disabled');
			$("#" + generator_name + "_eg_episode_thumbnails").attr('class', episode_thumbnails ? 'enabled' : 'disabled');
			$("#" + generator_name + "_eg_season_posters").attr('class', season_posters ? 'enabled' : 'disabled');
			$("#" + generator_name + "_eg_season_banners").attr('class', season_banners ? 'enabled' : 'disabled');
			$("#" + generator_name + "_eg_season_all_poster").attr('class', season_all_poster ? 'enabled' : 'disabled');
			$("#" + generator_name + "_eg_season_all_banner").attr('class', season_all_banner ? 'enabled' : 'disabled');
			$("#" + generator_name + "_data").val(config_arr.join('|'));

		});

		if (cur_most_provider !== '' && first) {
			$('#metadataType').find('option[value=' + cur_most_provider + ']').prop('selected', !0);
			$(this).showHideMetadata();
		}

	};

	$(this).refreshMetadataConfig(!0);
	$('img[title]').qtip({
		position: {
			viewport: $(window),
			my: 'top right',
			at: 'bottom center'
		},
		style: {
			classes: 'qtip-dark qtip-rounded qtip-shadow'
		}
	});
	$('i[title]').qtip({
		position: {
			viewport: $(window),
			my: 'bottom center',
			at: 'top center'
		},
		style: {
			classes: 'qtip-dark qtip-rounded qtip-shadow'
		}
	});
	$('.custom-pattern,#unpack').qtip({
		content: 'validating...',
		show: {
			event: !1,
			ready: !1
		},
		hide: !1,
		position: {
			viewport: $(window),
			my: 'right center',
			at: 'left center'
		},
		style: {
			classes: 'qtip-red qtip-rounded qtip-shadow'
		}
	});

	$('.config_submitter').on('click', (function() {
		var save_config = !0;
		$('#naming_pattern, #naming_abd_pattern, #naming_sports_pattern').each(function() {
			if (/^((?=.*%RG)(?:(?!-%RG).)*)$/.test($(this).val())
				|| /^((?=.*%rg)(?:(?!-%rg).)*)$/i.test($(this).val())) {
				$(this).focus();
				alert('You must insert a minus symbol before the %RG/%rg token i.e. -%RG, or -%rg');
				save_config = !1;
				return save_config;
			}
		});
		if (save_config) {
			$('#naming_anime_pattern').each(function() {
				if (/^((?=.*%RG)(?:(?!\[%RG\]).)*)$/.test($(this).val())
					|| /^((?=.*%rg)(?:(?!\[%rg\]).)*)$/i.test($(this).val())) {
					$(this).focus();
					alert('You must insert a bracket around the %RG/%rg token i.e. [%RG], or [%rg]');
					save_config = !1;
					return save_config;
				}
			});
		}
		return save_config;
	}))
});
