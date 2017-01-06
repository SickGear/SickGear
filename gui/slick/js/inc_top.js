/** @namespace $.SickGear.Root */
/** @namespace style.sheet */

function initHeader(){
	//settings
	var header = $('.header'), fadeSpeed = 100, fadeTo = 0.8, topDistance = 20, inside = !1;
	var topbarML = function(){$(header).fadeTo(fadeSpeed, fadeTo);},
		topbarME = function(){$(header).fadeTo(fadeSpeed, 1);};

	$(window).scroll($.debounce(250, function(){
		var position = $(window).scrollTop();
		if (position > topDistance && !inside){
			//add events
			topbarML();
			$(header).bind('mouseenter', topbarME);
			$(header).bind('mouseleave', topbarML);
			inside = !0;
		} else if (position < topDistance){
			topbarME();
			$(header).unbind('mouseenter', topbarME);
			$(header).unbind('mouseleave', topbarML);
			inside = !1;
		}
	}));
}

function showMsg(msg, loader, timeout, ms){
	var feedback = $('#ajaxMsg'), update = $('#updatebar');

	if (update.is(':visible')){
		var height = update.height() + 35;
		feedback.css('bottom', height + 'px');
	} else {
		feedback.removeAttr('style');
	}
	feedback.fadeIn();

	var message = $('<div class="msg">' + msg + '</div>');
	if (loader){
		message = $('<div class="msg"><img src="interfaces/default/images/loader_black.gif" alt="loading" class="loader" style="position:relative;top:10px;margin-top:-15px;margin-left:-10px">' + msg + "</div>");
		feedback.css('padding', '14px 10px')
	}
	$(feedback).prepend(message);
	if (timeout){
		setTimeout(function(){
			message.fadeOut(function(){
				$(this).remove();
				feedback.fadeOut();
			});
		}, ms);
	}
}

function preventDefault(){
	$('a[href="#"]').on('click', function(){
		return !1;
	});
}

function initFancybox(){
	if (0 < $('a[rel*=dialog]').length){
		$.getScript($.SickGear.Root + '/js/fancybox/jquery.fancybox.js', function(){
			$('head').append('<link rel="stylesheet" href="' + $.SickGear.Root + '/js/fancybox/jquery.fancybox.css">');
			$('a[rel*=dialog]').fancybox({
				type: 'image',
				padding: 0,
				helpers : {title : null, overlay : {locked: !1, css : {'background': 'rgba(0, 0, 0, 0.4)'}}}
			});
		});
	}
}

function initTabs(){
	$('#config-components').tabs({
		activate: function(event, ui){

			var lastOpenedPanel = $(this).data('lastOpenedPanel');
			var selected = $(this).tabs('option', 'selected');

			if (lastOpenedPanel){
			} else {
				lastOpenedPanel = $(ui.oldPanel)
			}

			if (!$(this).data('topPositionTab')){
				$(this).data('topPositionTab', $(ui.newPanel).position()['top'])
			}

			//Dont use the builtin fx effects. This will fade in/out both tabs, we dont want that
			//Fadein the new tab yourself
			$(ui.newPanel).hide().fadeIn(0);

			if (lastOpenedPanel){

				// 1. Show the previous opened tab by removing the jQuery UI class
				// 2. Make the tab temporary position:absolute so the two tabs will overlap
				// 3. Set topposition so they will overlap if you go from tab 1 to tab 0
				// 4. Remove position:absolute after animation
				lastOpenedPanel
					.toggleClass('ui-tabs-hide')
					.css('position', 'absolute')
					.css('top', $(this).data('topPositionTab') + 'px')
					.fadeOut(0, function(){
						$(this)
							.css('position', '');
					});
			}
			//Saving the last tab has been opened
			$(this).data('lastOpenedPanel', $(ui.newPanel));
		}
	});
}

var isFontFaceSupported = (function(){
	var ua = navigator.userAgent;
	if (!!ua.match(/Android 2.[01]/)) return !1;

	var sheet, doc = document, head = doc.head || doc.getElementsByTagName('head')[0] || doc.documentElement,
		style = doc.createElement('style'), impl = doc.implementation || {hasFeature: function(){return !1;}};
	style.type = 'text/css';
	head.insertBefore(style, head.firstChild);
	sheet = style.sheet || style.styleSheet;

	var supportAtRule = impl.hasFeature('CSS2', '') ?
		function(rule){
			if (!(sheet && rule)) return !1;
			var result = !1;
			try {
				sheet.insertRule(rule, 0);
				result = !(/unknown/i).test(sheet.cssRules[0].cssText);
				sheet.deleteRule(sheet.cssRules.length - 1);
			} catch(e){}
			return result;
		} :
		function(rule){
			if (!(sheet && rule)) return !1;
			sheet.cssText = rule;

			return 0 !== sheet.cssText.length
				&& !(/unknown/i).test(sheet.cssText)
				&& 0 === sheet.cssText
					.replace(/\r+|\n+/g, '')
					.indexOf(rule.split(' ')[0]);
		};
	return supportAtRule('@font-face {font-family:"font";src:"' + $.SickGear.Root + '/fonts/isfontface.otf";}');
})();

function setStyle(theme){
	var style$;
	$(['light','dark']).each(function(i, e){
		if ((style$ = $('link[rel*="stylesheet"][href*="' + e + '"]')).length){
			style$.disabled = !0;
			if (/undefined/i.test(typeof theme))
				theme = 'light' === e ? 'dark' : 'light'; // toggle style
			style$.attr('href', style$.attr('href').replace(e, theme));
			$.cookieJar('sg').set('theme', theme);
			style$.disabled = !1;
			return !1;
		}
	});
}
$.cookie = !0;
var theme = $.cookieJar('sg').get('theme'), set = !/undefined/i.test(typeof theme) && setStyle(theme);

$(function(){
	initHeader();
	preventDefault();
	initFancybox();
	initTabs();

	var body$ = $('body'), tailloc = location.href.replace(/.*([/][^_/?]+)[\w_/?].*?$/, '$1'),
		activemenu$ = $('.dropdown.active .dropdown-menu li');
	if (-1 !== tailloc.indexOf('displayShow')){
		tailloc = location.href.replace(/.*([/].*?)$/, '$1');
	}
	if (!activemenu$.find('a[href$="' + tailloc + '/"]').addClass('active').length)
		activemenu$.find('a[href*="' + tailloc + '"]').addClass('active');
	$('.dropdown-toggle').dropdownHover();
	$('#theme').click(function(){setStyle();});
	(/undefined/i.test(document.createElement('input').placeholder)) && body$.addClass('no-placeholders');
	if (isFontFaceSupported){
		body$.removeClass('noicons');
		$('nav').find('.text-home').hide();
	}

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
			var that = $(this), viewing='add-show', view='added-last', t;
			if (viewing === that.attr('data-view')){
				t = viewing;
				viewing = view;
				view = t;
			}
			that.attr('data-view', viewing);
			that.closest('.dropdown-menu')
				.find('.' + viewing).fadeOut('fast', 'linear', function(){
					that.closest('.dropdown-menu')
						.find('.' + view).fadeIn('fast', 'linear', function(){
							return !1;
					});
				});
		})
});
