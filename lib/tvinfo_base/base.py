import copy
import datetime
import logging
import threading
import time
from six import integer_types, iteritems, iterkeys, string_types, text_type
from _23 import list_items, list_values
from .exceptions import *

# noinspection PyUnreachableCode
if False:
    from typing import Any, AnyStr, Dict, List, Optional, Tuple, Union

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

    def __repr__(self):
        return self.__str__()


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
        self.ids = {}  # type: Dict[AnyStr, Optional[integer_types, AnyStr]]
        self.slug = None  # type: Optional[AnyStr]
        self.seriesid = None  # type: integer_types
        self.seriesname = None  # type: Optional[AnyStr]
        self.aliases = []  # type: List[AnyStr]
        self.season = None  # type: integer_types
        self.classification = None  # type: Optional[AnyStr]
        self.genre = None  # type: Optional[AnyStr]
        self.genre_list = []  # type: List[AnyStr]
        self.actors = []  # type: List[Dict]
        self.cast = CastList()  # type: Dict[integer_types, Character]
        self.show_type = []  # type: List[AnyStr]
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
        self.firstaired = None  # type: Optional[AnyStr]
        self.added = None  # type: Optional[AnyStr]
        self.addedby = None  # type: Union[integer_types, AnyStr]
        self.siteratingcount = None  # type: integer_types
        self.slug = None  # type: Optional[AnyStr]
        self.lastupdated = None  # type: integer_types
        self.contentrating = None  # type: Optional[AnyStr]
        self.rating = None  # type: integer_types
        self.status = None  # type: Optional[AnyStr]
        self.overview = None  # type: Optional[AnyStr]
        self.poster = None  # type: Optional[AnyStr]
        self.poster_thumb = None  # type: Optional[AnyStr]
        self.banner = None  # type: Optional[AnyStr]
        self.banner_thumb = None  # type: Optional[AnyStr]
        self.fanart = None  # type: Optional[AnyStr]
        self.banners = []  # type: Union[List, Dict]

    def __str__(self):
        nr_seasons = len(self)
        return '<Show %r (containing %s season%s)>' % (self.seriesname, nr_seasons, ('s', '')[1 == nr_seasons])

    def __repr__(self):
        return self.__str__()

    def __getattr__(self, key):
        if key in self:
            # Key is an episode, return it
            return self[key]

        if key in self.data:
            # Non-numeric request is for show-data
            return self.data[key]

        raise AttributeError

    def __getitem__(self, key):
        if key in self:
            # Key is an episode, return it
            return dict.__getitem__(self, key)

        if key in self.data:
            # Non-numeric request is for show-data
            return dict.__getitem__(self.data, key)

        # Data wasn't found, raise appropriate error
        if isinstance(key, integer_types) or isinstance(key, string_types) and key.isdigit():
            # Episode number x was not found
            raise BaseTVinfoSeasonnotfound('Could not find season %s' % (repr(key)))
        else:
            # If it's not numeric, it must be an attribute name, which
            # doesn't exist, so attribute error.
            raise BaseTVinfoAttributenotfound('Cannot find attribute %s' % (repr(key)))

    def __deepcopy__(self, memo):
        cls = self.__class__
        result = cls.__new__(cls)
        memo[id(self)] = result
        for k, v in self.__dict__.items():
            if 'lock' != k:
                setattr(result, k, copy.deepcopy(v, memo))
        for k, v in self.items():
            result[k] = copy.deepcopy(v)
            if isinstance(k, integer_types):
                setattr(result[k], 'show', result)
        return result

    def __nonzero__(self):
        return any(self.data.keys())

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
        self.cast = CastList()  # type: Dict[integer_types, Character]
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

    def __str__(self):
        nr_episodes = len(self)
        return '<Season %s instance (containing %s episode%s)>' % \
               (self.number, nr_episodes, ('s', '')[1 == nr_episodes])

    def __repr__(self):
        return self.__str__()

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
            if 'show' != k:
                setattr(result, k, copy.deepcopy(v, memo))
        for k, v in self.items():
            result[k] = copy.deepcopy(v)
            if isinstance(k, integer_types):
                setattr(result[k], 'season', result)
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


class TVInfoEpisode(dict):
    def __init__(self, season=None, **kwargs):
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
        self.cast = CastList()  # type: Dict[integer_types, Character]
        self.directors = []  # type: List[AnyStr]
        self.writer = None  # type: Optional[AnyStr]
        self.writers = []  # type: List[AnyStr]
        self.crew = CrewList()  # type: Dict[integer_types, Person]
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
        self.airtime = None  # type: Optional[AnyStr]
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

    def __str__(self):
        seasno, epno = int(getattr(self, 'seasonnumber', 0)), int(getattr(self, 'episodenumber', 0))
        epname = getattr(self, 'episodename', '')
        if None is not epname:
            return '<Episode %02dx%02d - %r>' % (seasno, epno, epname)
        else:
            return '<Episode %02dx%02d>' % (seasno, epno)

    def __repr__(self):
        return self.__str__()

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
            if 'season' != k:
                setattr(result, k, copy.deepcopy(v, memo))
        for k, v in self.items():
            result[k] = copy.deepcopy(v)
        return result

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


