from __future__ import unicode_literals

import re
import six
from datetime import datetime
import requests
from requests.packages.urllib3.util.retry import Retry
from requests.adapters import HTTPAdapter
from . import endpoints, logger
from .exceptions import *

# noinspection PyUnreachableCode
if False:
    from typing import AnyStr, Dict, List, Optional
    from six import integer_types


class Show(object):
    def __init__(self, data):
        self.status = data.get('status')  # type: Optional[AnyStr]
        self.rating = data.get('rating')  # type: Optional[integer_types]
        self.genres = data.get('genres')  # type: Optional[List[AnyStr]]
        self.weight = data.get('weight')  # type: Optional[integer_types]
        self.updated = data.get('updated')
        self.name = data.get('name')  # type: Optional[AnyStr]
        self.language = data.get('language')  # type: Optional[AnyStr]
        self.schedule = data.get('schedule')
        self.url = data.get('url')  # type: Optional[AnyStr]
        self.official_site = data.get('officialSite')  # type: Optional[AnyStr]
        self.image = data.get('image')
        self.externals = data.get('externals')
        self.premiered = data.get('premiered')  # type: Optional[AnyStr]
        self.summary = _remove_tags(data.get('summary', ''))  # type: Optional[AnyStr]
        self.links = data.get('_links')
        if data.get('webChannel'):
            self.web_channel = WebChannel(data.get('webChannel'))  # type: Optional[WebChannel]
        else:
            self.web_channel = None
        self.runtime = data.get('runtime')  # type: Optional[integer_types]
        self.type = data.get('type')  # type: Optional[AnyStr]
        self.id = data.get('id')  # type: integer_types
        self.maze_id = self.id  # type: integer_types
        if data.get('network'):
            self.network = Network(data.get('network'))  # type: Optional[Network]
        else:
            self.network = None
        self.__episodes = None  # type: Optional[List[Episode]]
        self._specials_loaded = False  # type: bool
        self._seasons = None  # type: Optional[List[Season]]
        self._cast = None  # type: Optional[List[Cast]]
        self._crew = None  # type: Optional[List[Crew]]
        self._images = None  # type: Optional[List[Image]]
        self._akas = None  # type: Optional[List[AnyStr]]
        self.__nextepisode = None  # type: Optional[Episode]
        self.__previousepisode = None  # type: Optional[Episode]
        self.populate(data)

    def __repr__(self):
        if self.premiered:
            year = str(self.premiered[:4])
        else:
            year = None
        if self.web_channel:
            platform = ',show_web_channel='
            network = self.web_channel.name
        elif self.network:
            platform = ',network='
            network = self.network.name
        else:
            platform = ''
            network = ''

        return _valid_encoding('<Show(maze_id={id},name={name},year={year}{platform}{network})>'.format(
                id=self.maze_id,
                name=self.name,
                year=year,
                platform=platform,
                network=network)
        )

    def __str__(self):
        n = ''
        if self.network:
            n = ' (%s)' % self.network.name
        return _valid_encoding('%s%s [%s]' % (self.name, n, self.premiered))

    def __unicode__(self):
        n = ''
        if self.network:
            n = ' (%s)' % self.network.name
        return '%s%s (%s)' % (self.name, n, self.premiered)

    def __iter__(self):
        return iter(self.seasons.values())

    # Python 3 bool evaluation
    def __bool__(self):
        return bool(self.id)

    # Python 2 bool evaluation
    def __nonzero__(self):
        return bool(self.id)

    def __len__(self):
        return len(self.seasons)

    def __getitem__(self, item):
        try:
            return self.seasons[item]
        except KeyError:
            raise SeasonNotFound('Season {0} does not exist for show {1}.'.format(item, self.name))

    @property
    def akas(self):
        if None is self._akas:
            self._akas = show_akas(self.maze_id, raise_error=False)
        return self._akas

    @property
    def crew(self):
        if None is self._crew:
            self._crew = get_show_crew(self.maze_id, raise_error=False)
        return self._crew

    @property
    def images(self):
        if None is self._images:
            self._images = get_show_images(self.maze_id, raise_error=False)
        return self._images

    @property
    def cast(self):
        if None is self._cast:
            self._cast = show_cast(self.maze_id, raise_error=False)
        return self._cast

    @property
    def next_episode(self):
        if self.__nextepisode is None and 'nextepisode' in self.links and 'href' in self.links['nextepisode']:
            episode_id = self.links['nextepisode']['href'].rsplit('/', 1)[1]
            if episode_id.isdigit():
                self.__nextepisode = episode_by_id(episode_id, show=self, raise_error=False)
        return self.__nextepisode

    @property
    def previous_episode(self):
        if self.__previousepisode is None and 'previousepisode' in self.links\
                and 'href' in self.links['previousepisode']:
            episode_id = self.links['previousepisode']['href'].rsplit('/', 1)[1]
            if episode_id.isdigit():
                self.__previousepisode = episode_by_id(episode_id, show=self, raise_error=False)
        return self.__previousepisode

    def _set_season_numbers(self):
        seasons = show_seasons(self.maze_id, show=self, raise_error=False)
        self._seasons = dict()
        for episode in self.__episodes:
            season_num = int(episode.season_number)
            if season_num not in self._seasons:
                self._seasons[season_num] = seasons[season_num]
                self._seasons[season_num].show = self

    @property
    def seasons(self):
        if None is self._seasons:
            self.episodes
        return self._seasons

    @property
    def episodes(self):
        if None is self.__episodes or not self._specials_loaded:
            self.__episodes = episode_list(self.maze_id, specials=True, raise_error=False, show=self)
            self._specials_loaded = True
            self._set_season_numbers()
        return self.__episodes

    def populate(self, data):
        embedded = data.get('_embedded')
        if embedded:
            if embedded.get('episodes'):
                self.__episodes = []
                for episode in embedded.get('episodes'):
                    self.__episodes.append(Episode(episode, self))
                self._set_season_numbers()
            if embedded.get('cast'):
                self._cast = Cast(embedded.get('cast'))


