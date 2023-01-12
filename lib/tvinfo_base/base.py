import copy
import datetime
import diskcache
import logging
import threading
import shutil
import time
from exceptions_helper import ex

from six import integer_types, iteritems, iterkeys, string_types, text_type
from _23 import list_items, list_values

from lib.tvinfo_base.exceptions import *
from sg_helpers import calc_age, make_path

# noinspection PyUnreachableCode
if False:
    from typing import Any, AnyStr, Dict, List, Optional, Set, Tuple, Union
    str_int = Union[AnyStr, integer_types]

TVINFO_TVDB = 1
TVINFO_TVRAGE = 2
TVINFO_TVMAZE = 3
TVINFO_TMDB = 4

# old tvdb api - version 1
# TVINFO_TVDB_V1 = 10001

# mapped only source
TVINFO_IMDB = 100
TVINFO_TRAKT = 101
# old tmdb id
TVINFO_TMDB_OLD = 102
# end mapped only source
TVINFO_TVDB_SLUG = 1001
TVINFO_TRAKT_SLUG = 1101

# generic stuff
TVINFO_SLUG = 100000

# social media sources
TVINFO_TWITTER = 250000
TVINFO_FACEBOOK = 250001
TVINFO_INSTAGRAM = 250002
TVINFO_WIKIPEDIA = 250003

tv_src_names = {
    TVINFO_TVDB: 'tvdb',
    TVINFO_TVRAGE: 'tvrage',
    TVINFO_TVMAZE: 'tvmaze',

    10001: 'tvdb v1',
    TVINFO_IMDB: 'imdb',
    TVINFO_TRAKT: 'trakt',
    TVINFO_TMDB: 'tmdb',
    TVINFO_TVDB_SLUG : 'tvdb slug',
    TVINFO_TRAKT_SLUG: 'trakt slug',

    TVINFO_SLUG: 'generic slug',

    TVINFO_TWITTER: 'twitter',
    TVINFO_FACEBOOK: 'facebook',
    TVINFO_INSTAGRAM: 'instagram',
    TVINFO_WIKIPEDIA: 'wikipedia'

}

log = logging.getLogger('TVInfo')
log.addHandler(logging.NullHandler())
TVInfoShowContainer = {}  # type: Dict[ShowContainer]


class ShowContainer(dict):
    """Simple dict that holds a series of Show instances
    """

    def __init__(self, **kwargs):
        super(ShowContainer, self).__init__(**kwargs)
        # limit caching of TVInfoShow objects to 15 minutes
        self.max_age = 900  # type: integer_types
        self.lock = threading.RLock()

    def __setitem__(self, k, v):
        super(ShowContainer, self).__setitem__(k, (v, time.time()))

    def __getitem__(self, k):
        return super(ShowContainer, self).__getitem__(k)[0]

    def cleanup_old(self):
        """
        remove entries that are older then max_age
        """
        acquired_lock = self.lock.acquire(False)
        if acquired_lock:
            try:
                current_time = time.time()
                for k, v in list_items(self):
                    if self.max_age < current_time - v[1]:
                        lock_acquired = self[k].lock.acquire(False)
                        if lock_acquired:
                            try:
                                del self[k]
                            except (BaseException, Exception):
                                try:
                                    self[k].lock.release()
                                except RuntimeError:
                                    pass
            finally:
                self.lock.release()

    def __str__(self):
        nr_shows = len(self)
        return '<ShowContainer (containing %s Show%s)>' % (nr_shows, ('s', '')[1 == nr_shows])

    __repr__ = __str__


class TVInfoIDs(object):
    def __init__(
            self,
            tvdb=None,  # type: integer_types
            tmdb=None,  # type: integer_types
            tvmaze=None,  # type: integer_types
            imdb=None,  # type: integer_types
            trakt=None,  # type: integer_types
            rage=None,  # type: integer_types
            ids=None  # type: Dict[int, integer_types]
    ):  # type: (...) -> TVInfoIDs
        ids = ids or {}
        self.tvdb = tvdb or ids.get(TVINFO_TVDB)
        self.tmdb = tmdb or ids.get(TVINFO_TMDB)
        self.tvmaze = tvmaze or ids.get(TVINFO_TVMAZE)
        self.imdb = imdb or ids.get(TVINFO_IMDB)
        self.trakt = trakt or ids.get(TVINFO_TRAKT)
        self.rage = rage or ids.get(TVINFO_TVRAGE)

    def __getitem__(self, key):
        return {TVINFO_TVDB: self.tvdb, TVINFO_TMDB: self.tmdb, TVINFO_TVMAZE: self.tvmaze,
                TVINFO_IMDB: self.imdb, TVINFO_TRAKT: self.trakt, TVINFO_TVRAGE: self.rage}.get(key)

    def get(self, key):
        return self.__getitem__(key)

    def __iter__(self):
        for s, v in [(TVINFO_TVDB, self.tvdb), (TVINFO_TMDB, self.tmdb), (TVINFO_TVMAZE, self.tvmaze),
                     (TVINFO_IMDB, self.imdb), (TVINFO_TRAKT, self.trakt), (TVINFO_TVRAGE, self.rage)]:
            yield s, v

    def __str__(self):
        return ', '.join('%s: %s' % (tv_src_names.get(k, k), v) for k, v in self.__iter__())

    __repr__ = __str__
    iteritems = __iter__
    items = __iter__


class TVInfoSocialIDs(object):
    def __init__(self, twitter=None, instagram=None, facebook=None, wikipedia=None, ids=None):
        # type: (str_int, str_int, str_int, str_int, Dict[int, str_int]) -> TVInfoSocialIDs
        ids = ids or {}
        self.twitter = twitter or ids.get(TVINFO_TWITTER)
        self.instagram = instagram or ids.get(TVINFO_INSTAGRAM)
        self.facebook = facebook or ids.get(TVINFO_FACEBOOK)
        self.wikipedia = wikipedia or ids.get(TVINFO_WIKIPEDIA)

    def __getitem__(self, key):
        return {TVINFO_TWITTER: self.twitter, TVINFO_INSTAGRAM: self.instagram, TVINFO_FACEBOOK: self.facebook,
                TVINFO_WIKIPEDIA: self.wikipedia}.get(key)

    def __iter__(self):
        for s, v in [(TVINFO_TWITTER, self.twitter), (TVINFO_INSTAGRAM, self.instagram),
                     (TVINFO_FACEBOOK, self.facebook), (TVINFO_WIKIPEDIA, self.wikipedia)]:
            yield s, v

    def __str__(self):
        return ', '.join('%s: %s' % (tv_src_names.get(k, k), v) for k, v in self.__iter__())

    __repr__ = __str__
    iteritems = __iter__
    items = __iter__


