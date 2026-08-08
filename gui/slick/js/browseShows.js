// to show the hide view set to true
// country alpha 3 ro 2
let cc_alpha3_to_alpha2 = {
	"afg": "af", "ala": "ax", "alb": "al", "dza": "dz", "asm": "as", "and": "ad", "ago": "ao", "aia": "ai", "ata": "aq",
	"atg": "ag", "arg": "ar", "arm": "am", "abw": "aw", "aus": "au", "aut": "at", "aze": "az", "bhs": "bs", "bhr": "bh",
	"bgd": "bd", "brb": "bb", "blr": "by", "bel": "be", "blz": "bz", "ben": "bj", "bmu": "bm", "btn": "bt", "bol": "bo",
	"bih": "ba", "bwa": "bw", "bvt": "bv", "bra": "br", "vgb": "vg", "iot": "io", "brn": "bn", "bgr": "bg", "bfa": "bf",
	"bdi": "bi", "khm": "kh", "cmr": "cm", "can": "ca", "cpv": "cv", "cym": "ky", "caf": "cf", "tcd": "td", "chl": "cl",
	"chn": "cn", "hkg": "hk", "mac": "mo", "cxr": "cx", "cck": "cc", "col": "co", "com": "km", "cog": "cg", "cod": "cd",
	"cok": "ck", "cri": "cr", "civ": "ci", "hrv": "hr", "cub": "cu", "cyp": "cy", "cze": "cz", "dnk": "dk", "dji": "dj",
	"dma": "dm", "dom": "do", "ecu": "ec", "egy": "eg", "slv": "sv", "gnq": "gq", "eri": "er", "est": "ee", "eth": "et",
	"flk": "fk", "fro": "fo", "fji": "fj", "fin": "fi", "fra": "fr", "guf": "gf", "pyf": "pf", "atf": "tf", "gab": "ga",
	"gmb": "gm", "geo": "ge", "deu": "de", "gha": "gh", "gib": "gi", "grc": "gr", "grl": "gl", "grd": "gd", "glp": "gp",
	"gum": "gu", "gtm": "gt", "ggy": "gg", "gin": "gn", "gnb": "gw", "guy": "gy", "hti": "ht", "hmd": "hm", "vat": "va",
	"hnd": "hn", "hun": "hu", "isl": "is", "ind": "in", "idn": "id", "irn": "ir", "irq": "iq", "irl": "ie", "imn": "im",
	"isr": "il", "ita": "it", "jam": "jm", "jpn": "jp", "jey": "je", "jor": "jo", "kaz": "kz", "ken": "ke", "kir": "ki",
	"prk": "kp", "kor": "kr", "kwt": "kw", "kgz": "kg", "lao": "la", "lva": "lv", "lbn": "lb", "lso": "ls", "lbr": "lr",
	"lby": "ly", "lie": "li", "ltu": "lt", "lux": "lu", "mkd": "mk", "mdg": "mg", "mwi": "mw", "mys": "my", "mdv": "mv",
	"mli": "ml", "mlt": "mt", "mhl": "mh", "mtq": "mq", "mrt": "mr", "mus": "mu", "myt": "yt", "mex": "mx", "fsm": "fm",
	"mda": "md", "mco": "mc", "mng": "mn", "mne": "me", "msr": "ms", "mar": "ma", "moz": "mz", "mmr": "mm", "nam": "na",
	"nru": "nr", "npl": "np", "nld": "nl", "ant": "an", "ncl": "nc", "nzl": "nz", "nic": "ni", "ner": "ne", "nga": "ng",
	"niu": "nu", "nfk": "nf", "mnp": "mp", "nor": "no", "omn": "om", "pak": "pk", "plw": "pw", "pse": "ps", "pan": "pa",
	"png": "pg", "pry": "py", "per": "pe", "phl": "ph", "pcn": "pn", "pol": "pl", "prt": "pt", "pri": "pr", "qat": "qa",
	"reu": "re", "rou": "ro", "rus": "ru", "rwa": "rw", "blm": "bl", "shn": "sh", "kna": "kn", "lca": "lc", "maf": "mf",
	"spm": "pm", "vct": "vc", "wsm": "ws", "smr": "sm", "stp": "st", "sau": "sa", "sen": "sn", "srb": "rs", "syc": "sc",
	"sle": "sl", "sgp": "sg", "svk": "sk", "svn": "si", "slb": "sb", "som": "so", "zaf": "za", "sgs": "gs", "ssd": "ss",
	"esp": "es", "lka": "lk", "sdn": "sd", "sur": "sr", "sjm": "sj", "swz": "sz", "swe": "se", "che": "ch", "syr": "sy",
	"twn": "tw", "tjk": "tj", "tza": "tz", "tha": "th", "tls": "tl", "tgo": "tg", "tkl": "tk", "ton": "to", "tto": "tt",
	"tun": "tn", "tur": "tr", "tkm": "tm", "tca": "tc", "tuv": "tv", "uga": "ug", "ukr": "ua", "are": "ae", "gbr": "gb",
	"usa": "us", "umi": "um", "ury": "uy", "uzb": "uz", "vut": "vu", "ven": "ve", "vnm": "vn", "vir": "vi", "wlf": "wf",
	"esh": "eh", "yem": "ye", "zmb": "zm", "zwe": "zw",
	// non-standard code on imdb for west germany
	'xwg': 'West Germany',
}

