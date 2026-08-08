"""
Get Data from IMDb using graphql
"""
import datetime

import requests
import logging

from .graphql_fragments import *
from .graphql_fragments import _compact_data

BASE_URL = "https://caching.graphql.imdb.com/"

HEADERS = {
    'accept': 'application/graphql+json, application/json',
    'accept-language': 'en-US,en;q=0.9',
    'content-type': 'application/json',
    'origin': 'https://www.imdb.com',
    'priority': 'u=1, i',
    'user-agent': 'Mozilla/5.0 (Linux; Android 6.0; Nexus 5 Build/MRA58N) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Mobile Safari/537.36',
    'x-imdb-client-name': 'imdb-web-next-localized',
    # 'x-imdb-user-country': 'US',
    'x-imdb-user-language': 'en'  # 'en-US'
}

date_format = '%Y-%m-%d'

imdb_group_ids = {
    'Actor': 'amzn1.imdb.concept.name_credit_category.a9ab2a8b-9153-4edb-a27a-7c2346830d77',
    'Actress': 'amzn1.imdb.concept.name_credit_category.7f6d81aa-23aa-4503-844d-38201eb08761',
    'Self': 'amzn1.imdb.concept.name_credit_category.d6017bdb-c3e7-4ca5-944b-68d74b9de6b6',
    'Producer': 'amzn1.imdb.concept.name_credit_category.0af123ce-1605-4a51-93cf-7ad477b11832',
    'Soundtrack': 'amzn1.imdb.concept.name_credit_category.4df03a1e-b90d-4c4a-8638-29eea26a156b',
    'Archive Footage': 'amzn1.imdb.concept.name_credit_group.6e871823-beae-458a-b972-2cdd635ec0d7',
    'Writer': 'amzn1.imdb.concept.name_credit_category.c84ecaff-add5-4f2e-81db-102a41881fe3',
    'Director': 'amzn1.imdb.concept.name_credit_category.ace5cb4c-8708-4238-9542-04641e7c8171',
    'Additional Crew': 'amzn1.imdb.concept.name_credit_category.a7c2d410-e513-4bd7-85d5-73060ec46a84',
    'Music Department': 'amzn1.imdb.concept.name_credit_category.aad1533c-6974-45a4-ba98-5f2f43286cfc',
    'Thanks': 'amzn1.imdb.concept.name_credit_category.90de891d-6d5e-4711-9179-3eda18bd18e1',
}

logger = logging.Logger('imdb_graphql')


def _get_tv_show_fields(title_types):
    # type: (list or None) -> str
    if not title_types or isinstance(title_types, list) and 'tvEpisode' in title_types:
        return tv_show_fields + '\n' + tv_show_series_fields
    return tv_show_fields


def compact_payload(payload):
    if 'query' in payload:
        payload['query'] = _compact_data(payload['query'])


def _get_response(payload):
    # type: (dict) -> dict
    compact_payload(payload)
    response = requests.post(BASE_URL, headers=HEADERS, json=payload)

    data = {}
    if response.status_code == 200:
        data = response.json()
        if 'errors' in data:
            logger.error(f"❌ GraphQL errors: {data['errors']}")
            return data
    else:
        logger.error(f"❌ Error {response.status_code}: {response.text}")
        return data

    return data


def fetch_person_page(person_id):
    payload = {
        "query": """query GetPersonDetails($id: ID!) {
        name(id: $id) {
            id
            nameText {
            text
            }
            primaryImage {
            url
            width
            height
            }
            primaryProfessions {
            category {
            text
            id
            }
            }
            knownFor(first: 10) {
            edges {
            node {
            title {
            id
            titleText {
            text
            }
            releaseYear {
            year
            }
            titleType {
            text
            }
            ratingsSummary {
            aggregateRating
            voteCount
            }
            metacritic {
              metascore {
                score
                reviewCount
              }
            }
            primaryImage {
            url
            }
            }
            }
            }
            }
            birthDate {
            dateComponents {
            day
            month
            year
            }
            }
            deathDate {
            dateComponents {
            day
            month
            year
            }
            }
            birthLocation {
            text
            }
            meterRanking {
            currentRank
            rankChange {
            changeDirection
            difference
            }
            }
            height {
            displayableProperty {
            value {
            plainText
            }
            }
            }
            bio {
            text {
            plainText
            }
            }
            akas(first: 5) {
            edges {
            node {
            text
            }
            }
        }
        }
        }""",
        "variables": {"id": f"{person_id}"}
    }

    return _get_response(payload)


