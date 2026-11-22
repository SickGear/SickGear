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

	$('.bulk-check').click(function(){

		$('.' + $(this).attr('id')).each(function(){
			if (!this.disabled)
				this.checked = !this.checked
		});
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
		});
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

	$('#edit-check, .edit-check').each(function(i, el$){
		$(el$).parent().attr('title', 'multiselect = ctrl/shift + left click');
	})

	$.SickGear.onRefreshSize = !1;
	function presortTable(table$){
		var asc = $('.sort-size.tablesorter-headerAsc').length,
			desc = $('.sort-size.tablesorter-headerDesc').length,
			value;

		if (!!(asc + desc) || !!$.SickGear.onRefreshSize){
			$('[data-size]').each(function(i, el){
				value = parseInt($(el).attr('data-size'), 10);
				$(el).attr('data-size', (!!desc !== !!$.SickGear.onRefreshSize) /* xor */
					? ((value < 0) ? (-1 * value) + $.SickGear.high : value)
					: ((value > $.SickGear.high) ? -1 * (value - $.SickGear.high) : value))
			});
		}
		// an action box sorts by its state now, it was read when the page loaded
		table$.trigger('updateCache');
	}

	$('#bulk-change-table')
		.bind('refreshComplete', function(){
			$.SickGear.onRefreshSize = !0;
		})
		.bind('sortEnd', function(){
			$.SickGear.onRefreshSize = !1;

			var el$ = $('.sort-size-type');
			if (!!($('.sort-size.tablesorter-headerAsc').length + $('.sort-size.tablesorter-headerDesc').length)){
				el$.removeClass('tablesorter-headerUnSorted').addClass('tablesorter-headerSorted');
			} else {
				el$.removeClass('tablesorter-headerSorted');
			}
		})
		.bind('sortStart', function(e, t){
			presortTable($(t));
		})
		.bind('filterInit filterEnd', function(e, data){
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
				$('.sort-size').attr('title', 'size of all show folder files');
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
			$('.sort-size-type').attr('title', 'total').attr('data-type', 'E').find('.sort-size-type-body').html('&Sigma;');
			showSizes('Size');
			button$.attr('title', 'sizes are of all show folder files, read again');
		}).always(function(){
			button$.prop('disabled', !1).html('Read folder sizes');
		});
	});

	$('.sort-size-type').on('click', function(){
		var that = $(this), title = 'total', htmlType = '&Sigma;', dataType = 'E', key = 'Size';
		if(dataType === $(this).attr('data-type')){
			title = 'average';
			htmlType = '<div class="average"><i>x</i></div>';
			dataType = 'x';
			key = 'AverageSize';
		} else if('x' === $(this).attr('data-type')){
			title = 'largest';
			htmlType = '&gt';
			dataType = '>';
			key = 'Largest';
		} else if('>' === $(this).attr('data-type')){
			title = 'smallest';
			htmlType = '&lt';
			dataType = '<';
			key = 'Smallest';
		}
		showSizes(key);
		that.attr('title', title);
		that.attr('data-type', dataType);
		that.find('.sort-size-type-body').html(htmlType);
	});

});