class Persons(dict):
    """Holds all Persons instances for a show
    """
    def __str__(self):
        persons_count = len(self)
        return '<Persons (containing %s Person%s)>' % (persons_count, ('', 's')[1 != persons_count])

    def __repr__(self):
        return self.__str__()


class CastList(Persons):
    def __init__(self, **kwargs):
        super(CastList, self).__init__(**kwargs)
        for t in iterkeys(RoleTypes.reverse):
            if t < RoleTypes.crew_limit:
                self[t] = []  # type: List[Character]

    def __str__(self):
        persons_count = []
        for t in iterkeys(RoleTypes.reverse):
            if t < RoleTypes.crew_limit:
                if len(self.get(t, [])):
                    persons_count.append('%s: %s' % (RoleTypes.reverse[t], len(self.get(t, []))))
        persons_text = ', '.join(persons_count)
        persons_text = ('0', '(%s)' % persons_text)['' != persons_text]
        return '<Cast (containing %s Person%s)>' % (persons_text, ('', 's')['' != persons_text])

    def __repr__(self):
        return self.__str__()


class CrewList(Persons):
    def __init__(self, **kwargs):
        super(CrewList, self).__init__(**kwargs)
        for t in iterkeys(RoleTypes.reverse):
            if t >= RoleTypes.crew_limit:
                self[t] = []  # type: List[Person]

    def __str__(self):
        persons_count = []
        for t in iterkeys(RoleTypes.reverse):
            if t >= RoleTypes.crew_limit:
                if len(self.get(t, [])):
                    persons_count.append('%s: %s' % (RoleTypes.reverse[t], len(self.get(t, []))))
        persons_text = ', '.join(persons_count)
        persons_text = ('0', '(%s)' % persons_text)['' != persons_text]
        return '<Crew (containing %s Person%s)>' % (persons_text, ('', 's')['' != persons_text])

    def __repr__(self):
        return self.__str__()


class PersonBase(dict):
    """Represents a single person. Should contain..

    id,
    image,
    name,
    role,
    sortorder
    """

    def __init__(self, p_id=None, name=None, image=None, gender=None, bio=None, birthdate=None, deathdate=None,
                 country=None, country_code=None, country_timezone=None, **kwargs):
        super(PersonBase, self).__init__(**kwargs)
        self.id = p_id  # type: Optional[integer_types]
        self.name = name  # type: Optional[AnyStr]
        self.image = image  # type: Optional[AnyStr]
        self.gender = gender  # type: Optional[int]
        self.bio = bio  # type: Optional[AnyStr]
        self.birthdate = birthdate  # type: Optional[datetime.date]
        self.deathdate = deathdate  # type: Optional[datetime.date]
        self.country = country  # type: Optional[AnyStr]
        self.country_code = country_code  # type: Optional[AnyStr]
        self.country_timezone = country_timezone  # type: Optional[AnyStr]

    def calc_age(self, date=None):
        # type: (Optional[datetime.date]) -> Optional[int]
        if isinstance(self.birthdate, datetime.date):
            today = (datetime.date.today(), date)[isinstance(date, datetime.date)]
            today = (today, self.deathdate)[isinstance(self.deathdate, datetime.date) and today > self.deathdate]
            try:
                birthday = self.birthdate.replace(year=today.year)

            # raised when birth date is February 29
            # and the current year is not a leap year
            except ValueError:
                birthday = self.birthdate.replace(year=today.year,
                                                  month=self.birthdate.month + 1, day=1)

            if birthday > today:
                return today.year - birthday.year - 1
            else:
                return today.year - birthday.year

    @property
    def age(self):
        # type: (...) -> Optional[int]
        """
        :return: age of person if birthdate is known, in case of deathdate is known return age of death
        """
        return self.calc_age()

    def __str__(self):
        return '<Person "%s">' % self.name

    def __repr__(self):
        return self.__str__()


class PersonGenders(object):
    male = 1
    female = 2

    reverse = {1: 'Male', 2: 'Female'}


class Person(PersonBase):
    def __init__(self, p_id=None, name=None, image=None, gender=None, bio=None, birthdate=None, deathdate=None,
                 country=None, country_code=None, country_timezone=None, **kwargs):
        super(Person, self).__init__(p_id=p_id, name=name, image=image, gender=gender, bio=bio, birthdate=birthdate,
                                     deathdate=deathdate, country=country, country_code=country_code,
                                     country_timezone=country_timezone, **kwargs)
        self.credits = []  # type: List

    def __str__(self):
        return '<Person "%s">' % self.name

    def __repr__(self):
        return self.__str__()


