function generate_bwlist() {
	var realvalues = [];

		$('#white option').each(function(i, selected) {
			realvalues[i] = $(selected).val();
		});
		$("#whitelist").val(realvalues.join(","));

		realvalues = [];
		$('#black option').each(function(i, selected) {
			realvalues[i] = $(selected).val();
		});
		$("#blacklist").val(realvalues.join(","));
};

$('#removeW').click(function() {
	!$('#white option:selected').remove().appendTo('#pool');
});

$('#addW').click(function() {
	!$('#pool option:selected').remove().appendTo('#white');
});

$('#addB').click(function() {
	!$('#pool option:selected').remove().appendTo('#black');
});

$('#removeP').click(function() {
	!$('#pool option:selected').remove();
});

$('#removeB').click(function() {
	!$('#black option:selected').remove().appendTo('#pool');
});

$('#addToWhite').click(function() {
	var group = $('#addToPoolText').attr("value");
	if(group == "") { return; }
	$('#addToPoolText').attr("value", "");
	var option = $("<option>");
	option.attr("value",group);
	option.html(group);
	option.appendTo('#white');
});

$('#addToBlack').click(function() {
	var group = $('#addToPoolText').attr("value");
	if(group == "") { return; }
	$('#addToPoolText').attr("value", "");
	var option = $("<option>");
	option.attr("value",group);
	option.html(group);
	option.appendTo('#black');
});