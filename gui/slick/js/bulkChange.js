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

		var toChange = !1, toDo = {update: [], refresh: [], rename: [], subtitle: [], remove: []},
			names = {update: [], refresh: [], rename: [], subtitle: [], remove: []}, dropped = {update: 0, remove: 0};

		// as the server does it, a show to remove has no other action, and Update rescans a show too
		$.each(Object.keys(toDo), function(i, k){
			$('.' + k + '-check:checked').each(function(){
				var row$ = $(this).closest('tr'),
					by = 'remove' !== k && row$.find('.remove-check').is(':checked') ? 'remove'
						: 'refresh' === k && row$.find('.update-check').is(':checked') ? 'update' : '';
				if (by){
					dropped[by]++;
					return;
				}
				toDo[k].push(row$.attr('data-tvid_prodid'));
				names[k].push({name: $.trim(row$.find('.tvShow').text()), hidden: row$.hasClass('filtered')});
				toChange = !0;
			});
		});

		if (!toChange)
			return !1;

		// sent as a form post with the page token, an address with the shows would be kept in the browser history, where
		// a reload or a step back could send it again
		var command = function(deleteFiles){
				var form$ = $('<form method="post">').attr('action', $.SickGear.Root + '/manage/bulk-change');
				$.each({to_update: toDo.update, to_refresh: toDo.refresh, to_rename: toDo.rename, to_subtitle: toDo.subtitle,
					to_delete: deleteFiles ? toDo.remove : [], to_remove: deleteFiles ? [] : toDo.remove}, function(name, ids){
					form$.append($('<input type="hidden">').attr({name: name, value: ids.join('|')}));
				});
				form$.append($('input[name="_xsrf"]').first().clone()).appendTo('body').submit();
				return !0;
			},
			labels = {update: 'Update', refresh: 'Rescan', rename: 'Rename', subtitle: 'Subtitle', remove: 'Remove'},
			plural = function(n){return n + ' show' + (1 === n ? '' : 's');},
			text$ = $('<div>'), total = 0;

		// Submit shows what it will do to which shows before it does it, a show a filter hides is marked
		$.each(Object.keys(names), function(i, k){
			if (!names[k].length)
				return;
			total += names[k].length;
			var list$ = $('<ul class="review-shows">');
			$.each(names[k], function(j, show){
				list$.append($('<li>').text(show.name).append(show.hidden ? ' <span class="grey-text">(hidden by the filter)</span>' : ''));
			});
			text$.append($('<div class="review-action">').text(labels[k] + ' ' + plural(names[k].length)), list$);
		});
		if (dropped.update || dropped.remove){
			text$.append($('<p class="grey-text">').text($.grep([
				dropped.update ? 'Update also rescans a show, so ' + dropped.update + ' Rescan tick' + (1 === dropped.update ? ' is' : 's are') + ' left out' : '',
				dropped.remove ? 'a show to remove has no other action, so ' + dropped.remove + ' tick' + (1 === dropped.remove ? ' is' : 's are') + ' left out' : ''
			], Boolean).join(', ').replace(/^./, function(c){return c.toUpperCase();}) + '.'));
		}
		if (toDo.remove.length){
			// what Remove does with the folders and files, they are kept unless chosen
			text$.append('<label class="remove-choice"><input type="radio" name="remove-files" value="keep" checked> Keep their folders and files</label>'
				+ '<label class="remove-choice"><input type="radio" name="remove-files" value="delete"> Also '
				+ $('#remove-check').closest('th').attr('data-files') + ' their folders and files</label>');
		}
		var modal$ = confirmDialog({
			title: 'Submit ' + total + ' action' + (1 === total ? '' : 's') + '?',
			text: text$.html(),
			confirmButton: toDo.remove.length ? 'Remove ' + plural(toDo.remove.length) + (total > toDo.remove.length ? ' and submit' : '') : 'Submit',
			confirmButtonClass: toDo.remove.length ? 'red' : 'green',
			cancelButton: 'Cancel', cancelButtonClass: '',
			// Return does not confirm, the focus starts on Cancel
			enterConfirm: !1,
			confirm: function(){
				command(toDo.remove.length && 'delete' === $('input[name="remove-files"]:checked').val());
			}
		});
		if (modal$)
			modal$.one('shown.bs.modal', function(){modal$.find('.cancel').focus();}).find('.cancel').focus();

	});

	// ticks in rows a filter hides are still submitted, the footer says how many shows have them
	function showHiddenTicks(){
		var count = $('#bulk-change-table tbody tr.filtered').filter(function(){return !!$(this).find('input[type="checkbox"]:checked').length;}).length;
		$('#hidden-ticks').prop('hidden', !count).text(count + ' ticked show' + (1 === count ? ' is' : 's are') + ' hidden by the filter');
	}

	var updateButtons = function(){
		showHiddenTicks();
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
	function tickAll(name, on){
		shownBoxes(name).prop('checked', on);
		syncTickAll(name);
		updateButtons();
	}

	// Submit shows the shows of each action before it acts, so tick all acts at once, Remove too
	$(document).on('click', '.bulk-check', function(){
		tickAll($(this).attr('id'), this.checked);
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
		orderYesNo('#bulk-change-table');
		$('#bulk-change-table .tablesorter-filter').each(function(){
			var name = $.trim($('#bulk-change-table thead tr:first th').eq($(this).attr('data-column')).text());
			if (name && !this.disabled){
				$(this).attr('aria-label', 'Filter ' + name).attr('placeholder', 'Filter');
				// the name filter says how to leave words out
				if (1 === +$(this).attr('data-column'))
					$(this).attr({placeholder: 'Filter, !word skips', title: 'part of a name, or !word to leave out the names with it'});
			} else
				$(this).removeAttr('aria-label').attr({'aria-hidden': 'true', tabindex: '-1'});
		});
	}
	nameFilters();
	$('#bulk-change-table').on('updateComplete filterInit filterEnd', nameFilters);

	// a yes or no filter menu lists Yes before No, the table script sorts its options
	function orderYesNo(table){
		$(table + ' select.tablesorter-filter').each(function(){
			$(this).find('option[value="Yes"]').insertBefore($(this).find('option[value="No"]'));
		});
	}

	// the sticky header is a copy for the pointer, a keyboard or screen reader uses the table header, not both
	function hideStickyCopy(){
		orderYesNo('#bulk-change-table-sticky');
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

	$(document).on('click', '#footer-clear-filters', function(){
		$('#bulk-change-table').trigger('filterReset');
		$('#bulk-change-table .tablesorter-filter[data-column="1"]').focus();
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
			// a filter in use is marked, its box and the label of its column, in the table and its sticky copy
			$('#bulk-change-table .tablesorter-filter, #bulk-change-table-sticky .tablesorter-filter').each(function(){
				var used = !!$(this).val();
				$(this).toggleClass('filter-in-use', used)
					.closest('table').find('thead tr:first th').eq($(this).attr('data-column')).toggleClass('column-filtered', used);
			});
			if (!data.filteredRows)
				showNoMatch();
			$('.bulk-check').each(function(){syncTickAll(this.id);});
			$('#tfoot').find('.stats').html(
				(data.filteredRows === data.totalRows
					? '<span class="total-rows">' +  data.totalRows + '</span> shows'
					: '<span class="filter-rows">' + data.filteredRows + '</span> of <span class="total-rows">' + data.totalRows + '</span> shows'));
			// the button is out of the announced count, so a screen reader hears the count only
			$('#footer-clear-filters').prop('hidden', data.filteredRows === data.totalRows);
			showHiddenTicks();
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
