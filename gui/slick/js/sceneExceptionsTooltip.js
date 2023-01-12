$(function () {
    $('.title span, [id^="season"] .title').each(function () {
        var match = $(this).parent().attr('id').match(/^scene_exception_(.*)$/)
        if (undefined == typeof (match) || !match) {
            match = $(this).parent().attr('id').match(/^season-([^-]+)-(\d+)$/);
        }
        $(this).qtip({
            content: {
                text: function(event, api) {
                    // deferred object ensuring the request is only made once
                    $.ajax({
                        url: $.SickGear.Root + '/home/scene-exceptions',
                        type: 'GET',
                        data: {
                            tvid_prodid: match[1],
                            wanted_season: 3 === match.length ? match[2] : ''
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
                at: 'right center',
                adjust: {
                    y: 0,
                    x: 2
                }
            },
            style: {
                classes: 'qtip-dark qtip-rounded qtip-shadow'
            }
        });
    });
});