class TVInfoImageType(object):
    poster = 1
    banner = 2
    # fanart/background
    fanart = 3
    typography = 4
    other = 10
    # person
    person_poster = 50
    # season
    season_poster = 100
    season_banner = 101
    season_fanart = 103
    # stills
    still = 200

    reverse_str = {
        poster: 'poster',
        banner: 'banner',
        # fanart/background
        fanart: 'fanart',
        typography: 'typography',
        other: 'other',
        # person
        person_poster: 'person poster',
        # season
        season_poster: 'season poster',
        season_banner: 'season banner',
        season_fanart: 'season fanart',
        # stills
        still: 'still'
    }


class TVInfoImageSize(object):
    original = 1
    medium = 2
    small = 3

    reverse_str = {
        1: 'original',
        2: 'medium',
        3: 'small'
    }


class TVInfoImage(object):
    def __init__(self, image_type, sizes, img_id=None, main_image=False, type_str='', rating=None, votes=None,
                 lang=None, height=None, width=None, aspect_ratio=None):
        self.img_id = img_id  # type: Optional[integer_types]
        self.image_type = image_type  # type: integer_types
        self.sizes = sizes  # type: Dict[TVInfoImageSize, AnyStr]
        self.type_str = type_str  # type: AnyStr
        self.main_image = main_image  # type: bool
        self.rating = rating  # type: Optional[Union[float, integer_types]]
        self.votes = votes  # type: Optional[integer_types]
        self.lang = lang  # type: Optional[AnyStr]
        self.height = height  # type: Optional[integer_types]
        self.width = width  # type: Optional[integer_types]
        self.aspect_ratio = aspect_ratio  # type: Optional[Union[float, integer_types]]

    def __str__(self):
        return '<TVInfoImage %s [%s]>' % (TVInfoImageType.reverse_str.get(self.image_type, 'unknown'),
                                          ', '.join(TVInfoImageSize.reverse_str.get(s, 'unkown') for s in self.sizes))

    __repr__ = __str__


class TVInfoNetwork(object):
    def __init__(self, name, n_id=None, country=None, country_code=None, timezone=None, stream=None):
        self.name = name  # type: AnyStr
        self.id = n_id  # type: Optional[integer_types]
        self.country = country  # type: Optional[AnyStr]
        self.country_code = country_code  # type: Optional[AnyStr]
        self.timezone = timezone  # type: Optional[AnyStr]
        self.stream = stream  # type: Optional[bool]

    def __str__(self):
        return '<Network (%s)>' % ', '.join('%s' % s for s in [self.name, self.id, self.country, self.country_code,
                                                               self.timezone] if s)

    __repr__ = __str__


class TVInfoShow(dict):
    """Holds a dict of seasons, and show data.
    """

    def __init__(self):
        dict.__init__(self)
        self.lock = threading.RLock()
        self.data = {}  # type: Dict
        self.ep_loaded = False  # type: bool
        self.poster_loaded = False  # type: bool
        self.banner_loaded = False  # type: bool
        self.fanart_loaded = False  # type: bool
        self.season_images_loaded = False  # type: bool
        self.seasonwide_images_loaded = False  # type: bool
        self.actors_loaded = False  # type: bool
        self.show_not_found = False  # type: bool
        self.id = None  # type: integer_types
        self.ids = TVInfoIDs()  # type: TVInfoIDs
        self.social_ids = TVInfoSocialIDs()  # type: TVInfoSocialIDs
        self.slug = None  # type: Optional[AnyStr]
        self.seriesid = None  # type: integer_types
        self.seriesname = None  # type: Optional[AnyStr]
        self.aliases = []  # type: List[AnyStr]
        self.season = None  # type: integer_types
        self.classification = None  # type: Optional[AnyStr]
        self.genre = None  # type: Optional[AnyStr]
        self.genre_list = []  # type: List[AnyStr]
        self.actors = []  # type: List[Dict]
        self.cast = CastList()  # type: CastList
        self.crew = CrewList()  # type: CrewList
        self.show_type = []  # type: List[AnyStr]
        self.networks = []  # type: List[TVInfoNetwork]
        self.network = None  # type: Optional[AnyStr]
        self.network_id = None  # type: integer_types
        self.network_timezone = None  # type: Optional[AnyStr]
        self.network_country = None  # type: Optional[AnyStr]
        self.network_country_code = None  # type: Optional[AnyStr]
        self.network_is_stream = None  # type: Optional[bool]
        self.runtime = None  # type: integer_types
        self.language = None  # type: Optional[AnyStr]
        self.official_site = None  # type: Optional[AnyStr]
        self.imdb_id = None  # type: Optional[AnyStr]
        self.zap2itid = None  # type: Optional[AnyStr]
        self.airs_dayofweek = None  # type: Optional[AnyStr]
        self.airs_time = None  # type: Optional[AnyStr]
        self.time = None  # type: Optional[datetime.time]
        self.firstaired = None  # type: Optional[AnyStr]
        self.added = None  # type: Optional[AnyStr]
        self.addedby = None  # type: Union[integer_types, AnyStr]
        self.siteratingcount = None  # type: integer_types
        self.lastupdated = None  # type: integer_types
        self.contentrating = None  # type: Optional[AnyStr]
        self.rating = None  # type: Union[integer_types, float]
        self.status = None  # type: Optional[AnyStr]
        self.overview = None  # type: Optional[AnyStr]
        self.poster = None  # type: Optional[AnyStr]
        self.poster_thumb = None  # type: Optional[AnyStr]
        self.banner = None  # type: Optional[AnyStr]
        self.banner_thumb = None  # type: Optional[AnyStr]
        self.fanart = None  # type: Optional[AnyStr]
        self.banners = {}  # type: Dict
        self.images = {}  # type: Dict[TVInfoImageType, List[TVInfoImage]]
        self.updated_timestamp = None  # type: Optional[integer_types]
        # special properties for trending, popular, ...
        self.popularity = None  # type: Optional[Union[integer_types, float]]
        self.vote_count = None  # type: Optional[integer_types]
        self.vote_average = None  # type: Optional[Union[integer_types, float]]
        self.origin_countries = []  # type: List[AnyStr]

    def __str__(self):
        nr_seasons = len(self)
        return '<Show %r (containing %s season%s)>' % (self.seriesname, nr_seasons, ('s', '')[1 == nr_seasons])

    def __getattr__(self, key):
        if key in self:
            # Key is an episode, return it
            return self[key]

        if key in self.data:
            # Non-numeric request is for show-data
            return self.data[key]

        raise AttributeError

    def __getitem__(self, key, raise_error=True):
        if isinstance(key, string_types) and key in self.__dict__:
            return self.__dict__[key]

        if key in self:
            # Key is an episode, return it
            return dict.__getitem__(self, key)

        if key in self.data:
            # Non-numeric request is for show-data
            return dict.__getitem__(self.data, key)

        if raise_error:
            # Data wasn't found, raise appropriate error
            if isinstance(key, integer_types) or isinstance(key, string_types) and key.isdigit():
                # Episode number x was not found
                raise BaseTVinfoSeasonnotfound('Could not find season %s' % (repr(key)))
            else:
                # If it's not numeric, it must be an attribute name, which
                # doesn't exist, so attribute error.
                raise BaseTVinfoAttributenotfound('Cannot find attribute %s' % (repr(key)))

    def get(self, __key, __default=None):
        return self.__getitem__(__key, raise_error=None is __default) or __default

    def __deepcopy__(self, memo):
        cls = self.__class__
        result = cls.__new__(cls)
        memo[id(self)] = result
        for k, v in self.__dict__.items():
            if 'lock' == k:
                setattr(result, k, threading.RLock())
            else:
                setattr(result, k, copy.deepcopy(v, memo))
        for k, v in self.items():
            result[k] = copy.deepcopy(v, memo)
        return result

    def __bool__(self):
        # type: (...) -> bool
        return bool(self.id) or any(iterkeys(self.data))

    def to_dict(self):
        return self.__dict__.copy()

    def aired_on(self, date):
        ret = self.search(str(date), 'firstaired')
        if 0 == len(ret):
            raise BaseTVinfoEpisodenotfound('Could not find any episodes that aired on %s' % date)
        return ret

    def search(self, term=None, key=None):
        """
        Search all episodes in show. Can search all data, or a specific key (for
        example, episodename)

        Always returns an array (can be empty). First index contains the first
        match, and so on.
        """
        results = []
        for cur_season in list_values(self):
            searchresult = cur_season.search(term=term, key=key)
            if 0 != len(searchresult):
                results.extend(searchresult)

        return results

    def __getstate__(self):
        d = dict(self.__dict__)
        try:
            del d['lock']
        except (BaseException, Exception):
            pass
        return d

    def __setstate__(self, d):
        self.__dict__ = d
        self.lock = threading.RLock()

    __repr__ = __str__
    __nonzero__ = __bool__


