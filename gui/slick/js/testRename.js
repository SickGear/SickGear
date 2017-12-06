$(document).ready(function(){
    $('.seasonCheck').click(function(){
        var seasCheck = this;
        var seasNo = $(seasCheck).attr('id');

        $('.epCheck:visible').each(function(){
            var epParts = $(this).attr('id').split('x')

            if (epParts[0] == seasNo) {
                this.checked = seasCheck.checked
            }
        });
    });

    // selects all visible episode checkboxes
    $('.seriesCheck').click(function () {
        $('.epCheck:visible, .seasonCheck:visible').each(function () {
            this.checked = true
        });
    });

    // clears all visible episode checkboxes and the season selectors
    $('.clearAll').click(function () {
        $('.epCheck:visible, .seasonCheck:visible').each(function () {
            this.checked = false
        });
    });

    $('input[type=submit]').click(function(){
        var epArr = new Array()

        $('.epCheck').each(function() {
            if (this.checked == true) {
                epArr.push($(this).attr('id'))
            }
        });  

        if (epArr.length == 0)
            return false

        url = sbRoot+'/home/doRename?show='+$('#showID').val()+'&eps='+epArr.join('|')
        window.location.href = url
    });
    
});