class Season(object):
    def __init__(self, data, show=None, season_number=None):
        self.show = show
        if None is not season_number and None is not show and show.episodes:
            self.__episodes = [ep for ep in show.episodes if season_number == ep.season_number]
        else:
            self.__episodes = None
        self.id = data.get('id')
        self.url = data.get('url')
        self.season_number = data.get('number')
        self.name = data.get('name')
        self.episode_order = data.get('episodeOrder')
        self.premiere_date = data.get('premiereDate')
        self.end_date = data.get('endDate')
        if data.get('network'):
            self.network = Network(data.get('network'))
        else:
            self.network = None
        if data.get('webChannel'):
            self.web_channel = WebChannel(data.get('webChannel'))
        else:
            self.web_channel = None
        self.image = data.get('image')
        self.summary = data.get('summary')
        self.links = data.get('_links')

    def __repr__(self):
        return _valid_encoding('<Season(id={id},season_number={number})>'.format(
                id=self.id,
                number=str(self.season_number).zfill(2)
        ))

    def _get_showname(self):
        sn = ''
        if self.show:
            sn = '%s - ' % self.show.name
        return '%sSeason %02d (%s/%s)' % (sn, self.season_number, len(self.episodes), self.episode_order)

    def __unicode__(self):
        return self._get_showname()

    def __str__(self):
        return _valid_encoding(self._get_showname())

    def __iter__(self):
        return iter(self.episodes.values())

    def __len__(self):
        return len(self.episodes)

    def __getitem__(self, item):
        try:
            return self.episodes[item]
        except KeyError:
            raise EpisodeNotFound(
                    'Episode {0} does not exist for season {1} of show {2}.'.format(item, self.season_number,
                                                                                    self.show))

    # Python 3 bool evaluation
    def __bool__(self):
        return bool(self.id)

    # Python 2 bool evaluation
    def __nonzero__(self):
        return bool(self.id)

    @property
    def episodes(self):
        # type: (...) -> List[Episode]
        if None is self.__episodes or not self.show._specials_loaded:
            self.__episodes = [ep for ep in episode_list(self.show.maze_id, specials=True, raise_error=False,
                                                         show=self.show) if ep.season_number == self.season_number]
            self.show._specials_loaded = True
        return self.__episodes


class Episode(object):
    def __init__(self, data, show=None):
        self.title = data.get('name')
        self.airdate = data.get('airdate')
        self.url = data.get('url')
        self.season_number = data.get('season')
        self.episode_number = data.get('number')
        self.image = data.get('image')
        self.airstamp = data.get('airstamp')
        self.airtime = data.get('airtime')
        self.runtime = data.get('runtime')
        self.summary = _remove_tags(data.get('summary'))
        self.maze_id = data.get('id')
        self.type = data.get('type')  # type: AnyStr # ("regular", "significant_special", "insignificant_special")
        self.special = self.is_special()
        # Reference to show for when using get_schedule()
        self.show = show
        if not show:
            if data.get('show'):
                self.show = Show(data.get('show'))
            # Reference to show for when using get_full_schedule()
            if data.get('_embedded'):
                if data['_embedded'].get('show'):
                    self.show = Show(data['_embedded']['show'])

    def __repr__(self):
        if self.special:
            epnum = 'Special'
        else:
            epnum = self.episode_number
        return _valid_encoding('<Episode(season={season},episode_number={number})>'.format(
                season=str(self.season_number).zfill(2),
                number=str(epnum).zfill(2))
        )

    def _gen_ep_name(self):
        season = 'S' + str(self.season_number).zfill(2)
        if self.special:
            episode = ' Special'
        else:
            episode = 'E' + str(self.episode_number).zfill(2)
        sn = ''
        if self.show:
            sn = '%s - ' % self.show.name
        return sn + season + episode + ' ' + self.title

    def __str__(self):
        return _valid_encoding(self._gen_ep_name())

    def __unicode__(self):
        return self._gen_ep_name()

    def is_special(self):
        if self.type in ('significant_special', 'insignificant_special'):
            return True
        elif 'regular' == self.type:
            return False
        # fallback for previous api without type field
        if self.episode_number:
            return False
        return True


class Person(object):
    def __init__(self, data):
        if data.get('person'):
            data = data['person']
        self.links = data.get('_links')
        self.id = data.get('id')
        self.image = data.get('image')
        self.name = data.get('name')
        self.score = data.get('score')
        self.url = data.get('url')
        self.birthday = data.get('birthday')
        self.death_day = data.get('deathday')
        self.gender = data.get('gender')
        self.country = data.get('country')
        self.character = None
        self._castcredits = None
        self._crewcredits = None
        # self.populate(data)

    # def populate(self, data):
    #     if data.get('_embedded'):
    #         if data['_embedded'].get('castcredits'):
    #             self._castcredits = [CastCredit(credit)
    #                                 for credit in data['_embedded']['castcredits']]
    #         elif data['_embedded'].get('crewcredits'):
    #             self.crewcredits = [CrewCredit(credit)
    #                                 for credit in data['_embedded']['crewcredits']]

    @property
    def castcredits(self):
        if None is self._castcredits:
            self._castcredits = person_cast_credits(self.id, embed='show,character', raise_error=False)
        return self._castcredits

    @property
    def crewcredits(self):
        if None is self._crewcredits:
            self._crewcredits = person_crew_credits(self.id, embed='show', raise_error=False)
        return self._crewcredits

    def __repr__(self):
        return _valid_encoding('<Person(name={name},maze_id={id})>'.format(
                name=self.name,
                id=self.id
        ))

    def _gen_lifetime(self):
        l = ''
        if self.birthday:
            l = '%s' % self.birthday
        if self.death_day:
            if 0 < len(l):
                l += ' - '
            l = '%s' % self.death_day
        if 0 < len(l):
            l = ' (%s)' % l
        return l

    def __str__(self):
        return _valid_encoding('%s%s' % (self.name, self._gen_lifetime()))

    def __unicode__(self):
        return '%s%s' % (self.name, self._gen_lifetime())


