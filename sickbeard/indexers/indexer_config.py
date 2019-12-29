from lib.tvdb_api.tvdb_api import Tvdb
from lib.libtrakt.indexerapiinterface import TraktIndexer

TVINFO_TVDB = 1
TVINFO_TVRAGE = 2
TVINFO_TVMAZE = 3

# old tvdb api - version 1
# TVINFO_TVDB_V1 = 10001

# mapped only source
TVINFO_IMDB = 100
TVINFO_TRAKT = 101
TVINFO_TMDB = 102
# end mapped only source

init_config = {
    'valid_languages': ['da', 'fi', 'nl', 'de', 'it', 'es', 'fr', 'pl', 'hu', 'el', 'tr',
                        'ru', 'he', 'ja', 'pt', 'zh', 'cs', 'sl', 'hr', 'ko', 'en', 'sv', 'no'],
    'langabbv_to_id': dict(el=20, en=7, zh=27, it=15, cs=28, es=16, ru=22, nl=13, pt=26, no=9, tr=21, pl=18,
                           fr=17, hr=31, de=14, da=10, fi=11, hu=19, ja=25, he=24, ko=32, sv=8, sl=30)}

tvinfo_config = {
    TVINFO_TVDB: dict(
        main_url='https://thetvdb.com/',
        api_url='https://api.thetvdb.com/',
        id=TVINFO_TVDB,
        name='TheTVDB', slug='tvdb', kodi_slug='tvdb',
        module=Tvdb,
        api_params=dict(apikey='6cfd6399fd2bee018a8793da976f6522', language='en'),
        active=True,
        dupekey='',
        mapped_only=False,
        icon='thetvdb16.png',
    ),
    TVINFO_TVRAGE: dict(
        main_url='http://tvrage.com/',
        id=TVINFO_TVRAGE,
        name='TVRage', slug='tvrage',
        module=None,
        api_params=dict(apikey='Uhewg1Rr0o62fvZvUIZt', language='en'),
        active=False,
        dupekey='tvr',
        mapped_only=False,
        icon='tvrage16.png',
    ),
    TVINFO_TVMAZE: dict(
        main_url='https://www.tvmaze.com/',
        id=TVINFO_TVMAZE,
        name='TVmaze', slug='tvmaze',
        module=None,
        api_params={},
        active=False,
        dupekey='tvm',
        mapped_only=True,
        icon='tvmaze16.png',
    ),
    TVINFO_IMDB: dict(
        main_url='https://www.imdb.com/',
        id=TVINFO_IMDB,
        name='IMDb', slug='imdb', kodi_slug='imdb',
        module=None,
        api_params={},
        active=False,
        dupekey='imdb',
        mapped_only=True,
        icon='imdb16.png',
    ),
    TVINFO_TRAKT: dict(
        main_url='https://www.trakt.tv/',
        id=TVINFO_TRAKT,
        name='Trakt', slug='trakt',
        module=TraktIndexer,
        api_params={},
        active=True,
        dupekey='trakt',
        mapped_only=True,
        icon='trakt16.png',
    ),
    TVINFO_TMDB: dict(
        main_url='https://www.themoviedb.org/',
        id=TVINFO_TMDB,
        name='TMDb', slug='tmdb',  kodi_slug='tmdb',
        module=None,
        api_params={},
        active=False,
        dupekey='tmdb',
        mapped_only=True,
        icon='tmdb16.png',
    )
}

src = TVINFO_TVDB
tvinfo_config[src].update(dict(
    base_url=(tvinfo_config[src]['main_url'] +
              'api/%(apikey)s/series/' % tvinfo_config[src]['api_params']),
    show_url='%s?tab=series&id=%%d' % tvinfo_config[src]['main_url'],
    finder=(tvinfo_config[src]['main_url'] +
            'index.php?fieldlocation=2&language=7&order=translation&searching=Search&tab=advancedsearch&seriesname=%s'),
    scene_url='https://midgetspy.github.io/sb_tvdb_scene_exceptions/exceptions.txt',
    xem_origin='tvdb',
    # use kodi key for kodi <> tvdb api
    # https://github.com/xbmc/metadata.tvdb.com.python/blob/master/resources/lib/tvdb.py
    epg_url=(tvinfo_config[src]['api_url'] +
             'login?{&quot;apikey&quot;:&quot;%(apikey)s&quot;,&quot;id&quot;:{MID}}|Content-Type=application/json'
             % {'apikey': 'd60d3c015fdb148931e8254c0e96f072'}),
    # use internal key (backup, last resort)
    # epg_url=(tvinfo_config[src]['api_url'] +
    #          'login?{&quot;apikey&quot;:&quot;%(apikey)s&quot;,&quot;id&quot;:{MID}}|Content-Type=application/json'
    #          % tvinfo_config[src]['api_params']),
))

src = TVINFO_TVRAGE
tvinfo_config[src].update(dict(
    base_url=(tvinfo_config[src]['main_url'] +
              'showinfo.php?key=%(apikey)s&sid=' % tvinfo_config[src]['api_params']),
    show_url='%sshows/id-%%d' % tvinfo_config[src]['main_url'],
    scene_url='https://sickgear.github.io/sg_tvrage_scene_exceptions/exceptions.txt',
    defunct=True,
))

src = TVINFO_TVMAZE
tvinfo_config[src].update(dict(
    base_url='https://api.tvmaze.com/',
    show_url='%sshows/%%d' % tvinfo_config[src]['main_url'],
    finder='%ssearch?q=%s' % (tvinfo_config[src]['main_url'], '%s'),
))

src = TVINFO_IMDB
tvinfo_config[src].update(dict(
    base_url=tvinfo_config[src]['main_url'],
    show_url='%stitle/tt%%07d' % tvinfo_config[src]['main_url'],
    finder='%sfind?q=%s&s=tt&ttype=tv&ref_=fn_tv' % (tvinfo_config[src]['main_url'], '%s'),
))

src = TVINFO_TRAKT
tvinfo_config[src].update(dict(
    base_url=tvinfo_config[src]['main_url'],
    show_url='%sshows/%%d' % tvinfo_config[src]['main_url'],
    finder='%ssearch/shows?query=%s' % (tvinfo_config[src]['main_url'], '%s'),
))

src = TVINFO_TMDB
tvinfo_config[src].update(dict(
    base_url=tvinfo_config[src]['main_url'],
    show_url='%stv/%%d' % tvinfo_config[src]['main_url'],
    finder='%ssearch/tv?query=%s' % (tvinfo_config[src]['main_url'], '%s'),
))
