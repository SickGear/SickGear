/** @namespace $.SickGear.Root */
/** @namespace $.SickGear.anonURL */
$(document).ready(function(){

	$.sgd = !1;

	$.fn.showHideProviders = function(){
		$('.providerDiv').each(function(){
			var providerName = $(this).attr('id');
			var selectedProvider = $('#editAProvider').find(':selected').val();

			if (selectedProvider + 'Div' == providerName){
				$(this).show();
			} else {
				$(this).hide();
			}
		});
	};

	/**
	 * Gets categories for the provided newznab provider.
     * no return data. Function updateNewznabCaps() is run at callback
	 * @param {String} isNative
	 * @param {Array} selectedProvider
	 * @return
	 */
	$.fn.getCategories = function(isNative, selectedProvider){

		var name = selectedProvider[0];
		var url = selectedProvider[1];
		var key = selectedProvider[2];

		if (!name || !url || !key)
			return;

		var params = {url: url, name: name, key: key};

		$.getJSON($.SickGear.Root + '/config/providers/getNewznabCategories', params,
			function(data){
				updateNewznabCaps(data, selectedProvider);
			});
	};

	$.fn.addProvider = function(id, name, url, key, cat, isNative, showProvider){

		url = $.trim(url);
		if (!url)
			return;

		if (!/^https?:\/\//i.test(url))
			url = 'http://' + url;

		url += /[^/]$/.test(url) && '/' || '';

		newznabProviders[id] = [isNative, [name, url, key, cat]];

		if (!isNative){
			$('#editANewznabProvider').addOption(id, name);
			$(this).populateNewznabSection();
		}

		if (0 == $('#provider_order_list > #' + id).length && !1 != showProvider){
			var toAdd = '<li class="ui-state-default" id="' + id + '"> '
				+ '<input type="checkbox" id="enable_' + id + '" class="provider_enabler" CHECKED> '
				+ '<a href="' + $.SickGear.anonURL + url + '" class="imgLink" target="_new">'
				+ '<img src="' + $.SickGear.Root + '/images/providers/newznab.png" alt="' + name + '" width="16" height="16"></a> '
				+ name + '</li>', prov$ = $('#provider_order_list');

			prov$.append(toAdd);
			prov$.sortable('refresh');
		}

		$(this).makeNewznabProviderString();
	};

	$.fn.addTorrentRssProvider = function(id, name, url, cookies){

		torrentRssProviders[id] = [name, url, cookies];

		$('#editATorrentRssProvider').addOption(id, name);
		$(this).populateTorrentRssSection();

		if (0 == $('#provider_order_list > #' + id).length){
			var toAdd = '<li class="ui-state-default" id="' + id + '"> '
				+ '<input type="checkbox" id="enable_' + id + '" class="provider_enabler" CHECKED> '
				+ '<a href="' + $.SickGear.anonURL + url + '" class="imgLink" target="_new">'
				+ '<img src="' + $.SickGear.Root + '/images/providers/torrentrss.png" alt="' + name + '" width="16" height="16"></a> '
				+ name + '</li>', prov$ = $('#provider_order_list');

			prov$.append(toAdd);
			prov$.sortable('refresh');
		}

		$(this).makeTorrentRssProviderString();
	};

	$.fn.updateProvider = function(id, url, key, cat){

		newznabProviders[id][1][1] = url;
		newznabProviders[id][1][2] = key;
		newznabProviders[id][1][3] = cat;

		$(this).populateNewznabSection();

		$(this).makeNewznabProviderString();
	};

	$.fn.deleteProvider = function(id){

		$('#editANewznabProvider').removeOption(id);
		delete newznabProviders[id];
		$(this).populateNewznabSection();
		$('li').remove('#' + id);
		$(this).makeNewznabProviderString();
	};

	$.fn.updateTorrentRssProvider = function(id, url, cookies){
		torrentRssProviders[id][1] = url;
		torrentRssProviders[id][2] = cookies;
		$(this).populateTorrentRssSection();
		$(this).makeTorrentRssProviderString();
	};

	$.fn.deleteTorrentRssProvider = function(id){
		$('#editATorrentRssProvider').removeOption(id);
		delete torrentRssProviders[id];
		$(this).populateTorrentRssSection();
		$('li').remove('#' + id);
		$(this).makeTorrentRssProviderString();
	};

	$.fn.populateNewznabSection = function(){

		var data, isNative, rrcat, selectedProvider = $('#editANewznabProvider').find(':selected').val(),
			nnName$ = $('#newznab_name'), nnCat$ = $('#newznab_cat'), nn$ = $('#newznab_cat, #newznab_cap');

		if ('addNewznab' == selectedProvider){
			data = ['','',''];
			isNative = 0;
			$('#newznab_add_div').show();
			$('#newznab_update_div').hide();
			nn$.find('option').each(function(){
				$(this).remove();
			});
			nn$.attr('disabled', 'disabled');
		} else {
			data = newznabProviders[selectedProvider][1];
			isNative = newznabProviders[selectedProvider][0];
			$('#newznab_add_div').hide();
			$('#newznab_update_div').show();
			nn$.removeAttr('disabled');
		}

		nnName$.val(data[0]);
		$('#newznab_url').val(data[1]);
		$('#newznab_key').val(data[2]);

		//Check if not already array
		rrcat = ('string' === typeof data[3]) ? data[3].split(',') : data[3];

		// Update the category select box (on the right)
		var newCatOptions = [];
		if (rrcat){
			rrcat.forEach(function(cat){
				newCatOptions.push({text : cat, value : cat});
			});
			nnCat$.replaceOptions(newCatOptions);
		}

		if ('addNewznab' == selectedProvider) {

			$('#newznab_url, #newznab_name').removeAttr('disabled');

		} else {

			nnName$.attr('disabled', 'disabled');

			if (isNative){
				$('#newznab_url, #newznab_delete').attr('disabled', 'disabled');
			} else {
				$('#newznab_url, #newznab_delete').removeAttr('disabled');

				//Get Categories Capabilities
				if (data[0] && data[1] && data[2] && !ifExists($.fn.newznabProvidersCapabilities, data[0])){
					$(this).getCategories(isNative, data);
				} else {
					updateNewznabCaps(null, data);
				}
			}
		}
	};

	var ifExists = function(loopThroughArray, searchFor){
		var found = !1;

		loopThroughArray.forEach(function(rootObject){
			if (rootObject.name == searchFor){
				found = !0;
			}
		});
		return found;
	};

	/**
	 * Updates the Global array $.fn.newznabProvidersCapabilities with a combination of newznab prov name
	 * and category capabilities. Return
	 * @param {Array} newzNabCaps, is the returned object with newzNabprod Name and Capabilities.
	 * @param {Array} selectedProvider
	 * @return no return data. The multiselect input $("#newznab_cap") is updated, as a result.
	 */
	/** @namespace newzNabCaps.tv_categories */
	var updateNewznabCaps = function(newzNabCaps, selectedProvider){

		if (newzNabCaps && !ifExists($.fn.newznabProvidersCapabilities, selectedProvider[0])){

			$.fn.newznabProvidersCapabilities.push({
				'name' : selectedProvider[0],
				'enabled' : newzNabCaps.state,
				'categories' : newzNabCaps.tv_categories
					.sort(function(a, b){return a.name > b.name})})
		}

		$.sgd && console.log(selectedProvider);
		//Loop through the array and if currently selected newznab provider name matches one in the array, use it to
		//update the capabilities select box (on the left).
		if (selectedProvider[0]){
			var elShow, newCapOptions = [], catName = '', hasCats = !1, enabled = !1;
			if ($.fn.newznabProvidersCapabilities.length){
				$.fn.newznabProvidersCapabilities.forEach(function(newzNabCap){
					if (newzNabCap.name && newzNabCap.name == selectedProvider[0]) {
						$.sgd && console.log('newzNabCap...');
						$.sgd && console.log(newzNabCap);
						enabled = newzNabCap.enabled;

						if (newzNabCap.categories instanceof Array) {
							newzNabCap.categories.forEach(function(category_set){
								if (category_set.id && category_set.name){
									catName = category_set.name.replace(/Docu([^\w]|$)(.*?)/i, 'Documentary$1');
									newCapOptions.push({
										value: category_set.id,
										text: catName + ' (' + category_set.id + ')'
									});
								}
							});
							$('#newznab_cap').replaceOptions(newCapOptions);
							hasCats = !!newCapOptions.length
						}
						return !1;
					}
				});

				$('#nn-cats, #nn-nocats, #nn-enable-for-cats, #nn-loadcats').removeClass('show').addClass('hide');
				if (!enabled) {
					elShow =  '#nn-enable-for-cats'
				} else if (hasCats){
					elShow = '#nn-cats';
				 } else {
					elShow = '#nn-nocats';
				}
				$.sgd && console.log('for ' + selectedProvider[0] + ' unhide("' + elShow + '")');
				$(elShow).removeClass('hide').addClass('show');

			} else {

				$.sgd && console.log('no caps - yet');
				$('#nn-cats, #nn-nocats').removeClass('show').addClass('hide');
				$('#nn-loadcats').removeClass('hide').addClass('show');
			}
		}
	};

	$.fn.makeNewznabProviderString = function(){

		var provStrings = [];

		for (var id in newznabProviders){
			provStrings.push(newznabProviders[id][1].join('|'));
		}

		$('#newznab_string').val(provStrings.join('!!!'))
	};

	$.fn.populateTorrentRssSection = function(){

		var data, selectedProvider = $('#editATorrentRssProvider').find(':selected').val(),
			torRSSadd$ = $('#torrentrss_add_div'), torRSSupd$ = $('#torrentrss_update_div'),
			torRSSname$ = $('#torrentrss_name');

		if ('addTorrentRss' == selectedProvider) {
			data = ['', '', ''];
			torRSSadd$.show();
			torRSSupd$.hide();
		} else {
			data = torrentRssProviders[selectedProvider];
			torRSSadd$.hide();
			torRSSupd$.show();
		}

		torRSSname$.val(data[0]);
		$('#torrentrss_url').val(data[1]);
		$('#torrentrss_cookies').val(data[2]);

		if ('addTorrentRss' == selectedProvider) {
			$('#torrentrss_name, #torrentrss_url, #torrentrss_cookies').removeAttr('disabled');
		} else {
			torRSSname$.attr('disabled', 'disabled');
			$('#torrentrss_url, #torrentrss_cookies, #torrentrss_delete').removeAttr('disabled');
		}
	};

	$.fn.makeTorrentRssProviderString = function(){

		var provStrings = [];
		for (var id in torrentRssProviders){
			provStrings.push(torrentRssProviders[id].join('|'));
		}
		$('#torrentrss_string').val(provStrings.join('!!!'))
	};


	$.fn.refreshProviderList = function(){
		var idArr = $('#provider_order_list').sortable('toArray');
		var finalArr = [];
		$.each(idArr, function(key, val){
			var checked = + $('#enable_' + val).prop('checked') ? '1' : '0';
			finalArr.push(val + ':' + checked);
		});

		$('#provider_order').val(finalArr.join(' '));
	};

	var newznabProviders = [];
	var torrentRssProviders = [];

	$(this).on('change', '.newznab_key', function(){

		var provider_id = $(this).attr('id');
		provider_id = provider_id.substring(0, provider_id.length-'_hash'.length);

		var url = $('#' + provider_id + '_url').val();
		var cat = $('#' + provider_id + '_cat').val();
		var key = $(this).val();

		$(this).updateProvider(provider_id, url, key, cat);

	});

	$('#newznab_key, #newznab_url').change(function(){

		var selectedProvider = $('#editANewznabProvider').find(':selected').val();

		if ('addNewznab' == selectedProvider)
			return;

		var url = $('#newznab_url').val(),
			key = $('#newznab_key').val(),
			cat = $('#newznab_cat').find('option').map(function(i, opt){
				return $(opt).text();
			}).toArray().join(',');

		$(this).updateProvider(selectedProvider, url, key, cat);

	});

	$('#torrentrss_url, #torrentrss_cookies').change(function(){

		var selectedProvider = $('#editATorrentRssProvider').find(':selected').val();

		if ('addTorrentRss' == selectedProvider)
		  return;

		var url = $('#torrentrss_url').val(),
			cookies = $('#torrentrss_cookies').val();

		$(this).updateTorrentRssProvider(selectedProvider, url, cookies);
	});


	$('#editAProvider').change(function(){
		$(this).showHideProviders();
	});

	$('#editANewznabProvider').change(function(){
		$(this).populateNewznabSection();
	});

	$('#editATorrentRssProvider').change(function(){
		$(this).populateTorrentRssSection();
	});

	$(this).on('click', '.provider_enabler', function(){
		$(this).refreshProviderList();
	});

	$(this).on('click', '#newznab_cat_update', function(){

		var nnCat$ = $('#newznab_cat');
		//Maybe check if there is anything selected?
		nnCat$.find('option').each(function(){
			$(this).remove();
		});

		var newOptions = [];

		// When the update botton is clicked, loop through the capabilities list
		// and copy the selected category id's to the category list on the right.
		$('#newznab_cap').find(':selected').each(function(){
			var selected_cat = $(this).val();
			newOptions.push({text: selected_cat, value: selected_cat})
		});

		nnCat$.replaceOptions(newOptions);

		var selectedProvider = $('#editANewznabProvider').find(':selected').val();
		if ('addNewznab' == selectedProvider)
			return;

		var url = $('#newznab_url').val();
		var key = $('#newznab_key').val();

		var cat = nnCat$.find('option').map(function(i, opt){
		  return $(opt).text();
		}).toArray().join(',');

		nnCat$.find('option:not([value])').remove();

		$(this).updateProvider(selectedProvider, url, key, cat);
	});


	$('#newznab_add').click(function(){

		var name = $.trim($('#newznab_name').val());
		var url = $.trim($('#newznab_url').val());
		var key = $.trim($('#newznab_key').val());

		var cat = $.trim($('#newznab_cat').find('option').map(function(i, opt){
			  return $(opt).text();}).toArray().join(','));

		if (!name || !url || !key)
			return;

		// send to the form with ajax, get a return value
		$.getJSON($.SickGear.Root + '/config/providers/canAddNewznabProvider', {name: name},
			function(data){
				if (data.error != undefined){
					alert(data.error);
					return;
				}
				$(this).addProvider(data.success, name, url, key, cat, 0);
			});
	});

	$('.newznab_delete').click(function(){

		var selectedProvider = $('#editANewznabProvider').find(':selected').val();
		$(this).deleteProvider(selectedProvider);
	});

	$('#torrentrss_add').click(function(){

		var name = $('#torrentrss_name').val();
		var url = $('#torrentrss_url').val();
		var cookies = $('#torrentrss_cookies').val();
		var params = { name: name, url: url, cookies: cookies};

		// send to the form with ajax, get a return value
		$.getJSON($.SickGear.Root + '/config/providers/canAddTorrentRssProvider', params,
			function(data){
				if (data.error != undefined){
					alert(data.error);
					return;
				}
				$(this).addTorrentRssProvider(data.success, name, url, cookies);
			});
	});

	$('.torrentrss_delete').on('click', function(){
		var selectedProvider = $('#editATorrentRssProvider').find(':selected').val();
		$(this).deleteTorrentRssProvider(selectedProvider);
	});


	$(this).on('change', '[class="providerDiv_tip"] input', function(){
		$('div .providerDiv ' + '[name=' + $(this).attr('name') + ']').replaceWith($(this).clone());
		$('div .providerDiv ' + '[newznab_name=' + $(this).attr('id') + ']').replaceWith($(this).clone());
	});

	$(this).on('change', '[class="providerDiv_tip"] select', function(){

	$(this).find('option').each(function(){
		if ($(this).is(':selected')){
			$(this).prop('defaultSelected', !0)
		} else {
			$(this).prop('defaultSelected', !1);
		}
	});

	$('div .providerDiv ' + '[name=' + $(this).attr('name') + ']').empty().replaceWith($(this).clone())});

	$(this).on('change', '.enabler', function(){
		if ($(this).is(':checked')){
			$('.content_' + $(this).attr('id')).each(function(){
				$(this).show()
			})
		} else {
			$('.content_' + $(this).attr('id')).each(function(){
				$(this).hide()
			})
		}
	});

	$('.enabler').each(function(){
		if (!$(this).is(':checked')){
			$('.content_' + $(this).attr('id')).hide();
		} else {
			$('.content_' + $(this).attr('id')).show();
		}
	});

	$.fn.makeTorrentOptionString = function(provider_id){

		var seed_ratio = $('.providerDiv_tip #' + provider_id + '_seed_ratio').prop('value');
		var seed_time = $('.providerDiv_tip #' + provider_id + '_seed_time').prop('value');
		var process_met = $('.providerDiv_tip #' + provider_id + '_process_method').prop('value');
		var option_string = $('.providerDiv_tip #' + provider_id + '_option_string');

		option_string.val([seed_ratio, seed_time, process_met].join('|'))
	};

	$(this).on('change', '.seed_option', function(){

		var provider_id = $(this).attr('id').split('_')[0];

		$(this).makeTorrentOptionString(provider_id);
	});


	$.fn.replaceOptions = function(options){

		var self, $option;

		this.empty();
		self = this;

		$.each(options, function(index, option){
			$option = $('<option></option>')
			.attr('value', option.value)
			.text(option.text);
			self.append($option);
		});
	};

	//
	// initialization stuff
	//
	$.fn.newznabProvidersCapabilities = [];

	$(this).showHideProviders();

	var providers$ = $('#provider_order_list');

	providers$.sortable({
		placeholder: 'ui-state-highlight',
		update: function(event, ui){
			$(this).refreshProviderList();
		}
	});

	providers$.disableSelection();

});
