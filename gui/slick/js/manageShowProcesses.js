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

	function disableSaveBtn(state){
		$('#save-nowarnicon').prop('disabled', state)
	}
	$('#save-nowarnicon').click(function(){
		disableSaveBtn(!0);
		var param = {};
		$('.nowarnicon').each(function(i, selected){
			param[$(selected).data('indexer-id') + '|' + $(selected).prop('checked')] = $(selected).data('indexer');
		});
		$.getJSON(sbRoot + '/manage/showProcesses/switch_ignore_warning', param)
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
