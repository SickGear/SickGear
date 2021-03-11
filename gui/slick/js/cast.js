function getContainedSize(img){
	var width, height, ratio;
	try {
		ratio = img.naturalWidth / img.naturalHeight;
		width = height = img.height;
		width *= ratio;
		if (width > img.width) {
			height = width = img.width;
			height /= ratio;
		}
	} catch (error) {
		width = height = 0;
	}
	return {w:width, h:height}
}

function removeImageBackground(oImage){
	var image$ = $(oImage).load(function(){
		// swap out placeholder
		if (-1 !== $(this).css('background-image').indexOf('poster-person.jpg')){

			$(this).css('background', 'transparent');
			var sizeImage = getContainedSize(oImage);

			if (0 < sizeImage.w){
				if (sizeImage.w < oImage.width){

					$(this).css('width', 'auto');

				} else if (sizeImage.h < oImage.height){

					var heightDiff = oImage.height - sizeImage.h,
						margin = Math.floor(heightDiff / 2),
						roundError = Math.floor(oImage.height - sizeImage.h - (margin * 2)),
						marginTop = margin + ((0 < roundError) ? roundError : 0);

					$(this).css('height', 'auto')
						.css('marginTop', marginTop)
						.css('marginBottom', margin);
				}
			}
		}
	});

	// trigger the load handler if the image is already loaded
	if (image$[0].complete){
		image$.trigger('load');
	}
}

function scaleImage(oImage) {
	var image$ = $(oImage).load(function() {

		var sizeImage = getContainedSize(oImage),
			containerWidth = $(oImage).parent().width()

		if (sizeImage.w > containerWidth) {
			// image width is wider than its container so reduce image height to down scale
			var ratio = (containerWidth - 4) / sizeImage.w,
				height = Math.floor(oImage.height * ratio);

			$(this).css('height', height);
		}
	});

	// trigger the load handler if the image is already loaded
	if (image$[0].complete){
		image$.trigger('load');
	}
}

var addQTip = (function(){
	$(this).css('cursor', 'help');
	$(this).qtip({
		show: {solo:true},
		position: {viewport:$(window), my:'right center', at: 'left center', adjust:{y: 0, x: 2}},
		style: {tip: {corner:true, method:'polygon'}, classes:'qtip-dark qtip-rounded qtip-shadow'}
	});
});

$(function() {
	objectFitImages();

	$('#person .cast-bg, #character .cast-bg').each(function(i, oImage){
		removeImageBackground(oImage);
	});

	$('#display-show .cast-bg').each(function (i, oImage){
		scaleImage(oImage);
	});

	$('.addQTip').each(addQTip);
});