class Character(object):
    def __init__(self, data, base_data=None):
        base_data = {} if None is base_data else base_data
        self.id = data.get('id')
        self.url = data.get('url')
        self.name = data.get('name')
        self.image = data.get('image')
        self.links = data.get('_links')
        self.plays_self = base_data.get('self')
        self.voice = base_data.get('voice')
        self.person = None  # type: Optional[Person]

    def __repr__(self):
        return _valid_encoding('<Character(name={name},maze_id={id})>'.format(
                name=self.name,
                id=self.id
        ))

    def _get_person(self):
        p = ''
        if self.person:
            p = ' (%s)' % self.person.name
        return p

    def __str__(self):
        return _valid_encoding('%s%s' % (self.name, self._get_person()))

    def __unicode__(self):
        return '%s%s' % (self.name, self._get_person())


class Cast(object):
    def __init__(self, data):
        self.people = []
        self.characters = []  # type: List[Character]
        self.populate(data)

    def populate(self, data):
        for cast_member in data:
            self.people.append(Person(cast_member['person']))
            self.characters.append(Character(cast_member['character'], cast_member))
            self.people[-1].character = self.characters[-1]  # add reference to character
            self.characters[-1].person = self.people[-1]  # add reference to cast member

    def __repr__(self):
        return self.__str__()

    def __str__(self):
        return _valid_encoding('%s (%s)' % (self.characters, self.people))

    def __unicode__(self):
        return '%s (%s)' % (self.characters, self.people)


class CastCredit(object):
    def __init__(self, data):
        self.links = data.get('_links')
        self.character = None
        self.show = None
        self.populate(data)

    def populate(self, data):
        if data.get('_embedded'):
            if data['_embedded'].get('character'):
                self.character = Character(data['_embedded']['character'])
            if data['_embedded'].get('show'):
                self.show = Show(data['_embedded']['show'])

    def __repr__(self):
        return self.__str__()

    def __str__(self):
        return _valid_encoding('%s (%s)' % (self.character, self.show))

    def __unicode__(self):
        return '%s (%s)' % (self.character, self.show)


class CrewCredit(object):
    def __init__(self, data):
        self.links = data.get('_links')
        self.type = data.get('type')
        self.show = None
        self.populate(data)

    def populate(self, data):
        if data.get('_embedded'):
            if data['_embedded'].get('show'):
                self.show = Show(data['_embedded']['show'])

    def __repr__(self):
        return self.__str__()

    def __str__(self):
        return _valid_encoding('%s (%s)' % (self.type, self.show))

    def __unicode__(self):
        return '%s (%s)' % (self.type, self.show)


class Crew(object):
    def __init__(self, data):
        self.person = Person(data.get('person'))
        self.type = data.get('type')

    def __unicode__(self):
        return '%s: %s' % (self.type, self.person)

    def __str__(self):
        return _valid_encoding('%s: %s' % (self.type, self.person))

    def __repr__(self):
        return _valid_encoding('<Crew(name={name},maze_id={id},type={type})>'.format(
                name=self.person.name,
                id=self.person.id,
                type=self.type
        ))


class Image(object):
    def __init__(self, data):
        self.main = data.get('main')  # type: bool
        self.type = data.get('type')  # type: AnyStr
        self.id = data.get('id')  # type: integer_types
        self.resolutions = data.get('resolutions')  # type: Dict[AnyStr, AnyStr]

    def _get_type_name(self):
        return ('unknown', self.type)[isinstance(self.type, six.string_types)]

    def _get_main_str(self):
        return ('Other', 'Main')[True is self.main]

    def __unicode__(self):
        return '%s: %s' % (self._get_type_name(), self._get_main_str())

    def __str__(self):
        return _valid_encoding('%s: %s' % (self._get_type_name(), self._get_main_str()))

    def __repr__(self):
        return _valid_encoding('<Image(main={main},maze_id={id},type={type})>'.format(
                main=self.main,
                id=self.id,
                type=self._get_type_name()
        ))


class Updates(object):
    def __init__(self, data):
        self.updates = dict()
        self.populate(data)

    def populate(self, data):
        for maze_id, time in data.items():
            self.updates[int(maze_id)] = Update(maze_id, time)

    def __getitem__(self, item):
        try:
            return self.updates[item]
        except KeyError:
            logger.error('No update found for Maze id {}.'.format(item))
            raise UpdateNotFound('No update found for Maze id {}.'.format(item))

    def __iter__(self):
        return iter(self.updates.values())


class Update(object):
    def __init__(self, maze_id, time):
        self.maze_id = int(maze_id)
        self.seconds_since_epoch = time
        self.timestamp = datetime.fromtimestamp(time)

    def __repr__(self):
        return _valid_encoding('<Update(maze_id={maze_id},time={time})>'.format(
                maze_id=self.maze_id,
                time=self.seconds_since_epoch
        ))


class AKA(object):
    def __init__(self, data):
        self.name = data.get('name')
        self.country = data.get('country')

    def __repr__(self):
        return _valid_encoding('<AKA(name={name},country={country})>'.format(name=self.name, country=self.country))

    def _get_country(self):
        c = ''
        if self.country:
            c = ' (%s)' % self.country.get('name')
        return c

    def __unicode__(self):
        return '%s%s' % (self.name, self._get_country())

    def __str__(self):
        return _valid_encoding('%s%s' % (self.name, self._get_country()))


class NetworkBase(object):
    def __init__(self, data, *args, **kwargs):
        self.name = data.get('name')
        self.maze_id = data.get('id')
        if data.get('country'):
            self.country = data['country'].get('name')
            self.timezone = data['country'].get('timezone')
            self.code = data['country'].get('code')
        else:
            self.country = None
            self.timezone = None
            self.code = None

    def _get_coutnry(self):
        c = ''
        if self.country:
            c = ' (%s)' % self.country.name
        return c

    def __unicode__(self):
        return '%s%s' % (self.name, self._get_coutnry())

    def __str__(self):
        return _valid_encoding('%s%s' % (self.name, self._get_coutnry()))


class Network(NetworkBase):
    def __init__(self, data):
        super(Network, self).__init__(data)

    def __repr__(self):
        return _valid_encoding('<Network(name={name},country={country})>'.format(name=self.name, country=self.country))


