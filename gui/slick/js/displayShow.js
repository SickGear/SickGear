/** @namespace $.SickGear.Root */
/** @namespace $.SickGear.glideFancyBoxOpen */
/** @namespace config.TVShowList */
/** @namespace config.useIMDbInfo */
/** @namespace $.SickGear.config.useFuzzy */
/** @namespace $.SickGear.config.dateFormat */
/** @namespace $.SickGear.config.timeFormat */
/** @namespace $.SickGear.config.fuzzyTrimZero */
/** @namespace $.SickGear.config.glideStartAt */
/** @namespace $.SickGear.config.glideSlideTime */
$(document).ready(function() {

	// handle the show selection dropbox
	var select$ = $('#pickShow');
	select$.change(function() {
		var val = $(this).val();
		if (0 !== val)
			window.location.href = $.SickGear.Root + '/home/view-show?tvid_prodid=' + val;
	});
	select$.select2({
		templateResult: function(data){
			if (!data.element || !$(data.element).hasClass('ended')) {
				return data.text;
			}
			return $('<span class="ended"><span class="label" title="">ended</span> <i>' + data.text + '</i></span>');
		}
	});

	$('#prevShow, #nextShow').on('click', function() {
		var select$ = $('#pickShow'),
			index = $.inArray(select$.find('option:selected').val(), config.TVShowList);
		//noinspection JSUnresolvedVariable
		select$.find('option[value="' + config.TVShowList[('nextShow' === $(this).attr('id')
			? (index < config.TVShowList.length - 1 ? index + 1 : 0)
			: (0 < index ? index - 1 : config.TVShowList.length - 1))] + '"]').prop('selected', !0);
		select$.change();
		return !1;
	});

	$('#seasonJump').change(function() {
		var id = $(this).val();
		if (id && 'jump' != id) {
			$('html,body').animate({scrollTop: $(id).offset().top}, 'slow');
			location.hash = id;
		}
		$(this).val('jump');
	});

	var slideGap = 5,
	slideCount = $('.cast').length;

	if (0 < slideCount) {

		function slideTime(){
			return 0 < $.SickGear.config.glideSlideTime && !$.SickGear.glideFancyBoxOpen
				? $.SickGear.config.glideSlideTime : !1;
		}

		$.calcSlideCount = function(initSet){
			var maxCount = Math.floor($('.glide__track').width() / (170 + slideGap)),
				perView = maxCount < slideCount ? maxCount : slideCount;
			if (initSet)
				return {perView: perView, isNotEnd: maxCount < slideCount};

			if (maxCount < slideCount) {
				$.glide.update({perView: perView, autoplay: slideTime()});
				if (slideTime()){
					$.glide.play();
				}
			} else {
				$.glide.pause();
				$.glide.update({perView: perView, autoplay: !1});
				$.glide.go('=0');
			}
		}

		var initGlideVars = $.calcSlideCount(!0),
			startAt = $('.cast[data-rid="' + $.SickGear.config.glideStartAt + '"]').index();
		$.glide = new Glide('.cast-holder', {
			type: 'carousel',
			gap: slideGap,
			startAt: -1 === startAt ? 0 : startAt,
			peek: 0,
			perSwipe: '|',
			perView: initGlideVars.perView,
			autoplay: initGlideVars.isNotEnd && slideTime()
		});

		$.glide.on('resize', function(){
			$.calcSlideCount(!1);
			$('#display-show .cast-bg').each(function (i, oImage){
				scaleImage(oImage);
			});
		});

		$.glide.on('run.after', function(){
			saveGlide();
		});

		function initFancybox(){
			try {
				setupFancyBox();
			} catch {
				var fancy = $.SickGear.Root + '/js/fancybox/jquery.fancybox.min';
				$.getScript(fancy + '.js', function() {
					$('head').append('<link rel="stylesheet" href="' + fancy + '.css">');
					setupFancyBox();
				});
			}
		}

		function setupFancyBox(){
			if (!!$('a[rel="glide"]').length){
				$().fancybox(jQuery.extend({
					selector: 'li:not(.glide__slide--clone) a[rel="glide"]',
					slideShow: {
						speed: Math.abs($.SickGear.config.glideSlideTime)
					},
					afterShow: function(instance, slide){
						$.SickGear.glideFancyBoxOpen = !0;
						$.glide.go('=' + slide.index);
					},
					beforeShow: function(instance, slide){
						if (!$.SickGear.glideFancyBoxOpen && 0 < $.SickGear.config.glideSlideTime){
							$.glide.pause();
							$.glide.update({autoplay: !1});
						}
					},
					afterClose: function(instance, slide){
						if (!!$.SickGear.glideFancyBoxOpen){
							$.SickGear.glideFancyBoxOpen = !1;
							if (0 < $.SickGear.config.glideSlideTime){
								$.calcSlideCount(!1);
							}
						}
					},
				}, $.sgFancyBoxOptions));
			}
		}

		$.glide.on('build.after', function(){
			initFancybox();
			$('.cast.glide__slide').removeClass('last');
			$('.cast.glide__slide:not(.glide__slide--clone):last').addClass('last');
			$('.cast.body .cast-bg, #pin-glide, .glide-arrows, .cast.body .links').fadeIn('slow', 'linear');
			$('#about-hide').addClass('hide');
			$('#about-show').removeClass('hide');
			$('.glide__slide--clone').click(function(){
				$('li[data-rid="' + $(this).data('rid') + '"]:not(.glide__slide--clone) a[rel="glide"]')[0].click();
				return !1;
			});
			$('#display-show .cast-bg').each(function (i, oImage){
				scaleImage(oImage);
			});
		});

		window.onload = function(){
			$.glide.mount();
		};

		function saveGlide(saveTime){
			if (!$.SickGear.glideFancyBoxOpen){
				var params = {};
				if (!slideTime()){
					params = {
						tvid_prodid: $('#tvid-prodid').val(),
						start_at: $('.cast.glide__slide--active').data('rid')
					};
				}
				if (saveTime){
					params.slidetime = $.SickGear.config.glideSlideTime;
				}
				$.get($.SickGear.Root + '/home/set-display-show-glide', params);
			}
		}

		var ivTimes = [10000, 6000, 3000];
		function pinState(el$){
			var ivTime = slideTime();

			el$.removeClass('one two three four');
			if (!ivTime) {
				el$.addClass('one');
			} else if (ivTimes[0] === ivTime) {
				el$.addClass('two');
			} else if (ivTimes[1] === ivTime) {
				el$.addClass('three');
			} else {
				el$.addClass('four');
			}
		}

		var pinGlide$ = $('#pin-glide');
		pinState(pinGlide$);
		pinGlide$.on('click', function (){
			var ivTime = slideTime();

			if (!ivTime) { // unpause as was paused when clicked
				$.SickGear.config.glideSlideTime *= -1;
			} else if (ivTimes[0] === ivTime) {
				$.SickGear.config.glideSlideTime = ivTimes[1];
			} else if (ivTimes[1] === ivTime) {
				$.SickGear.config.glideSlideTime = ivTimes[2];
			} else {
				$.SickGear.config.glideSlideTime = -1 * ivTimes[0];
			}
			pinState($(this));
			$.calcSlideCount(!1);
			saveGlide(!0);
		});
	}

	$('.details-plot').collapser({
		mode: 'lines',
		truncate: 10,
		showText: '<i class="sgicon-arrowdown"></i>more',
		hideText: '<i class="sgicon-arrowup"></i>less',
		showClass: 'show-class'
	});

	if (config.useIMDbInfo){
		$.fn.generateStars = function() {
			return this.each(function(i,e){$(e).html($('<span/>').width($(e).text()*12));});
		};
		$('.imdbstars').generateStars();
	}

	$('#changeStatus').on('click', function() {
		var epArr = [];

		$('.epCheck').each(function() {
			this.checked && epArr.push($(this).attr('id'))
		});
		if (epArr.length)
			window.location.href = $.SickGear.Root + '/home/set-show-status?tvid_prodid=' + $('#tvid-prodid').val() +
				'&eps=' + epArr.join('|') + '&status=' + $('#statusSelect').val();
	});

	// show/hide different types of rows when the checkboxes are changed
	var el = $('#checkboxControls').find('input');
	el.change(function() {
		$(this).showHideRows($(this).attr('id'));
	});

	// initially show/hide all the rows according to the checkboxes
	el.each(function() {
		var status = this.checked;
		$('tr.' + $(this).attr('id')).each(function() {
			status && $(this).show() || $(this).hide();
		});
	});

	$.fn.showHideRows = function(whichClass) {

		var status = $('#checkboxControls > input, #' + whichClass).prop('checked');
		$('tr.' + whichClass).each(function() {
			status && $(this).show() || $(this).hide();
		});

		// hide season headers with no episodes under them
		$('tr.seasonheader').each(function() {
			var numRows = 0;
			var seasonNo = $(this).attr('id');
			$('tr.' + seasonNo + ' :visible').each(function() {
				numRows++
			});
			var el = $('#' + seasonNo + '-cols');
			if (0 == numRows) {
				$(this).hide();
				el.hide();
			} else {
				$(this).show();
				el.show();
			}

		});
	};

	function checkState(state){
		$('.epCheck:visible, .seasonCheck:visible').prop('checked', state)
	}
	// selects all visible episode checkboxes.
	$('.seriesCheck').on('click', function() { checkState(!0); });

	// clears all visible episode checkboxes and the season selectors
	$('.clearAll').on('click', function() { checkState(!1); });

	function setEpisodeSceneNumbering(forSeason, forEpisode, sceneSeason, sceneEpisode) {
		var show = $('#tvid-prodid').val();

		if ('' === sceneSeason) sceneSeason = null;
		if ('' === sceneEpisode) sceneEpisode = null;

		$.getJSON($.SickGear.Root + '/home/set-scene-numbering',
			{
				'tvid_prodid': show,
				'for_season': forSeason,
				'for_episode': forEpisode,
				'scene_season': sceneSeason,
				'scene_episode': sceneEpisode
			},
			function(data) {
				//	Set the values we get back
				var value = ((null === data.sceneSeason || null === data.sceneEpisode)
						? '' : data.sceneSeason + 'x' + data.sceneEpisode);
				$(document.getElementById('sceneSeasonXEpisode_' + show + '_' + forSeason + '_' + forEpisode))
					.val(value).attr('value', value);
				if (!data.success)
					alert(data.errorMessage ? data.errorMessage : 'Update failed.');
			}
		);
	}

	function setAbsoluteSceneNumbering(forSeason, forEpisode, sceneAbsolute) {
		var show = $('#tvid-prodid').val();

		if ('' === sceneAbsolute)
			sceneAbsolute = null;

		$.getJSON($.SickGear.Root + '/home/set-scene-numbering',
			{
				'tvid_prodid': show,
				'for_season': forSeason,
				'for_episode': forEpisode,
				'scene_absolute': sceneAbsolute
			},
			function(data) {
				//	Set the values we get back
				var value = (null === data.sceneAbsolute ? '' : data.sceneAbsolute);
				$(document.getElementById('sceneAbsolute_' + show + '_' + forSeason + '_' + forEpisode))
					.val(value).attr('value', value);
				if (!data.success)
					alert(data.errorMessage ? data.errorMessage : 'Update failed.');
			}
		);
	}

	function qTips(select$){
		select$.each(function() {
			$(this).qtip({
				show: {solo:true},
				position: {viewport:$(window), my:'left center', adjust:{y:-10, x:2}},
				style: {classes:'qtip-dark qtip-rounded qtip-shadow qtip-maxwidth'}
			});
		});
	}
	qTips($('.addQTip'));

	function tableInit(table$) {
		$('#sbRoot').ajaxEpSearch();
		$('#sbRoot').ajaxEpSubtitlesSearch();

		if ($.SickGear.config.useFuzzy) {
			fuzzyMoment({
				containerClass: '.airdate',
				dateHasTime: !1,
				dateFormat: $.SickGear.config.dateFormat,
				timeFormat: $.SickGear.config.timeFormat,
				trimZero: $.SickGear.config.fuzzyTrimZero
			});
		}

		table$.each(function (i, obj) {
			$(obj).has('tbody.collapse tr').tablesorter({
				widgets: ['zebra'],
				selectorHeaders: '> thead tr.tablesorter-headerRow th',
				textExtraction: {
					'.tablesorter-ep-num': function(node) {
						var n = /(\d+)\)?$/img.exec(''+$(node).find('span').text()); return (null == n ? '' : n[1]); },
					'.tablesorter-ep-scene': function(node) {
							var n = $(node).find('input'); return n.val() || n.attr('placeholder'); },
					'.tablesorter-airdate': function(node) { return $(node).find('span').attr('data-airdate') || ''; }
				},
				headers: {
					'.tablesorter-no-sort': {sorter: !1, parser: !1},
					'.tablesorter-ep-num': {sorter: 'digit'},
					'.tablesorter-airdate': {sorter: 'digit'}
				}
			});

			$(obj).find('.seasonCheck').on('click', function() {
				var seasCheck = this, seasNo = $(seasCheck).attr('id');

				$(obj).find('.epCheck:visible').each(function() {
					var epParts = $(this).attr('id').split('x');
					if (epParts[0] == seasNo)
						this.checked = seasCheck.checked

				});
			});

			var lastCheck = null;
			$(obj).find('.epCheck').on('click', function(event) {

				if (!lastCheck || !event.shiftKey) {
					lastCheck = this;
					return;
				}

				var check = this, found = 0;
				$(obj).find('.epCheck').each(function() {
					switch(found) {
						case 2:
							return !1;
						case 1:
							this.checked = lastCheck.checked;
					}
					(this == check || this == lastCheck) && found++;
				});
				lastCheck = this;
			});

			qTips($(obj).find('.addQTip'));
			plotter($(obj).find('.plotInfo'));

			$(obj).find('.sceneSeasonXEpisode').change(function() {
				//	Strip non-numeric characters
				$(this).val($(this).val().replace(/[^0-9xX]*/g, ''));

				var forSeason = $(this).attr('data-for-season'),
					forEpisode = $(this).attr('data-for-episode'),
					m = $(this).val().match(/^(\d+)x(\d+)$/i),
					sceneSeason = m && m[1] || null, sceneEpisode = m && m[2] || null;

				setEpisodeSceneNumbering(forSeason, forEpisode, sceneSeason, sceneEpisode);
			});

			$(obj).find('.sceneAbsolute').change(function() {
				//	Strip non-numeric characters
				$(this).val($(this).val().replace(/[^0-9]*/g, ''));

				var forSeason = $(this).attr('data-for-season'),
					forEpisode = $(this).attr('data-for-episode'),
					m = $(this).val().match(/^(\d{1,4})$/i),
					sceneAbsolute = m && m[1] || null;

				setAbsoluteSceneNumbering(forSeason, forEpisode, sceneAbsolute);
			});
		});
	}
	tableInit($('.sickbeardTable'));

	$.SickGear.season = [];
	$.SickGear.run = !1;
	$('button[id*="showseason-"]').on('click', function() {
		var that = this, this$ = $('#' + this.id), table$ = this$.parents('.sickbeardTable');

		if (0 < table$.find('tbody').find('tr').length) {
			table$.toggleClass('open');
		} else {
			table$.find('span.images').toggleClass('hide');
			this$.toggleClass('hide');
			function fetchSeason() {
				if (0 == $.SickGear.season.length)
					return;

				var season = $.SickGear.season[0];
				$.SickGear.season.shift();
				$.getJSON($.SickGear.Root + '/home/season-render', {'tvid_prodid': $('#tvid-prodid').val(), 'season': season},
					function(data) {
						if (!data.success) {
							alert('Season listing failed.');
						} else {
							table$.find('tbody').html(data.success);
							tableInit(table$);
						}
						table$.toggleClass('open');
						this$.toggleClass('hide');
						table$.find('span.images').toggleClass('hide');
						fetchSeason()
					}
				);
			}
			$.SickGear.season.push(this.id);
			var result = [];
			$.each($.SickGear.season, function(i, e) {
				if (-1 == $.inArray(e, result)) result.push(e);
			});
			$.SickGear.season = result;
			if (!$.SickGear.run && 1 == $.SickGear.season.length) $.SickGear.run = !0 && fetchSeason();
		}
		return !1;
	});

	$('button.allseasons').on('click', function() {
		$('table.sickbeardTable:not(.display-season)').each(function() {
			$(this).find('button[id*="showseason-"]').click();
		});

		var liveStates = $('#display-show');
		return liveStates.toggleClass('min'), $.get($.SickGear.Root + '/live-panel/?allseasons='
			+ String.prototype.toLowerCase.apply(+liveStates.hasClass('min'))), !1;
	});

});