var nbsp_code = '\xa0';
var iso_show_hidden_filter = false;
var iso_showcards = null;
var iso_tag_container = null;
let languageNames = null;
let regionNamesInEnglish = null;
try {
	languageNames = new Intl.DisplayNames(['en'], {type: 'language'});
	regionNamesInEnglish = new Intl.DisplayNames(['en'], {type: 'region'});
} catch {languageNames = null;regionNamesInEnglish = null;}

const hide_regex = new RegExp('^hide-(tag-.+-)(.+)');
const class_tag_regex = new RegExp('^tag-(.+)-.+');
const class_hide_regex = new RegExp('^hide-tag-(.+)-.+');
const class_exclude_regex = new RegExp('^exclude-tag-(.+)-.+');

var multi_button_styles = {
	2: {0: 'exclude', 1: 'include'},
	3: {0: 'exclude', 1: 'none', 2: 'include'}
}
var multi_button_styles_rev = {
	2: {'exclude': 0, 'include': 1},
	3: {'exclude': 0, 'none': 1, 'include': 2}
}

// icon classes for buttons
var multi_button_ico = {
	'include': 'yes',
	'none': 'placeholder',
	'exclude': 'no'
}
// button classes
var multi_button_class = {
	'include': 'btn-on',
	'none': 'btn-none deselect-text',
	'exclude': 'btn-off'
}

var multi_button_ico_classes = [];
$.each(multi_button_ico,function(index,value){
   multi_button_ico_classes.push(value);
});
multi_button_ico_classes = multi_button_ico_classes.join(' ');

var multi_button_classes = [];
$.each(multi_button_class,function(index,value){
   multi_button_classes.push(value);
});
multi_button_classes = multi_button_classes.join(' ');

function str_title(cur_str) {
	return cur_str.replace(/\b(?!and\b|or\b)[a-z]/g, function(letter) {return letter.toUpperCase();});
}

function match_starts_in_list(to_find, full_list, re_match=true){
	for (let cl in full_list) {
				if (0 === full_list[cl].trim().indexOf(to_find)) {
					if (re_match){
						let hide_match = full_list[cl].trim().match(hide_regex);

						let new_list = null;
						if (hide_match){
							new_list = jQuery.grep(full_list, function(value) {
							  return value != hide_match[1] + hide_match[2];
							});
						}

						if (!hide_match || !match_starts_in_list(hide_match[1], new_list, false)) {
							return true;
						}
					} else {return true;}
				}
			}
	return false;
}

