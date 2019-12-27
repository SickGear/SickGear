$(document).ready(function() {

    function make_row(tvid_prodid, season, episode, name, subtitles, checked) {
        if (checked)
            var checked = ' checked';
        else
            var checked = '';

        var row = '';
        row += ' <tr class="good">';
        row += '  <td align="center"><input type="checkbox" class="' + tvid_prodid + '-epcheck" name="' + tvid_prodid + '-' + season + 'x' + episode + '"' + checked + '></td>';
        row += '  <td style="width:7%;white-space:nowrap;">' + season + ' x ' + episode + '</td>';
        row += '  <td><span class="pull-left">'+name+'</span></td>';
        row += '  <td style="float: right;">';
        	subtitles = subtitles.split(',')
        	for (i in subtitles)
        	{
        		row += '   <img src="' + sbRoot + '/images/flags/'+subtitles[i]+'.png" width="16" height="11" alt="'+subtitles[i]+'" />&nbsp;';
        	}
        row += '  </td>';
        row += ' </tr>'

        return row;
    }

    $('.allCheck').click(function(){
        var tvid_prodid = $(this).attr('id').split('-')[1];
        $('[class="' + tvid_prodid + '-epcheck"]').prop('checked', $(this).prop('checked'));
    });

    $('.get_more_eps').click(function(){
        var tvid_prodid = $(this).attr('id'),
            checked = $('[id="allCheck-' + tvid_prodid + '"]').prop('checked'),
            last_row = $('tr[id="' + tvid_prodid + '"]');

        $.getJSON(sbRoot+'/manage/show-subtitle-missed',
                  {
                   tvid_prodid: tvid_prodid,
                   which_subs: $('#selectSubLang').val()
                  },
                  function (data) {
                      $.each(data, function(season,eps){
                          $.each(eps, function(episode, data) {
                              //alert(season+'x'+episode+': '+name);
                              last_row.after(make_row(tvid_prodid, season, episode, data.name, data.subtitles, checked));
                          });
                      });
                  });
        $(this).hide();
    });

    // selects all visible episode checkboxes.
    $('.selectAllShows').click(function(){
        $('.allCheck').each(function(){
                this.checked = true;
        });
        $('input[class*="-epcheck"]').each(function(){
                this.checked = true;
        });
    });

    // clears all visible episode checkboxes and the season selectors
    $('.unselectAllShows').click(function(){
        $('.allCheck').each(function(){
                this.checked = false;
        });
        $('input[class*="-epcheck"]').each(function(){
                this.checked = false;
        });
    });

});
