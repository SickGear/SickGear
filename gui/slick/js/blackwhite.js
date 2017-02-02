function generate_bwlist() {
	$.each(['white', 'black'], function(i, list) {
		var group_list = [];

		$('#' + list + ' option').each(function(i, option) {
			group_list.push($(option).val());
		});

		$('#' + list + 'list').val(group_list.join(','));
	});
}

$('#add-white, #add-black').click(function() {
	!$('#pool option:selected').remove().appendTo('#' + $(this).attr('id').replace(/add[-]/i, ''));
});

$('#remove-white, #remove-black').click(function() {
	!$('#' + $(this).attr('id').replace(/remove[-]/i, '') + ' option:selected').remove().appendTo('#pool');
});

$('#new-white, #new-black').click(function() {
	var group = $('#addToPoolText').val();
	if ('' != group) {
		var option = $('<option>');
		option.val(group);
		option.html(group);
		option.appendTo('#' + $(this).attr('id').replace(/new[-]/i, ''));
		$('#addToPoolText').val('');
	}
});