var iso_filter_func = function(){
		if (iso_show_hidden_filter) {
			return $(this).hasClass('to-hide');
		} else {
			let classes = $(this).attr('class').split(' ');
			 let tag_list = {};
			 let hidden_list = {};
			 let shown = true;
			 for (let cl in classes) {
				if (_m = classes[cl].match(class_tag_regex)) {
					let group_name = _m[1];
					group_name in tag_list || (tag_list[group_name] = []);
					tag_list[group_name].push(classes[cl]);
				} else if (_m = classes[cl].match(class_hide_regex)) {
					let group_name = _m[1];
					group_name in hidden_list || (hidden_list[group_name] = []);
					hidden_list[group_name].push(classes[cl]);
				} else if (_m = classes[cl].match(class_exclude_regex)) {
					shown = false;
					break;
				}
			 }
			 if (shown) {
				 $.each(hidden_list, function (index, value) {
					if (index in tag_list) {
						$.each(value, function (index2, value2) {
							 if (to_remove = $.inArray(value2, tag_list[index])) {
								tag_list[index].splice(to_remove, 1);
							 }
							 if (0 === tag_list[index].length) {
								shown = false;
								return false;
							 }
						});
					}
					if (!shown) {return false;}
				 });
			 }
			return shown;
		}
	};

function updateTagCount() {
	$(iso_tag_container).each(function () {
		let target = $(this).data('target');
		let cur_count = $(iso_showcards).filter($('.' + target)).length;
		$(this).children('.count:first').text(' (' + cur_count + ')');
	});
}