def _get_person_filmography(name_id, type_categories=None, limits=None, tv_limit=None, credits_limit=None,
                            episode_limit=None, group_ids=None, after_cursor=None):

    def _get_type_categories(cats):
        categories = ['movie', 'tv', 'video', 'music', 'gaming', 'audio']
        cat = ''
        for _c in cats or categories:
            cat += filmography_types[_c]
        return cat

    if None is tv_limit:
        tv_limit = 9999

    if None is group_ids:
        group_ids = ('Actor', 'Actress', 'Self', 'Archive Footage')

    group_ids = [imdb_group_ids[g] for g in group_ids]

    variables = {
        'nameId': name_id,
        'creditsCount': credits_limit or 0,
        'episodeCount': episode_limit or 10,
        'isProPage': False,
        'tv_limit': tv_limit,
        'groupingIds': group_ids
    }

    # We enumerate all 6 possible titleTypeCategory values here,
    # and map them to the same field names as their enum values.
    #
    # This is a deliberate trade-off: if we dynamically built this query instead,
    # we would lose the benefits of static typing, which help keep our code type-safe
    # and prevent bugs.
    #
    # WARNING: If the API team ever adds/removes/modifies values in "TitleTypeCategoryValue",
    # this query will not fetch what we expect. However, this enum is very stable,
    # changed about once per decade, so we accept this compromise.

    payload = {
        'query': """query FilmographyV2TitleType(
        $nameId: ID!
        $creditsCount: Int!
        $includedGenre: [ID!]
        $excludedGenre: [ID!]
        $isProPage: Boolean!
        $tv_limit: Int!
        $groupingIds: [ID!]
    ) {
        name(id: $nameId) {
            id
            nameText {
              text
            }
            primaryProfessions {
              category {
                text
                id
              }
            }
            primaryImage {
              url
              width
              height
              caption {
                plainText
              }
            }
            birthDate {
              dateComponents {
                day
                month
                year
              }
            }
            deathDate {
              dateComponents {
                day
                month
                year
              }
            }
            birthLocation {
              text
            }
            height {
              measurement {
                value
                unit
              }
              displayableProperty {
                value {
                  plainText
                }
              }
            }
            bio {
              text {
                plainText
              }
            }
            akas(first: 10) {
              edges {
                node {
                  text
                }
              }
            }
""" + _get_type_categories(type_categories) + """
        }
    }""",
    'operationName': 'FilmographyV2TitleType',
    'variables': variables
    }

    res = _get_response(payload)
    return res


def _check_dates(min_date, max_date, default_min, default_max):
    if isinstance(min_date, int) or (isinstance(min_date, str) and 4 == len(min_date)):
        start_date = f"{min_date or 1900}-01-01"
    elif isinstance(min_date, str):
        start_date = min_date
    elif isinstance(min_date, (datetime.date, datetime.datetime)):
        start_date = min_date.strftime(date_format)
    else:
        start_date = default_min.strftime(date_format)

    if isinstance(max_date, int) or (isinstance(max_date, str) and 4 == len(max_date)):
        end_date = f"{max_date or 2030}-12-31"
    elif isinstance(max_date, str):
        end_date = max_date
    elif isinstance(max_date, (datetime.date, datetime.datetime)):
        end_date = max_date.strftime(date_format)
    else:
        end_date = default_max.strftime(date_format)

    return start_date, end_date


