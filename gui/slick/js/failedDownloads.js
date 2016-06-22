$(document).ready(function() {

	$('#limit').change(function() {
		window.location.href = sbRoot + '/manage/failedDownloads/?limit=' + $(this).val();
	});

	$('#submitMassRemove').click(function() {

		var removeArr = [];

		$('.removeCheck').each(function() {
			if (!0 == this.checked) {
				removeArr.push($(this).attr('id').split('-')[1])
			}
		});

		if (0 == removeArr.length)
			return !1;

		window.location.href = sbRoot + '/manage/failedDownloads?toRemove=' + removeArr.join('|');
	});

	$('.bulkCheck').click(function() {

		var bulkCheck = this, whichBulkCheck = $(bulkCheck).attr('id');

		$('.' + whichBulkCheck + ':visible').each(function() {
			this.checked = bulkCheck.checked
		});
	});

	['.removeCheck'].forEach(function(name) {

		var lastCheck = null;

		$(name).click(function(event) {

			var table$ = $('#failedTable');
			if(!lastCheck || !event.shiftKey) {
				lastCheck = this;
				$(this).parent('td').attr('data-order', this.checked ? '1' : '0');
				table$.trigger('update');
				return;
			}

			var check = this, found = 0;

			$(name + ':visible').each(function() {
				switch (found) {
					case 2:
						return !1;
					case 1:
						this.checked = lastCheck.checked;
						$(this).parent('td').attr('data-order', this.checked ? '1' : '0');
				}

				if (this == check || this == lastCheck)
					found++;
			});

			table$.trigger('update');
		});
	});

	$('#failedTable:has(tbody tr)').tablesorter({
		widgets: ['zebra'],
		sortList: [[0,0]],
		sortAppend: [[0,0]],
		textExtraction: {
			0: function(node) { return $(node).attr('data-order'); },
			3: function(node) { return $(node).find('img').attr('title'); },
			4: function(node) { return $(node).attr('data-order'); }}
	});

});
