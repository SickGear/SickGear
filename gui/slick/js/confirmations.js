$(document).ready(function () {
	$('a.logout').bind('click',function(e) {
		e.preventDefault();
		var target = $( this ).attr('href');
		$.confirm({
			'title'		: 'Logout',
			'message'	: 'Are you sure you want to Logout from SickGear ?',
			'buttons'	: {
				'Yes'	: {
					'class'	: 'green',
					'action': function(){
						location.href = target;
					}
				},
				'No'	: {
					'class'	: 'red',
					'action': function(){}	// Nothing to do in this case. You can as well omit the action property.
				}
			}
		});
	});

	$('a.shutdown').bind('click',function(e) {
		e.preventDefault();
		var target = $( this ).attr('href');
		$.confirm({
			'title'		: 'Shutdown',
			'message'	: 'Are you sure you want to shutdown SickGear ?',
			'buttons'	: {
				'Yes'	: {
					'class'	: 'green',
					'action': function(){
						location.href = target;
					}
				},
				'No'	: {
					'class'	: 'red',
					'action': function(){}	// Nothing to do in this case. You can as well omit the action property.
				}
			}
		});
	});

	$('a.restart').bind('click',function(e) {
		e.preventDefault();
		var target = $( this ).attr('href');
		$.confirm({
			'title'		: 'Restart',
			'message'	: 'Are you sure you want to restart SickGear ?',
			'buttons'	: {
				'Yes'	: {
					'class'	: 'green',
					'action': function(){
						location.href = target;
					}
				},
				'No'	: {
					'class'	: 'red',
					'action': function(){}	// Nothing to do in this case. You can as well omit the action property.
				}
			}
		});
	});

	$('a.remove').bind('click',function(e) {
		e.preventDefault();
		var target = $( this ).attr('href');
		var showname = document.getElementById('showtitle').getAttribute('data-showname');
		$.confirm({
			'title'		: 'Remove Show',
			'message'	: 'Are you sure you want to remove <span class="footerhighlight">' + showname + '</span> from the database ?<br /><br /><input type="checkbox" id="delete-files"> <span class="red-text">Check to delete files as well. IRREVERSIBLE</span>',
			'buttons'	: {
				'Yes'	: {
					'class'	: 'green',
					'action': function(){
						location.href = target + (document.getElementById('delete-files').checked ? '&full=1' : '');
						// If checkbox is ticked, remove show and delete files. Else just remove show.
					}
				},
				'No'	: {
					'class'	: 'red',
					'action': function(){}	// Nothing to do in this case. You can as well omit the action property.
				}
			}
		});
	});

	$('#del-watched').bind('click', function(e) {
		e.preventDefault();

		var dedupe = [], delArr = [], mFiles = 0;
		$('.del-check').each(function() {
			if (!0 === this.checked) {
				var pathFile = $(this).closest('tr').attr('data-file'),
					thisId = $(this).attr('id');

				if (-1 === jQuery.inArray(pathFile, dedupe)) {
					dedupe.push(pathFile);
					mFiles += 1 - $(this).closest('tr').find('.tvShow .strike-deleted').length;
				}

				delArr.push(thisId.replace('del-', ''));

				/** @namespace $.SickGear.history.isCompact */
				if ($.SickGear.history.isCompact) {
					// then select all related episode checkboxes
					var tvepId = $(this).closest('tr').attr('data-tvep-id');
					$('tr[data-tvep-id="' + tvepId + '"] input.del-check:not("#' + thisId + '")')
						.each(function(){
							delArr.push($(this).attr('id').replace('del-', ''));
						});
				}
			}
		});
		if (0 === delArr.length)
			return !1;

		/** @namespace $.SickGear.history.isTrashit */
		/** @namespace $.SickGear.history.lastDeleteFiles */
		/** @namespace $.SickGear.history.lastDeleteRecords */
		var action = $.SickGear.history.isTrashit ? 'Trash' : 'Delete',
			btns = {
				'Yes'	: {
					'class'	: 'green',
					'action': function(){
						var deleteFiles = !!$('#delete-files:checked').length,
							deleteRecords = !!$('#delete-records:checked').length,
							checked = ' checked="checked"';
						$.SickGear.history.lastDeleteFiles = deleteFiles ? checked : '';
						$.SickGear.history.lastDeleteRecords = deleteRecords ? checked : '';
						$.post($.SickGear.Root + '/history/watched',
							{
								_xsrf: Cookies.get('_xsrf'),
								tvew_id: delArr.join('|'),
								files: (deleteFiles ? '1' : ''),
								records: (deleteRecords ? '1' : '')
							},
							function(data){
								var result = $.parseJSON(data);
								result.success && window.location.reload(true);
								/* using window.location as the following is
								   sluggish when deleting 20 of 100 records
								*/
								/*
								result.success && $.each(result.success, function(){
									var tr = $('#del-' + this).closest('tr');
									var t = tr.closest('table');
									tr.addClass('delete-me').fadeToggle('fast', 'linear').promise().done(
										function(){
											$('.delete-me').html('');
											t.trigger('update');
											$.SickGear.sumChecked();
										});
								});*/
						});
					}
				}
			};

		// btn pre-created here in order to use a custom btn text as named key to object
		btns['No' + (0 < mFiles ? ', abort ' + ($.SickGear.history.isTrashit ? 'trash' : 'permanent delete') : '')] = {'class' : 'red'};
		$.confirm({
			'title'		: (action + (0 < mFiles ? ' media' : ' records')
				+ '<span style="float:right;font-size:12px">(<a class="highlight-text contrast-text" href="/config/general/">"Send to trash" options</a>)</span>'),
			'message'	: (0 < mFiles
					? '<input id="delete-files" style="margin-right:6px"' + $.SickGear.history.lastDeleteFiles + ' type="checkbox">'
					+ '<span>' + action + ' <span class="footerhighlight">' + mFiles + '</span>'
					+ ' media file' + (1===mFiles?'':'s') + ' from disk</span>'
					: ''
			)
			+ '<span style="display:block;margin-top:20px">'
			+ '<input id="delete-records" style="margin-right:6px"' + $.SickGear.history.lastDeleteRecords + ' type="checkbox">'
			+ 'Remove <span class="footerhighlight">'
			+ delArr.length + '</span> history record' + (1===delArr.length?'':'s')
			+ '</span>'
			+ '<span class="red-text" style="display:block;margin-top:20px">Are you sure ?</span>',
			'buttons'	: btns
		});
	});

	$('a.clearhistory').bind('click',function(e) {
		e.preventDefault();
		var target = $( this ).attr('href');
		$.confirm({
			'title'		: 'Clear History',
			'message'	: 'Are you sure you want to clear all download history ?',
			'buttons'	: {
				'Yes'	: {
					'class'	: 'green',
					'action': function(){
						location.href = target;
					}
				},
				'No'	: {
					'class'	: 'red',
					'action': function(){}	// Nothing to do in this case. You can as well omit the action property.
				}
			}
		});
	});

	$('a.trimhistory').bind('click',function(e) {
		e.preventDefault();
		var target = $( this ).attr('href');
		$.confirm({
			'title'		: 'Trim History',
			'message'	: 'Are you sure you want to trim all download history older than 30 days ?',
			'buttons'	: {
				'Yes'	: {
					'class'	: 'green',
					'action': function(){
						location.href = target;
					}
				},
				'No'	: {
					'class'	: 'red',
					'action': function(){}	// Nothing to do in this case. You can as well omit the action property.
				}
			}
		});
	});

});