class WebChannel(NetworkBase):
    def __init__(self, data):
        super(WebChannel, self).__init__(data)

    def __repr__(self):
        return _valid_encoding('<WebChannel(name={name},country={country})>'.format(name=self.name, country=self.country))


class FollowedShow(object):
    def __init__(self, data):
        self.maze_id = data.get('show_id')
        self.show = None
        if data.get('_embedded'):
            self.show = Show(data['_embedded'].get('show'))

    def __repr__(self):
        return _valid_encoding('<FollowedShow(maze_id={})>'.format(self.maze_id))


class FollowedPerson(object):
    def __init__(self, data):
        self.person_id = data.get('person_id')
        self.person = None
        if data.get('_embedded'):
            self.person = Person(data['_embedded'].get('person'))

    def __repr__(self):
        return _valid_encoding('<FollowedPerson(person_id={id})>'.format(id=self.person_id))


class FollowedNetwork(object):
    def __init__(self, data):
        self.network_id = data.get('network_id')
        self.network = None
        if data.get('_embedded'):
            self.network = Network(data['_embedded'].get('network'))

    def __repr__(self):
        return _valid_encoding('<FollowedNetwork(network_id={id})>'.format(id=self.network_id))


class FollowedWebChannel(object):
    def __init__(self, data):
        self.web_channel_id = data.get('webchannel_id')
        self.web_channel = None
        if data.get('_embedded'):
            self.web_channel = WebChannel(data['_embedded'].get('webchannel'))

    def __repr__(self):
        return _valid_encoding('<FollowedWebChannel(web_channel_id={id})>'.format(id=self.web_channel_id))


class MarkedEpisode(object):
    def __init__(self, data):
        self.episode_id = data.get('episode_id')
        self.marked_at = data.get('marked_at')
        type_ = data.get('type')
        types = {0: 'watched', 1: 'acquired', 2: 'skipped'}
        self.type = types[type_]

    def __repr__(self):
        return _valid_encoding('<MarkedEpisode(episode_id={id},marked_at={marked_at},type={type})>'.format(
            id=self.episode_id, marked_at=self.marked_at, type=self.type))


class VotedShow(object):
    def __init__(self, data):
        self.maze_id = data.get('show_id')
        self.voted_at = data.get('voted_at')
        self.vote = data.get('vote')
        if data.get('_embedded'):
            self.show = Show(data['_embedded'].get('show'))

    def __repr__(self):
        return _valid_encoding('<VotedShow(maze_id={id},voted_at={voted_at},vote={vote})>'.format(id=self.maze_id,
                                                                                  voted_at=self.voted_at,
                                                                                  vote=self.vote))


class VotedEpisode(object):
    def __init__(self, data):
        self.episode_id = data.get('episode_id')
        self.voted_at = data.get('voted_at')
        self.vote = data.get('vote')

    def __repr__(self):
        return _valid_encoding('<VotedEpisode(episode_id={id},voted_at={voted_at},vote={vote})>'.format(id=self.episode_id,
                                                                                        voted_at=self.voted_at,
                                                                                        vote=self.vote))


def _valid_encoding(text):
    if not text:
        return
    if sys.version_info > (3,):
        return text
    else:
        return unicode(text).encode('utf-8')


def _url_quote(show):
    return requests.compat.quote(show.encode('UTF-8'))


def _remove_tags(text):
    if not text:
        return None
    return re.sub(r'<.*?>', '', text)


# noinspection PyUnusedLocal
def _record_hook(r, *args, **kwargs):
    r.hook_called = True
    if 301 == r.status_code and isinstance(r.headers.get('Location'), six.string_types) \
            and r.headers.get('Location').startswith('http://api.tvmaze'):
        r.headers['Location'] = r.headers['Location'].replace('http://', 'https://')
    return r


def _embed_url(base_url, embed, possible_embeds, glue):
    if isinstance(embed, six.string_types):
        embed_words = [em.strip() for em in embed.split(',')]
    elif None is embed:
        embed_words = []
    else:
        embed_words = None
    if None is embed_words or any(ew not in possible_embeds for ew in embed_words):
        raise InvalidEmbedValue('Value for embed must be %s' % possible_embeds)
    if embed_words:
        if 1 == len(embed_words):
            return '%s%sembed=%s' % (base_url, glue, embed_words[0])
        else:
            eu = ''
            for word in embed_words:
                eu += '%sembed[]=%s' % (glue, word)
                glue = '&'
        return '%s%s' % (base_url, eu)
    return base_url


