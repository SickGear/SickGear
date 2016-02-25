function setFromPresets (preset) {
	var elCustomQuality = $('.show-if-quality-custom'),
		selected = 'selected';
	if (preset = parseInt(preset)) {
		elCustomQuality.fadeOut('fast', 'linear');

		var upgrade = !0;
		$('#anyQualities, #bestQualities').find('option').each(function() {
			if (upgrade && 'bestQualities' === $(this).parent().attr('id')) {
				upgrade = !1;
				switch (preset) {
					case 3: preset = 128 + 32 + 4; break;
					case 164: preset = 256 + 64 + 16 + 4; break;
					case 336: preset = 256; break;
					default: preset = 0;
				}
			}
			$(this).attr(selected, ((preset & parseInt($(this).val())) ? selected : false));
		});
	} else
		elCustomQuality.fadeIn('fast', 'linear');
}

$(document).ready(function() {
	var elQualityPreset = $('#qualityPreset'),
		selected = ':selected';

	elQualityPreset.change(function() {
		setFromPresets($(this).find(selected).val());
	});

	setFromPresets(elQualityPreset.find(selected).val());
});
