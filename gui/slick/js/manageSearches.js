$(function(){
	$('#recentsearch,#propersearch').click(function(){
		$(this).addClass('disabled');
	});
	$('#forcebacklog,#forcefullbacklog').click(function(){
		$('#forcebacklog,#forcefullbacklog').addClass('disabled');
		$('#pausebacklog').removeClass('disabled');
	});
	$('#pausebacklog').click(function(){
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
		var table$ = $(this).nextAll('table:first');
		table$ = table$.length ? table$ : $(this).parent().nextAll('table:first');
		table$.hide();
		$(this).hide();
		$(this).prevAll('input:first').show();
	});
	$('.shows-more').click(function(){
		var table$ = $(this).nextAll('table:first');
		table$ = table$.length ? table$ : $(this).parent().nextAll('table:first');
		table$.show();
		$(this).hide();
		$(this).nextAll('input:first').show();
	});
	$('input[id^="remove-btn-"]').click(function() {
		var param = {'to_remove': $(this).data('uid')};
		$.getJSON(sbRoot + '/manage/search-tasks/remove-from-search-queue', param)
			.done(function(){
				location.reload();
		})
	});
	$('input[id^="clear-btn-"]').click(function() {
		var param = {'search_type': $(this).data('action')};
		$.getJSON(sbRoot + '/manage/search-tasks/clear-search-queue', param)
			.done(function(){
				location.reload();
		})
	});
});
