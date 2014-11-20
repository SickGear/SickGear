$(document).ready(function (){

	function getRecommendedShows(){

		$('#searchResults').empty().html('<img id="searchingAnim"'
			+ ' src="' + sbRoot + '/images/loading32' + themeSpinner + '.gif"'
			+ ' height="32" width="32" />'
			+ ' fetching recommendations...');

		$.getJSON(sbRoot + '/home/addShows/getRecommendedShows',
			{},
			function (data){
				var resultStr = '', checked = '', rowType, row = 0;

				if (null === data || 0 === data.results.length){
					resultStr += '<p>Sorry, no recommended shows found, this can happen from time to time.</p>'
						+ '<p>However, if the issue persists, then try updating your watched shows list on trakt.tv</p>';
				} else {

					$.each(data.results, function (index, obj){
						checked = (0 == row ? ' checked' : '');
						rowType = (0 == row % 2 ? '' : ' class="alt"');
						row++;

						var whichSeries = obj[6] + '|' + obj[0] + '|' + obj[1] + '|' + obj[2] + '|' + obj[3],
							showstartdate = '';

						if (null !== obj[3]){
							var startDate = new Date(obj[3]);
							var today = new Date();
							showstartdate = '&nbsp;<span class="stepone-result-date">('
								+ (startDate > today ? 'will debut' : 'started')
								+ ' on ' + obj[3] + ')</span>';
						}

						resultStr += '<div' + rowType + '>'
							+ '<input id="whichSeries" type="radio"'
							+ ' class="stepone-result-radio"'
							+ ' style="float:left;margin-top:4px"'
                            + ' title="Add show <span style=\'color: rgb(66, 139, 202)\'>' + obj[1] + '</span>"'
							+ ' name="whichSeries"'
							+ ' value="' + whichSeries + '"'
							+ checked
							+ ' />'
							+ '<div style="margin-left:20px">'
							+ '<a'
							+ ' class="stepone-result-title"'
							+ ' style="margin-left:5px"'
							+ ' title="View <span class=\'boldest\'>Trakt</span> detail for <span style=\'color: rgb(66, 139, 202)\'>' + obj[1] + '</span>"'
							+ ' href="' + anonURL + obj[0] + '"'
							+ ' onclick="window.open(this.href, \'_blank\'); return false;"'
							+ '>' + obj[1] + '</a>'
							+ showstartdate
							+ (null == obj[6] ? ''
								: '&nbsp;'
									+ '<span class="stepone-result-db grey-text">'
									+ '<a class="service" href="' + anonURL + obj[7] + '"'
									+ ' onclick="window.open(this.href, \'_blank\'); return false;"'
									+ ' title="View <span class=\'boldest\'>' + obj[4] + '</span> detail for <span style=\'color: rgb(66, 139, 202)\'>' + obj[1] + '</span>"'
									+ '>'
									+ '<img alt="' + obj[4] + '" height="16" width="16" src="' + sbRoot + '/images/' + obj[5] + '" />'
									+ ''
									+ '</a>'
									+ '</span>'
								)
							+ (null == obj[10] ? ''
								: '&nbsp;'
									+ '<span class="stepone-result-db grey-text">'
									+ '<a class="service" href="' + anonURL + obj[11] + '"'
									+ ' onclick="window.open(this.href, \'_blank\'); return false;"'
									+ ' title="View <span class=\'boldest\'>' + obj[8] + '</span> detail for <span style=\'color: rgb(66, 139, 202)\'>' + obj[1] + '</span>"'
									+ '>'
									+ '<img alt="' + obj[8] + '" height="16" width="16" src="' + sbRoot + '/images/' + obj[9] + '" />'
									+ ''
									+ '</a>'
									+ '</span>'
								)
							+ (null == obj[2] ? ''
									: '&nbsp;<div class="stepone-result-overview grey-text">' + obj[2] + '</div>')
							+ '</div></div>';
					});
				}

				$('#searchResults').html(
					'<fieldset>' + "\n" + '<legend class="legendStep" style="margin-bottom: 15px">'
						+ (0 < row ? row : 'No')
						+ ' recommended result' + (1 == row ? '' : 's') + '...</legend>' + "\n"
						+ resultStr
						+ '</fieldset>'
					);
				updateSampleText();
				myform.loadsection(0);
				$('.stepone-result-radio, .stepone-result-title, .service').each(addQTip);
			}
		);
	}

	$('#addShowButton').click(function () {
		// if they haven't picked a show don't let them submit
		if (!$('input:radio[name="whichSeries"]:checked').val()
			&& !$('input:hidden[name="whichSeries"]').val().length) {
				alert('You must choose a show to continue');
				return false;
		}
		$('#addShowForm').submit();
	});

	$('#qualityPreset').change(function (){
		myform.loadsection(2);
	});

	var myform = new FormToWizard({
		fieldsetborderwidth: 0,
		formid: 'addShowForm',
		revealfx: ['slide', 500],
		oninit: function (){
			getRecommendedShows();
			updateSampleText();
		}
	});

	function goToStep(num){
		$('.step').each(function (){
			if ($.data(this, 'section') + 1 == num){
				$(this).click();
			}
		});
	}

	function updateSampleText(){
		// if something's selected then we have some behavior to figure out

		var elRadio = $('input:radio[name="whichSeries"]:checked'),
			elFullShowPath = $('#fullShowPath'),
			sep_char = '',
			root_dirs = $('#rootDirs'),
			// if they've picked a radio button then use that
			show_name = (elRadio.length ? elRadio.val().split('|')[2] : ''),
			sample_text = '<p>Adding show <span class="show-name">' + show_name + '</span>'
				+ ('' == show_name ? 'into<br />' : '<br />into')
				+ ' <span class="show-dest">';

		// if we have a root dir selected, figure out the path
		if (root_dirs.find('option:selected').length){
			var root_dir_text = root_dirs.find('option:selected').val();
			if (0 <= root_dir_text.indexOf('/')){
				sep_char = '/';
			} else if (0 <= root_dir_text.indexOf('\\')){
				sep_char = '\\';
			}

			root_dir_text += (sep_char != root_dir_text.substr(sample_text.length - 1)
				? sep_char : '')
				+ '<i>||</i>' + sep_char;

			sample_text += root_dir_text;
		} else if (elFullShowPath.length && elFullShowPath.val().length){
			sample_text += elFullShowPath.val();
		} else {
			sample_text += 'unknown dir.';
		}

		sample_text += '</span></p>';

		// if we have a show name then sanitize and use it for the dir name
		if (show_name.length){
			$.get(sbRoot + '/home/addShows/sanitizeFileName', {name: show_name}, function (data){
				$('#displayText').html(sample_text.replace('||', data));
			});
		// if not then it's unknown
		} else {
			$('#displayText').html(sample_text.replace('||', '??'));
		}

		// also toggle the add show button
		$('#addShowButton').attr('disabled',
			((root_dirs.find('option:selected').length
				|| (elFullShowPath.length && elFullShowPath.val().length))
				&& elRadio.length
				? false : true));
	}

	var addQTip = (function(){
		$(this).css('cursor', 'help');
		$(this).qtip({
			show: {
				solo: true
			},
			position: {
				viewport: $(window),
				my: 'left center',
				adjust: {
					y: -10,
					x: 2
				}
			},
			style: {
				tip: {
					corner: true,
					method: 'polygon'
				},
				classes: 'qtip-rounded qtip-bootstrap qtip-shadow ui-tooltip-sb'
			}
		});
	});

	$('#rootDirText').change(updateSampleText);

	$('#searchResults').on('click', '.stepone-result-radio', updateSampleText);

});
