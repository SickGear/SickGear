$(function () {
    $('.title span').each(function () {
        var match = $(this).parent().attr('id').match(/^scene_exception_(\d+)$/);
        $(this).qtip({
            content: {
                text: function(event, api) {
                    // deferred object ensuring the request is only made once
                    $.ajax({
                        url: $.SickGear.Root + '/home/sceneExceptions',
                        type: 'GET',
                        data: {
                            show: match[1]
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
