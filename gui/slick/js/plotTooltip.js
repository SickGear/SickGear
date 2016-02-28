var plotter = function(select$) {
	select$.each(function() {
		var match = $(this).attr('id').match(/^plot(?:_info_|-)((\d+)_(\d+)[_x](\d+))$/);
		var showName = $('#show-' + match[1]).attr('data-rawname');
		$(this).qtip({
			content: {
				text: function(event, api) {
					// deferred object ensuring the request is only made once
					$.ajax({
						url: $.SickGear.Root + '/home/plotDetails',
						type: 'GET',
						data: {
							show: match[2],
							episode: match[4],
							season: match[3]
						}
					})
					.then(function(content) {
						// Set the tooltip content upon successful retrieval
						api.set('content.text', ('undefined' === typeof(showName) ? ''
							: ('' !== content ? '<b class="boldest">' + showName + '</b>' : showName))
							+ ('' !== content ? ' ' + content : ''));
					}, function(xhr, status, error) {
						// Upon failure... set the tooltip content to the status and error value
						api.set('content.text', status + ': ' + error);
					});
					return 'Loading...'; // Set initial text
				}
			},
			show: {
				solo: true
			},
			position: {
				viewport: $(window),
				my: 'left center',
				adjust: {
					y: -10,
					x: 0
				}
			},
			style: {
				classes: 'qtip-dark qtip-rounded qtip-shadow'
			}
		});
	});
};
$(function () { plotter($('.plotInfo, .plot-daybyday')) });