class TVmaze(object):
    """This is the main class of the module enabling interaction with both free and Premium
    TVmaze features.

    Attributes:
        username (str): Username for http://www.tvmaze.com
        api_key (str): TVmaze api key.  Find your key at http://www.tvmaze.com/dashboard

    """

    def __init__(self, username=None, api_key=None):
        self.username = username
        self.api_key = api_key

    # Query TVmaze free endpoints
    @staticmethod
    def endpoint_standard_get(url):
        s = requests.Session()
        retries = Retry(total=5,
                        backoff_factor=0.1,
                        status_forcelist=[429])
        s.mount('http://', HTTPAdapter(max_retries=retries))
        s.mount('https://', HTTPAdapter(max_retries=retries))
        try:
            r = s.get(url, hooks={'response': _record_hook})
        except requests.exceptions.ConnectionError as e:
            logger.error(repr(e))
            raise ConnectionError(repr(e))

        s.close()

        if r.status_code in [404, 422]:
            return None

        if r.status_code == 400:
            raise BadRequest('Bad Request for url {}'.format(url))

        results = r.json()
        return results

    # Query TVmaze Premium endpoints
    def _endpoint_premium_get(self, url):
        s = requests.Session()
        retries = Retry(total=5,
                        backoff_factor=0.1,
                        status_forcelist=[429])
        s.mount('http://', HTTPAdapter(max_retries=retries))
        s.mount('https://', HTTPAdapter(max_retries=retries))
        try:
            r = s.get(url, auth=(self.username, self.api_key), hooks={'response': _record_hook})
        except requests.exceptions.ConnectionError as e:
            logger.error(repr(e))
            raise ConnectionError(repr(e))

        s.close()

        if r.status_code in [404, 422]:
            return None

        if r.status_code == 400:
            raise BadRequest('Bad Request for url {}'.format(url))

        results = r.json()
        return results

    def _endpoint_premium_delete(self, url):
        s = requests.Session()
        retries = Retry(total=5,
                        backoff_factor=0.1,
                        status_forcelist=[429])
        s.mount('http://', HTTPAdapter(max_retries=retries))
        s.mount('https://', HTTPAdapter(max_retries=retries))
        try:
            r = s.delete(url, auth=(self.username, self.api_key), hooks={'response': _record_hook})
        except requests.exceptions.ConnectionError as e:
            logger.error(repr(e))
            raise ConnectionError(repr(e))

        s.close()

        if r.status_code == 400:
            logger.error('Bad Request for url {}'.format(url))
            raise BadRequest('Bad Request for url {}'.format(url))

        if r.status_code == 200:
            return True

        if r.status_code == 404:
            return None

    def _endpoint_premium_put(self, url, payload=None):
        s = requests.Session()
        retries = Retry(total=5,
                        backoff_factor=0.1,
                        status_forcelist=[429])
        s.mount('http://', HTTPAdapter(max_retries=retries))
        s.mount('https://', HTTPAdapter(max_retries=retries))
        try:
            r = s.put(url, data=payload, auth=(self.username, self.api_key), hooks={'response': _record_hook})
        except requests.exceptions.ConnectionError as e:
            logger.error(repr(e))
            raise ConnectionError(repr(e))

        s.close()

        if r.status_code == 400:
            raise BadRequest('Bad Request for url {}'.format(url))

        if r.status_code == 200:
            return True

        if r.status_code in [404, 422]:
            return None

    # Get Show object
    def get_show(self, maze_id=None, tvdb_id=None, tvrage_id=None, imdb_id=None, show_name=None,
                 show_year=None, show_network=None, show_language=None, show_country=None,
                 show_web_channel=None, embed=None):
        # type: (...) -> Show
        """
        Get Show object directly via id or indirectly via name + optional qualifiers

        If only a show_name is given, the show with the highest score using the
        tvmaze algorithm will be returned.
        If you provide extra qualifiers such as network or language they will be
        used for a more specific match, if one exists.
        Args:
            maze_id: Show maze_id
            tvdb_id: Show tvdb_id
            tvrage_id: Show tvrage_id
            imdb_id: Show tvrage_id
            show_name: Show name to be searched
            show_year: Show premiere year
            show_network: Show TV Network (like ABC, NBC, etc.)
            show_web_channel: Show Web Channel (like Netflix, Amazon, etc.)
            show_language: Show language
            show_country: Show country
            embed: embed parameter to include additional data. Currently 'episodes' and 'cast' are supported
        """
        errors = []
        if not (maze_id or tvdb_id or tvrage_id or imdb_id or show_name):
            raise MissingParameters(
                    'Either maze_id, tvdb_id, tvrage_id, imdb_id or show_name are required to get show, none provided,')
        if maze_id:
            try:
                return show_main_info(maze_id, embed=embed)
            except IDNotFound as e:
                errors.append(e.value)
        if tvdb_id:
            try:
                return show_main_info(lookup_tvdb(tvdb_id).id, embed=embed)
            except IDNotFound as e:
                errors.append(e.value)
        if tvrage_id:
            try:
                return show_main_info(lookup_tvrage(tvrage_id).id, embed=embed)
            except IDNotFound as e:
                errors.append(e.value)
        if imdb_id:
            try:
                return show_main_info(lookup_imdb(imdb_id).id, embed=embed)
            except IDNotFound as e:
                errors.append(e.value)
        if show_name:
            try:
                show = self._get_show_by_search(show_name, show_year, show_network, show_language,
                                                show_country, show_web_channel, embed=embed)
                return show
            except ShowNotFound as e:
                errors.append(e.value)
        raise ShowNotFound(' ,'.join(errors))

    @staticmethod
    def _get_show_with_qualifiers(show_name, qualifiers):
        shows = get_show_list(show_name)
        best_match = -1  # Initialize match value score
        show_match = None

        for show in shows:
            if show.premiered:
                premiered = show.premiered[:-6].lower()
            else:
                premiered = None
            if show.network and show.network.name:
                network = show.network.name.lower()
            else:
                network = None
            if show.web_channel and show.web_channel.name:
                web_channel = show.web_channel.name.lower()
            else:
                web_channel = None
            if show.network and show.network.code:
                country = show.network.code.lower()
            else:
                if show.web_channel and show.web_channel.code:
                    country = show.web_channel.code.lower()
                else:
                    country = None
            if show.language:
                language = show.language.lower()
            else:
                language = None

            attributes = [premiered, country, network, language, web_channel]
            show_score = len(set(qualifiers) & set(attributes))
            if show_score > best_match:
                best_match = show_score
                show_match = show
        return show_match

    # Search with user-defined qualifiers, used by get_show() method
    def _get_show_by_search(self, show_name, show_year, show_network, show_language, show_country,
                            show_web_channel, embed):
        if show_year:
            show_year = str(show_year)
        qualifiers = list(filter(None, [show_year, show_network, show_language, show_country, show_web_channel]))
        if qualifiers:
            qualifiers = [q.lower() for q in qualifiers if q]
            show = self._get_show_with_qualifiers(show_name, qualifiers)
        else:
            return show_single_search(show=show_name, embed=embed)
        if embed:
            return show_main_info(maze_id=show.id, embed=embed)
        else:
            return show

    # TVmaze Premium Endpoints
    # NOT DONE OR TESTED
    def get_followed_shows(self, embed=None):
        if embed not in [None, 'show']:
            raise InvalidEmbedValue('Value for embed must be "show" or None')
        url = endpoints.followed_shows.format('/')
        if embed == 'show':
            url = endpoints.followed_shows.format('?embed=show')

        q = self._endpoint_premium_get(url)
        if q:
            return [FollowedShow(show) for show in q]
        else:
            raise NoFollowedShows('You have not followed any shows yet')

    def get_followed_show(self, maze_id):
        url = endpoints.followed_shows.format('/' + str(maze_id))
        q = self._endpoint_premium_get(url)
        if q:
            return FollowedShow(q)
        else:
            raise ShowNotFollowed('Show with ID {} is not followed'.format(maze_id))

    def follow_show(self, maze_id):
        url = endpoints.followed_shows.format('/' + str(maze_id))
        q = self._endpoint_premium_put(url)
        if not q:
            raise ShowNotFound('Show with ID {} does not exist'.format(maze_id))

    def unfollow_show(self, maze_id):
        url = endpoints.followed_shows.format('/' + str(maze_id))
        q = self._endpoint_premium_delete(url)
        if not q:
            raise ShowNotFollowed('Show with ID {} was not followed'.format(maze_id))

    def get_followed_people(self, embed=None):
        if embed not in [None, 'person']:
            raise InvalidEmbedValue('Value for embed must be "person" or None')
        url = endpoints.followed_people.format('/')
        if embed == 'person':
            url = endpoints.followed_people.format('?embed=person')
        q = self._endpoint_premium_get(url)
        if q:
            return [FollowedPerson(person) for person in q]
        else:
            raise NoFollowedPeople('You have not followed any people yet')

    def get_followed_person(self, person_id):
        url = endpoints.followed_people.format('/' + str(person_id))
        q = self._endpoint_premium_get(url)
        if q:
            return FollowedPerson(q)
        else:
            raise PersonNotFound('Person with ID {} is not followed'.format(person_id))

    def follow_person(self, person_id):
        url = endpoints.followed_people.format('/' + str(person_id))
        q = self._endpoint_premium_put(url)
        if not q:
            raise PersonNotFound('Person with ID {} does not exist'.format(person_id))

    def unfollow_person(self, person_id):
        url = endpoints.followed_people.format('/' + str(person_id))
        q = self._endpoint_premium_delete(url)
        if not q:
            raise PersonNotFollowed('Person with ID {} was not followed'.format(person_id))

    def get_followed_networks(self, embed=None):
        if embed not in [None, 'network']:
            raise InvalidEmbedValue('Value for embed must be "network" or None')
        url = endpoints.followed_networks.format('/')
        if embed == 'network':
            url = endpoints.followed_networks.format('?embed=network')
        q = self._endpoint_premium_get(url)
        if q:
            return [FollowedNetwork(network) for network in q]
        else:
            raise NoFollowedNetworks('You have not followed any networks yet')

    def get_followed_network(self, network_id):
        url = endpoints.followed_networks.format('/' + str(network_id))
        q = self._endpoint_premium_get(url)
        if q:
            return FollowedNetwork(q)
        else:
            raise NetworkNotFound('Network with ID {} is not followed'.format(network_id))

    def follow_network(self, network_id):
        url = endpoints.followed_networks.format('/' + str(network_id))
        q = self._endpoint_premium_put(url)
        if not q:
            raise NetworkNotFound('Network with ID {} does not exist'.format(network_id))

    def unfollow_network(self, network_id):
        url = endpoints.followed_networks.format('/' + str(network_id))
        q = self._endpoint_premium_delete(url)
        if not q:
            raise NetworkNotFollowed('Network with ID {} was not followed'.format(network_id))

    def get_followed_web_channels(self, embed=None):
        if embed not in [None, 'webchannel']:
            raise InvalidEmbedValue('Value for embed must be "webchannel" or None')
        url = endpoints.followed_web_channels.format('/')
        if embed == 'webchannel':
            url = endpoints.followed_web_channels.format('?embed=webchannel')
        q = self._endpoint_premium_get(url)
        if q:
            return [FollowedWebChannel(webchannel) for webchannel in q]
        else:
            raise NoFollowedWebChannels('You have not followed any Web Channels yet')

    def get_followed_web_channel(self, webchannel_id):
        url = endpoints.followed_web_channels.format('/' + str(webchannel_id))
        q = self._endpoint_premium_get(url)
        if q:
            return FollowedWebChannel(q)
        else:
            raise NetworkNotFound('Web Channel with ID {} is not followed'.format(webchannel_id))

    def follow_web_channel(self, webchannel_id):
        url = endpoints.followed_web_channels.format('/' + str(webchannel_id))
        q = self._endpoint_premium_put(url)
        if not q:
            raise WebChannelNotFound('Web Channel with ID {} does not exist'.format(webchannel_id))

    def unfollow_web_channel(self, webchannel_id):
        url = endpoints.followed_web_channels.format('/' + str(webchannel_id))
        q = self._endpoint_premium_delete(url)
        if not q:
            raise WebChannelNotFollowed('Web Channel with ID {} was not followed'.format(webchannel_id))

    def get_marked_episodes(self, maze_id=None):
        if not maze_id:
            url = endpoints.marked_episodes.format('/')
        else:
            show_id = '?show_id={}'.format(maze_id)
            url = endpoints.marked_episodes.format(show_id)
        q = self._endpoint_premium_get(url)
        if q:
            return [MarkedEpisode(episode) for episode in q]
        else:
            raise NoMarkedEpisodes('You have not marked any episodes yet')

    def get_marked_episode(self, episode_id):
        path = '/{}'.format(episode_id)
        url = endpoints.marked_episodes.format(path)
        q = self._endpoint_premium_get(url)
        if q:
            return MarkedEpisode(q)
        else:
            raise EpisodeNotMarked('Episode with ID {} is not marked'.format(episode_id))

    def mark_episode(self, episode_id, mark_type):
        types = {'watched': 0, 'acquired': 1, 'skipped': 2}
        try:
            status = types[mark_type]
        except IndexError:
            raise InvalidMarkedEpisodeType('Episode must be marked as "watched", "acquired", or "skipped"')
        payload = {'type': str(status)}
        path = '/{}'.format(episode_id)
        url = endpoints.marked_episodes.format(path)
        q = self._endpoint_premium_put(url, payload=payload)
        if not q:
            raise EpisodeNotFound('Episode with ID {} does not exist'.format(episode_id))

    def unmark_episode(self, episode_id):
        path = '/{}'.format(episode_id)
        url = endpoints.marked_episodes.format(path)
        q = self._endpoint_premium_delete(url)
        if not q:
            raise EpisodeNotMarked('Episode with ID {} was not marked'.format(episode_id))

    def get_voted_shows(self, embed=None):
        if embed not in [None, 'show']:
            raise InvalidEmbedValue('Value for embed must be "show" or None')
        url = endpoints.voted_shows.format('/')
        if embed == 'show':
            url = endpoints.voted_shows.format('?embed=show')
        q = self._endpoint_premium_get(url)
        if q:
            return [VotedShow(show) for show in q]
        else:
            raise NoVotedShows('You have not voted for any shows yet')

    def get_voted_show(self, maze_id):
        url = endpoints.voted_shows.format('/' + str(maze_id))
        q = self._endpoint_premium_get(url)
        if q:
            return VotedShow(q)
        else:
            raise ShowNotVotedFor('Show with ID {} not voted for'.format(maze_id))

    def remove_show_vote(self, maze_id):
        url = endpoints.voted_shows.format('/' + str(maze_id))
        q = self._endpoint_premium_delete(url)
        if not q:
            raise ShowNotVotedFor('Show with ID {} was not voted for'.format(maze_id))

    def vote_show(self, maze_id, vote):
        if not 1 <= vote <= 10:
            raise InvalidVoteValue('Vote must be an integer between 1 and 10')
        payload = {'vote': int(vote)}
        url = endpoints.voted_shows.format('/' + str(maze_id))
        q = self._endpoint_premium_put(url, payload=payload)
        if not q:
            raise ShowNotFound('Show with ID {} does not exist'.format(maze_id))

    def get_voted_episodes(self):
        url = endpoints.voted_episodes.format('/')
        q = self._endpoint_premium_get(url)
        if q:
            return [VotedEpisode(episode) for episode in q]
        else:
            raise NoVotedEpisodes('You have not voted for any episodes yet')

    def get_voted_episode(self, episode_id):
        path = '/{}'.format(episode_id)
        url = endpoints.voted_episodes.format(path)
        q = self._endpoint_premium_get(url)
        if q:
            return VotedEpisode(q)
        else:
            raise EpisodeNotVotedFor('Episode with ID {} not voted for'.format(episode_id))

    def remove_episode_vote(self, episode_id):
        path = '/{}'.format(episode_id)
        url = endpoints.voted_episodes.format(path)
        q = self._endpoint_premium_delete(url)
        if not q:
            raise EpisodeNotVotedFor('Episode with ID {} was not voted for'.format(episode_id))

    def vote_episode(self, episode_id, vote):
        if not 1 <= vote <= 10:
            raise InvalidVoteValue('Vote must be an integer between 1 and 10')
        payload = {'vote': int(vote)}
        path = '/{}'.format(episode_id)
        url = endpoints.voted_episodes.format(path)
        q = self._endpoint_premium_put(url, payload=payload)
        if not q:
            raise EpisodeNotFound('Episode with ID {} does not exist'.format(episode_id))


