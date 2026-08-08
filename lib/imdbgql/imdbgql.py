# -*- coding: utf-8 -*-
import logging

from .graphql import fetch_person_page, _search_by_filters, _trending, _coming_soon, _most_popular, _get_watchlist, \
    _get_person_filmography, _get_favorite_people, _get_person_episodes
from .exceptions import IMDbGQLError, IMDbGQLPersonNotFound

logger = logging.getLogger(__name__)


class IMDb(object):

    def __init__(self, locale=None, *args, **kwargs):
        self.locale = locale or 'en_US'

    @staticmethod
    def _check_sort_params(sort_by, sort_order, extra_orders=None):
        extra_orders = extra_orders or []
        sort_order_choices = ["DESC", "ASC"]
        sort_by_choices = ["MY_RATING", "MY_RATING_DATE", "POPULARITY", "RANKING", "RELEASE_DATE", "RUNTIME",
                           "TITLE_REGIONAL", "USER_RATING", "USER_RATING_COUNT", "YEAR",
                           "METACRITIC_SCORE"] + extra_orders
        if sort_by not in sort_by_choices:
            msg = f'Unsupported sort_by: {sort_by}, choices: {sort_by_choices}'
            logger.error(msg)
            raise IMDbGQLError(msg)
        if sort_order not in sort_order_choices:
            msg = f'Unsupported sort_order: {sort_order}, choices: {sort_order_choices}'
            logger.error(msg)
            raise IMDbGQLError(msg)

    @staticmethod
    def _get_after_cursor(page_info):
        # type: (dict) -> str or None
        if page_info['hasNextPage']:
            return page_info['endCursor']

    def get_full_filmography(self, name_id, limits=None, type_categories=None, tv_limit=None, credits_limit=None,
                             group_ids=None):
        # type: (str, int, list, int, int, list) -> (dict, list, str)
        categories = ['movie', 'tv', 'video', 'music', 'gaming', 'audio']
        type_categories = type_categories or []
        for _c in type_categories:
            if _c not in categories:
                msg = f'Invalid type_category: {_c}'
                logger.error(msg)
                raise IMDbGQLError(msg)
        res = _get_person_filmography(
            name_id=name_id, limits=limits, type_categories=type_categories, tv_limit=tv_limit,
            credits_limit=credits_limit, group_ids=group_ids)
        if None is res['data']['name']['nameText']:
            raise IMDbGQLPersonNotFound(f'Person not found with id: {name_id}')
        credit_types = ['Actress', 'Actor', 'Self', 'Archive Footage']
        result = [t['node'] for r in res['data']['name']['tv']['edges'] for t in r['node']['credits']['edges']
                  if any(_c in r['node']['grouping']['text'] for _c in credit_types)]
        page_info = [r['node']['credits']['pageInfo'] for r in res['data']['name']['tv']['edges']
                     if any(_c in r['node']['grouping']['text'] for _c in credit_types)][0]
        primary_data = res['data']['name']
        return primary_data, result, self._get_after_cursor(page_info)

    def get_person_episodes(self, name_id, limits=None, tv_limit=None, credits_limit=None, group_ids=None,
                            episode_limit=None, credited_roles=None):
        # type: (str, int, int, int, list, int, int) -> (dict, list, str)
        res = _get_person_episodes(
            name_id=name_id, limits=limits, tv_limit=tv_limit,
            credits_limit=credits_limit, group_ids=group_ids, episode_limit=episode_limit,
            credited_roles=credited_roles)
        if None is res['data']['name']['id']:
            raise IMDbGQLPersonNotFound(f'Person not found with id: {name_id}')
        credit_types = ['Actress', 'Actor', 'Self', 'Archive Footage']
        result = [t['node'] for r in res['data']['name']['tv']['edges'] for t in r['node']['credits']['edges']
                  if t['node']['episodeCredits']['total'] and any(_c in r['node']['grouping']['text'] for _c in credit_types)]
        page_info = [r['node']['credits']['pageInfo'] for r in res['data']['name']['tv']['edges']
                     if any(_c in r['node']['grouping']['text'] for _c in credit_types)][0]
        primary_data = res['data']['name']
        return primary_data, result, self._get_after_cursor(page_info)

    def get_coming_soon(self, limit=100, title_type='TV_EPISODE', disablePopularityFilter=True, region="US",
                        min_date=None, max_date=None, sort_by='RELEASE_DATE', sort_order='ASC', after_cursor=None):
        # type: (...) -> (list, str)
        self._check_sort_params(sort_by, sort_order)
        title_tyes = ['TV_EPISODE', 'TV', 'MOVIE']
        if title_type not in title_tyes:
            msg = f'Unsupported title type: {title_type}, choices: {title_tyes}'
            logger.error(msg)
            raise IMDbGQLError(msg)

        res = _coming_soon(limit=limit, title_type=title_type, disablePopularityFilter=disablePopularityFilter,
                           region=region, min_date=min_date, max_date=max_date, sort_by=sort_by, sort_order=sort_order,
                           after_cursor=after_cursor)
        res_list = [r['node'] for r in res['data']['comingSoon']['edges']]
        return res_list, self._get_after_cursor(res['data']['comingSoon']['pageInfo'])

    def get_most_popular(self, limit=100, min_date=None, max_date=None, chart_type='MOST_POPULAR_TV_SHOWS',
                         sort_by='RANKING', sort_order='ASC', incl_Adult=False, after_cursor=None):
        # type: (...) -> (list, str, int)
        self._check_sort_params(sort_by, sort_order)
        chart_types = ['LOWEST_RATED_MOVIES', 'MOST_POPULAR_MOVIES', 'MOST_POPULAR_TV_SHOWS', 'TOP_RATED_MOVIES',
                       'TOP_RATED_ENGLISH_MOVIES', 'TOP_RATED_TV_SHOWS']
        if chart_type not in chart_types:
            msg = f'Invalid chart_type: {chart_type}, choices: {chart_types}'
            logger.error(msg)
            raise IMDbGQLError(msg)

        res = _most_popular(limit=limit, min_date=min_date, max_date=max_date, chart_type=chart_type, sort_by=sort_by,
                            sort_order=sort_order, incl_Adult=incl_Adult, after_cursor=after_cursor)
        res_list = [r['node'] for r in res['data']['chartTitles']['edges']]
        return res_list, self._get_after_cursor(res['data']['chartTitles']['pageInfo']), \
            res['data']['chartTitles']['total']

    def get_watchlist(self, user_id, limit=250, jump_pos=1, target_genre=None, min_rating=None, max_rating=None,
                      title_type=None, min_date=None, max_date=None, loc="en-US", sort_by='LIST_ORDER',
                      sort_order='ASC', title_text_constraint=None, keyword_constraint=None, after_cursor=None):
        self._check_sort_params(sort_by, sort_order, ['LIST_ORDER', 'DATE_ADDED'])
        if title_type:
            title_type = title_type if isinstance(title_type, list) else [title_type]

        res = _get_watchlist(limit=limit, jump_pos=jump_pos, user_id=user_id, target_genre=target_genre,
                             min_rating=min_rating, max_rating=max_rating, title_type=title_type,
                             min_date=min_date, max_date=max_date, loc=loc, sort_by=sort_by, sort_order=sort_order,
                             title_text_constraint=title_text_constraint, keyword_constraint=keyword_constraint,
                             after_cursor=after_cursor)
        res_list = [r['listItem'] for r in res['data']['predefinedList']['titleListItemSearch']['edges']]
        list_info = {
            'list_id': res['data']['predefinedList']['id'],
            'isTrusted': res['data']['predefinedList']['isTrusted'],
            'username': res['data']['predefinedList']['author']['username']['text'],
            'createdDate': res['data']['predefinedList']['createdDate'],
            'lastModifiedDate': res['data']['predefinedList']['lastModifiedDate'],
            'visibility': res['data']['predefinedList']['visibility']['id']
        }
        return res_list, self._get_after_cursor(res['data']['predefinedList']['titleListItemSearch']['pageInfo']), \
            res['data']['predefinedList']['titleListItemSearch']['total'], list_info

    def search_by_filters(self, target_genre=None, limit=100, languages=None, min_date=None, max_date=None,
                          min_rating=None, max_rating=None, title_type=None, sort_by=None, sort_order='DESC',
                          episodicConstraint=None, seasonsConstraint=None, after_cursor=None,
                          seasonsExlcudeConstraint=None):
        # type: (...) -> (list, str, int)
        self._check_sort_params(sort_by, sort_order)
        if title_type:
            title_type = title_type if isinstance(title_type, list) else [title_type]

        res = _search_by_filters(target_genre=target_genre, limit=limit, languages=languages, min_date=min_date,
                                 max_date=max_date, min_rating=min_rating, max_rating=max_rating, title_type=title_type,
                                 after_cursor=after_cursor, sort_by=sort_by, sort_order=sort_order,
                                 episodicConstraint=episodicConstraint, seasonsConstraint=seasonsConstraint,
                                 seasonsExlcudeConstraint=seasonsExlcudeConstraint)
        res_list = [r['node']['title'] for r in res['data']['advancedTitleSearch']['edges']
                    if r['node']['title']['titleType']['id'] in title_type]
        return res_list, self._get_after_cursor(res['data']['advancedTitleSearch']['pageInfo']), \
            res['data']['advancedTitleSearch']['total']

    def get_trending(self, limit=100, languages=None, title_type=None, data_window='HOURS', after_cursor=None):
        # type: (int, list or str, list or str, str, str) -> (list, str)
        if title_type:
            title_type = title_type if isinstance(title_type, list) else [title_type]
        data_window_choices = ["HOURS", "MINUTES", "WEEKS"]
        if data_window not in data_window_choices:
            msg = f'Invalid data_window: {data_window}, available choices {data_window_choices}'
            logger.error(msg)
            raise IMDbGQLError(msg)

        res_list = []
        res = _trending(limit=limit, languages=languages, title_type=title_type, data_window=data_window,
                        after_cursor=after_cursor)
        res_list += [r['node']['item'] for r in res['data']['topTrendingTitles']['edges']
                     if r['node']['item']['titleType']['id'] in title_type]

        return res_list, self._get_after_cursor(res['data']['topTrendingTitles']['pageInfo'])

    def get_name_biography(self, imdb_id):
        try:
            data = fetch_person_page(imdb_id)
            return data['data']['name']['bio']['text']['plainText']
        except (BaseException, Exception) as e:
            IMDbGQLError(f'Error fetching biography for {imdb_id}: {e}')

    def get_favorite_people(self, user_id, limit=250, jump_pos=1, loc="en-US", sort_by='LIST_ORDER', sort_order='ASC',
                            after_cursor=None):
        self._check_sort_params(sort_by, sort_order, ['LIST_ORDER', 'DATE_ADDED'])

        res = _get_favorite_people(limit=limit, jump_pos=jump_pos, user_id=user_id, loc=loc,
                                   sort_by=sort_by, sort_order=sort_order, after_cursor=after_cursor)
        if 'nameListItemSearch' not in res['data']['predefinedList']:
            return None, None, None, None
        res_list = [r['listItem'] for r in res['data']['predefinedList']['nameListItemSearch']['edges']]
        list_info = {
            'list_id': res['data']['predefinedList']['id'],
            'username': res['data']['predefinedList']['author']['username']['text'],
            'createdDate': res['data']['predefinedList']['createdDate'],
            'lastModifiedDate': res['data']['predefinedList']['lastModifiedDate'],
            'visibility': res['data']['predefinedList']['visibility']['id']
        }
        return res_list, self._get_after_cursor(res['data']['predefinedList']['nameListItemSearch']['pageInfo']), \
            res['data']['predefinedList']['nameListItemSearch']['total'], list_info
