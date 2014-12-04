$(function () {
    $('.title span').each(function () {
        $(this).qtip({
            content: {
                text: 'Loading...',
                ajax: {
                    url: $("#sbRoot").val() + '/home/sceneExceptions',
                    type: 'GET',
                    data: {
                        show: match[1]
                    },
                    success: function (data, status) {
                        this.set('content.text', data);
                    }
                }
            },
            show: {
                solo: true
            },
            position: {
                viewport: $(window),
                my: 'left middle',
                at: 'right middle',
                adjust: {
                    y: 0,
                    x: 10
                }
            },
            style: {
                tip: {
                    corner: true,
                    method: 'polygon'
                },
                classes: 'qtip-rounded qtip-shadow ui-tooltip-sb'
            }
        });
    });
});