# Return list of Show objects
def get_show_list(show_name):
    """
    Return list of Show objects from the TVmaze "Show Search" endpoint

    List will be ordered by tvmaze score and should mimic the results you see
    by doing a show search on the website.
    :param show_name: Name of show
    :return: List of Show(s)
    """
    shows = show_search(show_name)
    return shows


# Get list of Person objects
def get_people(name):
    """
    Return list of Person objects from the TVmaze "People Search" endpoint
    :param name: Name of person
    :return: List of Person(s)
    """
    people = people_search(name)
    if people:
        return people


def show_search(show):
    _show = _url_quote(show)
    url = endpoints.show_search.format(_show)
    q = TVmaze.endpoint_standard_get(url)
    if q:
        shows = []
        for result in q:
            show = Show(result['show'])
            show.score = result['score']
            shows.append(show)
        return shows
    else:
        raise ShowNotFound('Show {0} not found'.format(show))


def show_single_search(show, embed=None):
    _show = _url_quote(show)
    url = _embed_url(endpoints.show_single_search.format(_show), embed,
                     [None, 'episodes', 'cast', 'previousepisode', 'nextepisode'], '&')
    q = TVmaze.endpoint_standard_get(url)
    if q:
        return Show(q)
    else:
        raise ShowNotFound('show name "{0}" not found'.format(show))


