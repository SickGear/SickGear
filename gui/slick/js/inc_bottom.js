function hide_lazy_ani (element){
	if (element.id) {
		var el = document.getElementById('loading-' + element.id), className = 'hide';
		if (!!document.body.classList) {
			el.classList.add(className);
		} else {
			el.className += (el.className ? ' ' : '') + className;
		}
	}
}

function initLazyload(){
	$.ll = new LazyLoad({elements_selector:'img[data-original]', callback_load: hide_lazy_ani,
		callback_error: hide_lazy_ani});
	$.ll.handleScroll();
	return !0;
}

$(document).ready(function(){
	!/undefined/i.test(typeof(LazyLoad)) && initLazyload();
});