function init_buttons(){
	//let tag_menu = $('#tag-menu');
	if (persistent_tag_button_states[browse_cat] === undefined) {
		persistent_tag_button_states[browse_cat] = {'current': {}, 'names': {}}
	}
	if (persistent_tag_button_states[browse_cat]['names'] === undefined) {
		persistent_tag_button_states[browse_cat]['names'] = {}
	}
	$.get($.SickGear.Root + '/add-shows/get-btn-profile-states',
	{'browse_cat': browse_cat}).done(
		function (data) {
			if (data) {
				try {
					data = JSON.parse(data);
					if (data !== undefined && data.constructor == Object) {
						persistent_tag_button_states[browse_cat] = data;
						if (persistent_tag_button_states[browse_cat]['names'] === undefined) {
							persistent_tag_button_states[browse_cat]['names'] = {}
						}
						if (persistent_tag_button_states[browse_cat]['names']) {
							$.each(persistent_tag_button_states[browse_cat]['names'], function (index, value) {
								$('.profile_load[value="' + index + '"], .profile_save[value="' + index + '"], .profile_rename[value="' + index + '"]').children('div').text(value);
							});
						}
					}
				} catch {}
			}
		}
	);
	iso_showcards = $('.show-card');
	function gen_tag_checkboxes(value, parent_obj, category, extra_remove, button_count) {
	   let new_checkbox = $('<input type="checkbox">');
		let tag_name = value.replace('tag-', '');
		if (extra_remove) {
			tag_name = tag_name.replace(extra_remove, '');
		}
		let button_title = '';
		if ('networks' === category || 'content_rating' === category){
			try {
			button_title = decodeURIComponent(tag_name.replaceAll('_', '%')).replaceAll(' ', nbsp_code);} catch {}
		} else {
			button_title = str_title(tag_name.replaceAll('-', ' ').replaceAll('_', nbsp_code));
		}
		$(new_checkbox).attr('data-button-count', button_count).attr('id', value).data('target', value).prop('checked', true);
		let new_label = $('<label></label>');
		$(new_label).attr('for', value).text(button_title);
		if (('country' === category || 'language' === category)/* && 'unknown' !== tag_name.toLowerCase()*/) {
			let is_lang = 'language' === category;
			let extra_lang = is_lang ? 'svg/lang/' : '';
			let width = '16';
			let file_ext = is_lang ? '.svg' : '.png';
			let lang_name = '';
			try {
			if (is_lang && languageNames){
				lang_name = languageNames.of(tag_name.toLowerCase());
			} else {
				lang_name = cc_alpha3_to_alpha2[tag_name.toLowerCase()] || tag_name.toLowerCase();
				lang_name = regionNamesInEnglish.of(lang_name);
			}} catch {}
			let country_img = $('<img style="margin:0 0 2px 4px;width:' + width + 'px;height:11px;vertical-align:middle" title="' + (lang_name || tag_name.toLowerCase()) + '" src="' + sg_root + '/images/flags/' + extra_lang + tag_name.toLowerCase() + file_ext + '" width="' + width +'" height="11">');
			$(new_label).prepend(country_img);
		}
		$(parent_obj).append(new_checkbox).append(new_label);
	}
	if (all_tag_classes){
		let tag_container = $('#tags-container');
		$.each(all_tag_classes,function(index,value){
			let group_el = $('<tr></tr');
			let btn_type = 3;
			let button_contain_el = $('<td class="button-container"></td>').data('num-max-state', btn_type);
			let label_el = $('<td class="label-container"></td>');
			$(label_el).text(str_title(index.replaceAll('_', nbsp_code)) + ':');
			let select_el = $('<td class="select-buttons"></td>');
			$(select_el).append($('<button type="button" value="include" class="btn row-select-all">Include All</button><br><button type="button" value="exclude" class="btn row-select-exclude">Exclude All</button>'));
			if (2 < btn_type){
				$(select_el).append($('<br><button type="button" value="none" class="btn row-select-none">Deselect All</button>'));
			}
			$(group_el).append(label_el).append(button_contain_el).append(select_el);
			$(tag_container).append(group_el);
			$.each(value, function(index2, value2) {
					gen_tag_checkboxes(value2, button_contain_el, index, index + '-', value.length);
				});
		});
	}
	checkbox2button('#tags-container');
	if (-1 !== saved_showsort_view.indexOf('.hide')) {
		iso_show_hidden_filter = true;
		$('#tags').hide();
	}
	if (-1 != saved_showsort_view.indexOf('library')) {
		if (-1 === saved_showsort_view.indexOf('not')) {
			$('.notinlibrary').addClass('hide-notinlibrary');
		} else {
			$('.inlibrary').addClass('hide-inlibrary');
		}
	}

	function iso_filter_update() {
		$.iso.off('layoutComplete');
		$.iso.on('revealComplete', llUpdate);
		$.iso.on('hideComplete', llUpdate);
		$.iso.isotope({ filter: iso_filter_func });
	}

	function change_tag_btn(target_btn, profile_nb) {
		let changed = false;
		let tag_target = $(target_btn).data('target');
		let btn_status = $(target_btn).val();
		let remove_classes = 'hide-' + tag_target + ' exclude-' + tag_target;
		if(this.checked || 'include' === btn_status) {
			$('.' + tag_target).removeClass(remove_classes);
		} else if ('none' === btn_status) {
			$('.' + tag_target).removeClass(remove_classes).addClass('hide-' + tag_target);
		} else {
			$('.' + tag_target).removeClass(remove_classes).addClass('exclude-' + tag_target);
		}
		if (persistent_tag_button_states[browse_cat][profile_nb || 'current'] === undefined){
			persistent_tag_button_states[browse_cat][profile_nb || 'current'] = {}
		}
		if (persistent_tag_button_states[browse_cat][profile_nb || 'current'][tag_target] !== btn_status){
			persistent_tag_button_states[browse_cat][profile_nb || 'current'][tag_target] = btn_status;
			changed = true;
		}
		return changed;
	}

	function change_button_status (button_el, button_type, new_state) {
		if (new_state !== $(button_el).data('state')) {
			let new_state_name = multi_button_styles[button_type][new_state];
			$(button_el).prop('checked', 'include' === new_state_name).val(multi_button_styles[button_type][new_state]).data('state', new_state).removeClass(multi_button_classes).addClass(multi_button_class[new_state_name]).children('i').removeClass(multi_button_ico_classes).addClass(multi_button_ico[new_state_name]).trigger("change");
		}
	}

	function checkbox2button(selector) {
		const button = $('<button type="button"></button>');
		$(selector).find('input[type="checkbox"]').each(function (){
			let cur_parent = $(this).parent();
			let button_count = $(this).data('button-count');
			//let button_type = button_count > 3 ? 3 : 2;
			let button_type = $(cur_parent).data('num-max-state');
			let cur_checkbox = $(this);
			let cur_checkbox_id = $(cur_checkbox).attr('id');
			let cur_target = $(cur_checkbox).data('target');
			let cur_checked = $(cur_checkbox).is(':checked');
			let label_for_checkbox = $("label[for='"+cur_checkbox_id+"']");
			let cur_img = $(label_for_checkbox).find('img');
			let label_text = $(label_for_checkbox).text();
			let text_span = $('<span class="button-label-text"></span>');
			$(text_span).text(label_text);
			let new_button = $(button).clone();
			$(cur_parent).append(new_button);
			$(cur_checkbox).remove();
			$(label_for_checkbox).remove();
			let new_ico = $('<i></i>');
			let count_el = $('<span class="count"> (0)</span>');
			let new_state = cur_checked ? button_type - 1 : 0;
			$(new_ico).addClass(multi_button_ico[multi_button_styles[button_type][new_state]]);
			$(new_button).val(multi_button_styles[button_type][new_state]).data('state', new_state).data('num-max-state', button_type).prop('checked', cur_checked).attr('id', cur_checkbox_id).addClass('btn-toggle').addClass(cur_checked ? 'btn-on' : 'btn-off').attr('data-target', cur_target).append(text_span).prepend(new_ico).append(count_el);
			if (0 < cur_img.length) {
				$(cur_img).css('width', '24px').css('height', '20px');
				let title = $(cur_img).attr('title');
				$(new_button).attr('title', title).children('i').after(cur_img);
				$(new_button).children('.button-label-text').text('');
			}
			$(new_button).click(function (){
				let cur_state = $(this).data('state');
				let new_state = (cur_state + 1) % $(this).data('num-max-state');
				let button_type = $(this).data('num-max-state');
				change_button_status(this, button_type, new_state);
			});

		});
	}
	$('#tags-container').find('.row-select-all,.row-select-none,.row-select-exclude').click(
		function (element) {
			let button_val = $(element.target).val();
			let button_td_el = $(this).closest('td').prev();
			let button_type = $(button_td_el).data('num-max-state');
			$(button_td_el).find('.btn-toggle').each(function () {
				let new_state = multi_button_styles_rev[button_type][button_val];
				change_button_status(this, button_type, new_state);
			});
		}
	);
	iso_tag_container = $('#tags-container .btn-toggle');
	updateTagCount();
	if (persistent_tag_button_states[browse_cat] && persistent_tag_button_states[browse_cat]['current']){
		$.each(persistent_tag_button_states[browse_cat]['current'], function (index, value) {
			let btn_el = $('#' + index);
			if (btn_el.length){
				let button_type = $(btn_el).data('num-max-state');
				let new_state = multi_button_styles_rev[button_type][value];
				change_button_status(btn_el, button_type, new_state);
			}
		});
	}

	let tag_el = $('#tags-container').find('[id^="tag-"]');  //'#tag-self, #tag-acting');
	function set_tag_filters (profile_nb) {
		let changed = false;
		$(tag_el).each(function(){
			let ch = change_tag_btn(this, profile_nb);
			changed ||= ch;
		});
		if (changed){
			iso_filter_update();
		}
		return changed;
	}

	function tag_dialog_close ( event, ui ) {
		save_profile(null, null, false);
		llUpdate();
	}
	function save_profile (profile_nb, force_save, save_msg) {
		if (set_tag_filters(profile_nb) || force_save) {
			$.post($.SickGear.Root + '/add-shows/set-persistent-btn-status',
				{
					_xsrf: Cookies.get('_xsrf'),
					'browse_cat': browse_cat,
					button_states: JSON.stringify(persistent_tag_button_states),
				},
				function(data){
					let result = $.parseJSON(data);
					if ('success' === result['result']) {
						//console.log('saved');
						if (save_msg !== false){
							$.toast({
								heading: 'Information',
								icon: 'success',
								text: 'Profile saved!',
								showHideTransition: 'slide',
								allowToastClose: true,
								position: 'bottom-left',
								hideAfter: 5000   // in milli seconds
							});
							}
					} else {
						if (save_msg !== false){
							$.toast({
								heading: 'Error',
								icon: 'error',
								hideAfter: false,
								text: 'Profile failed to save!',
								showHideTransition: 'slide',
								allowToastClose: true,
								position: 'bottom-left'
							});
						}
					}
				}
			);
		}
	}
	$('#filter_button').click(function () {
		$('#tag-dialog').dialog( "open" );
	});
	$(window).resize(function() {
		$('#tag-dialog').dialog("option", "width", $(window).width());
		$('#tag-dialog').dialog("option", "height", $(window).height());
	});
	$('#tag-dialog').dialog(    {
		title: 'Filters',
		modal: true,
		resizable: false,
		draggable: false,
		autoOpen: false,
		width:  $(window).width(),
		height:  $(window).height(),
		beforeClose: tag_dialog_close,
		create: disableScroll,
		close: enableScroll,
		open: function(){
			$(this).dialog("option", "height", $(window).height());
			$(this).dialog("option", "width", $(window).width());
		},
	});
	set_tag_filters();
	try {
	initLazyload();} catch {}
	iso_filter_update();
	$('div.profile-menu').hover(
		function () {
			let pos = $(this).position();
			let width = $(this).outerWidth();
			$(this).children('.profile-menu-items').css({
				top: pos.bottom,
				left: pos.left,
				'min-width': width,
				position:'absolute'
				}).slideDown(0);
		},
		function () {
			$(this).children('.profile-menu-items').slideUp(0);
		}
	);

	$('.profile_load').click(function (){
		$(this).parents('.profile-menu-items').slideUp(0);
		let value = $(this).val();
		let new_vals = persistent_tag_button_states[browse_cat][value] || {};
		$('button.btn-toggle').each(function (){
			let button_id = $(this).attr('id');
			let val = new_vals[button_id] || 'include';
			let button_type = $(this).data('num-max-state');
			let new_state = multi_button_styles_rev[button_type][val];
			change_button_status($(this), button_type, new_state);
		});
		set_tag_filters();
		save_profile(null, true, false);
		$.toast({
			heading: 'Information',
			icon: 'success',
			text: 'Profile loaded!',
			showHideTransition: 'slide',
			allowToastClose: true,
			position: 'bottom-left',
			hideAfter: 3000   // in milli seconds
		});
	});
	$('.profile_save').click(function (){
		$(this).parents('.profile-menu-items').slideUp(0);
		let value = $(this).val();
		save_profile(value, true);
	});
	$('.profile_rename').click(function (){
		$(this).parents('.profile-menu-items').slideUp(0);
		let value = $(this).val();
		let pro_text_el = $(this).children('div');
		let pro_name= $(pro_text_el).text();
		let new_name = prompt('Enter new name (min 3 Char)', pro_name);
		if (new_name && 3 <= new_name.length && new_name.length <= 30) {
			persistent_tag_button_states[browse_cat]['names'][value] = new_name;
			$(pro_text_el).text(new_name);
			$('.profile_load[value="' + value +'"], .profile_save[value="' + value +'"]').children('div').text(new_name);
			save_profile(null, true, false);
		} else if (new_name !== null) {
			$.toast({
				heading: 'Warning',
				icon: 'warning',
				text: 'Profile name needs to be between 3 and 30 characters!',
				showHideTransition: 'slide',
				allowToastClose: true,
				position: 'bottom-left',
				hideAfter: 10000   // in milli seconds
			});
		}
	});
}

