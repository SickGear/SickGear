$(document).ready(function() {
	$('#recentsearch,#propersearch').click(function(){
		$(this).addClass('disabled');
	})
	$('#forcebacklog,#forcefullbacklog').click(function(){
		$('#forcebacklog,#forcefullbacklog').addClass('disabled');
		$('#pausebacklog').removeClass('disabled');
	})
	$('#pausebacklog').click(function(){
		$(this).addClass('disabled');
	})
	$('.show-all-less').click(function(){
		$(this).nextAll('table').hide();
		$(this).nextAll('input.shows-more').show();
		$(this).nextAll('input.shows-less').hide();
	})
	$('.show-all-more').click(function(){
		$(this).nextAll('table').show();
		$(this).nextAll('input.shows-more').hide();
		$(this).nextAll('input.shows-less').show();
	})

	$('.shows-less').click(function(){
		$(this).nextAll('table:first').hide();
		$(this).hide();
		$(this).prevAll('input:first').show();
	})
	$('.shows-more').click(function(){
		$(this).nextAll('table:first').show();
		$(this).hide();
		$(this).nextAll('input:first').show();
	})
	$('.prov-retry').click(function () {
		$(this).addClass('disabled');
		var match = $(this).attr('id').match(/^(.+)-btn-retry$/);
		$.ajax({
			url: sbRoot + '/manage/manageSearches/retryProvider?provider=' + match[1],
			type: 'GET',
			complete: function () {
				window.location.reload(true);
            }
		});
	})
});