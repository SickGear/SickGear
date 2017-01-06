function initMousetrap(){

	// ESC switch between window and element focus
	var focused$ = !1;
	Mousetrap(document.querySelector('body')).bind('esc', function(){
		var el$ = $('input:focus, select:focus');
		if (!el$.length) {
			if ((!1 === focused$) || (0 === focused$.length))
				focused$ = $('.mt-esc:first');
			if (!!focused$.length)
				focused$.focus();
			focused$ = !1;
		} else {
			focused$ = el$;
			focused$.blur();
		}
	});

	// key combos for menu items
	function goMenu(item){
		$('.navbar-nav').find('a[href$="' + item + '"]')[0].click();
	}
	function goMenuIn(item){
		$('.navbar-nav').find('a[href*="' + item + '"]')[0].click();
	}
	Mousetrap.bind({
		// show + ...
		's l': function(){goMenu('showlistView/')}, 's e': function(){goMenu('episodeView/')},
		's h': function(){goMenu('history/')},
		's s': function(){goMenu('new_show/')}, 's t': function(){goMenu('trakt_default/')},
		's i': function(){goMenu('imdb_default/')}, 's a': function(){goMenu('anidb_default/')},
		// manage + ...
		'm m': function(){goMenu('postprocess/')}, 'm b': function(){goMenu('bulk/')},
		'm o': function(){goMenu('Overview/')}, 'm s': function(){goMenu('Searches/')},
		'm p': function(){goMenu('Processes/')}, 'm e': function(){goMenu('Statuses/')},
		'm f': function(){goMenu('failedDownloads/')}, 'm u': function(){goMenu('Missed/')},
		// config + ...
		'c g': function(){goMenu('general/')}, 'c m': function(){goMenu('providers/')},
		'c s': function(){goMenu('search/')}, 'c u': function(){goMenu('subtitles/')},
		'c p': function(){goMenu('Processing/')}, 'c n': function(){goMenu('notifications/')},
		'c a': function(){goMenu('anime/')},
		// tools + ...
		't a': function(){goMenu('about/')},
		't u': function(){goMenu('Check/')}, 't c': function(){goMenu('changes')},
		't e': function(){goMenu('errorlogs/')}, 't f': function(){goMenu('viewlog/')},
		't i': function(){goMenu('import_shows/')}, 't l': function(){goMenu('logout/')},
		't r': function(){goMenuIn('restart')}, 't s': function(){goMenuIn('shutdown')}
	});

	// key combos for tabs
	var tab = 1;
	$('div[id^="core-component-group"]').each(function(){
		// tab + ... 1, 2, 3, 4
		Mousetrap.bind('t ' + tab++, function(e, kc){
			var k = kc.split(' ');
			if (2 === k.length){
				var n = parseInt(k[k.length - 1], 10);
				if (0 < n < 5)
					$('#config-components').tabs('option', 'active', n - 1)
			}
		});
	});

	// key combos for specific pages
	var pageId = $('body').attr('id');
	if (/display[-]show/i.test(pageId)) {
		Mousetrap.bind({
			'e': function(){$('#SubMenu').find('a[href*="editShow"]')[0].click()},
			'p': function(){$('#SubMenu').find('a[href*="toggle_paused"]')[0].click()}
		});
	} else if (/edit[-]show/i.test(pageId)) {
		Mousetrap.unbind('esc');
		Mousetrap.bind({
			'esc': function(){$('#editShow').find('a[href*="displayShow"]')[0].click()}
		});
	}

	// key combos for config items
	if (/\/config\//i.test(location.href)){
		// more/less gear + ...
		Mousetrap.bind(['m g', 'l g'], function(){
			$('.feature-toggle:first').click()
		});

		// save
		Mousetrap.bind(['ctrl+s', 'meta+s'], function(){
			$('.config_submitter:first').click();
			return !1;
		});
	}

}

$(document).ready(function(){
	!/undefined/i.test(typeof(Mousetrap)) && initMousetrap();

	$('.toolbar')
		.controlgroup()
		.find('select').each(function(i, select){
			var ctrlElId = '#' + select.id;
			$(ctrlElId).find('.selected').each(function(i, elSelected){
				$(ctrlElId + '-menu').find('.ui-menu-item').eq(elSelected.index).addClass('selected');
			});
	});
	$('.ui-widget.regex').button({'icon':'ui-icon-star'});
	$('.ui-widget.undo').button({'icon':'ui-icon-arrowreturnthick-1-w'});
	$('.ui-widget.nolabel').each(function () {$(this).button({'showLabel':!1})});
});
