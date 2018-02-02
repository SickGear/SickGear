function setFromPresets (preset){
	var elCustomQuality = $('.show-if-quality-custom');

	if(preset = parseInt(preset)){
		var upgradePreset = !0, quality, stateReqd, btn$;
		elCustomQuality.fadeOut('fast', 'linear');

		$('#wanted-qualities, #upgrade-qualities').find('option').each(function(){
			if(upgradePreset && /upgrade/.test($(this).parent().attr('id'))){
				upgradePreset = !1;
				switch(preset){
					case 3: preset = 128 + 32 + 4; break;
					case 164: preset = 256 + 64 + 16 + 4; break;
					case 336: preset = 256; break;
					default: preset = 0;
				}
			}

			quality = $(this).val(); // quality from select$
			stateReqd = ((preset & parseInt(quality, 10)) ? !0 : !1);
			if(stateReqd !== this.selected){
				$(this).prop('selected', stateReqd);

				btn$ = $(/upgrade/.test($(this).parent().attr('id')) ? '#upgrade-quality' : '#wanted-quality')
					.find('a.btn[data-quality="' + quality + '"]');
				if(!stateReqd){
					btn$.removeClass('active');
				} else {
					btn$.removeClass('disabled').addClass('active');
				}
			}
		});
	} else
		elCustomQuality.fadeIn('fast', 'linear');

	refreshUpgrades();
	presentTips();
}

function presentTips(){
	var tip$ = $('#unknown-quality'), tip2$;
	if($('#wanted-quality').find('a.btn[data-quality="32768"]').hasClass('active')){
		tip$.fadeIn('fast', 'linear');
	} else {
		tip$.fadeOut('fast', 'linear');
	}

	tip$ = $('#no-upgrade'); tip2$ = $('#upgrade-cond, #upgrade-once-opt');
	if($('#upgrade-quality').find('a.btn').hasClass('active')){
		tip$.fadeOut('fast', 'linear', function(){tip2$.fadeIn('fast', 'linear');});
	} else {
		if(!!$('#upgrade-once:checked').length){
			$('#upgrade-once').click();
		}
		tip2$.fadeOut('fast', 'linear', function(){tip$.fadeIn('fast', 'linear');});
	}
}

function refreshUpgrades(){
	var btn$, minQuality=99999999, quality, upgrade$;

	$.map($('#wanted-quality').find('a.btn.active'), function(btn){
		btn$ = $(btn);
		quality = parseInt(btn$.data('quality'), 10);
		minQuality = quality < minQuality ? quality : minQuality;
	});

	$.map($('#upgrade-quality').find('a.btn'), function(btn){
		btn$ = $(btn);
		quality = parseInt(btn$.data('quality'), 10);
		upgrade$ = $('#upgrade-qualities');
		if(quality <= minQuality){
			if(btn$.hasClass('active') // then btn is about to changed state so reflect change to select option
				|| 1 === upgrade$.find('option[value="' + quality + '"]:selected').length){
				upgrade$.find('option[value="' + quality + '"]').prop('selected', !1);
			}
			btn$.removeClass('active').addClass('disabled');
		} else if(btn$.hasClass('disabled')){
			btn$.removeClass('disabled');
		}
	});
}

$(function(){
	var elQualityPreset = $('#quality-preset'),
		selected = ':selected';

	elQualityPreset.change(function(){
		setFromPresets($(this).find(selected).val());
	});

	setFromPresets(elQualityPreset.find(selected).val());

	$('#wanted-qualities').change(function(){
		presentTips();
	});

	$('#custom-quality').find('a[href="#"].btn').on('click', function(event){
		event.stopPropagation();
		var active$ = $('#wanted-quality').find('a.btn.active'), num_active = active$.length;

		if(1 < num_active || (1 === num_active && $(this).data('quality') !== active$.data('quality'))){

			$(this).toggleClass('active');

			var isInit = 'wanted-quality' === $(this).closest('.component-desc').attr('id'),
				select$ = $(isInit ? '#wanted-qualities' : '#upgrade-qualities'),
				quality = $(this).data('quality'),
				arrSelected = $.map(select$.val(), function (v){
					return parseInt(v, 10)
				}) || Array();

			if($(this).hasClass('active')){
				arrSelected.push(quality);
			} else {
				arrSelected = arrSelected.filter(function (elem){
					return elem !== quality;
				});
			}

			select$.val(arrSelected).change();

			if(isInit){
				refreshUpgrades();
			}

			presentTips();

		}
		return !1;
	});
});