def _search_by_filters(target_genre=None, limit=50, languages=None, min_date=None, max_date=None, min_rating=None,
                       max_rating=None, title_type=None, after_cursor=None, sort_by='POPULARITY', sort_order='DESC',
                       episodicConstraint=None, seasonsConstraint=None, seasonsExlcudeConstraint=None,
                       incl_adult=False):
    """Search movies by filters using IMDb GraphQL API"""

    # Build constraints object
    constraints = {}

    if target_genre:
        constraints["genreConstraint"] = {"allGenreIds": [target_genre]}

    if languages:
        lang_list = languages if isinstance(languages, list) else [languages]
        constraints["languageConstraint"] = {"allLanguages": lang_list}

    if min_date or max_date:
        start_date, end_date = _check_dates(min_date, max_date, datetime.date(1900, 1, 1),
                                            datetime.date.today() + datetime.timedelta(days=3650))
        constraints["releaseDateConstraint"] = {
            "releaseDateRange": {"start": start_date, "end": end_date}
        }

    if min_rating or max_rating:
        rating_range = {}
        if min_rating:
            rating_range["min"] = min_rating
        if max_rating:
            rating_range["max"] = max_rating
        constraints["userRatingsConstraint"] = {"aggregateRatingRange": rating_range}

    if episodicConstraint:
        constraints['episodicConstraint'] = {'anyEpisodeNumbers': f'{episodicConstraint}'}
    if seasonsConstraint:
        constraints.setdefault('episodicConstraint', {})['anySeasons'] = f'{seasonsConstraint}'
    if seasonsExlcudeConstraint:
        constraints.setdefault('episodicConstraint', {})['excludeSeasons'] = f'{seasonsExlcudeConstraint}'

    if title_type:
        title_type = title_type if isinstance(title_type, list) else [title_type]
        constraints["titleTypeConstraint"] = {"anyTitleTypeIds": title_type}

    sort_order_choices = ["DESC", "ASC"]
    sort_by_choices = ["USER_RATING", "RELEASE_DATE", "POPULARITY", "ALPHA", "NUM_VOTES", "BOXOFFICE_GROSS_US",
                       "RUNTIME", "YEAR", "METACRITIC_SCORE"]
    if sort_by not in sort_by_choices:
        logger.error(f'Unsupported sort_by: {sort_by}, choices: {sort_by_choices}')
    if sort_order not in sort_order_choices:
        logger.error(f'Unsupported sort_order: {sort_order}, choices: {sort_order_choices}')

    if incl_adult:
        constraints["explicitContentConstraint"] = {"explicitContentFilter": "INCLUDE_ADULT"}

    variables = {
        "first": limit,
        "sort": {
            "sortBy": sort_by, # "USER_RATING", # "RELEASE_DATE", #  "POPULARITY", # "USER_RATING",
            "sortOrder": sort_order  # "DESC" # "ASC"
            }
    }

    if after_cursor:
        variables["after"] = after_cursor
    if constraints:
        variables["constraints"] = constraints

    payload = {
        "query": """query AdvancedTitleSearch($first: Int!, $constraints: AdvancedTitleSearchConstraints, $after: String, $sort: AdvancedTitleSearchSort) {
          advancedTitleSearch(first: $first, constraints: $constraints, after: $after, sort: $sort) {
          total
          edges {
              node {
                title {""" +
                 _get_tv_show_fields(title_type) +
                """}
              }
            }""" + page_info +
                 """}
       }""",
        "operationName": "AdvancedTitleSearch",
        "variables": variables
    }

    res = _get_response(payload=payload)
    return res


def _trending(limit=100, languages=None, title_type=None, data_window='HOURS', after_cursor=None, incl_adult=False):
    data_window_choices = ["HOURS", "MINUTES", "WEEKS"]
    if data_window not in data_window_choices:
        logger.error(f'Invalid data_window: {data_window}, available choices {data_window_choices}')

    data_window = 'MINUTES'
    variables = {
        "first": limit,
        "input": {"dataWindow": data_window, "trafficSource": "XWW"}
    }

    # Build constraints object
    constraints = {}

    if languages:
        lang_list = languages if isinstance(languages, list) else [languages]
        constraints["languageConstraint"] = {"allLanguages": lang_list}

    if title_type:
        title_type = title_type if isinstance(title_type, list) else [title_type]
        constraints["titleTypeConstraint"] = {"anyTitleTypeIds": title_type}

    if incl_adult:
        constraints["explicitContentConstraint"] = {"explicitContentFilter": "INCLUDE_ADULT"}

    if after_cursor:
        variables["after"] = after_cursor

    if constraints:
        variables["filter"] = constraints

    payload = {
        "query": """query Trending($first: Int!, $input: TopTrendingInput!) {
      topTrendingTitles(first: $first, input: $input) {
        edges {
          node {
            item {""" + _get_tv_show_fields(title_type) +
         """}
          }
        }""" + page_info +
                 """}
    }""",
        "operationName": "Trending",
        "variables": variables
    }

    res = _get_response(payload)
    return res


