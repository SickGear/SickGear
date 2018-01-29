function setFromPresets (preset) {
	var elCustomQuality = $('.show-if-quality-custom'),
		selected = 'selected', quality, selectState, btn$, dev = !1;
	if (preset = parseInt(preset)) {
		!dev && elCustomQuality.fadeOut('fast', 'linear');

		var upgrade = !0;
		$('#initial-qualities, #upgrade-qualities').find('option').each(function() {
			if (upgrade && 'upgrade-qualities' === $(this).parent().attr('id')) {
				upgrade = !1;
				switch (preset) {
					case 3: preset = 128 + 32 + 4; break;
					case 164: preset = 256 + 64 + 16 + 4; break;
					case 336: preset = 256; break;
					default: preset = 0;
				}
			}

			quality = $(this).val();
			selectState = ((preset & parseInt(quality, 10)) ? selected : !1);
			$(this).attr(selected, selectState);

			var list = /initial/.test($(this).parent().attr('id')) ? '#initial-quality': '#upgrade-quality';
			btn$ = $(/initial/.test($(this).parent().attr('id')) ? '#initial-quality': '#upgrade-quality').find('a.btn[data-quality="' + quality + '"]');
			if(!selectState){
				btn$.removeClass('active')

			} else {
				btn$.addClass('active')
			}
			dev && console.log(preset, list, 'this.val():', quality, 'selectState:', selectState, 'hasClass:', btn$.hasClass('active'))
		});
		dev && console.log('-----------------------');
	} else
		elCustomQuality.fadeIn('fast', 'linear');

	presentTips();
}

function presentTips() {
	var tip$ = $('#unknown-quality');
	if ($('#initial-quality').find('a.btn[data-quality="32768"]').hasClass('active')) {
		tip$.fadeIn('fast', 'linear');
	} else {
		tip$.fadeOut('fast', 'linear');
	}

	var tip$ = $('#no-upgrade'), tip2$ = $('#upgrade-cond');
	if ($('#upgrade-quality').find('a.btn').hasClass('active')) {
		tip$.fadeOut('fast', 'linear', function(){tip2$.fadeIn('fast', 'linear');});
	} else {
		tip2$.fadeOut('fast', 'linear', function(){tip$.fadeIn('fast', 'linear');});
	}
}

$(function() {
	var elQualityPreset = $('#quality-preset'),
		selected = ':selected';

	elQualityPreset.change(function() {
		setFromPresets($(this).find(selected).val());
	});

	setFromPresets(elQualityPreset.find(selected).val());

	$('#initial-qualities').change(function() {
		presentTips();
	});

	$('#custom-quality').find('a[href="#"].btn').on('click', function(event){
		event.stopPropagation();

		$(this).toggleClass('active');

		var select$ = $('initial-quality' === $(this).closest('.component-desc').attr('id') ? '#initial-qualities' : '#upgrade-qualities'),
			quality = $(this).data('quality'), arrSelected = $.map(select$.val(), function(v){return parseInt(v, 10)}) || Array();

		if($(this).hasClass('active')){
			arrSelected.push(quality);
		} else {
			arrSelected = arrSelected.filter(function(elem){
				return elem !== quality;
			});
		}

		select$.val(arrSelected).change();

		presentTips();
		return !1;
	});
});
