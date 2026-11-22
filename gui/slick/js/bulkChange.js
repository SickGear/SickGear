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
	function readSizes(refresh){
		var url = $.SickGear.Root + '/home/media_stats';
		return $.getJSON(url, refresh ? {refresh: 1} : {}).then(function(content){
			var read = content._read;
			delete content._read;
			if (read){
				displayPNotify('success', 'Folder sizes',
					read.shows + ' show folders ' + (read.ago
						? 'were read ' + read.ago + ' ago in ' + read.took
						: 'read in ' + read.took));
				$('.sort-size').attr('title', 'size of all show folder files');
			}
			return content;
		}, function(xhr, status, error){
			console.log('data fetch error', url, status + ': ' + error);
			displayPNotify('error', 'Folder sizes', 'The show folders could not be read');
		});
	}

	function showSizes(content, key){
		var html, val, el$;
		$.each(content, function(tvidProdid, data){
			html = '---';
			val = '-10';
			el$ = $('tr[data-tvid_prodid="' + tvidProdid + '"][data-size]');
			if (/undefined/.test(data.message) || 'Size' === key){
				html = data['h' + key];
				val = data['b' + key];
			}
			el$.find('.ui-size').removeClass('grey-text').removeAttr('title').html(html);
			el$.attr('data-size', val);
		});
		$('#bulk-change-table').trigger('updateAll', [!0]);
	}

	$('#read-folder-sizes').on('click', function(){
		var button$ = $(this).prop('disabled', !0).html('<i class="spinner"></i> Reading folders');
		readSizes(!0).then(function(content){
			showSizes(content, 'Size');
			var type$ = $('.sort-size-type');
			type$.attr('title', 'total').attr('data-type', 'E').find('.sort-size-type-body').html('&Sigma;');
			button$.attr('title', 'sizes are of all show folder files, read again');
		}).always(function(){
			button$.prop('disabled', !1).html('Read folder sizes');
		});
	});

	$('.sort-size-type').on('click', function(){
		$('.sort-size-type-body').hide();
		$('.sort-size-type-image').show();
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

		readSizes(!1).then(function(content){
			showSizes(content, key);
			that.attr('title', title);
			that.attr('data-type', dataType);
			that.find('.sort-size-type-body').html(htmlType);
		}).always(function(){
			$('.sort-size-type-image').hide();
			$('.sort-size-type-body').show();
		});
	});

});
