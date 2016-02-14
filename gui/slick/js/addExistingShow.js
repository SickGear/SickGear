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
				var show = $(this).attr('id');
				var indexer = $(this).closest('tr').find('select').val();
				dirArr.push(encodeURIComponent(indexer + '|' + show));
			}
		});

		if (0 == dirArr.length)
			return false;

		window.location.href = sbRoot + '/home/addShows/addExistingShows'
			+ '?promptForSettings=' + ($('#promptForSettings').prop('checked') ? 'on' : 'off')
			+ (undefined !== $.sgSid && 0 < $.sgSid.length ? '&sid=' + $.sgSid : '')
			+ '&shows_to_add=' + dirArr.join('&shows_to_add=');
	});


	function loadContent(){
		var url = '';
		$('.dir_check').each(function(i, w){
			if ($(w).is(':checked')){
				url += (url.length ? '&' : '')
					+ 'rootDir=' + encodeURIComponent($(w).attr('id'));
			}
		});

		$('#tableDiv').html('<img id="searchingAnim"'
			+ ' style="margin-right:10px"'
			+ ' src="' + sbRoot + '/images/loading32' + themeSpinner + '.gif"'
			+ ' height="32" width="32" />'
			+ ' scanning parent folders...');

		$.get(sbRoot + '/home/addShows/massAddTable' + (undefined !== $.sgHashDir && 0 < $.sgHashDir.length ? '?hash_dir=' + $.sgHashDir : ''),
			url,
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
