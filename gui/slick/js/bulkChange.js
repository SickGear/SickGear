/** @namespace $.SickGear.Root */

$(function(){

	$('#bulk-change-edit').click(function(){
		var toDo = [];

		$('.edit-check:checked').each(function(){
			toDo.push($(this).closest('tr').attr('data-tvid_prodid'));
		});

		if (0 === toDo.length)
			return !1;

		window.location.href = $.SickGear.Root + '/manage/mass-edit?to_edit=' + toDo.join('|');
	});

	$('#bulk-change-submit').click(function(){

		var toChange = !1, toDo = {update: [], refresh: [], rename: [], subtitle: [], delete: [], remove: []};

		$.each(Object.keys(toDo), function(i, k){
			$('.' + k + '-check:checked').each(function(){
				toDo[k].push($(this).closest('tr').attr('data-tvid_prodid'));
				toChange = !0;
			});
		});

		if (!toChange)
			return !1;

		var confirmArr = [],
			command = function(){
				window.location.href = $.SickGear.Root + '/manage/bulk-change?'
					+ 'to_update=' + toDo.update.join('|')
					+ '&to_refresh=' + toDo.refresh.join('|')
					+ '&to_rename=' + toDo.rename.join('|')
					+ '&to_subtitle=' + toDo.subtitle.join('|')
					+ '&to_delete=' + toDo.delete.join('|')
					+ '&to_remove=' + toDo.remove.join('|');
				return !0;
			};
		if(toDo.delete.length){
			confirmArr.push('delete ' + toDo.delete.length);
		}
		if(toDo.remove.length){
			confirmArr.push('remove ' + toDo.remove.length);
		}
		if(!confirmArr.length){
			command();
		} else {
			confirmDialog({
				title: 'Are you sure ?',
				text: confirmArr.join(' and ') + ' show(s)',
				confirm	: command
			});
		}

	});

	var updateButtons = function(){
		var editBtn$ = $('#bulk-change-edit'), submitBtn$ = $('#bulk-change-submit'), numEdits = $('.edit-check:checked').length,
			numToDo = $('.update-check:checked, .refresh-check:checked, .rename-check:checked, .subtitle-check:checked,'
				+ ' .delete-check:checked, .remove-check:checked').length;
		if(!!numEdits){
			editBtn$.attr('disabled', !1);
			editBtn$.val('Edit ' + numEdits + ' selected');
		} else {
			editBtn$.attr('disabled', !0);
			editBtn$.val('Select items');
		}
		if(!!numToDo){
			submitBtn$.attr('disabled', !1);
			submitBtn$.val('Submit ' + numToDo + ' action(s)');
		} else {
			submitBtn$.attr('disabled', !0);
			submitBtn$.val('Select actions');
		}
	}
	updateButtons();

	// a header box shows whether all the boxes of its column that can be ticked are ticked, or part ticked when some are
	// the table header and its sticky copy have the same box, so both are set
	function syncTickAll(name){
		var boxes$ = $('.' + name).filter(function(){return !this.disabled}), ticked = boxes$.filter(':checked').length;
		$('[id="' + name + '"]').each(function(){
			this.checked = !!boxes$.length && ticked === boxes$.length;
			this.indeterminate = !!ticked && ticked < boxes$.length;
		});
	}

	// on the document, as the sticky header copy is made after this script runs, ticks or clears all boxes of the
	// column that can be ticked, it no longer flips each box, which reversed a selection made by hand
	$(document).on('click', '.bulk-check', function(){
		var name = $(this).attr('id'), on = this.checked;
		$('.' + name).each(function(){
			if (!this.disabled)
				this.checked = on;
		});
		syncTickAll(name);
		updateButtons();
	});

	['.edit-check', '.update-check', '.refresh-check', '.rename-check', '.subtitle-check', '.delete-check', '.remove-check'].forEach(function(name){
		var lastCheck = null;

		$(name).click(function(event){

			if(!lastCheck || !event.shiftKey){

				lastCheck = this;

			} else {
				var check = this, found = 0;

				$(name).each(function(){
					switch (found){
						case 2:
							return !1;
						case 1:
							if (!this.disabled)
								this.checked = lastCheck.checked;
					}

					if (this === check || this === lastCheck)
						found++;
				});
			}
			updateButtons();
			syncTickAll(name.slice(1));
		});
		syncTickAll(name.slice(1));
	});

	// a click on a row, not on a link or a control, ticks the Edit checkbox of the row, with shift as on the checkbox
	$('#bulk-change-table tbody')
		.on('mousedown', 'tr', function(event){
			// a shift click selects rows, not the text between them
			if (event.shiftKey && !$(event.target).closest('a, input, button, select, label, textarea').length)
				event.preventDefault();
		})
		.on('click', 'tr', function(event){
			if ($(event.target).closest('a, input, button, select, label, textarea').length)
				return;
			var check = $(this).find('.edit-check')[0];
			if (check && !check.disabled)
				check.dispatchEvent(new MouseEvent('click', {bubbles: !0, cancelable: !0,
					shiftKey: event.shiftKey, ctrlKey: event.ctrlKey}));
		});

	// a name for each filter box in use, from its column header, a box of a column with no filter is hidden from all,
	// again after a table update, as the filter widget then makes the filter boxes anew, a change of size type does
	function nameFilters(){
		$('#bulk-change-table .tablesorter-filter').each(function(){
			var name = $.trim($('#bulk-change-table thead tr:first th').eq($(this).attr('data-column')).text());
			if (name && !this.disabled)
				$(this).attr('aria-label', 'Filter ' + name).attr('placeholder', 'Filter');
			else
				$(this).removeAttr('aria-label').attr({'aria-hidden': 'true', tabindex: '-1'});
		});
	}
	nameFilters();
	$('#bulk-change-table').on('updateComplete filterInit', nameFilters);

	// the sticky header is a copy for the pointer, a keyboard or screen reader uses the table header, not both
	function hideStickyCopy(){
		$('#bulk-change-table-sticky').attr('aria-hidden', 'true')
			.find('input, button, select, a, [tabindex]').attr('tabindex', '-1')
			.end().find('.tablesorter-filter').attr('placeholder', 'Filter');
	}
	hideStickyCopy();
	$('#bulk-change-table').on('updateComplete sortEnd filterEnd', hideStickyCopy);

	$('#edit-check, .edit-check').each(function(i, el$){
		$(el$).parent().attr('title', 'multiselect = ctrl/shift + left click');
	})

	function refreshSortCache(table$){
		// a size, or an action box, sorts by its value now, not as it was when the page loaded
		table$.trigger('updateCache');
	}

	$('#clear-filters').on('click', function(){
		$('#bulk-change-table').trigger('filterReset');
		$('#bulk-change-table .tablesorter-filter[data-column="1"]').focus();
	});

	$('#bulk-change-table')
		.bind('sortStart', function(e, t){
			refreshSortCache($(t));
		})
		.bind('filterInit filterEnd', function(e, data){
			$('#no-match').prop('hidden', 0 < data.filteredRows);
			$('#tfoot').find('.stats').html(
				(data.filteredRows === data.totalRows
					? '<span class="total-rows">' +  data.totalRows + '</span> shows'
					: '<span class="filter-rows">' + data.filteredRows + '</span> of <span class="total-rows">' + data.totalRows + '</span>  shows (' + (data.totalRows - data.filteredRows) + ' filtered)'));
		});

	// read the size of every show folder, slow on a large or network drive, so only when asked for
	// a size as the server writes it, e.g. 443 KB, 4.3 MB, 4.43 GB
	function human(size){
		if (1 === size)
			return '1 byte';
		var units = [['bytes', 0], ['KB', 0], ['MB', 1], ['GB', 2], ['TB', 2], ['PB', 2]], n = 0, num = size, text;
		while (1024 <= num && n < units.length - 1){
			num /= 1024;
			n++;
		}
		if (!units[n][1])
			return Math.floor(num) + ' ' + units[n][0];
		text = String(Math.round(num * Math.pow(10, units[n][1])) / Math.pow(10, units[n][1]));
		return (/\./.test(text) ? text : text + '.0') + ' ' + units[n][0];
	}

	// read the size of every show folder, slow on a large or network drive, so only when the button asks for it
	function readSizes(){
		var url = $.SickGear.Root + '/home/media_stats';
		return $.getJSON(url, {refresh: 1}).then(function(content){
			var read = content._read;
			delete content._read;
			if (read){
				displayPNotify('success', 'Folder sizes', read.shows + ' show folders read in ' + read.took);
				$('.sort-size').attr('title', 'Total size: all files in a show folder; average, largest and smallest file: one of its media files');
			}
			return content;
		}, function(xhr, status, error){
			console.log('data fetch error', url, status + ': ' + error);
			displayPNotify('error', 'Folder sizes', 'The show folders could not be read');
		});
	}

	// each row keeps its total size and its media file stats, files,smallest,largest,average, from the database or
	// a folder read, so the size type column changes what the size column shows without asking the server
	function keepSizes(content){
		$.each(content, function(tvidProdid, data){
			$('tr[data-tvid_prodid="' + tvidProdid + '"][data-size]')
				.attr('data-total', data.bSize)
				.attr('data-stats', [data.nFiles || 0, data.bSmallest || 0, data.bLargest || 0, data.bAverageSize || 0].join(','));
		});
	}

	function showSizes(key){
		$('tr[data-tvid_prodid][data-stats]').each(function(){
			var row$ = $(this), size$ = row$.find('.ui-size'), stats = row$.attr('data-stats').split(',').map(Number),
				val = {Size: Number(row$.attr('data-total')), Smallest: stats[1], Largest: stats[2], AverageSize: stats[3]}[key];
			if (!size$.length)
				return;
			if (0 < val && ('Size' === key || 0 < stats[0])){
				size$.removeClass('grey-text').removeAttr('title').html(human(val));
				row$.attr('data-size', val);
			} else {
				size$.addClass('grey-text').attr('title', 'no media files').html('---');
				row$.attr('data-size', -10);
			}
		});
		// the sort values and the sort only, a table update makes the filter boxes anew, clears a filter, and filters
		// again, after which the sticky header scrolls the page up to the top of the table
		var table$ = $('#bulk-change-table');
		table$.trigger('updateCache').trigger('sorton', [table$[0].config.sortList]);
	}

	$('#read-folder-sizes').on('click', function(){
		var button$ = $(this).prop('disabled', !0).html('<i class="spinner"></i> Reading folders');
		readSizes().then(function(content){
			keepSizes(content);
			showSizes('Size');
			$('select.size-type').val('Size');
			button$.attr('title', 'sizes are of all show folder files, read again');
		}).always(function(){
			button$.prop('disabled', !1).html('Read folder sizes');
		});
	});

	// on the document, the sticky header of the table is a copy that tablesorter makes after this script runs
	$(document).on('change', 'select.size-type', function(){
		var key = $(this).val();
		showSizes(key);
		$.tablesorter.setColumnAriaLabel($('#bulk-change-table')[0].config, $('#bulk-change-table th.sort-size'));
		// both menus after the sizes, as their table update makes the sticky header copy again, with no menu choice
		$('select.size-type').val(key);
	});

});
