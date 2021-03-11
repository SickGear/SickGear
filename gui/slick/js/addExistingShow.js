$(document).ready(function(){

	var tableDiv = $('#tableDiv');

	tableDiv.on('click', '#checkAll', function(){

		var cbToggle = this.checked;

		$('.dirCheck').each(function(){
			this.checked = cbToggle;
		});
	});

	$('#submitShowDirs').click(function(){

		var dirArr = [];

		$('.dirCheck').each(function(){
			if (true == this.checked){
				var show = $(this).attr('id'),
					indexer = $(this).closest('tr').find('select').val(),
					folderEl$ = $(this).closest('tr').find('input.new-folder'),
					newName = !folderEl$.length || folderEl$.attr('data-name') === folderEl$.val().trim() ? '' : '|folder=' + folderEl$.val().trim();
				dirArr.push(encodeURIComponent(indexer + '|' + show + newName));
			}
		});

		if (0 == dirArr.length)
			return false;

		window.location.href = sbRoot + '/add-shows/add-existing-shows'
			+ '?prompt_for_settings=' + ($('#prompt-for-settings').prop('checked') ? 'on' : 'off')
			+ (undefined !== $.sgSid && 0 < $.sgSid.length ? '&tvid_prodid=' + $.sgSid : '')
			+ '&shows_to_add=' + dirArr.join('&shows_to_add=');
	});


	function loadContent(){
		var params = {}, dirs = [];

		if (undefined !== $.sgHashDir && !!$.sgHashDir.length){params['hash_dir'] = $.sgHashDir}
		if (undefined !== $.sgRenameSuggest && !!$.sgRenameSuggest.length){params['rename_suggest'] = $.sgRenameSuggest}

		$('.dir_check:checked').each(function(i, dirSelected){
			dirs.push($(dirSelected).attr('id'));
		});
		if (dirs.length){
			params['root_dir'] = dirs;
		}

		$('#tableDiv').html('<img id="searchingAnim"'
			+ ' style="margin-right:10px"'
			+ ' src="' + sbRoot + '/images/loading32' + themeSpinner + '.gif"'
			+ ' height="32" width="32" />'
			+ ' scanning parent folders...');

		$.get(sbRoot + '/add-shows/mass-add-table', params,
			function(data){
				$('#tableDiv').html(data);
				$.tablesorter.addParser({
					id: 'showNames',
					is: function(s) { return !1; },
					format: function(s) {
						var name = (s || '');
						return config.sortArticle ? name : name.replace(/(?:(?:A(?!\s+to)n?)|The)\s(\w)/i, '$1');
					},
					type: 'text'
				});
				$('#addRootDirTable').tablesorter({
					sortList: [[1,0]],
					widgets: ['zebra'],
					headers: {
						0: { sorter: false },
						1: { sorter: 'showNames' }
					}
				});
			});
	}

	var last_txt = '', new_text = '', id;
	$('#rootDirText').change(function(){
		if (last_txt == (new_text = $('#rootDirText').val()))
			return false;

		last_txt = new_text;
		$('#rootDirStaticList').html('');
		$('#rootDirs').find('option').each(function(i, w){
			id = $(w).val();
			$('#rootDirStaticList').append('<li class="ui-state-default ui-corner-all">'
				+ '<input id="' + id + '" type="checkbox"' + ' checked=checked'
				+ ' class="dir_check"'
				+ ' />'
				+ ' <label for="' + id + '"'
				+ ' style="color:#09A2FF">'
				+ '<b>' + id + '</b></label>'
				+ '</li>')
		});
		loadContent();
	});

	$('#rootDirStaticList').on('click', '.dir_check', loadContent);

	tableDiv.on('click', '.showManage', function(event) {
		event.preventDefault();
		$('#tabs').tabs('option', 'active', 0);
		$('html,body').animate({scrollTop: 0}, 1000);
	});

});