def _coming_soon(limit=100, title_type='TV_EPISODE', disablePopularityFilter=True, region="US", min_date=None,
                 max_date=None, sort_by='RELEASE_DATE', sort_order='ASC', after_cursor=None):
    start_date, end_date = _check_dates(min_date, max_date, datetime.date.today(), datetime.date.today() + datetime.timedelta(days=365))

    if 'TV_EPISODE' == title_type:
        req_type = ['tvEpisode']

    title_types = ['TV_EPISODE', 'TV', 'MOVIE']
    if title_type not in title_types:
        logger.error(f'Invalid title_type: {title_type}, available options: {title_types}')

    variables = {
        "first": limit,
        "type": title_type,
        "filter": disablePopularityFilter,
        "region": region,
        "startDate": start_date,
        "futureDate": end_date,
        "sortBy": sort_by,
        "sortOrder": sort_order
    }

    if after_cursor:
        variables["after"] = after_cursor

    payload = {
        "query": """query ComingSoon($first: Int!, $after: ID, $type: ComingSoonType!, $filter: Boolean, $region: String, $startDate: Date!, $futureDate: Date!, $sortBy: ComingSoonSortBy!, $sortOrder: SortOrder!) {
        comingSoon(
            first: $first
            comingSoonType: $type 
            disablePopularityFilter: $filter
            regionOverride: $region
            releasingOnOrAfter: $startDate
            releasingOnOrBefore: $futureDate
            after: $after
            sort: {sortBy: $sortBy, sortOrder: $sortOrder}) {
    edges {
      node {""" + _get_tv_show_fields(None) +
   """}
    }""" + page_info +
  """}
}
""",
        "operationName": "ComingSoon",
        "variables": variables
    }

    res = _get_response(payload)
    return res


def _most_popular(limit=100, min_date=None, max_date=None, chart_type='MOST_POPULAR_TV_SHOWS', sort_by='RANKING',
                  sort_order='ASC', incl_Adult=False, after_cursor=None):
    variables = {
        "limit": limit,
        "chart_type": chart_type,
        "sortBy": sort_by,
        "sortOrder": sort_order
    }

    chart_types = ['LOWEST_RATED_MOVIES', 'MOST_POPULAR_MOVIES', 'MOST_POPULAR_TV_SHOWS', 'TOP_RATED_MOVIES',
                   'TOP_RATED_ENGLISH_MOVIES', 'TOP_RATED_TV_SHOWS']
    if chart_type not in chart_types:
        logger.error(f'Invalid chart_type: {chart_type}, choices: {chart_types}')

    constraints = {}

    start_date, end_date = _check_dates(min_date, max_date, datetime.date(1900, 1, 1),
                                        datetime.date.today() + datetime.timedelta(days=3650))

    constraints["releaseDateConstraint"] = {
        "releaseDateRange": {"start": start_date, "end": end_date}}

    if incl_Adult:
        constraints['explicitContentConstraint'] = {'explicitContentFilter': 'INCLUDE_ADULT'}

    if after_cursor:
        variables["after"] = after_cursor

    if constraints:
        variables['filter'] = constraints

    payload = {
        "query": """query MostPopularTitle($filter: AdvancedTitleSearchConstraints!, $limit: Int!, $chart_type: ChartTitleType!, $sortBy: AdvancedTitleSearchSortBy!, $sortOrder: SortOrder!) {
  chartTitles(
    first: $limit
    chart: {chartType: $chart_type}
    sort: {sortBy: $sortBy, sortOrder: $sortOrder}
    filter: $filter
  ) {
    total
    edges {
      currentRank
          node {""" + _get_tv_show_fields(None) +
                 """}
                  }""" + page_info +
                 """}
               }
               """,
        "operationName": "MostPopularTitle",
        "variables": variables
    }

    res = _get_response(payload)
    return res


constraints = {}


