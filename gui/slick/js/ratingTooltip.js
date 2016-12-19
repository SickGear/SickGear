$(function () {
	$('.imdbstars').qtip({
		content: {
			text: function(event, api) {
				// Retrieve content from custom attribute of the $('.selector') elements.
				return $(this).attr('qtip-content');
			}
		},
        show: {
            solo: true
        },
        position: {
            viewport: $(window),
            my: 'right center',
			at: 'center left',
            adjust: {
                y: 0,
                x: -2
            }
        },
        style: {
            classes: 'qtip-dark qtip-rounded qtip-shadow'
        }
    });
});

