/** @namespace $.SickGear.Root */
/** @namespace content.path */
/** @namespace content.hSize */
/** @namespace content.nFiles */
/** @namespace content.hLargest */
/** @namespace content.hSmallest */
/** @namespace content.hAverageSize */

function updateMenus(){
	const items = ['home', 'manage', 'config', 'tools'];
	for (let i = 0; i < items.length; i++) {
		updateMenu(items[i]);
	}
}

function updateMenu(menuHeader) {
	const dev = !1,
		window$ = $(window),
		menu$ = $(`#NAV${menuHeader}`).find('.dropdown-menu'),
		menu = menu$[0],
		ms = menu.style,
		visibleHeight = window$.height() - 50,
		scrollbarWidth = window.innerWidth - window$.width();
		
	const originalStyles = {position: ms.position, opacity: ms.opacity, visibility: ms.visibility, display: ms.display};
	// make menu element non visible but allow it into the page flow
	menu$.css({'position': 'absolute', 'opacity': '0', 'visibility': 'hidden'});
	menu$.css({'display': 'block'}); 	
	const menuRect = menu.getBoundingClientRect();  // position and dimensions
	menu$.css(originalStyles);

	dev && console.log('menu=', menu, 'winh=', visibleHeight, 'barw=', scrollbarWidth, 'menuw', parseInt(ms.minWidth, 10));
	dev && console.log('menuRect', menuRect);

	// store menu width once* on DOM load
	if (/undefined/.test(menu$.data('initial-width'))) {
		menu$.attr('data-initial-width', menuRect.width);
		menu$.attr('data-initial-height', menuRect.height);
	}

	let width = parseInt(menu$.data('initial-width'), 10),
		height = parseInt(menu$.data('initial-height'), 10);
	dev && console.log("menuRect.height > visibleHeight = ", menuRect.height > visibleHeight, "height > visibleHeight", height > visibleHeight);
	if (visibleHeight > 0 && (menuRect.height > visibleHeight || height > visibleHeight)) {
		width = width + scrollbarWidth;
	}
	menu$.css({
		'min-width': `${width}px`,
		'max-height': `${visibleHeight}px`,
		'overflow-y': 'auto'
	});
}

function setStyle(){
	let style$, fromTheme='light', toTheme = 'dark';

	if (!(style$ = $('link[rel*="stylesheet"][href*="light"]')).length){
		style$ = $('link[rel*="stylesheet"][href*="dark"]');
		fromTheme='dark';
		toTheme = 'light';
	}
	style$.disabled = !0;
	style$.attr('href', style$.attr('href').replace(fromTheme, toTheme));
	$.get($.SickGear.Root + '/add-shows/toggle-theme',
		{'theme': toTheme});
	style$.disabled = !1;
	return !0;
}