def _get_watchlist(limit=250, jump_pos=1, user_id=None, target_genre=None, min_rating=None, max_rating=None,
                   title_type=None, min_date=None, max_date=None, loc="en-US", sort_by='LIST_ORDER', sort_order='ASC',
                   title_text_constraint=None, keyword_constraint=None, after_cursor=None):
    variables = {
        "first": limit,
        "jumpToPosition": jump_pos,
        "locale": loc,
        "sort": {"by": f"{sort_by}", "order": sort_order},
        "urConst": f"ur{user_id}"
    }

    constraints = {}
    if min_date or max_date:
        start_date, end_date = _check_dates(min_date, max_date, datetime.date(1900, 1, 1),
                                            datetime.date.today() + datetime.timedelta(days=3650))
        constraints["releaseDateConstraint"] = {
            "releaseDateRange": {"start": start_date, "end": end_date}}
    if title_type:
        title_type = title_type if isinstance(title_type, list) else [title_type]
        constraints["titleTypeConstraint"] = {"anyTitleTypeIds": title_type}
    if min_rating or max_rating:
        rating_range = {}
        if min_rating:
            rating_range["min"] = min_rating
        if max_rating:
            rating_range["max"] = max_rating
        constraints["userRatingsConstraint"] = {"aggregateRatingRange": rating_range}
    if target_genre:
        target_genre = target_genre if isinstance(target_genre, list) else [target_genre]
        constraints["genreConstraint"] = {"allGenreIds": target_genre}
    if title_text_constraint:
        constraints["titleTextConstraint"] = {"searchTerm": title_text_constraint}
    if keyword_constraint:
        keyword_constraint = keyword_constraint if isinstance(keyword_constraint, list) else [keyword_constraint]
        constraints["keywordConstraint"] = {"allKeywords": keyword_constraint}

    # if cert_constraint:
    #     constraints["certificateConstraint"] = {}
    # if watch_constraint:
    #     constraints["watchOptionsConstraint"] = {}

    if constraints:
        variables["filter"] = constraints

    if after_cursor:
        variables["after"] = after_cursor

    payload = {
        "query": """query WatchListPage(
            $urConst: ID!
            $first: Int!
            $sort: TitleListSearchSort
            $filter: AdvancedTitleSearchConstraints
            $jumpToPosition: Int
        ) {
            predefinedList(classType: WATCH_LIST, userId: $urConst) {
                id
                isTrusted
                createdDate
                lastModifiedDate
                author {
                    username {
                        text
                    }
                }
                visibility {
                    id
                }
                titleListItemSearch(
                    first: $first
                    sort: $sort
                    filter: $filter
                    jumpToPosition: $jumpToPosition
                ) {
                    total
                    """ + page_info +
                 """
                    edges {
                        node {
                            absolutePosition
                            description {
                                originalText {
                                    plaidHtml(showLineBreak: true)
                                }
                            }
                        }
                        listItem: title {""" + _get_tv_show_fields(None) +
                 """}
                    }
                }
            }
        }""",
        "variables": variables,
        'operationName': 'WatchListPage',
    }

    res = _get_response(payload)
    return res


def _get_favorite_people(limit=250, jump_pos=1, user_id=None, loc="en-US", sort_by='LIST_ORDER', sort_order='ASC',
                         after_cursor=None):
    variables = {
        "first": limit,
        "jumpToPosition": jump_pos,
        "sort": {"by": f"{sort_by}", "order": sort_order},
        "urConst": f"ur{user_id}",
    }

    constraints = {}

    if after_cursor:
        variables["after"] = after_cursor

    payload = {
        "query": """query FavoritePeoplePage(
        $urConst: ID!
        $first: Int!
        $sort: NameListSearchSort
        $jumpToPosition: Int
    ) {
        predefinedList(classType: FAVORITE_ACTORS, userId: $urConst) {
            ...""" + UserListListItemMetadata + """
            author {
                primaryImage {
                    image {
                        id
                        url
                        height
                        width
                        caption {
                            plainText
                        }
                    }
                }
            }
            nameListItemSearch(
                first: $first
                jumpToPosition: $jumpToPosition
                sort: $sort
            ) {
                total
                pageInfo {
                    hasNextPage
                    hasPreviousPage
                    endCursor
                }
                edges {
                    listItem: name {
                        ...""" + NameListItemMetadata + """
                    }
                    node {
                        ...""" + ListSearchItemMetadata + """
                    }
                }
            }
        }
    }
""",
        "variables": variables,
        'operationName': 'FavoritePeoplePage',
    }

    res = _get_response(payload)
    return res


def _get_person_episodes(name_id, limits=None, tv_limit=None, credits_limit=None, episode_limit=None, group_ids=None,
                         credited_roles=10, after_cursor=None):

    if None is tv_limit:
        tv_limit = 9999

    if None is group_ids:
        group_ids = ('Actor', 'Actress', 'Self', 'Archive Footage')

    group_ids = [imdb_group_ids[g] for g in group_ids]

    variables = {
        'nameId': name_id,
        'creditsCount': credits_limit or 1000,
        'episodeCount': episode_limit or 250,  # 250 is api limit, uses pagination after
        'isProPage': False,
        'tv_limit': tv_limit,
        'groupingIds': group_ids,
        'creditedRoles': credited_roles or 10
    }

    payload = {
        'query': """query FilmographyV2TitleType(
        $nameId: ID!
        $creditsCount: Int!
        $episodeCount: Int!
        $includedGenre: [ID!]
        $excludedGenre: [ID!]
        $isProPage: Boolean!
        $tv_limit: Int!
        $groupingIds: [ID!]
        $creditedRoles: Int
    ) {
        name(id: $nameId) {
            id
""" + person_episodes + """
        }
    }""",
    'operationName': 'FilmographyV2TitleType',
    'variables': variables
    }

    res = _get_response(payload)
    return res

