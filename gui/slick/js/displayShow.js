/** @namespace $.SickGear.Root */
/** @namespace config.TVShowList */
/** @namespace config.useIMDbInfo */
/** @namespace $.SickGear.config.useFuzzy */
/** @namespace $.SickGear.config.dateFormat */
/** @namespace $.SickGear.config.timeFormat */
/** @namespace $.SickGear.config.fuzzyTrimZero */
$(document).ready(function() {

	// handle the show selection dropbox
	$('#pickShow').change(function() {
		var val = $(this).val();
		if (val != 0)
			window.location.href = $.SickGear.Root + '/home/displayShow?show=' + val;
	});

	$('#prevShow, #nextShow').on('click', function() {
		var select$ = $('#pickShow'),
			index = $.inArray(select$.find('option:selected').val()*1, config.TVShowList);
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

	$('.details-plot').collapser({
		mode: 'lines',
		truncate: 10,
		showText: '<span class="pull-right moreless"><i class="sgicon-arrowdown" style="margin-right:2px"></i>more</span>',
		hideText: '<span class="pull-right moreless"><i class="sgicon-arrowup" style="margin-right:2px"></i>less</span>',
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
			window.location.href = $.SickGear.Root + '/home/setStatus?show=' + $('#showID').val() +
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
		var showId = $('#showID').val(), indexer = $('#indexer').val();

		if ('' === sceneSeason) sceneSeason = null;
		if ('' === sceneEpisode) sceneEpisode = null;

		$.getJSON($.SickGear.Root + '/home/setSceneNumbering',
			{
				'show': showId,
				'indexer': indexer,
				'forSeason': forSeason,
				'forEpisode': forEpisode,
				'sceneSeason': sceneSeason,
				'sceneEpisode': sceneEpisode
			},
			function(data) {
				//	Set the values we get back
				var value = ((null === data.sceneSeason || null === data.sceneEpisode)
						? '' : data.sceneSeason + 'x' + data.sceneEpisode);
				$('#sceneSeasonXEpisode_' + showId + '_' + forSeason + '_' + forEpisode)
					.val(value).attr('value', value);
				if (!data.success)
					alert(data.errorMessage ? data.errorMessage : 'Update failed.');
			}
		);
	}

	function setAbsoluteSceneNumbering(forSeason, forEpisode, sceneAbsolute) {
		var showId = $('#showID').val(), indexer = $('#indexer').val();

		if ('' === sceneAbsolute)
			sceneAbsolute = null;

		$.getJSON($.SickGear.Root + '/home/setSceneNumbering',
			{
				'show': showId,
				'indexer': indexer,
				'forSeason': forSeason,
				'forEpisode': forEpisode,
				'sceneAbsolute': sceneAbsolute
			},
			function(data) {
				//	Set the values we get back
				var value = (null === data.sceneAbsolute ? '' : data.sceneAbsolute);
				$('#sceneAbsolute_' + showId + '_' + forSeason + '_' + forEpisode)
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

	function table_init(table$) {
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
	table_init($('.sickbeardTable'));

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
				$.getJSON($.SickGear.Root + '/home/display_season', {'show': $('#showID').val(), 'season': season},
					function(data) {
						if (!data.success) {
							alert('Season listing failed.');
						} else {
							table$.find('tbody').html(data.success);
							table_init(table$);
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
		return liveStates.toggleClass('min'), $.get($.SickGear.Root + '/live_panel/?allseasons='
			+ String.prototype.toLowerCase.apply(+liveStates.hasClass('min'))), !1;
	});

});