$(function(){
	// handle menus heights on init and when window is resized
	$(window).on('resize', updateMenus).resize(); // also executes func immediately on load

	// handle menus heights on init and when window is resized
	let activemenu$ = $('.dropdown.active .dropdown-menu li');
	let tailloc = location.href.replace(/.*\/([^\/]+)\/?$/, '/$1');
	if (-1 !== tailloc.indexOf('view-show')){
		tailloc = location.href.replace(/.*\/([^\/]+)\/?$/, '$1');
	}
	if (!activemenu$.find('a[href$="' + tailloc + '/"]').addClass('active').length)
		activemenu$.find('a[href*="' + tailloc + '"]').addClass('active');

	// use library to enable dropdown menus on the jquery selected elements
	$('.dropdown-toggle').dropdownHover();

	// add event to change theme on click of the selected element
	$('#theme').click(function(){setStyle();});

	(/undefined/i.test(document.createElement('input').placeholder)) && $('body').addClass('no-placeholders');

	$('.bubblelist').on('click', '.list .item a', function(){
		var bubbleAfter$ = $('#bubble-after'),
			lastBubble$ = $('.bubble.last'), toBubble = $(this).attr('href').replace('#', ''),
			doLast = (lastBubble$.length && toBubble === lastBubble$.find('div[name*="section"]').attr('name'));

		doLast && lastBubble$.removeClass('last');
		(bubbleAfter$.length && bubbleAfter$ || $(this).closest('.component-group')).after(
			$('[name=' + $(this).attr('href').replace('#','') + ']').closest('.component-group')
		);
		doLast && $('.bubble').last().addClass('last');
		return !1;
	});

	var search = function(){
		var link$ = $('#add-show-name'), text = encodeURIComponent(link$.find('input').val()),
			param = '?show_to_add=|||' + text + '&use_show_name=True';
		window.location.href = link$.attr('data-href') + (!text.length ? '' : param);
	}, removeHref = function(){$('#add-show-name').removeAttr('href');};
	$('#add-show-name')
		.on('click', function(){ search(); })
		.hover(function() {$(this).attr('href', $(this).attr('data-href'));}, removeHref);
	$('#add-show-name input')
		.hover(removeHref)
		.on('click', function(e){ e.stopPropagation(); })
		.on('focus', function(){$.SickGear.PauseCarousel = !0;})
		.on('blur', function(){delete $.SickGear.PauseCarousel;})
		.keydown(function(e){
			if (13 === e.keyCode) {
				e.stopPropagation();
				e.preventDefault();
				search();
				return !1;
			}
		});

	$('#NAVhome').find('.dropdown-menu li a#add-view')
		.on('click', function(e){
			e.stopPropagation();
			e.preventDefault();
			var that = $(this), view=['add-tab1', 'add-tab2', 'add-tab3'], i, is, to;
			for(i = 0; i < view.length; i++){
				if (view[i] === that.attr('data-view')){
					is = view[i];
					to = view[((i + 1) === view.length) ? 0 : i + 1];
					break;
				}
			}
			that.attr('data-view', to);
			that.closest('.dropdown-menu')
				.find('.' + is).fadeOut('fast', 'linear', function(){
					that.closest('.dropdown-menu')
						.find('.' + to).fadeIn('fast', 'linear', function(){
							return !1;
					});
				});
		})

	$('[data-size] .ui-size, #data-size').each(function(){
		$(this).qtip({
			content:{
				text: function(event, api){
					// deferred object ensuring the request is only made once
					var tvidProdid = $('#tvid-prodid').val(), tipText = '';
					if (/undefined/i.test(tvidProdid)){
						tvidProdid = $(event.currentTarget).closest('[data-tvid_prodid]').attr('data-tvid_prodid');
					}
					$.getJSON($.SickGear.Root + '/home/media_stats', {tvid_prodid: tvidProdid})
						.then(function(content){
							// on success...
							if (/undefined/.test(content[tvidProdid].message)){
								tipText = (1 === content[tvidProdid].nFiles
									? '<span class="grey-text">One media file,</span> ' + content[tvidProdid].hAverageSize
									: '' + content[tvidProdid].nFiles + ' <span class="grey-text">media files,</span>'
										+ ((content[tvidProdid].hLargest === content[tvidProdid].hSmallest)
											? (content[tvidProdid].hAverageSize + ' <span class="grey-text">each</span>')
											: ('<br><span class="grey-text">largest</span> ' + content[tvidProdid].hLargest + ' <span class="grey-text">(<span class="tip">></span>)</span>'
												+ '<br><span class="grey-text">smallest</span> ' + content[tvidProdid].hSmallest + ' <span class="grey-text">(<span class="tip"><</span>)</span>'
												+ '<br><span class="grey-text">average size</span> ' + content[tvidProdid].hAverageSize + ' <span class="grey-text">(<span class="tip-average"><i>x</i></span>)</span>')));
							} else {
								tipText = '<span class="grey-text">' + content[tvidProdid].message + '</span>';
							}
							api.set('content.text',
								tipText + '<div style="width:100%; border-top:1px dotted; margin-top:3px"></div>'
										+ '<div style="margin-top:3px">' + '<span class="grey-text">location size</span> ' + content[tvidProdid].hSize + ' <span class="grey-text">(<span class="tip">&Sigma;</span>)</span>' + '</div>'
										+ content[tvidProdid].path);
						}, function(xhr, status, error){
								// on fail...
								api.set('content.text', status + ': ' + error);
						});
					return 'Loading...'; // set initial text
				}
			},
			show: {solo: true},
			position: {viewport: $(window), my: 'left center', adjust: {y: -10, x: 0}},
			style: {classes: 'qtip-dark qtip-rounded qtip-shadow'}
		});
	});

});