class TVInfoSeason(dict):
    def __init__(self, show=None, **kwargs):
        """The show attribute points to the parent show
        """
        super(TVInfoSeason, self).__init__(**kwargs)
        self.show = show  # type: TVInfoShow
        self.id = None  # type: integer_types
        self.number = None  # type: integer_types
        self.name = None  # type: Optional[AnyStr]
        self.actors = []  # type: List[Dict]
        self.cast = CastList()  # type: Dict[integer_types, TVInfoCharacter]
        self.network = None  # type: Optional[AnyStr]
        self.network_id = None  # type: integer_types
        self.network_timezone = None  # type: Optional[AnyStr]
        self.network_country = None  # type: Optional[AnyStr]
        self.network_country_code = None  # type: Optional[AnyStr]
        self.network_is_stream = None  # type: Optional[bool]
        self.ordered = None  # type: Optional[integer_types]
        self.start_date = None  # type: Optional[AnyStr]
        self.end_date = None  # type: Optional[AnyStr]
        self.poster = None  # type: Optional[AnyStr]
        self.summery = None  # type: Optional[AnyStr]
        self.episode_order = None  # type: Optional[integer_types]

    def __str__(self):
        nr_episodes = len(self)
        return '<Season %s instance (containing %s episode%s)>' % \
               (self.number, nr_episodes, ('s', '')[1 == nr_episodes])

    def __getattr__(self, episode_number):
        if episode_number in self:
            return self[episode_number]
        raise AttributeError

    def __getitem__(self, episode_number):
        if episode_number not in self:
            raise BaseTVinfoEpisodenotfound('Could not find episode %s' % (repr(episode_number)))
        else:
            return dict.__getitem__(self, episode_number)

    def __deepcopy__(self, memo):
        cls = self.__class__
        result = cls.__new__(cls)
        memo[id(self)] = result
        for k, v in self.__dict__.items():
            setattr(result, k, copy.deepcopy(v, memo))
        for k, v in self.items():
            result[k] = copy.deepcopy(v, memo)
        return result

    def search(self, term=None, key=None):
        """Search all episodes in season, returns a list of matching Episode
        instances.
        """
        results = []
        for ep in list_values(self):
            searchresult = ep.search(term=term, key=key)
            if None is not searchresult:
                results.append(searchresult)
        return results

    __repr__ = __str__


