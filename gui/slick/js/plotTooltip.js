$(function () {
    $('.plotInfo, .plot-daybyday').each(function () {
        var match = $(this).attr('id').match(/^plot_info_(\d+)_(\d+)_(\d+)$/);
        $(this).qtip({
            content: {
                text: function(event, api) {
                    // deferred object ensuring the request is only made once
                    $.ajax({
                        url: $('#sbRoot').val() + '/home/plotDetails',
                        type: 'GET',
                        data: {
                            show: match[1],
                            episode: match[3],
                            season: match[2]
                        }
                    })
                    .then(function(content) {
                        // Set the tooltip content upon successful retrieval
                        api.set('content.text', content);
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
                    x: 2
                }
            },
            style: {
                classes: 'qtip-rounded qtip-shadow'
            }
        });
    });
});