def lookup_tvrage(tvrage_id):
    url = endpoints.lookup_tvrage.format(tvrage_id)
    q = TVmaze.endpoint_standard_get(url)
    if q:
        return Show(q)
    else:
        raise IDNotFound('TVRage id {0} not found'.format(tvrage_id))


def lookup_tvdb(tvdb_id):
    url = endpoints.lookup_tvdb.format(tvdb_id)
    q = TVmaze.endpoint_standard_get(url)
    if q:
        return Show(q)
    else:
        raise IDNotFound('TVDB ID {0} not found'.format(tvdb_id))


def lookup_imdb(imdb_id):
    url = endpoints.lookup_imdb.format(imdb_id)
    q = TVmaze.endpoint_standard_get(url)
    if q:
        return Show(q)
    else:
        raise IDNotFound('IMDB ID {0} not found'.format(imdb_id))


def get_schedule(country='US', date=str(datetime.today().date())):
    url = endpoints.get_schedule.format(country, date)
    q = TVmaze.endpoint_standard_get(url)
    if q:
        return [Episode(episode) for episode in q]
    else:
        raise ScheduleNotFound('Schedule for country {0} at date {1} not found'.format(country, date))


# ALL known future episodes, several MB large, cached for 24 hours
def get_full_schedule():
    url = endpoints.get_full_schedule
    q = TVmaze.endpoint_standard_get(url)
    if q:
        return [Episode(episode) for episode in q]
    else:
        raise GeneralError('Something went wrong, www.tvmaze.com may be down')


def show_main_info(maze_id, embed=None):
    url = _embed_url(endpoints.show_main_info.format(maze_id), embed,
                     [None, 'episodes', 'cast', 'previousepisode', 'nextepisode'], '?')
    q = TVmaze.endpoint_standard_get(url)
    if q:
        return Show(q)
    else:
        raise IDNotFound('Maze id {0} not found'.format(maze_id))