class TVInfoEpisode(dict):
    def __init__(self, season=None, show=None, **kwargs):
        """The season attribute points to the parent season
        """
        super(TVInfoEpisode, self).__init__(**kwargs)
        self.id = None  # type: integer_types
        self.seriesid = None  # type: integer_types
        self.season = season  # type: TVInfoSeason
        self.seasonnumber = None  # type: integer_types
        self.episodenumber = None  # type: integer_types
        self.absolute_number = None  # type: integer_types
        self.is_special = None  # type: Optional[bool]
        self.actors = []  # type: List[Dict]
        self.gueststars = None  # type: Optional[AnyStr]
        self.gueststars_list = []  # type: List[AnyStr]
        self.cast = CastList()  # type: Dict[integer_types, TVInfoCharacter]
        self.directors = []  # type: List[AnyStr]
        self.writer = None  # type: Optional[AnyStr]
        self.writers = []  # type: List[AnyStr]
        self.crew = CrewList()  # type: CrewList
        self.episodename = None  # type: Optional[AnyStr]
        self.overview = None  # type: Optional[AnyStr]
        self.language = {'episodeName': None, 'overview': None}  # type: Dict[AnyStr, Optional[AnyStr]]
        self.productioncode = None  # type: Optional[AnyStr]
        self.showurl = None  # type: Optional[AnyStr]
        self.lastupdated = None  # type: integer_types
        self.dvddiscid = None  # type: Optional[AnyStr]
        self.dvd_season = None  # type: integer_types
        self.dvd_episodenumber = None  # type: integer_types
        self.dvdchapter = None  # type: integer_types
        self.firstaired = None  # type: Optional[AnyStr]
        self.airtime = None  # type: Optional[datetime.time]
        self.runtime = 0  # type: integer_types
        self.timestamp = None  # type: Optional[integer_types]
        self.network = None  # type: Optional[AnyStr]
        self.network_id = None  # type: integer_types
        self.network_timezone = None  # type: Optional[AnyStr]
        self.network_country = None  # type: Optional[AnyStr]
        self.network_country_code = None  # type: Optional[AnyStr]
        self.network_is_stream = None  # type: Optional[bool]
        self.filename = None  # type: Optional[AnyStr]
        self.lastupdatedby = None  # type: Union[integer_types, AnyStr]
        self.airsafterseason = None  # type: integer_types
        self.airsbeforeseason = None  # type: integer_types
        self.airsbeforeepisode = None  # type: integer_types
        self.imdb_id = None  # type: Optional[AnyStr]
        self.contentrating = None  # type: Optional[AnyStr]
        self.thumbadded = None  # type: Optional[AnyStr]
        self.rating = None  # type: Union[integer_types, float]
        self.siteratingcount = None  # type: integer_types
        self.show = show  # type: Optional[TVInfoShow]

    def __str__(self):
        show_name = (self.show and self.show.seriesname and '<Show  %s> - ' % self.show.seriesname) or ''
        seasno, epno = int(getattr(self, 'seasonnumber', 0)), int(getattr(self, 'episodenumber', 0))
        epname = getattr(self, 'episodename', '')
        if None is not epname:
            return '%s<Episode %02dx%02d - %r>' % (show_name, seasno, epno, epname)
        else:
            return '%s<Episode %02dx%02d>' % (show_name, seasno, epno)

    def __getattr__(self, key):
        if key in self:
            return self[key]
        raise AttributeError

    def __getitem__(self, key):
        try:
            return dict.__getitem__(self, key)
        except KeyError:
            raise BaseTVinfoAttributenotfound('Cannot find attribute %s' % (repr(key)))

    def __deepcopy__(self, memo):
        cls = self.__class__
        result = cls.__new__(cls)
        memo[id(self)] = result
        for k, v in self.__dict__.items():
            setattr(result, k, copy.deepcopy(v, memo))
        for k, v in self.items():
            result[k] = copy.deepcopy(v, memo)
        return result

    def __bool__(self):
        # type: (...) -> bool
        return bool(self.id) or bool(self.episodename)

    def search(self, term=None, key=None):
        """Search episode data for term, if it matches, return the Episode (self).
        The key parameter can be used to limit the search to a specific element,
        for example, episodename.
        """
        if None is term:
            raise TypeError('must supply string to search for (contents)')

        term = text_type(term).lower()
        for cur_key, cur_value in iteritems(self):
            cur_key, cur_value = text_type(cur_key).lower(), text_type(cur_value).lower()
            if None is not key and cur_key != key:
                # Do not search this key
                continue
            if cur_value.find(text_type(term).lower()) > -1:
                return self

    __unicode__ = __str__
    __repr__ = __str__
    __nonzero__ = __bool__


class Persons(dict):
    """Holds all Persons instances for a show
    """
    def __str__(self):
        persons_count = len(self)
        return '<Persons (containing %s Person%s)>' % (persons_count, ('', 's')[1 != persons_count])

    __repr__ = __str__


class CastList(Persons):
    def __init__(self, **kwargs):
        super(CastList, self).__init__(**kwargs)
        for t in iterkeys(RoleTypes.reverse):
            if t < RoleTypes.crew_limit:
                self[t] = []  # type: List[TVInfoCharacter]

    def __str__(self):
        persons_count = []
        for t in iterkeys(RoleTypes.reverse):
            if t < RoleTypes.crew_limit:
                if len(self.get(t, [])):
                    persons_count.append('%s: %s' % (RoleTypes.reverse[t], len(self.get(t, []))))
        persons_text = ', '.join(persons_count)
        persons_text = ('0', '(%s)' % persons_text)['' != persons_text]
        return '<Cast (containing %s Person%s)>' % (persons_text, ('', 's')['' != persons_text])

    __repr__ = __str__


class CrewList(Persons):
    def __init__(self, **kwargs):
        super(CrewList, self).__init__(**kwargs)
        for t in iterkeys(RoleTypes.reverse):
            if t >= RoleTypes.crew_limit:
                self[t] = []  # type: List[Crew]

    def __str__(self):
        persons_count = []
        for t in iterkeys(RoleTypes.reverse):
            if t >= RoleTypes.crew_limit:
                if len(self.get(t, [])):
                    persons_count.append('%s: %s' % (RoleTypes.reverse[t], len(self.get(t, []))))
        persons_text = ', '.join(persons_count)
        persons_text = ('0', '(%s)' % persons_text)['' != persons_text]
        return '<Crew (containing %s Person%s)>' % (persons_text, ('', 's')['' != persons_text])

    __repr__ = __str__


