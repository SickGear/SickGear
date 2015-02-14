var message_url = sbRoot + '/ui/get_messages';

PNotify.prototype.options.styling = 'jqueryui';
PNotify.prototype.options.buttons.closer_hover = false;
PNotify.prototype.options.delay = 4000;
PNotify.prototype.options.width = '340px';
PNotify.prototype.options.shadow = false;
PNotify.prototype.options.addclass = 'stack-bottomright';
PNotify.prototype.options.stack = {'dir1': 'up', 'dir2': 'left', 'firstpos1': 25, 'firstpos2': 25};

function check_notifications() {
	if(document.visibilityState == 'visible') {
		$.getJSON(message_url, function(data){
			$.each(data, function(name,data){
				var text = data.message.replace(/<\/?i>/ig, '*');
				new PNotify({
					type: data.type,
					hide: data.type == 'notice',
					title: data.title,
					text: text,
					history: false,
					desktop: {
						desktop: true,
						icon: "../images/ico/apple-touch-icon-180x180.png"
					}
				});
			});
		});
	}

	setTimeout(check_notifications, 3000)
}

$(document).ready(function(){
	check_notifications();
});