def episode_list(maze_id, specials=None, raise_error=True, show=None):
    if specials:
        url = endpoints.episode_list.format(maze_id) + '?specials=1'
    else:
        url = endpoints.episode_list.format(maze_id)
    q = TVmaze.endpoint_standard_get(url)
    if type(q) == list:
        return [Episode(episode, show) for episode in q]
    elif raise_error:
        raise IDNotFound('Maze id {0} not found'.format(maze_id))
    return []


def episode_by_number(maze_id, season_number, episode_number):
    url = endpoints.episode_by_number.format(maze_id,
                                             season_number,
                                             episode_number)
    q = TVmaze.endpoint_standard_get(url)
    if q:
        return Episode(q)
    else:
        raise EpisodeNotFound(
                'Couldn\'t find season {0} episode {1} for TVmaze ID {2}'.format(season_number,
                                                                                 episode_number,
                                                                                 maze_id))


def episodes_by_date(maze_id, airdate):
    try:
        datetime.strptime(airdate, '%Y-%m-%d')
    except ValueError:
        raise IllegalAirDate('Airdate must be string formatted as \"YYYY-MM-DD\"')
    url = endpoints.episodes_by_date.format(maze_id, airdate)
    q = TVmaze.endpoint_standard_get(url)
    if q:
        return [Episode(episode) for episode in q]
    else:
        raise NoEpisodesForAirdate(
                'Couldn\'t find an episode airing {0} for TVmaze ID {1}'.format(airdate, maze_id))


def show_cast(maze_id, raise_error=True):
    url = endpoints.show_cast.format(maze_id)
    q = TVmaze.endpoint_standard_get(url)
    if q:
        return Cast(q)
    elif raise_error:
        raise CastNotFound('Couldn\'nt find show cast for TVmaze ID {0}'.format(maze_id))
    return Cast({})


def show_index(page=1):
    url = endpoints.show_index.format(page)
    q = TVmaze.endpoint_standard_get(url)
    if q:
        return [Show(show) for show in q]
    else:
        raise ShowIndexError('Error getting show index, www.tvmaze.com may be down')


def people_search(person):
    # type: (AnyStr) -> List[Person]
    person = _url_quote(person)
    url = endpoints.people_search.format(person)
    q = TVmaze.endpoint_standard_get(url)
    if q:
        return [Person(person) for person in q]
    else:
        raise PersonNotFound('Couldn\'t find person {0}'.format(person))


def person_main_info(person_id, embed=None):
    # type: (integer_types, AnyStr) -> Person
    url = _embed_url(endpoints.person_main_info.format(person_id), embed,
                     [None, 'castcredits', 'crewcredits'], '?')
    q = TVmaze.endpoint_standard_get(url)
    if q:
        return Person(q)
    else:
        raise PersonNotFound('Couldn\'t find person {0}'.format(person_id))


def person_cast_credits(person_id, embed=None, raise_error=True):
    url = _embed_url(endpoints.person_cast_credits.format(person_id), embed,
                     [None, 'show', 'character'], '?')
    q = TVmaze.endpoint_standard_get(url)
    if q:
        return [CastCredit(credit) for credit in q]
    elif raise_error:
        raise CreditsNotFound('Couldn\'t find cast credits for person ID {0}'.format(person_id))
    return []


def person_crew_credits(person_id, embed=None, raise_error=True):
    url = _embed_url(endpoints.person_crew_credits.format(person_id), embed,
                     [None, 'show'], '?')
    q = TVmaze.endpoint_standard_get(url)
    if q:
        return [CrewCredit(credit) for credit in q]
    elif raise_error:
        raise CreditsNotFound('Couldn\'t find crew credits for person ID {0}'.format(person_id))
    return []


def get_show_crew(maze_id, raise_error=True):
    url = endpoints.show_crew.format(maze_id)
    q = TVmaze.endpoint_standard_get(url)
    if q:
        return [Crew(crew) for crew in q]
    elif raise_error:
        raise CrewNotFound('Couldn\'t find crew for TVmaze ID {}'.format(maze_id))
    return []


def get_show_images(maze_id, raise_error=True):
    url = endpoints.show_images.format(maze_id)
    q = TVmaze.endpoint_standard_get(url)
    if q:
        return [Image(img) for img in q]
    elif raise_error:
        raise ShowImagesNotFound('Couldn\'t find images for TVmaze ID {}'.format(maze_id))
    return []


def show_updates():
    # type: (...) -> Updates
    url = endpoints.show_updates
    q = TVmaze.endpoint_standard_get(url)
    if q:
        return Updates(q)
    else:
        raise ShowIndexError('Error getting show updates, www.tvmaze.com may be down')


def show_akas(maze_id, raise_error=True):
    url = endpoints.show_akas.format(maze_id)
    q = TVmaze.endpoint_standard_get(url)
    if q:
        return [AKA(aka) for aka in q]
    elif raise_error:
        raise AKASNotFound('Couldn\'t find AKA\'s for TVmaze ID {0}'.format(maze_id))
    return []


def show_seasons(maze_id, raise_error=True, show=None):
    url = endpoints.show_seasons.format(maze_id)
    q = TVmaze.endpoint_standard_get(url)
    if q:
        season_dict = dict()
        for season in q:
            season_dict[season['number']] = Season(season, show=show, season_number=season['number'])
        return season_dict
    elif raise_error:
        raise SeasonNotFound('Couldn\'t find Season\'s for TVmaze ID {0}'.format(maze_id))
    return {}


def season_by_id(season_id, embed=None):
    url = _embed_url(endpoints.season_by_id.format(season_id), embed,
                     [None, 'episodes'], '?')
    q = TVmaze.endpoint_standard_get(url)
    if q:
        return Season(q)
    else:
        raise SeasonNotFound('Couldn\'t find Season with ID {0}'.format(season_id))


def episode_by_id(episode_id, show=None, raise_error=True):
    url = endpoints.episode_by_id.format(episode_id)
    q = TVmaze.endpoint_standard_get(url)
    if q:
        return Episode(q, show=show)
    elif raise_error:
        raise EpisodeNotFound('Couldn\'t find Episode with ID {0}'.format(episode_id))
