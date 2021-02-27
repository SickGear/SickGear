/* globals sbRoot */
$(document).ready(function() {
	$('#showupdatebutton').click(function(){
		$(this).addClass('disabled');
	});
	$('.show-all-less').click(function(){
		$(this).nextAll('table').hide();
		$(this).nextAll('input.shows-more').show();
		$(this).nextAll('input.shows-less').hide();
	});
	$('.show-all-more').click(function(){
		$(this).nextAll('table').show();
		$(this).nextAll('input.shows-more').hide();
		$(this).nextAll('input.shows-less').show();
	});

	$('.shows-less').click(function(){
		$(this).nextAll('table:first').hide();
		$(this).hide();
		$(this).prevAll('input:first').show();
	});
	$('.shows-more').click(function(){
		$(this).nextAll('table:first').show();
		$(this).hide();
		$(this).nextAll('input:first').show();
	});

	$('input[id^="remove-btn-"]').click(function() {
		var param = {'to_remove': $(this).data('uid'), 'force': $(this).data('force') !== undefined};
		$.getJSON(sbRoot + '/manage/show-tasks/remove-from-show-queue', param)
			.done(function(){
				location.reload();
			})
	});

	$('input[id^="remove-people-btn-"]').click(function() {
		var param = {'to_remove': $(this).data('uid')};
		$.getJSON(sbRoot + '/manage/show-tasks/remove-from-people-queue', param)
			.done(function(){
				location.reload();
			})
	});

	$('input[id^="clear-btn-"]').click(function() {
		var param = {'show_type': $(this).data('action')};
		$.getJSON(sbRoot + '/manage/show-tasks/clear-show-queue', param)
			.done(function(){
				location.reload();
		})
	});

		$('input[id^="clear-people-btn"]').click(function() {
			var param = {'people_type': $(this).data('action')};
			$.getJSON(sbRoot + '/manage/show-tasks/clear-people-queue', param)
				.done(function(){
					location.reload();
		})
	});

	function disableSaveBtn(state){
		$('#save-nowarnicon').prop('disabled', state)
	}
	$('#save-nowarnicon').click(function(){
		disableSaveBtn(!0);
		var param = {};
		$('.nowarnicon').each(function(i, selected){
			param[$(selected).data('tvid-prodid')] = $(selected).prop('checked');
		});
		$.getJSON(sbRoot + '/manage/show-tasks/switch-ignore-warning', param)
			.done(function(){
				var body$ = $('body'), nNotChecked = $('.nowarnicon').not(':checked').length;
				body$.removeClass('n nn nnn nnnn');
				if (nNotChecked){
					body$.addClass(1 === nNotChecked ? 'n' : 2 === nNotChecked ? 'nn' : 3 === nNotChecked ? 'nnn' : 'nnnn');
				}
				disableSaveBtn(!1);
			}).fail(function(){disableSaveBtn(!1);});
	});
});
