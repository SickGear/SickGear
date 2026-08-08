import re

remove_leading_spaces = re.compile(f'^ +', flags=re.M)
remove_spaces = re.compile(r'  +', re.M)


def _compact_data(data):
    return remove_spaces.sub(' ', remove_leading_spaces.sub('', data))


tv_show_fields = _compact_data("""id
                  isAdult
                  titleText {
                    text
                  }
                  titleType {
                    id
                    text
                  }
                  originalTitleText { 
                    text 
                  }
                  releaseYear {
                    year
                    endYear
                  }
                  releaseDate { 
                    day 
                    month 
                    year 
                  }
                  runtime {
                    seconds
                  }
                  plot {
                    plotText {
                      plainText
                    }
                    language {
                      id
                    }
                  }
                  primaryImage {
                    url
                    width
                    height
                    type
                    caption {
                      plainText
                    }
                  }
                  spokenLanguages {
                    spokenLanguages {
                      text
                      id
                    }
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
                  certificate {
                    rating
                    country {
                      text
                    }
                  }
                  countriesOfOrigin {
                    countries {
                      text
                      id
                    }
                  }
                  productionStatus {
                    currentProductionStage {
                      text
                      id
                    }
                  }
                  genres {
                    genres {
                      text
                    }
                  }
""")

tv_show_series_fields = _compact_data("""series {
                    series {""" + tv_show_fields + """
                    }
                    episodeNumber {
                      episodeNumber
                      seasonNumber
                    }
                  }
""")

page_info = _compact_data("""pageInfo {
              hasNextPage
              endCursor
            }""")

CreditCard = """ on Title {
    """ + tv_show_fields + """
}
"""

CreditCard_tv = """ on Title {
    """ + tv_show_fields + tv_show_series_fields + """
}
"""

CreditRolesMetadata = """ on CreditV2 {
    creditedRoles(first: 250) {
        edges {
            node {
                text
                category {
                    categoryId
                    text
                    traits
                }
                attributes {
                    text
                }
                # Characters doesn't support pagination, instead the graph will serve up to 2,500 items
                characters(first: 2500) {
                    edges {
                        node {
                            name
                        }
                    }
                }
            }
        }
    }
}
"""

creditDisplayableSeasonAndYear = """ on EpisodeCreditConnection {
    displayableYears(first: 100) {
        total
        edges {
            node {
                year
            }
        }
    }
    displayableSeasons(first: 100) {
        total
        edges {
            node {
                season
            }
        }
    }
}
"""

episodedata = """        total
        edges {
          node {
            title {
              id
              titleText {
                text
              }
              originalTitleText {
                text
              }
              releaseDate {
                day 
                month 
                year
              }
              series {
                  episodeNumber {
                    episodeNumber
                    seasonNumber
                  }
              }
            }
            creditedRoles(first: 5) {
              edges {
                node {
                  text
                  category {
                    text
                    traits
                  }
                }
              }
            }
          }
        }
"""

CreditMetaDataPace = """ on CreditV2 {
    ...""" + CreditRolesMetadata + """
    episodeCredits(first: 0) {
        total
        yearRange {
            year
            endYear
        }
        ...""" + creditDisplayableSeasonAndYear + """
    }
}
"""

titleCredit = """ on CreditV2Edge {
    node {

        title {
            ...""" + CreditCard + """
        }
    }
}
"""

titleCredit_tv = """ on CreditV2Edge {
    node {
        ...""" + CreditMetaDataPace + """
        title {
            ...""" + CreditCard_tv + """
        }
    }
}
"""

filmographyV2Grouping = """ on CreditGroupingEdge {
    node {
        grouping {
            groupingId
            text
        }
        credits(first: $creditsCount) {
            edges {
                ...""" + titleCredit + """
            }
            total
            pageInfo {
                hasNextPage
                endCursor
            }
        }
    }
}
"""

filmographyV2Grouping_tv = """ on CreditGroupingEdge {
    node {
        grouping {
            groupingId
            text
        }
        credits(first: $creditsCount) {
            edges {
                ...""" + titleCredit_tv + """
            }
            total
            pageInfo {
                hasNextPage
                endCursor
            }
        }
    }
}
"""