class PersonBase(dict):
    """Represents a single person. Should contain..

    id,
    image,
    name,
    role,
    sortorder
    """
    def __init__(
            self,  # type:
            p_id=None,  # type: integer_types
            name=None,  # type: AnyStr
            image=None,  # type: AnyStr
            images=None,  # type: List[TVInfoImage]
            gender=None,  # type: int
            bio=None,  # type: AnyStr
            birthdate=None,  # type: datetime.date
            deathdate=None,  # type: datetime.date
            country=None,  # type: AnyStr
            country_code=None,  # type: AnyStr
            country_timezone=None,  # type: AnyStr
            ids=None,  # type: Dict
            thumb_url=None,  # type: AnyStr
            **kwargs  # type: Dict
    ):  # type: (...) -> PersonBase
        super(PersonBase, self).__init__(**kwargs)
        self.id = p_id  # type: Optional[integer_types]
        self.name = name  # type: Optional[AnyStr]
        self.image = image  # type: Optional[AnyStr]
        self.images = images or []  # type: List[TVInfoImage]
        self.thumb_url = thumb_url  # type: Optional[AnyStr]
        self.gender = gender  # type: Optional[int]
        self.bio = bio  # type: Optional[AnyStr]
        self.birthdate = birthdate  # type: Optional[datetime.date]
        self.deathdate = deathdate  # type: Optional[datetime.date]
        self.country = country  # type: Optional[AnyStr]
        self.country_code = country_code  # type: Optional[AnyStr]
        self.country_timezone = country_timezone  # type: Optional[AnyStr]
        self.ids = ids or {}  # type: Dict[int, integer_types]

    def calc_age(self, date=None):
        # type: (Optional[datetime.date]) -> Optional[int]
        return calc_age(self.birthdate, self.deathdate, date)

    @property
    def age(self):
        # type: (...) -> Optional[int]
        """
        :return: age of person if birthdate is known, in case of deathdate is known return age of death
        """
        return self.calc_age()

    def __bool__(self):
        # type: (...) -> bool
        return bool(self.name)

    def __str__(self):
        return '<Person "%s">' % self.name

    __repr__ = __str__
    __nonzero__ = __bool__


class PersonGenders(object):
    unknown = 0
    male = 1
    female = 2

    named = {'unknown': 0, 'male': 1, 'female': 2}
    reverse = {v: k for k, v in iteritems(named)}
    tmdb_map = {0: unknown, 1: female, 2: male}
    imdb_map = {'female': female, 'male': male}


class Crew(PersonBase):

    def __init__(self, crew_type_name=None, **kwargs):
        super(Crew, self).__init__(**kwargs)
        self.crew_type_name = crew_type_name

    def __str__(self):
        return '<Crew%s "%s)">' % (('', ('/%s' % self.crew_type_name))[isinstance(self.crew_type_name, string_types)],
                                   self.name)

    __repr__ = __str__


class TVInfoPerson(PersonBase):
    def __init__(
            self,
            p_id=None,  # type: integer_types
            name=None,  # type: AnyStr
            image=None,  # type: Optional[AnyStr]
            images=None,  # type: List[TVInfoImage]
            thumb_url=None,  # type: AnyStr
            gender=None,  # type: int
            bio=None,  # type: AnyStr
            birthdate=None,  # type: datetime.date
            deathdate=None,  # type: datetime.date
            country=None,  # type: AnyStr
            country_code=None,  # type: AnyStr
            country_timezone=None,  # type: AnyStr
            ids=None,  # type: Dict
            homepage=None,  # type: AnyStr
            social_ids=None,  # type: Dict
            birthplace=None,  # type: AnyStr
            url=None,  # type: AnyStr
            characters=None,  # type: List[TVInfoCharacter]
            height=None,  # type: Union[integer_types, float]
            deathplace=None,  # type: AnyStr
            nicknames=None,  # type: Set[AnyStr]
            real_name=None,  # type: AnyStr
            akas=None,  # type: Set[AnyStr]
            **kwargs  # type: Dict
    ):  # type: (...) -> TVInfoPerson
        super(TVInfoPerson, self).__init__(
            p_id=p_id, name=name, image=image, thumb_url=thumb_url, bio=bio, gender=gender,
            birthdate=birthdate, deathdate=deathdate, country=country, images=images,
            country_code=country_code, country_timezone=country_timezone, ids=ids, **kwargs)
        self.credits = []  # type: List
        self.homepage = homepage  # type: Optional[AnyStr]
        self.social_ids = social_ids or {}  # type: Dict
        self.birthplace = birthplace  # type: Optional[AnyStr]
        self.deathplace = deathplace  # type: Optional[AnyStr]
        self.nicknames = nicknames or set()  # type: Set[AnyStr]
        self.real_name = real_name  # type: AnyStr
        self.url = url  # type: Optional[AnyStr]
        self.height = height  # type: Optional[Union[integer_types, float]]
        self.akas = akas or set()  # type: Set[AnyStr]
        self.characters = characters or []  # type: List[TVInfoCharacter]

    def __str__(self):
        return '<Person "%s">' % self.name

    __repr__ = __str__


class TVInfoCharacter(PersonBase):
    def __init__(self, person=None, voice=None, plays_self=None, regular=None, show=None, start_year=None,
                 end_year=None, **kwargs):
        # type: (List[TVInfoPerson], bool, bool, bool, TVInfoShow, int, int, Dict) -> TVInfoCharacter
        super(TVInfoCharacter, self).__init__(**kwargs)
        self.person = person  # type: List[TVInfoPerson]
        self.voice = voice  # type: Optional[bool]
        self.plays_self = plays_self  # type: Optional[bool]
        self.regular = regular  # type: Optional[bool]
        self.show = show  # type: Optional[TVInfoShow]
        self.start_year = start_year  # type: Optional[integer_types]
        self.end_year = end_year  # type: Optional[integer_types]

    def __str__(self):
        pn = []
        if None is not self.person:
            for p in self.person:
                if getattr(p, 'name', None):
                    pn.append(p.name)
        return '<Character "%s%s">' % (self.name, ('', ' - (%s)' % ', '.join(pn))[bool(pn)])

    __repr__ = __str__


