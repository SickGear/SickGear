/** @namespace $.SickGear.Root */

$(document).ready(function() {

	$('#submitMassEdit').click(function() {
		var editArr = [];

		$('.editCheck').each(function() {
			if (true == this.checked) {
				editArr.push($(this).attr('id').split('-')[1])
			}
		});

		if (0 == editArr.length)
			return !1;

		window.location.href = $.SickGear.Root + '/manage/massEdit?toEdit=' + editArr.join('|');
	});


	$('#submitMassUpdate').click(function() {

		var updateArr = [], refreshArr = [], renameArr = [], subtitleArr = [],
			deleteArr = [], removeArr = [], metadataArr = [];

		$('.updateCheck').each(function() {
			if (true == this.checked) {
				updateArr.push($(this).attr('id').split('-')[1])
			}
		});

		$('.refreshCheck').each(function() {
			if (true == this.checked) {
				refreshArr.push($(this).attr('id').split('-')[1])
			}
		});

		$('.renameCheck').each(function() {
			if (true == this.checked) {
				renameArr.push($(this).attr('id').split('-')[1])
			}
		});

		$('.subtitleCheck').each(function() {
			if (true == this.checked) {
				subtitleArr.push($(this).attr('id').split('-')[1])
			}
		});

		$('.deleteCheck').each(function() {
			if (true == this.checked) {
				deleteArr.push($(this).attr('id').split('-')[1])
			}
		});

		$('.removeCheck').each(function() {
			if (true == this.checked) {
				removeArr.push($(this).attr('id').split('-')[1])
			}
		});

/*
		$('.metadataCheck').each(function() {
			if (true == this.checked) {
				metadataArr.push($(this).attr('id').split('-')[1])
			}
		});
*/
		if (0 == updateArr.length + refreshArr.length + renameArr.length + subtitleArr.length + deleteArr.length + removeArr.length + metadataArr.length)
			return !1;

		window.location.href = $.SickGear.Root + 'massUpdate?toUpdate=' + updateArr.join('|') + '&toRefresh=' + refreshArr.join('|') + '&toRename=' + renameArr.join('|') + '&toSubtitle=' + subtitleArr.join('|') + '&toDelete=' + deleteArr.join('|') + '&toRemove=' + removeArr.join('|') + '&toMetadata=' + metadataArr.join('|');

	});

	$('.bulkCheck').click(function() {

		var bulkCheck = this, whichBulkCheck = $(bulkCheck).attr('id');

		$('.' + whichBulkCheck).each(function() {
			if (!this.disabled)
				this.checked = !this.checked
		});
	});

	['.editCheck', '.updateCheck', '.refreshCheck', '.renameCheck', '.deleteCheck', '.removeCheck'].forEach(function(name) {
		var lastCheck = null;

		$(name).click(function(event) {

			if(!lastCheck || !event.shiftKey) {
				lastCheck = this;
				return;
			}

			var check = this, found = 0;

			$(name).each(function() {
				switch (found) {
					case 2:
						return !1;
					case 1:
						if (!this.disabled)
							this.checked = lastCheck.checked;
				}

				if (this == check || this == lastCheck)
					found++;
			});
		});
	});

});