# filmography fragments
filmography_types = {
    'movie': """movie: creditGroupings(
                first: 250
                useEntitlement: $isProPage
                creditSort: { by: "RELEASE_DATE", order: DESC }
                filter: {
                    titleLevelFilter: {
                        titleTypeCategory: [movie]
                        genres: $includedGenre
                        excludeGenres: $excludedGenre
                    }
                    creditLevelFilter: { 
                        groupings: $groupingIds 
                    }                    
                }
            ) {
                edges {
                    ...""" + filmographyV2Grouping + """
                }
            }
    """,

    'tv': """tv: creditGroupings(
                first: $tv_limit
                useEntitlement: $isProPage
                creditSort: { by: "RELEASE_DATE", order: DESC }
                filter: {
                    titleLevelFilter: {
                        titleTypeCategory: [tv]
                        genres: $includedGenre
                        excludeGenres: $excludedGenre
                    }
                    creditLevelFilter: { 
                        groupings: $groupingIds 
                    }                    
                }
            ) {
                edges {
                    ...""" + filmographyV2Grouping_tv + """
                }
            }
    """,

    'video': """video: creditGroupings(
                first: 250
                useEntitlement: $isProPage
                creditSort: { by: "RELEASE_DATE", order: DESC }
                filter: {
                    titleLevelFilter: {
                        titleTypeCategory: [video]
                        genres: $includedGenre
                        excludeGenres: $excludedGenre
                    }
                    creditLevelFilter: { 
                        groupings: $groupingIds 
                    }                    
                }
            ) {
                edges {
                    ...""" + filmographyV2Grouping_tv + """
                }
            }
    """,

    'music': """music: creditGroupings(
                first: 250
                useEntitlement: $isProPage
                creditSort: { by: "RELEASE_DATE", order: DESC }
                filter: {
                    titleLevelFilter: {
                        titleTypeCategory: [music]
                        genres: $includedGenre
                        excludeGenres: $excludedGenre
                    }
                    creditLevelFilter: { 
                        groupings: $groupingIds 
                    }                    
                }
            ) {
                edges {
                    ...""" + filmographyV2Grouping_tv + """
                }
            }
    """,

    'gaming': """gaming: creditGroupings(
                first: 250
                useEntitlement: $isProPage
                creditSort: { by: "RELEASE_DATE", order: DESC }
                filter: {
                    titleLevelFilter: {
                        titleTypeCategory: [gaming]
                        genres: $includedGenre
                        excludeGenres: $excludedGenre
                    }
                    creditLevelFilter: { 
                        groupings: $groupingIds 
                    }                    
                }
            ) {
                edges {
                    ...""" + filmographyV2Grouping + """
                }
            }
    """,

    'audio': """audio: creditGroupings(
                first: 250
                useEntitlement: $isProPage
                creditSort: { by: "RELEASE_DATE", order: DESC }
                filter: {
                    titleLevelFilter: {
                        titleTypeCategory: [audio]
                        genres: $includedGenre
                        excludeGenres: $excludedGenre
                    }
                    creditLevelFilter: { 
                        groupings: $groupingIds 
                    }
                }
            ) {
                edges {
                    ...""" + filmographyV2Grouping_tv + """
                }
            }
    """
}

filmography_types = {_k: _compact_data(_v) for _k, _v in filmography_types.items()}


UserListListItemMetadata = """ on List {
        author {
            username {
                text
            }
            userId
        }
        id
        name {
            originalText
        }
        listType {
            id
        }
        listClass {
            id
            name {
                text
            }
        }
        description {
            originalText {
                plaidHtml(showLineBreak: true)
                markdown
                plainText
            }
        }
        items(first: 0) {
            total
        }
        createdDate
        lastModifiedDate
        primaryImage {
            image {
                id
                caption {
                    plainText
                }
                height
                width
                url
            }
        }
        visibility {
            id
        }
    }
"""

NameListItemMetadata = """ on Name {
        id
        primaryImage {
            url
            caption {
                plainText
            }
            width
            height
        }
        nameText {
            text
        }
        primaryProfessions {
            category {
                text
            }
        }
        professions {
            profession {
                text
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
        knownForV2(limit: 1) {
            credits {
                title {
                    id
                    originalTitleText {
                        text
                    }
                    titleText {
                        text
                    }
                    titleType {
                        canHaveEpisodes
                    }
                    releaseYear {
                        year
                        endYear
                    }
                }
                episodeCredits(first: 0) {
                    yearRange {
                        year
                        endYear
                    }
                }
            }
        }
        bio {
            text {
                plainText
            }
        }
    }
"""

ListSearchItemMetadata = """ on ListItemSearchNode {
        itemId
        absolutePosition
        createdDate
        description {
            originalText {
                plaidHtml(showLineBreak: true)
            }
        }
    }
"""

creditDisplayableSeasonAndYear_episodes = """ on EpisodeCreditConnection {
    edges {
        node {
            ... on CreditV2 {
                creditedRoles(first: $creditedRoles) {
                    edges {
                        node {
                            text
                            category {
                                text
                                traits
                            }
                        }
                    }
                }
                title {
                    ... on Title {
                        id
                        titleText {
                            text
                        }
                        releaseDate {
                            day
                            month
                            year
                        }
                        series {
                            series {
                                id
                            }
                            episodeNumber {
                                episodeNumber
                                seasonNumber
                            }
                        }
                    }
                }
            }
        }
    }
}
"""

CreditMetaDataPace_episodes = """ on CreditV2 {
    episodeCredits(first: $episodeCount) {
        total
        ...""" + creditDisplayableSeasonAndYear_episodes + """
        pageInfo {
            hasNextPage
            endCursor
        }
    }
}
"""

titleCredit_tv_episodes = """ on CreditV2Edge {
    node {
        ...""" + CreditMetaDataPace_episodes + """
    }
}
"""

filmographyV2Grouping_tv_episodes = """ on CreditGroupingEdge {
    node {
        grouping {
            groupingId
            text
        }
        credits(first: $creditsCount) {
            edges {
                ...""" + titleCredit_tv_episodes + """
            }
            total
            pageInfo {
                hasNextPage
                endCursor
            }
        }
    }
}
"""

person_episodes = """tv: creditGroupings(
            first: $tv_limit
            useEntitlement: $isProPage
            creditSort: { by: "RELEASE_DATE", order: DESC }
            filter: {
                titleLevelFilter: {
                    titleTypeCategory: [tv]
                    genres: $includedGenre
                    excludeGenres: $excludedGenre
                }
                creditLevelFilter: { 
                    groupings: $groupingIds 
                }
            }
        ) {
            edges {
                ...""" + filmographyV2Grouping_tv_episodes + """
            }
        }
"""