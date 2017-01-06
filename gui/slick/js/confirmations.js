function bindConfirm(selector, title, text, addShowName, funcParams){

	selector.on('click', function(e){
		e.preventDefault();

		if (!/undefined/i.test(addShowName))
			text = text.replace('%showname%', document.getElementById('showtitle').getAttribute('data-showname'));

		var href = $(this).attr('href');

		$.confirm({
			title		: title,
			text		: text,
			dialogClass	: 'modal-dialog' +
				(/Logout/.test(title) ? ' gold' :
					/Restart/.test(title) ? ' green' :
						/(Shutdown|Remove\sShow)/.test(title) ? ' red' : ''),
			confirm: function(){location.href = href + (/undefined/i.test(funcParams) ? '' : funcParams())},
			cancel: function(){},
			confirmButton: 'Yes', confirmButtonClass: 'green', cancelButton: 'No', cancelButtonClass: 'red'
		});
	});
}

$(document).ready(function () {
	var nav$ = $('nav'), menu$ = $('#SubMenu'), sure = 'Are you sure you want to ';

	bindConfirm(nav$.find('a.logout'), 'Logout', sure + 'logout SickGear ?');
	bindConfirm(nav$.find('a.restart'), 'Restart', sure + 'restart SickGear ?');
	bindConfirm(nav$.find('a.shutdown'), 'Shutdown', sure + 'shutdown SickGear ?');
	bindConfirm(menu$.find('a[href$="/clearHistory/"]'), 'Clear History', sure + 'clear all download history ?');
	bindConfirm(menu$.find('a[href$="/trimHistory/"]'), 'Trim History', sure + 'trim all download history<br />older than 30 days ?');
	bindConfirm(menu$.find('a[href$="/clearerrors/"]'), 'Clear Errors', sure + 'clear all errors ?');
	bindConfirm(menu$.find('a[href*="home/deleteShow"]'), 'Remove Show',
		'Remove <span class="footerhighlight">%showname%</span><br />'
		+ 'from the database, are you sure ?<br /><br />'
		+ '<input type="checkbox" id="delete-files">&nbsp;<span class="red-text">Delete media and meta files as well ?</span></input>',
		!0, function(){ // If checkbox is ticked, remove show and delete files. Else just remove show.
			return document.getElementById('delete-files').checked ? '&full=1' : '';
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
			onConfirm = function(){
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
			};

		$.confirm({
			title: (action + (0 < mFiles ? ' media' : ' records') +
				'<span style="float:right;font-size:12px">(<a class="highlight-text contrast-text" href="/config/general/">"Send to trash" options</a>)</span>'),
			text: (0 < mFiles
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
			dialogClass	: 'modal-dialog red',
			confirmButton: 'Yes', confirmButtonClass: 'green', confirm: onConfirm,
			cancelButton: 'No' + (0 < mFiles ? ', abort ' + ($.SickGear.history.isTrashit ? 'trash' : 'permanent delete') : ''),
			cancelButtonClass: 'red', cancel: function(){}
		});
	});

});
