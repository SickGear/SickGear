from lib.tvdb_api.tvdb_api import Tvdb
from lib.tvrage_api.tvrage_api import TVRage

INDEXER_TVDB = 1
INDEXER_TVRAGE = 2
INDEXER_TVMAZE = 3

# mapped only indexer
INDEXER_IMDB = 100
INDEXER_TRAKT = 101
INDEXER_TMDB = 102
# end mapped only indexer

initConfig = {
    'valid_languages': ['da', 'fi', 'nl', 'de', 'it', 'es', 'fr', 'pl', 'hu', 'el', 'tr',
                        'ru', 'he', 'ja', 'pt', 'zh', 'cs', 'sl', 'hr', 'ko', 'en', 'sv', 'no'],
    'langabbv_to_id': dict(el=20, en=7, zh=27, it=15, cs=28, es=16, ru=22, nl=13, pt=26, no=9, tr=21, pl=18,
                           fr=17, hr=31, de=14, da=10, fi=11, hu=19, ja=25, he=24, ko=32, sv=8, sl=30)}

indexerConfig = {
    INDEXER_TVDB: dict(
        main_url='https://thetvdb.com/',
        id=INDEXER_TVDB,
        name='TheTVDB',
        module=Tvdb,
        api_params=dict(apikey='F9C450E78D99172E', language='en', useZip=True),
        active=True,
        dupekey='',
        mapped_only=False,
        icon='thetvdb16.png',
    ),
    INDEXER_TVRAGE: dict(
        main_url='http://tvrage.com/',
        id=INDEXER_TVRAGE,
        name='TVRage',
        module=TVRage,
        api_params=dict(apikey='Uhewg1Rr0o62fvZvUIZt', language='en'),
        active=False,
        dupekey='tvr',
        mapped_only=False,
        icon='tvrage16.png',
    ),
    INDEXER_TVMAZE: dict(
        main_url='http://www.tvmaze.com/',
        id=INDEXER_TVMAZE,
        name='TVmaze',
        module=None,
        api_params={},
        active=False,
        dupekey='tvm',
        mapped_only=True,
        icon='tvmaze16.png',
    ),
    INDEXER_IMDB: dict(
        main_url='https://www.imdb.com/',
        id=INDEXER_IMDB,
        name='IMDb',
        module=None,
        api_params={},
        active=False,
        dupekey='imdb',
        mapped_only=True,
        icon='imdb16.png',
    ),
    INDEXER_TRAKT: dict(
        main_url='https://www.trakt.tv/',
        id=INDEXER_TRAKT,
        name='Trakt',
        module=None,
        api_params={},
        active=False,
        dupekey='trakt',
        mapped_only=True,
        icon='trakt16.png',
    ),
    INDEXER_TMDB: dict(
        main_url='https://www.themoviedb.org/',
        id=INDEXER_TMDB,
        name='TMDb',
        module=None,
        api_params={},
        active=False,
        dupekey='tmdb',
        mapped_only=True,
        icon='tmdb16.png',
    )
}

info_src = INDEXER_TVDB
indexerConfig[info_src].update(dict(
    base_url=(indexerConfig[info_src]['main_url'] +
              'api/%(apikey)s/series/' % indexerConfig[info_src]['api_params']),
    show_url='%s?tab=series&id=' % indexerConfig[info_src]['main_url'],
    finder=(indexerConfig[info_src]['main_url'] +
            'index.php?fieldlocation=2&language=7&order=translation&searching=Search&tab=advancedsearch&seriesname=%s'),
    scene_url='https://midgetspy.github.io/sb_tvdb_scene_exceptions/exceptions.txt',
    xem_origin='tvdb',
))

info_src = INDEXER_TVRAGE
indexerConfig[info_src].update(dict(
    base_url=(indexerConfig[info_src]['main_url'] +
              'showinfo.php?key=%(apikey)s&sid=' % indexerConfig[info_src]['api_params']),
    show_url='%sshows/id-' % indexerConfig[info_src]['main_url'],
    scene_url='https://sickgear.github.io/sg_tvrage_scene_exceptions/exceptions.txt',
    xem_origin='rage',
    defunct=True,
))

info_src = INDEXER_TVMAZE
indexerConfig[info_src].update(dict(
    base_url='http://api.tvmaze.com/',
    show_url='%sshows/' % indexerConfig[info_src]['main_url'],
    finder='%ssearch?q=%s' % (indexerConfig[info_src]['main_url'], '%s'),
))

info_src = INDEXER_IMDB
indexerConfig[info_src].update(dict(
    base_url=indexerConfig[info_src]['main_url'],
    show_url='%stitle/tt' % indexerConfig[info_src]['main_url'],
    finder='%sfind?q=%s&s=tt&ttype=tv&ref_=fn_tv' % (indexerConfig[info_src]['main_url'], '%s'),
))

info_src = INDEXER_TRAKT
indexerConfig[info_src].update(dict(
    base_url=indexerConfig[info_src]['main_url'],
    show_url='%sshows/' % indexerConfig[info_src]['main_url'],
    finder='%ssearch/shows?query=%s' % (indexerConfig[info_src]['main_url'], '%s'),
))

info_src = INDEXER_TMDB
indexerConfig[info_src].update(dict(
    base_url=indexerConfig[info_src]['main_url'],
    show_url='%stv/' % indexerConfig[info_src]['main_url'],
    finder='%ssearch/tv?query=%s' % (indexerConfig[info_src]['main_url'], '%s'),
))
