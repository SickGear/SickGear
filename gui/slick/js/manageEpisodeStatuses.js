$(document).ready(function() {

	function make_row(indexer_id, season, episode, name, checked, airdate_never, qualityCss, qualityStr, sxe) {
		var checkedbox = (checked ? ' checked' : ''),
			row_class = $('#row_class').val(),
			ep_id = season + 'x' + episode;

		return ' <tr id="ep-' + indexer_id + '-' + ep_id + '" class="' + (airdate_never ? 'airdate-never' : row_class) + '">'
			+ '  <td class="tableleft" align="center">'
				+ '<input type="checkbox"'
					+ ' class="' + indexer_id + '-epcheck"'
					+ ' name="' + indexer_id + '-' + ep_id + '"'
					+ checkedbox+'></td>'
			+ '  <td class="text-nowrap">' + sxe + '</td>'
			+ '  <td class="tableright" style="width: 100%">'
			+ ' <span class="quality show-quality ' + qualityCss + ' text-nowrap">' +  qualityStr + '</span>'
			+ name + (airdate_never ? ' (<strong><em>airdate is never, this should change in time</em></strong>)' : '') + '</td>'
			+ ' </tr>';
	}

	$('.go').click(function() {
		if ($('input[class*="-epcheck"]:checked').length === 0 && $('input[id*="allCheck-"]:checked').length === 0) {
			alert('Please select at least one Show or Episode');
			return false
		}
	});

	$('.allCheck').click(function(){
		var indexer_id = $(this).attr('id').split('-')[1];
		$('.' + indexer_id + '-epcheck').prop('checked', $(this).prop('checked'));
	});

	$('.get_more_eps').show();
	function show_episodes(btn_element) {
		var match = btn_element.attr('id').match(/(.*)[-](.*)/);
		if (null == match)
			return false;

		var cur_indexer_id = match[1], action = match[2], checked = $('#allCheck-' + cur_indexer_id).prop('checked'),
			show_header = $('tr#' + cur_indexer_id), episode_rows = $('tr[id*="ep-' + cur_indexer_id + '"]'),
			void_var = 'more' == action && episode_rows.show() ||  episode_rows.hide();

		$('input#' + match[0]).val('more' == action ? 'Expanding...' : 'Collapsing...');

		if (0 == episode_rows.length) {
			$.getJSON(sbRoot + '/manage/showEpisodeStatuses',
				{
					indexer_id: cur_indexer_id,
					whichStatus: $('#oldStatus').val()
				},
				function (data) {
					$.each(data, function(season, eps){
						$.each(eps, function(episode, meta) {
							show_header.after(make_row(cur_indexer_id, season, episode, meta.name, checked, meta.airdate_never, meta.qualityCss, meta.qualityStr, meta.sxe));
						});
					});
					$('input#' + match[0]).val('more' == action ? 'Expand' : 'Collapse');
					btn_element.hide();
					$('input[id="' + cur_indexer_id + '-' + ('more' == action ? 'less' : 'more') + '"]').show();
				});
		} else {
			$('input#' + match[0]).val('more' == action ? 'Expand' : 'Collapse');
			btn_element.hide();
			$('input[id="' + cur_indexer_id + '-' + ('more' == action ? 'less' : 'more') + '"]').show();
		}

	}

	$('.get_more_eps,.get_less_eps').click(function(){
		show_episodes($(this));
		($('.get_more_eps:visible').length == 0 ? $('.expandAll').hide() : '');
	});

	$('.expandAll').click(function() {
		$(this).hide();
		$('.get_more_eps').each(function() {
			show_episodes($(this));
		});
	});

	// selects all visible episode checkboxes.
	$('.selectAllShows').click(function(){
		$('.sickbeardTable input').each(function() {
			this.checked = true;
		});
	});

	// clears all visible episode checkboxes and the season selectors
	$('.unselectAllShows').click(function(){
		$('.sickbeardTable input').each(function() {
			this.checked = false;
		});
	});

});
