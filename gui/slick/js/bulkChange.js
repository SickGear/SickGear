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

		var toChange = !1, toDo = {update: [], refresh: [], rename: [], subtitle: [], remove: []};

		$.each(Object.keys(toDo), function(i, k){
			$('.' + k + '-check:checked').each(function(){
				toDo[k].push($(this).closest('tr').attr('data-tvid_prodid'));
				toChange = !0;
			});
		});

		if (!toChange)
			return !1;

		var command = function(deleteFiles){
				window.location.href = $.SickGear.Root + '/manage/bulk-change?'
					+ 'to_update=' + toDo.update.join('|')
					+ '&to_refresh=' + toDo.refresh.join('|')
					+ '&to_rename=' + toDo.rename.join('|')
					+ '&to_subtitle=' + toDo.subtitle.join('|')
					+ '&to_delete=' + (deleteFiles ? toDo.remove : []).join('|')
					+ '&to_remove=' + (deleteFiles ? [] : toDo.remove).join('|');
				return !0;
			};
		if(!toDo.remove.length){
			command(!1);
		} else {
			// one Remove column, the dialog asks what happens to the folders and files, they are kept unless chosen
			var count = toDo.remove.length, shows = count + ' show' + (1 === count ? '' : 's'),
				files = $('#remove-check').closest('th').attr('data-files');
			confirmDialog({
				title: 'Remove ' + shows + ' from SickGear?',
				text: '<label class="remove-choice"><input type="radio" name="remove-files" value="keep" checked> Keep their folders and files</label>'
					+ '<label class="remove-choice"><input type="radio" name="remove-files" value="delete"> Also ' + files + ' their folders and files</label>',
				confirmButton: 'Remove ' + shows, confirmButtonClass: 'red',
				cancelButton: 'Cancel', cancelButtonClass: '',
				confirm: function(){
					command('delete' === $('input[name="remove-files"]:checked').val());
				}
			});
		}

	});

	var updateButtons = function(){
		var editBtn$ = $('#bulk-change-edit'), submitBtn$ = $('#bulk-change-submit'), numEdits = $('.edit-check:checked').length,
			numToDo = $('.update-check:checked, .refresh-check:checked, .rename-check:checked, .subtitle-check:checked,'
				+ ' .remove-check:checked').length;
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

	// the boxes of a column that can be ticked in the rows a filter shows, the header boxes act on these only, so a
	// filter that shows 5 shows does not tick the other rows
	function shownBoxes(name){
		return $('#bulk-change-table tbody tr:not(.filtered) .' + name).filter(function(){return !this.disabled});
	}

	// a header box shows whether all the shown boxes of its column that can be ticked are ticked, or part ticked when
	// some are, the table header and its sticky copy have the same box, so both are set
	function syncTickAll(name){
		var boxes$ = shownBoxes(name), ticked = boxes$.filter(':checked').length;
		$('[id="' + name + '"]').each(function(){
			this.checked = !!boxes$.length && ticked === boxes$.length;
			this.indeterminate = !!ticked && ticked < boxes$.length;
		});
	}

	// on the document, as the sticky header copy is made after this script runs, ticks or clears all shown boxes of the
	// column that can be ticked, it no longer flips each box, which reversed a selection made by hand
	$(document).on('click', '.bulk-check', function(){
		var name = $(this).attr('id'), on = this.checked;
		shownBoxes(name).prop('checked', on);
		syncTickAll(name);
		updateButtons();
	});

	['.edit-check', '.update-check', '.refresh-check', '.rename-check', '.subtitle-check', '.remove-check'].forEach(function(name){
		var lastCheck = null;

		$(name).click(function(event){

			if(!lastCheck || !event.shiftKey){

				lastCheck = this;

			} else {
				var check = this, found = 0;

				// a range runs over the rows a filter shows
				$('#bulk-change-table tbody tr:not(.filtered) ' + name).each(function(){
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
			if (name && !this.disabled){
				$(this).attr('aria-label', 'Filter ' + name).attr('placeholder', 'Filter');
				// the name filter says how to leave words out
				if (1 === +$(this).attr('data-column'))
					$(this).attr({placeholder: 'Filter, !word leaves it out', title: 'part of a name, or !word to leave out the names with it'});
			} else
				$(this).removeAttr('aria-label').attr({'aria-hidden': 'true', tabindex: '-1'});
		});
	}
	nameFilters();
	$('#bulk-change-table').on('updateComplete filterInit filterEnd', nameFilters);

	// the sticky header is a copy for the pointer, a keyboard or screen reader uses the table header, not both
	function hideStickyCopy(){
		$('#bulk-change-table-sticky').attr('aria-hidden', 'true')
			.find('input, button, select, a, [tabindex]').attr('tabindex', '-1')
			.end().find('.tablesorter-filter').each(function(){
				// the hint of the box in the table, the copy is made without it
				$(this).attr('placeholder',
					$('#bulk-change-table .tablesorter-filter[data-column="' + $(this).attr('data-column') + '"]').attr('placeholder'));
			});
	}
	hideStickyCopy();
	$('#bulk-change-table').on('updateComplete sortEnd filterEnd', hideStickyCopy);

	$('#edit-check, .edit-check').each(function(i, el$){
		$(el$).parent().attr('title', 'shift click ticks every box between this one and the one ticked before, in any column');
	})

	function refreshSortCache(table$){
		// a size, or an action box, sorts by its value now, not as it was when the page loaded
		table$.trigger('updateCache');
	}

	// the filters are past 20 header stops for the keyboard, a skip link and the / key go to the name filter
	function focusFilters(){
		$('#bulk-change-table .tablesorter-filter[data-column="1"]').focus();
	}
	$('#skip-to-filters').on('click', function(e){
		e.preventDefault();
		focusFilters();
	});
	$(document).on('keydown', function(e){
		if ('/' === e.key && !e.ctrlKey && !e.altKey && !e.metaKey
			&& !$(e.target).closest('input, select, textarea, button, [contenteditable], .modal').length){
			e.preventDefault();
			focusFilters();
		}
	});

	$('#clear-filters').on('click', function(){
		$('#bulk-change-table').trigger('filterReset');
		$('#bulk-change-table .tablesorter-filter[data-column="1"]').focus();
	});

	// when no show matches, the row names each filter in use, a button clears that one, the focus goes to its box
	function showNoMatch(){
		var table$ = $('#bulk-change-table'), filters = $.tablesorter.getFilters(table$) || [], used = [];
		$.each(filters, function(col, value){
			if (!value)
				return;
			var name = $.trim(table$.find('thead tr:first th').eq(col).text());
			used.push($('<button type="button" class="btn clear-one">').attr({'data-column': col,
				'aria-label': 'Clear the ' + name + ' filter, ' + value}).text(name + ': ' + value + ' ')
				.append('<span aria-hidden="true">&times;</span>'));
		});
		$('#no-match .no-match-text').text(1 < used.length ? 'No shows match these filters' : 'No shows match the filter');
		$('#no-match .no-match-filters').empty().append(used);
		$('#clear-filters').prop('hidden', 2 > used.length);
	}
	$('#no-match').on('click', '.clear-one', function(){
		var table$ = $('#bulk-change-table'), col = +$(this).attr('data-column'), filters = $.tablesorter.getFilters(table$);
		filters[col] = '';
		$.tablesorter.setFilters(table$, filters, !0);
		table$.find('.tablesorter-filter[data-column="' + col + '"]').focus();
	});

	$('#bulk-change-table')
		.bind('sortStart', function(e, t){
			refreshSortCache($(t));
		})
		.bind('filterInit filterEnd', function(e, data){
			$('#no-match').prop('hidden', 0 < data.filteredRows);
			if (!data.filteredRows)
				showNoMatch();
			$('.bulk-check').each(function(){syncTickAll(this.id);});
			$('#tfoot').find('.stats').html(
				(data.filteredRows === data.totalRows
					? '<span class="total-rows">' +  data.totalRows + '</span> shows'
					: '<span class="filter-rows">' + data.filteredRows + '</span> of <span class="total-rows">' + data.totalRows + '</span> shows'));
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