class Character(PersonBase):
    def __init__(self, person=None, voice=None, plays_self=None, **kwargs):
        super(Character, self).__init__(**kwargs)
        self.person = person  # type: Optional[Person]
        self.voice = voice  # type: Optional[bool]
        self.plays_self = plays_self  # type: Optional[bool]

    def __str__(self):
        pn = ''
        if None is not self.person and getattr(self.person, 'name', None):
            pn = ' - (%s)' % getattr(self.person, 'name', '')
        return '<Character "%s%s">' % (self.name, pn)

    def __repr__(self):
        return self.__str__()


class RoleTypes(object):
    # Actor types
    ActorMain = 1
    ActorRecurring = 2
    ActorGuest = 3
    ActorSpecialGuest = 4
    # Crew types (int's >= crew_limit)
    CrewDirector = 50
    CrewWriter = 51
    CrewProducer = 52

    reverse = {1: 'Main', 2: 'Recurring', 3: 'Guest', 4: 'Special Guest', 50: 'Director', 51: 'Writer', 52: 'Producer'}
    crew_limit = 50


class TVInfoBase(object):
    def __init__(self, *args, **kwargs):
        global TVInfoShowContainer
        if self.__class__.__name__ not in TVInfoShowContainer:
            TVInfoShowContainer[self.__class__.__name__] = ShowContainer()
        self.shows = TVInfoShowContainer[self.__class__.__name__]  # type: ShowContainer
        self.shows.cleanup_old()
        self.lang = None  # type: Optional[AnyStr]
        self.corrections = {}  # type: Dict
        self.show_not_found = False  # type: bool
        self.not_found = False  # type: bool
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
            'banners_enabled': False,
            'posters_enabled': False,
            'seasons_enabled': False,
            'seasonwides_enabled': False,
            'fanart_enabled': False,
            'actors_enabled': False,
        }  # type: Dict[AnyStr, Any]

    def _must_load_data(self, sid, load_episodes):
        # type: (integer_types, bool) -> bool
        """
        returns if show data has to be fetched for (extra) data (episodes, images, ...)
        or can taken from self.shows cache
        :param sid: show id
        :param load_episodes: should episodes be loaded
        """
        if sid not in self.shows or None is self.shows[sid].id or \
                (load_episodes and not getattr(self.shows[sid], 'ep_loaded', False)):
            return True
        for data_type, en_type in [(u'poster', 'posters_enabled'), (u'banner', 'banners_enabled'),
                                   (u'fanart', 'fanart_enabled'), (u'season', 'seasons_enabled'),
                                   (u'seasonwide', 'seasonwides_enabled'), (u'actors', 'actors_enabled')]:
            if self.config.get(en_type, False) and not getattr(self.shows[sid], '%s_loaded' % data_type, False):
                return True
        return False

    def get_person(self, p_id, **kwargs):
        # type: (integer_types, Optional[Any]) -> Optional[Person]
        """
        get person's data
        :param p_id: persons id
        :return: person object
        """
        pass

    def search_person(self, name):
        # type: (AnyStr) -> List[Person]
        """
        search for person by name
        :param name: name to search for
        :return: list of found person's
        """
        pass

    def _get_show_data(self, sid, language, get_ep_info=False, **kwargs):
        # type: (integer_types, AnyStr, bool, Optional[Any]) -> bool
        """
        internal function that should be overwritten in class to get data for given show id
        :param sid: show id
        :param language: language
        :param get_ep_info: get episodes
        """
        pass

    def get_show(self, show_id, load_episodes=True, **kwargs):
        # type: (integer_types, bool, Optional[Any]) -> Optional[TVInfoShow]
        """
        get data for show id
        :param show_id: id of show
        :param load_episodes: load episodes
        :return: show object
        """
        self.shows.lock.acquire()
        try:
            if show_id not in self.shows:
                self.shows[show_id] = TVInfoShow()  # type: TVInfoShow
            with self.shows[show_id].lock:
                self.shows.lock.release()
                try:
                    if self._must_load_data(show_id, load_episodes):
                        self._get_show_data(show_id, self.config['language'], load_episodes)
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

    # noinspection PyMethodMayBeStatic
    def _search_show(self, name, **kwargs):
        # type: (AnyStr, Optional[Any]) -> List[Dict]
        """
        internal search function to find shows, should be overwritten in class
        :param name: name to search for
        """
        return []

    def search_show(self, name, **kwargs):
        # type: (AnyStr, Optional[Any]) -> List[Dict]
        """
        search for series with name
        :param name: series name to search for
        :return: list of series
        """
        if not isinstance(name, string_types):
            name = text_type(name)
        name = name.lower()
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
            self.shows[sid][seas][ep] = TVInfoEpisode(season=self.shows[sid][seas])
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
            return self.get_show(item, (True, arg)[None is not arg])

        return self.search_show(item)

    # noinspection PyMethodMayBeStatic
    def search(self, series):
        # type: (AnyStr) -> List
        """This searches for the series name
        and returns the result list
        """
        return []

    def __str__(self):
        return '<TVInfo(%s) (containing: %s)>' % (self.__class__.__name__, text_type(self.shows))

    def __repr__(self):
        return self.__str__()
