function generateAniGroupList() {
	$.each(['allow', 'block'], function(i, list) {
		var group_list = [];

		$('#' + list + ' option').each(function(i, option) {
			group_list.push($(option).val());
		});

		$('#' + list + 'list').val(group_list.join(','));
	});
}

$('#add-allow, #add-block').click(function() {
	!$('#pool option:selected').remove().appendTo('#' + $(this).attr('id').replace(/add[-]/i, ''));
});

$('#remove-allow, #remove-block').click(function() {
	!$('#' + $(this).attr('id').replace(/remove[-]/i, '') + ' option:selected').remove().appendTo('#pool');
});

$('#new-allow, #new-block').click(function() {
	var group = $('#addToPoolText').val();
	if ('' != group) {
		var option = $('<option>');
		option.val(group);
		option.html(group);
		option.appendTo('#' + $(this).attr('id').replace(/new[-]/i, ''));
		$('#addToPoolText').val('');
	}
});
