import lib.fanart as fanart
from .items import LeafItem, Immutable, ResourceItem
__all__ = (
    'CharacterItem',
    'ArtItem',
    'LogoItem',
    'BackgroundItem',
    'SeasonThumbItem',
    'SeasonPosterItem',
    'ThumbItem',
    'HdLogoItem',
    'HdArtItem',
    'PosterItem',
    'BannerItem',
    'TvShow',
)


class TvItem(LeafItem):
    @Immutable.mutablemethod
    def __init__(self, fa_id, url, likes, lang):
        super(TvItem, self).__init__(fa_id, url, likes)
        self.lang = lang


class SeasonedTvItem(TvItem):
    @Immutable.mutablemethod
    def __init__(self, fa_id, url, likes, lang, season):
        super(SeasonedTvItem, self).__init__(fa_id, url, likes, lang)
        self.season = 0 if 'all' == season else int(season or 0)


class CharacterItem(TvItem):
    KEY = fanart.TYPE.TV.CHARACTER


class ArtItem(TvItem):
    KEY = fanart.TYPE.TV.ART


class LogoItem(TvItem):
    KEY = fanart.TYPE.TV.LOGO


class BackgroundItem(SeasonedTvItem):
    KEY = fanart.TYPE.TV.BACKGROUND


class SeasonThumbItem(SeasonedTvItem):
    KEY = fanart.TYPE.TV.SEASONTHUMB


class SeasonPosterItem(SeasonedTvItem):
    KEY = fanart.TYPE.TV.SEASONPOSTER


class ThumbItem(TvItem):
    KEY = fanart.TYPE.TV.THUMB


class HdLogoItem(TvItem):
    KEY = fanart.TYPE.TV.HDLOGO


class HdArtItem(TvItem):
    KEY = fanart.TYPE.TV.HDART


class PosterItem(TvItem):
    KEY = fanart.TYPE.TV.POSTER


class BannerItem(TvItem):
    KEY = fanart.TYPE.TV.BANNER


class TvShow(ResourceItem):
    WS = fanart.WS.TV

    @Immutable.mutablemethod
    def __init__(self, name, tvdbid, backgrounds, characters, arts, logos,
                 seasonthumb, seasonposter, thumbs, hdlogos, hdarts, posters, banners):
        self.name = name
        self.tvdbid = tvdbid
        self.backgrounds = backgrounds
        self.characters = characters
        self.arts = arts
        self.logos = logos
        self.seasonthumb = seasonthumb
        self.seasonposter = seasonposter
        self.thumbs = thumbs
        self.hdlogos = hdlogos
        self.hdarts = hdarts
        self.posters = posters
        self.banners = banners

    @classmethod
    def from_dict(cls, resource):
        assert 1 == len(resource), 'Bad Format Map'
        name, resource = resource.items()[0]
        return cls(
            name=name,
            tvdbid=resource['thetvdb_id'],
            backgrounds=BackgroundItem.extract(resource),
            characters=CharacterItem.extract(resource),
            arts=ArtItem.extract(resource),
            logos=LogoItem.extract(resource),
            seasonthumb=SeasonThumbItem.extract(resource),
            seasonposter=SeasonPosterItem.extract(resource),
            thumbs=ThumbItem.extract(resource),
            hdlogos=HdLogoItem.extract(resource),
            hdarts=HdArtItem.extract(resource),
            posters=PosterItem.extract(resource),
            banners=BannerItem.extract(resource),
        )