// scroll prevention
// left: 37, up: 38, right: 39, down: 40,
// spacebar: 32, pageup: 33, pagedown: 34, end: 35, home: 36
var keys = {37: 1, 38: 1, 39: 1, 40: 1};

function preventDefaultE (e) {
	e.preventDefault();
}

function preventDefaultForScrollKeys(e) {
	if (keys[e.keyCode]) {
		preventDefaultE(e);
		return false;
	}
}

// modern Chrome requires { passive: false } when adding event
var supportsPassive = false;
try {
	window.addEventListener("test", null, Object.defineProperty({}, 'passive', {
		get: function () { supportsPassive = true; }
	}));
} catch(e) {}

var wheelOpt = supportsPassive ? { passive: false } : false;
var wheelEvent = 'onwheel' in document.createElement('div') ? 'wheel' : 'mousewheel';

// call this to Disable
function disableScroll() {
	window.addEventListener('DOMMouseScroll', preventDefault, false); // older FF
	window.addEventListener(wheelEvent, preventDefault, wheelOpt); // modern desktop
	window.addEventListener('touchmove', preventDefault, wheelOpt); // mobile
	window.addEventListener('keydown', preventDefaultForScrollKeys, false);
}

// call this to Enable
function enableScroll() {
	window.removeEventListener('DOMMouseScroll', preventDefault, false);
	window.removeEventListener(wheelEvent, preventDefault, wheelOpt);
	window.removeEventListener('touchmove', preventDefault, wheelOpt);
	window.removeEventListener('keydown', preventDefaultForScrollKeys, false);
}