class RoleTypes(object):
    # Actor types
    ActorMain = 1
    ActorRecurring = 2
    ActorGuest = 3
    ActorSpecialGuest = 4
    Host = 10
    HostGuest = 11
    Presenter = 12
    PresenterGuest = 13
    Interviewer = 14
    InterviewerGuest = 15
    MusicalGuest = 16
    # Crew types (int's >= crew_limit)
    CrewDirector = 50
    CrewWriter = 51
    CrewProducer = 52
    CrewExecutiveProducer = 53
    CrewCreator = 60
    CrewEditor = 61
    CrewCamera = 62
    CrewMusic = 63
    CrewStylist = 64
    CrewMakeup = 65
    CrewPhotography = 66
    CrewSound = 67
    CrewDesigner = 68
    CrewDeveloper = 69
    CrewAnimation = 70
    CrewVisualEffects = 71
    CrewShowrunner = 72
    CrewOther = 100

    reverse = {1: 'Main', 2: 'Recurring', 3: 'Guest', 4: 'Special Guest', 50: 'Director', 51: 'Writer', 52: 'Producer',
               53: 'Executive Producer', 60: 'Creator', 61: 'Editor', 62: 'Camera', 63: 'Music', 64: 'Stylist',
               65: 'Makeup', 66: 'Photography', 67: 'Sound', 68: 'Designer', 69: 'Developer', 70: 'Animation',
               71: 'Visual Effects', 100: 'Other'}
    crew_limit = 50


crew_type_names = {c.lower(): v for v, c in iteritems(RoleTypes.reverse) if v >= RoleTypes.crew_limit}


