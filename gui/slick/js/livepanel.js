/** @namespace $.SickGear.Root */
/** @namespace config.hasArt */
/** @namespace config.panelTitles */
$(document).ready(function() {

	var panel$ = $('#livepanel'),
		pTitle = config.panelTitles || [],
		isEpisodeView = !!$('#episode-view').length,
		liveStates$ = $(isEpisodeView ? '#episode-view' : '#display-show'),
		jqTooltipUsed = /(?!undefined)/i.test(typeof($('body').tooltip)),
		group = 'group', fave = 'fave', avoid = 'avoid', ratingVerbs = [group, fave, avoid].join(' ');

	panel$.removeClass('off');

	$('#viewart').on('click', function() {
		var state = 0, on = '', result = !1;

		if (isEpisodeView) {
			if (isSet('open-gear')) {
				state = 4; on = 'viewart';
			} else if (!isSet('viewart')) {
				state = 3; on = 'open-gear';
			}
		} else if (!isSet('back-art')) {
			if (!isSet('poster-right')) {
				state = 1; on = 'poster-right';
			}
		} else if (isSet('open-gear')) {
			state = 4; on = 'viewart';
		} else if (isSet('poster-off')) {
			state = 3; on = 'open-gear';
		} else if (isSet('poster-right')) {
			state = 2; on = 'poster-off';
		} else if (!isSet('viewart')) {
			state = 1; on = 'poster-right';
		}
		liveStates$.removeClass('poster-right poster-off open-gear viewart').addClass(on);
		if (state !== 4 && !!$('a[rel="glide"]').length) {
			$.calcSlideCount(!1);
		}
		refreshTitles($(this).attr('id'));
		send('viewart=' + state);

		var container = [];
		$.each($('[id^=day]'), function() { container.push($('#' + $(this).attr('id'))) });
		$.each(container, function() { $(this).isotope('layout') });

		return result;
	});

	$('#back-art,#translucent').on('click', function() {
		var result = !1,
			highlight = panel$.hasClass('highlight-off') ||
					panel$.hasClass('highlight2') && panel$.removeClass('highlight2').addClass('highlight1') ||
					panel$.hasClass('highlight1') &&  panel$.removeClass('highlight1').addClass('highlight') ||
					panel$.removeClass('highlight').addClass('highlight-off');

		if (config.hasArt) {
			var elid = $(this).attr('id');

			liveStates$.toggleClass(elid);
			refreshTitles(elid);
			if ('back-art' === elid){
				$.calcSlideCount(!1);
			}
			send(elid.replace('-', '') + '=' + String.prototype.toLowerCase.apply(+isSet(elid)));
		}
		return result;
	});

	$('#proview').on('click', function() {
		var state = 0, on = 'reg', result = !1;

		if (!isEpisodeView && isSet('viewart')) {
			liveStates$.toggleClass('allart');
		} else {
			if (isSet('reg')) {
				state = 1; on = 'pro';
			} else if(isSet('back-art') && !isSet('allart')) {
				if (isSet('ii')) {
					state = 3; on = 'pro ii allart';
				} else if (isSet('pro')) {
					state = 2; on = 'pro ii';
				}
			}
			liveStates$.removeClass('reg pro ii allart').addClass(on);
			send('viewmode=' + state);
		}
		maybeBackground();
		refreshTitles($(this).attr('id'));
		return result;
	});

	/*
	 * back art related
	 */
	function maybeArrows() {
		var backArts$ = $('#background-container'), result = !0;

		if (isSet('allart')
			|| (!isSet(fave) &&
				(1 < backArts$.find('li.' + group).length ||
				(1 != backArts$.find('li.' + group).length && 1 < backArts$.find('li').not('.' + group + ',.' + avoid).length)))
			|| (isEpisodeView &&
				1 < (backArts$.find('li.' + group).length + backArts$.find('li.' + fave).length +
				backArts$.find('li').not('.' + group + ',.' + avoid).length))) {
			liveStates$.removeClass('oneof');
		} else {
			liveStates$.addClass('oneof');
		}
		return result
	}

	function setArt(dir) {
		var backArts$ = $('#background-container'), curArt$ = backArts$.find('li.background'),
			faveArt$ = backArts$.find('li.' + fave), result = !0,
			newArt$, init = !1, noArt = function(el) { return /undefined/i.test(typeof(el.css('background-image'))); },
			viewable = !isSet('allart') && !!backArts$.find('li.' + group).length ? (isEpisodeView ? '': '.' + group) : '',
			mayAvoid = !isSet('allart') ? '.' + avoid : '.showall',
			artBefore$ = curArt$.prevAll(viewable).not(mayAvoid),
			artAfter$ = curArt$.nextAll(viewable).not(mayAvoid);

		switch (dir) {
			case 'next':
				if (noArt(newArt$ = artAfter$.first()) && noArt(newArt$ = artBefore$.last())
					&& noArt(newArt$ = curArt$))
					newArt$ = null;
				break;
			case 'prev':
				if (noArt(newArt$ = artBefore$.first()) && noArt(newArt$ = artAfter$.last())
					&& noArt(newArt$ = curArt$))
					newArt$ = null;
				break;
			case 'init':
				init = !0;
				if (noArt(newArt$ = curArt$))
					newArt$ = null;
				break;
			case fave:
				newArt$ = faveArt$;
				break;
		}

		if (!init || (null == newArt$))
			curArt$.addClass('background-rem').removeClass('background')
				.fadeOut(800, 'linear', function() {$(this).removeClass('background-rem')});

		if (null !== newArt$) {
			newArt$.addClass('background').fadeIn(800, 'linear', function () {
				$(this).removeClass('first-load')
			});

			liveStates$.removeClass(ratingVerbs).addClass(
				newArt$.hasClass(group) && group || newArt$.hasClass(fave) && fave || newArt$.hasClass(avoid) && avoid || '');
		}

		maybeArrows();
		refreshTitles();
		return result;
	}
	setArt('init');

	function maybeBackground() {
		var backArts$ = $('#background-container'), result = !0;

		if (isSet('allart')) {
			if (!backArts$.find('li.background').length) {
				backArts$.find('li').first().hide().addClass('background')
					.fadeIn(400, 'linear', function() {$(this).removeClass('first-load')});
			}
		} else {
			if (backArts$.find('li.' + fave).not('.background').length) {
				setArt(fave);
			} else if (!!backArts$.find('li.' + avoid).length
				&& backArts$.find('li.' + avoid).length == backArts$.find('li').length) {
				backArts$.find('li.' + avoid).fadeOut(800, 'linear', function () {
					$(this).removeClass('background')
				});
			} else if (backArts$.find('li.background.' + avoid).length) {
				setArt('next');
			}
		}
		maybeArrows();
		return result;
	}

	$('#art-next,#art-prev').on('click', function() {
		return (!(setArt('art-prev' === $(this).attr('id') ? 'prev' : 'next')));
	});

	function key(e, kCode){
		return e.hasOwnProperty('ctrlKey') && e.ctrlKey && e.hasOwnProperty('altKey') && e.altKey && (kCode == e.which)
	}
	$(document).on('keyup', function(e) {
		var left = key(e, 37), up = key(e, 38), right = key(e, 39), down = key(e, 40),
			s = key(e, 83), a = key(e, 65), f = key(e, 70), g = key(e, 71);
		return (
			(!isSet('oneof') && ((left && setArt('prev')) || (right && setArt('next'))))
			|| (s && liveStates$.toggleClass('allart') && maybeBackground() && refreshTitles('proview'))
			|| (g && setGroup()) || (up && setGroup() && (!isSet('allart') && $('#viewart').click() || !0))
			|| (a && setAvoid()) || (down && setAvoid() && (!isSet('allart') && $('#translucent').click() || !0))
			|| (f && setFave())
		);
	});

	function rate(state, rating) {
		var result = !0;

		if (isSet('allart')) {
			var rated = rating && isSet(rating);
			liveStates$.removeClass(ratingVerbs);
			if (rated) {
				state = 0;
				rating = '';
			} else
				liveStates$.addClass(rating);

			var curArt$ = $('#background-container').find('li.background'),
				art = /\?([^"]+)"/i.exec(curArt$.css('background-image'));
			if (null != art) {
				send('rate=' + state + '&' + art[1]);
				curArt$.removeClass().addClass((!!rating.length ? rating + ' ' : '') + 'background');
			}
			maybeBackground();
			refreshTitles('rate-art');
		}
		return result;
	}
	function setAvoid() {return rate(30, avoid);}
	function setFave() {return rate(20, fave);}
	function setGroup() {return rate(10, group);}
	function setRnd() {return rate(0, '');}
	$('#rate-art').on('click', function() {
		return isSet('allart') &&
			((isSet(fave) && setAvoid()) || (isSet(group) && setFave()) || (!isSet(avoid) && setGroup()) || setRnd()) || !0;
	});

	/*
	 * support functions
	 */
	function isSet(name) {return liveStates$.hasClass(name)}

	function send(value) {
		return $.get($.SickGear.Root + '/live_panel/?' + value + '&pg=' + (isEpisodeView ? 'ev' : 'ds'))}

	if (jqTooltipUsed) {
		panel$.find('a[title]').tooltip({placement: 'top', html: !0});
	}

	function refreshTitle(target$, title, refreshAll) {
		return jqTooltipUsed
			? target$.attr('data-original-title', title.replace(/<[\/]?em>/g, '')).tooltip('fixTitle') && refreshAll //|| target$.tooltip('show')
			: target$.attr('title', title);
	}

	function refreshTitles(id) {
		if (!$('#livepanel').length) return;

		var refreshAll = /undefined/i.test(typeof(id)), elId = !refreshAll && id.replace('#', '') || id, result = !0;
		if ('viewart' === elId || refreshAll) {
			refreshTitle($('#viewart'),
				isSet('poster-right') ? pTitle['viewart1']
					: (isSet('back-art') ?
						(isSet('viewart') ? pTitle['viewart4']
							: (isSet('open-gear') ? pTitle['viewart3']
							: (isSet('poster-off') ? pTitle['viewart2']
							: (isEpisodeView ? pTitle['viewmode0'] : pTitle['viewart0']))))
						: (isEpisodeView ? pTitle['viewmode0'] : pTitle['viewart0'])),
			refreshAll);
		}
		if ('translucent' === elId || refreshAll) {
			refreshTitle($('#translucent'), isSet('translucent') ? pTitle['translucent_on'] : pTitle['translucent_off'],
				refreshAll);
		}
		if (config.hasArt && ('back-art' === elId || refreshAll)) {
			refreshTitle($('#back-art'), isSet('back-art') ? pTitle['backart_on'] : pTitle['backart_off'],
				refreshAll);
		}
		if ('rate-art' === elId || refreshAll) {
			refreshTitle($('#rate-art'),
				isSet(avoid) ? pTitle['rateart3']
					: (isSet(fave) ? pTitle['rateart2']
					: (isSet(group) ? pTitle['rateart1']
					: pTitle['rateart0'])),
				refreshAll);
		}
		if ('proview' === elId || refreshAll) {
			refreshTitle($('#proview'),
				isSet('back-art') ?
					(isSet('allart') ? pTitle['viewmode3']
						: (isSet('ii') ? pTitle['viewmode2']
						: (isSet('pro') ? pTitle['viewmode1']
						: pTitle['viewmode0'])))
					: (isSet('pro') ? pTitle['viewmode1']
						: pTitle['viewmode0']),
				refreshAll);
		}
		return result;
	}
	refreshTitles();

});
