/* jQuery Form to Form Wizard (Initial: Oct 1st, 2010)
 * This notice must stay intact for usage
 * Author: Dynamic Drive at http://www.dynamicdrive.com/
 * Visit http://www.dynamicdrive.com/ for full source code
 */

// Oct 21st, 2010: Script updated to v1.1, which adds basic form validation functionality, triggered each time the user goes from one page to the next, or tries to submit the form.
// jQuery.noConflict()


function FormToWizard(options){
	this.setting = jQuery.extend({fieldsetborderwidth:2, persistsection:false, revealfx:['slide', 500],
		oninit:function(){}, onpagechangestart:function(){}}, options);
	this.currentsection = -1;
	this.init(this.setting)
}

FormToWizard.prototype = {

	loadsection:function(rawi, bypasshooks){

		//doload Boolean checks to see whether to load next section (true if bypasshooks param is true or onpagechangestart() event handler doesn't return false)
		var doload = bypasshooks || this.setting.onpagechangestart(jQuery, this.currentsection, this.sections.$sections.eq(this.currentsection)),
			tabIndex,
			thiswizard = this;

		doload = (doload !== false); //unless doload is explicitly false, set to true
		if (!bypasshooks && this.setting.validate && false === this.validate(this.currentsection))
			doload = false;

		//get index of next section to show
		tabIndex = ('prev' == rawi
			? this.currentsection - 1
			: ('next' == rawi
				? this.currentsection + 1
				: parseInt(rawi)));

		//don't exceed min/max limit
		tabIndex = (tabIndex < 0
			? this.sections.count - 1
			: (tabIndex > (this.sections.count - 1)
				? 0
				: tabIndex));

		//if next section to show isn't the same as the current section shown
		if (tabIndex < this.sections.count && doload){
			//dull current 'step' text then highlight next 'step' text
			this.$thesteps.eq(this.currentsection).addClass('disabledstep').end().eq(tabIndex).removeClass('disabledstep');

			if ('slide' == this.setting.revealfx[0]) {
				this.sections.$sections.css('visibility', 'visible');
				//animate fieldset wrapper's height to accommodate next section's height
				this.sections.$outerwrapper.stop().animate({height: this.sections.$sections.eq(tabIndex).outerHeight()}, this.setting.revealfx[1]);
				//slide next section into view
				this.sections.$innerwrapper.stop().animate({left: -tabIndex * this.maxfieldsetwidth}, this.setting.revealfx[1], function () {
					thiswizard.sections.$sections.each(function (thissec) {
						//hide fieldset sections currently not in view, so tabbing doesn't go to elements within them (and mess up layout)
						if (tabIndex != thissec)
							thiswizard.sections.$sections.eq(thissec).css('visibility', 'hidden')
					})
				})
			}
			else if ('fade' == this.setting.revealfx[0]) { //if fx is 'fade'
				this.sections.$sections.eq(this.currentsection).hide().end().eq(tabIndex).fadeIn(this.setting.revealfx[1], function () {
					if (document.all && this.style && this.style.removeAttribute)
					//fix IE clearType problem
						this.style.removeAttribute('filter');
				})
			} else {
				this.sections.$sections.eq(this.currentsection).hide().end().eq(tabIndex).show()
			}
			//update current page status text
			this.paginatediv.$status.text('step ' + (tabIndex + 1) + ' / ' + this.sections.count);
			this.paginatediv.$navlinks.css('visibility', 'visible');

			if (0 == tabIndex) //hide 'prev' link
				this.paginatediv.$navlinks.eq(0).css('visibility', 'hidden');
			else if ((this.sections.count - 1) == tabIndex)
			//hide 'next' link
				this.paginatediv.$navlinks.eq(1).css('visibility', 'hidden');

			if (this.setting.persistsection) //enable persistence?
				FormToWizard.routines.setCookie(this.setting.formid + '_persist', tabIndex);
			this.currentsection = tabIndex;
			if (0 === tabIndex) {
				setTimeout(function () {
					$('#nameToSearch').focus();
				}, 250);
			}
		}
	},

	addvalidatefields:function(){
		var $ = jQuery,
			setting = this.setting,
			theform = this.$theform.get(0),
			validatefields = setting.validate; //array of form element ids to validate

		for (var i = 0; i < validatefields.length; i++){
			var el = theform.elements[validatefields[i]]; //reference form element
			if (el){
				//find fieldset.sectionwrap this form element belongs to
				var $section = $(el).parents('fieldset.sectionwrap:eq(0)');
				//if element is within a fieldset.sectionwrap element
				if ($section.length == 1){
					//cache this element inside corresponding section
					$section.data('elements').push(el);
				}
			}
		}
	},

	validate:function(section){
		//reference elements within this section that should be validated
		var elements = this.sections.$sections.eq(section).data('elements');
		var validated = true, invalidtext = ['Please fill out the following fields:' + "\n"];
		function invalidate(el){
			validated = false;
			invalidtext.push('- '+ (el.id || el.name))
		}
		for (var i = 0; i < elements.length; i++){
			if (/(text)/.test(elements[i].type) && elements[i].value == ''){
				//text and textarea elements
				invalidate(elements[i])
			} else if (/(select)/.test(elements[i].type) && (elements[i].selectedIndex == -1 || elements[i].options[elements[i].selectedIndex].text == '')){
				//select elements
				invalidate(elements[i])
			} else if (undefined == elements[i].type && 0 < elements[i].length){
				//radio and checkbox elements
				var onechecked = false;
				for (var r = 0; r < elements[i].length; r++){
					if (elements[i][r].checked == true){
						onechecked = true;
						break
					}
				}
				if (!onechecked){
					invalidate(elements[i][0])
				}
			}
		}
		if (!validated)
			alert(invalidtext.join("\n"));
		return validated
	},

	init:function(setting){
		var thiswizard = this;
		jQuery(function($){ //on document.ready
			var $theform = $('#' + setting.formid),
				//create Steps Container to house the 'steps' text
				$stepsguide = $('<div class="stepsguide" />'),

				//find all fieldsets within form and hide them initially
				$sections = $theform.find('fieldset.sectionwrap').hide(),
				$sectionswrapper = '',
				$sectionswrapper_inner = '';

			if (0 == $theform.length)
			//if form with specified ID doesn't exist, try name attribute instead
				$theform = $('form[name=' + setting.formid + ']');

			if ('slide' == setting.revealfx[0]) {
				//create outer DIV that will house all the fieldset.sectionwrap elements
				//add DIV above the first fieldset.sectionwrap element
				$sectionswrapper = $('<div class="step-outer" style="position:relative"></div>').insertBefore($sections.eq(0));
				//create inner DIV of $sectionswrapper that will scroll to reveal a fieldset element
				$sectionswrapper_inner = $('<div class="step-inner" style="position:absolute; left:0"></div>');
			}

			//variable to get width of widest fieldset.sectionwrap
			var maxfieldsetwidth = $sections.eq(0).outerWidth();

			//loop through $sections (starting from 2nd one)
			$sections.slice(1).each(function(){
				maxfieldsetwidth = Math.max($(this).outerWidth(), maxfieldsetwidth)
			});

			//add default 2px or param px to final width to reveal fieldset border (if not removed via CSS)
			maxfieldsetwidth += setting.fieldsetborderwidth;
			thiswizard.maxfieldsetwidth = maxfieldsetwidth;

			//loop through $sections again
			$sections.each(function(i){
				var $section = $(this);
				if ('slide' == setting.revealfx[0]) {
					//set fieldset position to 'absolute' and move it to inside sectionswrapper_inner DIV
					$section.data('page', i).css({position: 'absolute', left: maxfieldsetwidth * i}).appendTo($sectionswrapper_inner);
				}
				//empty array to contain elements within this section that should be validated for data (applicable only if validate option is defined)
				$section.data('elements', []);

				//create each 'step' DIV and add it to main Steps Container:
				var $stepwords = ['first', 'second', 'third'], $thestep = $('<div class="step disabledstep" />').data('section', i).html(($stepwords[i]
					+ ' step') + '<div class="smalltext">' + $section.find('legend:eq(0)').text() + '<p></p></div>').appendTo($stepsguide);

				//assign behavior to each step div
				$thestep.click(function(){
					thiswizard.loadsection($(this).data('section'))
				})
			});

			if ('slide' == setting.revealfx[0]) {
				$sectionswrapper.width(maxfieldsetwidth); //set fieldset wrapper to width of widest fieldset
				$sectionswrapper.append($sectionswrapper_inner); //add $sectionswrapper_inner as a child of $sectionswrapper
				$stepsguide.append('<div style="clear:both">&nbsp;</div>')
			}

			//add $thesteps div to the beginning of the form
			$theform.prepend($stepsguide);

			//$stepsguide.insertBefore($sectionswrapper) //add Steps Container before sectionswrapper container
			var $thesteps = $stepsguide.find('div.step');

			//create pagination DIV and add it to end of form:
			var $paginatediv = $('<div class="formpaginate">'
				+ '<span class="prev" style="float:left">Prev</span>'
				+ ' <span class="status">step 1 of </span>'
				+ ' <span class="next" style="float:right">Next</span>'
				+ '</div>');
			$theform.append($paginatediv);

			thiswizard.$theform = $theform;
			if ('slide' == setting.revealfx[0]) {
				//remember various parts of section container
				thiswizard.sections = {
					$outerwrapper: $sectionswrapper,
					$innerwrapper: $sectionswrapper_inner,
					$sections: $sections,
					count: $sections.length
				};
				thiswizard.sections.$sections.show()
			} else {
				//remember various parts of section container
				thiswizard.sections = {
					$sections: $sections,
					count: $sections.length
				};
			}
			thiswizard.$thesteps = $thesteps;

			//remember various parts of pagination DIV
			thiswizard.paginatediv = {
				$main: $paginatediv,
				$navlinks: $paginatediv.find('span.prev, span.next'),
				$status: $paginatediv.find('span.status')
			};

			//assign behavior to pagination buttons
			thiswizard.paginatediv.$main.click(function(e){
				if (/(prev)|(next)/.test(e.target.className))
					thiswizard.loadsection(e.target.className)
			});

			var i = (setting.persistsection ? FormToWizard.routines.getCookie(setting.formid + '_persist') : 0);

			//show the first section
			thiswizard.loadsection(i||0, true);

			//call oninit event handler
			thiswizard.setting.oninit($, i, $sections.eq(i));

			//if validate array defined
			if (setting.validate){
				//seek out and cache form elements that should be validated
				thiswizard.addvalidatefields();
				thiswizard.$theform.submit(function(){
					for (var i = 0; i < thiswizard.sections.count; i++){
						if (!thiswizard.validate(i)){
							thiswizard.loadsection(i, true);
							return false;
						}
					}
					return true;
				})
			}
		})
	}
};

FormToWizard.routines = {

	getCookie:function(Name){
		var re = new RegExp(Name + '=[^;]+', 'i'); //construct RE to search for target name/value pair
		if (document.cookie.match(re)) //if cookie found
			return document.cookie.match(re)[0].split('=')[1]; //return its value
		return null
	},

	setCookie:function(name, value){
		document.cookie = name + '=' + value + ';path=/';
	}
};