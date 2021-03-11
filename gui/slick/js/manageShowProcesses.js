/* globals sbRoot */
$(document).ready(function() {
	$('#showupdatebutton').click(function(){
		$(this).addClass('disabled');
	});
	$('.show-all-less').click(function(){
		var root$ = $(this).closest('.section-tasks');
		root$.find('table').addClass('hide');
		root$.find('input.shows-more').removeClass('hide');
		root$.find('input.shows-less').addClass('hide');
		$(this).addClass('hide');
		$(this).prevAll('input:first').removeClass('hide');
		root$.find('table').prevAll('.task').find('input[value="Clear"]').addClass('hide');
	});
	$('.show-all-more').click(function(){
		var root$ = $(this).closest('.section-tasks');
		root$.find('table').removeClass('hide');
		root$.find('input.shows-more').addClass('hide');
		root$.find('input.shows-less').removeClass('hide');
		$(this).addClass('hide');
		$(this).nextAll('input:first').removeClass('hide');
		root$.find('input[value="Clear"]').removeClass('hide');
	});

	$('.shows-less').click(function(){
		$(this).parent().nextAll('table:first').addClass('hide');
		$(this).addClass('hide');
		$(this).prevAll('input:first').removeClass('hide');
		$(this).nextAll('input[value="Clear"]:first').addClass('hide');
		// if last open table is collapsed, ensure collapse all is actually expand all
		var root$ = $('.section-tasks');
		if (0 === root$.find('table').not('.hide').length){
			root$.find('.show-all-less.btn').addClass('hide');
			root$.find('.show-all-more.btn').removeClass('hide');
		}
	});
	$('.shows-more').click(function(){
		$(this).parent().nextAll('table:first').removeClass('hide');
		$(this).addClass('hide');
		$(this).nextAll('input:first').removeClass('hide');
		$(this).nextAll('input[value="Clear"]:first').removeClass('hide');
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
		$.confirm({
			'title': 'Confirm cancel',
			'message': 'Cancel pending actions ?',
			'buttons': {
				'Yes': {
					'class': 'green',
					'action': function () {
						$.getJSON(sbRoot + '/manage/show-tasks/clear-show-queue', param)
							.done(function(){
								location.reload();
						});
					}
				},
				'No': {
					'class': 'red',
					'action': function () {}
				}
			}
		});
	});

	$('input[id^="clear-people-btn"]').click(function() {
		var param = {'people_type': $(this).data('action')};
		$.confirm({
			'title': 'Confirm cancel',
			'message': 'Cancel pending actions ?',
			'buttons': {
				'Yes': {
					'class': 'green',
					'action': function () {
						$.getJSON(sbRoot + '/manage/show-tasks/clear-people-queue', param)
							.done(function(){
								location.reload();
							});
					}
				},
				'No': {
					'class': 'red',
					'action': function () {}
				}
			}
		});
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
