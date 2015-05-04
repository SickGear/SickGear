$(document).ready(function() { 
	$('#showupdatebutton').click(function(){
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
});