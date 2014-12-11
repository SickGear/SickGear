function setFromPresets (preset) {
	var elCustomQuality = $('#customQuality'),
		selected = 'selected';
	if (0 == preset) {
		elCustomQuality.show();
		return;
	}

	elCustomQuality.hide();

	$('#anyQualities').find('option').each(function() {
		var result = preset & $(this).val();
		$(this).attr(selected, (0 < result ? selected : false));
	});

	$('#bestQualities').find('option').each(function() {
		var result = preset & ($(this).val() << 16);
		$(this).attr(selected, (result > 0 ? selected: false));
	});
}

$(document).ready(function() {
	var elQualityPreset = $('#qualityPreset'),
		selected = ':selected';

	elQualityPreset.change(function() {
		setFromPresets($('#qualityPreset').find(selected).val());
	});

	setFromPresets(elQualityPreset.find(selected).val());
});