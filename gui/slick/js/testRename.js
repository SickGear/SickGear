$(document).ready(function(){
	$('.seasonCheck').click(function(){
		var seasCheck = this;
		var seasNo = $(seasCheck).attr('id');

		$('.epCheck:visible').each(function(){
			var epParts = $(this).attr('id').split('x');

			if (epParts[0] === seasNo) {
				this.checked = seasCheck.checked;
			}
		});
	});

	// selects all visible episode checkboxes
	$('.seriesCheck').click(function () {
		$('.epCheck:visible, .seasonCheck:visible').each(function () {
			this.checked = !0;
		});
	});

	// clears all visible episode checkboxes and the season selectors
	$('.clearAll').click(function () {
		$('.epCheck:visible, .seasonCheck:visible').each(function () {
			this.checked = !1;
		});
	});

	$('input[type=submit]').click(function(){
		var epArr = [];

		$('.epCheck').each(function() {
			if (this.checked === !0) {
				epArr.push($(this).attr('id'))
			}
		});

		if (0 === epArr.length)
			return !1;

		window.location.href = sbRoot + '/home/doRename?show=' + $('#showID').val() + '&eps=' + epArr.join('|');
	});

});
