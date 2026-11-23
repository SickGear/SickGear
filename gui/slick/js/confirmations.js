/**
 * Open a confirmation dialog. This is the one place that sets what all dialogs share.
 * Buttons are a green Yes and a red No unless given, Return confirms unless enterConfirm is false, Esc closes, and the
 * title bar moves the dialog.
 * @param options of jquery.confirm
 * @returns the dialog as a jQuery object, or undefined if a dialog is open
 */
function confirmDialog(options){
	$.confirm($.extend({
		cancel: function(){},
		confirmButton: 'Yes', confirmButtonClass: 'green',
		cancelButton: 'No', cancelButtonClass: 'red'
	}, options));

	const modal$ = $('.confirmation-modal');
	// jquery.confirm opens nothing while a dialog is open, and that dialog is set up
	if (modal$.children().hasClass('ui-draggable'))
		return;

	// Return confirms, unless a focused button, link, or text area handles it, or the dialog sets enterConfirm false.
	// Esc is handled by the bootstrap modal
	modal$.on('keydown', function(e){
		if (13 === e.which && false !== options.enterConfirm && !$(e.target).is('button, a, textarea')) {
			e.preventDefault();
			modal$.find('.confirm').click();
		}
	});
	modal$.children().draggable({handle: '.modal-header'}).find('.modal-header').css('cursor', 'move');

	return modal$;
}

function bindConfirm(selector, title, text, funcParams){

	selector.on('click', function(e){
		e.preventDefault();

		const href = $(this).attr('href');

		confirmDialog({
			title		: title,
			text		: text,
			dialogClass	: 'modal-dialog' +
				(/Logout/.test(title) ? ' gold' :
					/Restart/.test(title) ? ' green' :
						/(Shutdown|Remove\sShow)/.test(title) ? ' red' : ''),
			confirm: function(){location.href = href + (/undefined/i.test(funcParams) ? '' : funcParams())}
		});
	});
}

$(document).ready(function () {
	const nav$ = $('nav'), menu$ = $('#SubMenu'), sure = 'Are you sure you want to ';

	bindConfirm(nav$.find('a.logout'), 'Logout', sure + 'logout SickGear ?');
	bindConfirm(nav$.find('a.restart'), 'Restart', sure + 'restart SickGear ?');
	bindConfirm(nav$.find('a.shutdown'), 'Shutdown', sure + 'shutdown SickGear ?');

	bindConfirm(menu$.find('a[href$="/clear-history/"]'), 'Clear History', sure + 'clear all download history ?');
	bindConfirm(menu$.find('a[href$="/trim-history/"]'), 'Trim History', sure + 'trim all download history<br>older than 30 days ?');
	bindConfirm(menu$.find('a[href$="/clear-log/"]'), 'Clear Errors', sure + 'clear all errors ?');

	bindConfirm(menu$.find('a[href*="home/delete-show"]'), 'Remove Show',
		`Remove <span class="footerhighlight">${$('#showtitle').data('showname')}</span><br>`
		+ 'from the database, are you sure ?<br><br>'
		+ '<input type="checkbox" id="delete-files">&nbsp;<span class="red-text">Delete media and meta files as well ?</span></input>',
		function(){ // If checkbox is ticked, remove show and delete files. Else just remove show.
			return $('#delete-files')[0].checked ? '&full=1' : '';
		});

	$('#del-watched').bind('click', function(e) {
		e.preventDefault();

		let dedupe = [], delArr = [], mFiles = 0;
		$('.del-check').each(function() {
			if (!0 === this.checked) {
				const pathFile = $(this).closest('tr').attr('data-file');
				let thisId = $(this).attr('id');

				if (-1 === jQuery.inArray(pathFile, dedupe)) {
					dedupe.push(pathFile);
					mFiles += 1 - $(this).closest('tr').find('.tvShow .strike-deleted').length;
				}

				delArr.push(thisId.replace('del-', ''));

				/** @namespace $.SickGear.history.isCompact */
				if ($.SickGear.history.isCompact) {
					// then select all related episode checkboxes
					const tvepId = $(this).closest('tr').attr('data-tvep-id');
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
		const action = $.SickGear.history.isTrashit ? 'Trash' : 'Delete',
			onConfirm = function () {
				const deleteFiles = !!$('#delete-files:checked').length,
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
					function (data) {
						const result = $.parseJSON(data);
						result.success && $.hardReload();
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

		confirmDialog({
			title: (`${action} ${0 < mFiles ? 'media' : 'records'}` +
				`<span style="float:right;font-size:12px">(<a class="highlight-text contrast-text" href="/config/general/">"Send to trash" options</a>)</span>`),
			text: (0 < mFiles
				? `<input id="delete-files" style="margin-right:6px"${$.SickGear.history.lastDeleteFiles} type="checkbox">`
				+ `<span>${action} <span class="footerhighlight">${mFiles}</span> media file ${1 === mFiles ? '' : 's'} from disk</span>`
				: ``
			)
			+ '<span style="display:block;margin-top:20px">'
			+ '<input id="delete-records" style="margin-right:6px"' + $.SickGear.history.lastDeleteRecords + ' type="checkbox">'
			+ `Remove <span class="footerhighlight">${delArr.length}</span> history record${(1 === delArr.length ? '' : 's')}</span>`
			+ `<span class="red-text" style="display:block;margin-top:20px">Are you sure ?</span>`,
			dialogClass: 'modal-dialog red',
			confirm: onConfirm,
			cancelButton: 'No' + (0 < mFiles ? ', abort ' + ($.SickGear.history.isTrashit ? 'trash' : 'permanent delete') : '')
		});
	});

});