class TVInfoBase(object):
    supported_id_searches = []
    supported_person_id_searches = []
    _supported_languages = None
    map_languages = {'cs': 'ces', 'da': 'dan', 'de': 'deu', 'en': 'eng', 'es': 'spa', 'fi': 'fin', 'fr': 'fra',
                     'he': 'heb', 'hr': 'hrv', 'hu': 'hun', 'it': 'ita', 'ja': 'jpn', 'ko': 'kor', 'nb': 'nor',
                     'nl': 'nld', 'no': 'nor',
                     'pl': 'pol', 'pt': 'pot', 'ru': 'rus', 'sk': 'slv', 'sv': 'swe', 'zh': 'zho', '_1': 'srp'}
    reverse_map_languages = {v: k for k, v in iteritems(map_languages)}

    def __init__(self, banners=False, posters=False, seasons=False, seasonwides=False, fanart=False, actors=False,
                 *args, **kwargs):
        global TVInfoShowContainer
        if self.__class__.__name__ not in TVInfoShowContainer:
            TVInfoShowContainer[self.__class__.__name__] = ShowContainer()
        self.shows = TVInfoShowContainer[self.__class__.__name__]  # type: ShowContainer[integer_types, TVInfoShow]
        self.shows.cleanup_old()
        self.lang = None  # type: Optional[AnyStr]
        self.corrections = {}  # type: Dict
        self.show_not_found = False  # type: bool
        self.not_found = False  # type: bool
        self._old_config = None
        self._cachedir = kwargs.get('diskcache_dir')  # type: AnyStr
        self.diskcache = diskcache.Cache(directory=self._cachedir, disk_pickle_protocol=2)  # type: diskcache.Cache
        self.cache_expire = 60 * 60 * 18  # type: integer_types
        self.search_cache_expire = 60 * 15  # type: integer_types
        self.schedule_cache_expire = 60 * 30  # type: integer_types
        self.config = {
            'apikey': '',
            'debug_enabled': False,
            'custom_ui': None,
            'proxy': None,
            'cache_enabled': False,
            'cache_location': '',
            'valid_languages': [],
            'langabbv_to_id': {},
            'language': 'en',
            'base_url': '',
            'banners_enabled': banners,
            'posters_enabled': posters,
            'seasons_enabled': seasons,
            'seasonwides_enabled': seasonwides,
            'fanart_enabled': fanart,
            'actors_enabled': actors,
            'cache_search': kwargs.get('cache_search'),
        }  # type: Dict[AnyStr, Any]

    def _must_load_data(self, sid, load_episodes, banners, posters, seasons, seasonwides, fanart, actors):
        # type: (integer_types, bool, bool, bool, bool, bool, bool, bool) -> bool
        """
        returns if show data has to be fetched for (extra) data (episodes, images, ...)
        or can taken from self.shows cache
        :param sid: show id
        :param load_episodes: should episodes be loaded
        :param banners: should load banners
        :param posters: should load posters
        :param seasons: should load season images
        :param seasonwides: should load season wide images
        :param fanart: should load fanart
        :param actors: should load actors
        """
        if sid not in self.shows or None is self.shows[sid].id or \
                (load_episodes and not getattr(self.shows[sid], 'ep_loaded', False)):
            return True
        for data_type, en_type, p_type in [(u'poster', 'posters_enabled', posters),
                                           (u'banner', 'banners_enabled', banners),
                                           (u'fanart', 'fanart_enabled', fanart),
                                           (u'season', 'seasons_enabled', seasons),
                                           (u'seasonwide', 'seasonwides_enabled', seasonwides),
                                           (u'actors', 'actors_enabled', actors)]:
            if (p_type or self.config.get(en_type, False)) and \
                    not getattr(self.shows[sid], '%s_loaded' % data_type, False):
                return True
        return False

    def clear_cache(self):
        """
        Clear cache.
        """
        try:
            with self.diskcache as dc:
                dc.clear()
        except (BaseException, Exception):
            pass

    def clean_cache(self):
        """
        Remove expired items from cache.
        """
        try:
            with self.diskcache as dc:
                dc.expire()
        except (BaseException, Exception):
            pass

    def check_cache(self):
        """
        checks cache
        """
        try:
            with self.diskcache as dc:
                dc.check()
        except (BaseException, Exception):
            pass

    def _get_cache_entry(self, key, retry=False):
        # type: (Any, bool) -> Tuple[bool, Any]
        """
        returns tuple of is_None and value
        :param key:
        :param retry:
        """
        with self.diskcache as dc:
            try:
                v = dc.get(key)
                return 'None' == v, (v, None)['None' == v]
            except ValueError as e:
                if not retry:
                    dc.close()
                    try:
                        shutil.rmtree(self._cachedir)
                    except (BaseException, Exception) as e:
                        log.error(ex(e))
                        pass
                    try:
                        make_path(self._cachedir)
                    except (BaseException, Exception):
                        pass
                    return self._get_cache_entry(key, retry=True)
                else:
                    log.error('Error getting %s from cache: %s' % (key, ex(e)))
            except (BaseException, Exception) as e:
                log.error('Error getting %s from cache: %s' % (key, ex(e)))
        return False, None

    def _set_cache_entry(self, key, value, tag=None, expire=None):
        # type: (Any, Any, AnyStr, int) -> None
        try:
            with self.diskcache as dc:
                dc.set(key, (value, 'None')[None is value], expire=expire or self.cache_expire, tag=tag)
        except (BaseException, Exception) as e:
            log.error('Error setting %s to cache: %s' % (key, ex(e)))

    def get_person(self, p_id, get_show_credits=False, get_images=False, **kwargs):
        # type: (integer_types, bool, bool, Any) -> Optional[TVInfoPerson]
        """
        get person's data for id or list of matching persons for name

        :param p_id: persons id
        :param get_show_credits: get show credits
        :param get_images: get images for person
        :return: person object
        """
        pass

    def _search_person(self, name=None, ids=None):
        # type: (AnyStr, Dict[integer_types, integer_types]) -> List[TVInfoPerson]
        """
        search for person by name
        :param name: name to search for
        :param ids: dict of ids to search
        :return: list of found person's
        """
        return []

    def search_person(self, name=None, ids=None):
        # type: (AnyStr, Dict[integer_types, integer_types]) -> List[TVInfoPerson]
        """
        search for person by name
        :param name: name to search for
        :param ids: dict of ids to search
        :return: list of found person's
        """
        if not name and not ids:
            log.debug('Nothing to search')
            raise BaseTVinfoPersonNotFound('Nothing to search')
        found_persons = []
        if ids:
            if not any(1 for i in ids if i in self.supported_person_id_searches) and not name:
                log.debug('Id type not supported')
                raise BaseTVinfoPersonNotFound('Id type not supported')
            found_persons = self._search_person(name=name, ids=ids)
        elif name:
            found_persons = self._search_person(name=name, ids=ids)
        return found_persons

    def _get_show_data(self, sid, language, get_ep_info=False, banners=False, posters=False, seasons=False,
                       seasonwides=False, fanart=False, actors=False, **kwargs):
        # type: (integer_types, AnyStr, bool, bool, bool, bool, bool, bool, bool, Optional[Any]) -> bool
        """
        internal function that should be overwritten in class to get data for given show id
        :param sid: show id
        :param language: language
        :param get_ep_info: get episodes
        :param banners: load banners
        :param posters: load posters
        :param seasons: load seasons
        :param seasonwides: load seasonwides
        :param fanart: load fanard
        :param actors: load actors
        """
        pass

    def get_show(
            self,
            show_id,  # type: integer_types
            load_episodes=True,  # type: bool
            banners=False,  # type: bool
            posters=False,  # type: bool
            seasons=False,  # type: bool
            seasonwides=False,  # type: bool
            fanart=False,  # type: bool
            actors=False,  # type: bool
            old_call=False,  # type: bool
            language=None,  # type: AnyStr
            **kwargs  # type: Optional[Any]
    ):  # type: (...) -> Optional[TVInfoShow]
        """
        get data for show id
        :param show_id: id of show
        :param load_episodes: load episodes
        :param banners: load banners
        :param posters: load posters
        :param seasons: load season images
        :param seasonwides: load season wide images
        :param fanart: load fanart
        :param actors: load actors
        :param old_call: load legacy call
        :param language: set the request language
        :return: show object
        """
        if not old_call and None is self._old_config:
            self._old_config = self.config.copy()
            self.config.update({'banners_enabled': banners, 'posters_enabled': posters, 'seasons_enabled': seasons,
                                'seasonwides_enabled': seasonwides, 'fanart_enabled': fanart, 'actors_enabled': actors,
                                'language': language or 'en'})
        self.shows.lock.acquire()
        try:
            if show_id not in self.shows:
                self.shows[show_id] = TVInfoShow()  # type: TVInfoShow
            with self.shows[show_id].lock:
                self.shows.lock.release()
                try:
                    if self._must_load_data(show_id, load_episodes, banners, posters, seasons, seasonwides, fanart,
                                            actors):
                        self._get_show_data(show_id, self.map_languages.get(self.config['language'],
                                                                            self.config['language']),
                                            load_episodes, banners, posters, seasons, seasonwides, fanart, actors)
                        if None is self.shows[show_id].id:
                            with self.shows.lock:
                                del self.shows[show_id]
                    return None if show_id not in self.shows else copy.deepcopy(self.shows[show_id])
                finally:
                    try:
                        if None is self.shows[show_id].id:
                            with self.shows.lock:
                                del self.shows[show_id]
                    except (BaseException, Exception):
                        pass
        finally:
            try:
                self.shows.lock.release()
            except RuntimeError:
                pass
            if not old_call and None is not self._old_config:
                self.config = self._old_config
                self._old_config = None

    # noinspection PyMethodMayBeStatic
    def _search_show(self, name=None, ids=None, **kwargs):
        # type: (Union[AnyStr, List[AnyStr]], Dict[integer_types, integer_types], Optional[Any]) -> List[Dict]
        """
        internal search function to find shows, should be overwritten in class
        :param name: name to search for
        :param ids: dict of ids {tvid: prodid} to search for
        """
        return []

    @staticmethod
    def _convert_search_names(name):
        if name:
            names = ([name], name)[isinstance(name, list)]
            for i, n in enumerate(names):
                if not isinstance(n, string_types):
                    names[i] = text_type(n)
                names[i] = names[i].lower()
            return names
        return name

    def search_show(self, name=None, ids=None, **kwargs):
        # type: (Union[AnyStr, List[AnyStr]], Dict[integer_types, integer_types], Optional[Any]) -> List[Dict]
        """
        search for series with name(s) or ids

        :param name: series name or list of names to search for
        :param ids: dict of ids {tvid: prodid} to search for
        :return: combined list of series results
        """
        if not name and not ids:
            log.debug('Nothing to search')
            raise BaseTVinfoShownotfound('Nothing to search')
        name, selected_series = self._convert_search_names(name), []
        if ids:
            if not name and not any(1 for i in ids if i in self.supported_id_searches):
                log.debug('Id type not supported')
                raise BaseTVinfoShownotfound('Id type not supported')
            selected_series = self._search_show(name=name, ids=ids)
        elif name:
            selected_series = self._search_show(name)
        if isinstance(selected_series, dict):
            selected_series = [selected_series]
        if not isinstance(selected_series, list) or 0 == len(selected_series):
            log.debug('Series result returned zero')
            raise BaseTVinfoShownotfound('Show-name search returned zero results (cannot find show on TVDB)')
        return selected_series

    def _set_item(self, sid, seas, ep, attrib, value):
        # type: (integer_types, integer_types, integer_types, integer_types, Any, Any) -> None
        """Creates a new episode, creating Show(), Season() and
        Episode()s as required. Called by _get_show_data to populate show

        Since the nice-to-use tvinfo[1][24]['name] interface
        makes it impossible to do tvinfo[1][24]['name] = "name"
        and still be capable of checking if an episode exists
        so we can raise tvinfo_shownotfound, we have a slightly
        less pretty method of setting items.. but since the API
        is supposed to be read-only, this is the best way to
        do it!
        The problem is that calling tvinfo[1][24]['episodename'] = "name"
        calls __getitem__ on tvinfo[1], there is no way to check if
        tvinfo.__dict__ should have a key "1" before we auto-create it
        """
        # if sid not in self.shows:
        #     self.shows[sid] = TVInfoShow()
        if seas not in self.shows[sid]:
            self.shows[sid][seas] = TVInfoSeason(show=self.shows[sid])
            self.shows[sid][seas].number = seas
        if ep not in self.shows[sid][seas]:
            self.shows[sid][seas][ep] = TVInfoEpisode(season=self.shows[sid][seas], show=self.shows[sid])
        if attrib not in ('cast', 'crew'):
            self.shows[sid][seas][ep][attrib] = value
        self.shows[sid][seas][ep].__dict__[attrib] = value

    def _set_show_data(self, sid, key, value, add=False):
        # type: (integer_types, Any, Any, bool) -> None
        """Sets self.shows[sid] to a new Show instance, or sets the data
        """
        # if sid not in self.shows:
        #     self.shows[sid] = TVInfoShow()
        if key not in ('cast', 'crew'):
            if add and isinstance(self.shows[sid].data, dict) and key in self.shows[sid].data:
                self.shows[sid].data[key].update(value)
            else:
                self.shows[sid].data[key] = value
            if '_banners' == key:
                p_key = 'banners'
            else:
                p_key = key
            if add and key in self.shows[sid].__dict__ and isinstance(self.shows[sid].__dict__[p_key], dict):
                self.shows[sid].__dict__[p_key].update(self.shows[sid].data[key])
            else:
                self.shows[sid].__dict__[p_key] = self.shows[sid].data[key]
        else:
            if add and key in self.shows[sid].__dict__ and isinstance(self.shows[sid].__dict__[key], dict):
                self.shows[sid].__dict__[key].update(value)
            else:
                self.shows[sid].__dict__[key] = value

    def get_updated_shows(self):
        # type: (...) -> Dict[integer_types, integer_types]
        """
        gets all ids and timestamp of updated shows
        returns dict of id: timestamp
        """
        return {}

    def get_trending(self, result_count=100, **kwargs):
        # type: (...) -> List[TVInfoShow]
        """
        get trending shows
        :param result_count:
        """
        return []

    def get_popular(self, result_count=100, **kwargs):
        # type: (...) -> List[TVInfoShow]
        """
        get all popular shows
        """
        return []

    def get_top_rated(self, result_count=100, **kwargs):
        # type: (...) -> List[TVInfoShow]
        """
        get all latest shows
        """
        return []

    def discover(self, result_count=100, get_extra_images=False, **kwargs):
        # type: (...) -> List[TVInfoEpisode]
        return []

    def get_premieres(self, **kwargs):
        # type: (...) -> List[TVInfoEpisode]
        """
        get all premiering shows
        """
        return []

    def get_returning(self, **kwargs):
        # type: (...) -> List[TVInfoShow]
        """
        get all returning shows
        """
        return []

    def __getitem__(self, item):
        # type: (Union[AnyStr, integer_types, Tuple[integer_types, bool]]) -> Union[TVInfoShow, List[Dict], None]
        """Legacy handler (use get_show or search_show instead)
        Handles class_instance['seriesname'] calls.
        The dict index should be the show id
        """
        arg = None
        if isinstance(item, tuple) and 2 == len(item):
            item, arg = item
            if not isinstance(arg, bool):
                arg = None

        if isinstance(item, integer_types):
            # Item is integer, treat as show id
            return self.get_show(item, (True, arg)[None is not arg], old_call=True)

        # maybe adding this to make callee use showname so that i can bring in the new endpoint
        if isinstance(arg, string_types) and 'Tvdb' == self.__class__.__name__:
            return self.search_show(item)

        return self.search_show(item)

    # noinspection PyMethodMayBeStatic
    def search(self, series):
        # type: (AnyStr) -> List
        """This searches for the series name
        and returns the result list
        """
        return []

    @staticmethod
    def _which_type(img_width, img_ratio):
        # type: (integer_types, Union[integer_types, float]) -> Optional[int]
        """

        :param img_width:
        :param img_ratio:
        """

        msg_success = 'Treating image as %s with extracted aspect ratio'
        # most posters are around 0.68 width/height ratio (eg. 680/1000)
        if 0.55 <= img_ratio <= 0.8:
            log.debug(msg_success % 'poster')
            return TVInfoImageType.poster

        # most banners are around 5.4 width/height ratio (eg. 758/140)
        if 5 <= img_ratio <= 6:
            log.debug(msg_success % 'banner')
            return TVInfoImageType.banner

        # most fan art are around 1.7 width/height ratio (eg. 1280/720 or 1920/1080)
        if 1.7 <= img_ratio <= 1.8:
            if 500 < img_width:
                log.debug(msg_success % 'fanart')
                return TVInfoImageType.fanart

            log.warning(u'Skipped image with fanart aspect ratio but less than 500 pixels wide')
        else:
            log.warning(u'Skipped image with useless ratio %s' % img_ratio)

    def _get_languages(self):
        # type: (...) -> None
        """
        overwrite in class to create the language lists
        """
        pass

    def get_languages(self):
        # type: (...) -> List[Dict]
        """
        get all supported languages as list of dicts
        [{'id': 'lang code', 'name': 'english name', 'nativeName': 'native name', 'sg_lang': 'sg lang code'}]
        """
        if None is self._supported_languages:
            self._get_languages()
        return self._supported_languages

    def __str__(self):
        return '<TVInfo(%s) (containing: %s)>' % (self.__class__.__name__, text_type(self.shows))

    __repr__ = __str__
