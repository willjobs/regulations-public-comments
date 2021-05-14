# Analysis of public comment data on Regulations.gov

More information on the API, including a description and examples of the API responses and how to parse it, can be found in [this blog post](https://github.com/willjobs/regulations-public-comments/blob/master/blogposts/post2/README.md). The official Regulations.gov API documentation is here: https://open.gsa.gov/api/regulationsgov/.

To sign up for an API key, go to [this link](https://open.gsa.gov/api/regulationsgov/#getting-started). You can also use `DEMO_KEY` as an API key for up to 25 requests per hour. This is what the documentation at Regulations.gov uses in their examples.

Note: This code came about as the result of a final project for a course I took at UMass Amherst ("Text as Data"). The results are shown in [poster.pdf](https://github.com/willjobs/regulations-public-comments/blob/master/poster.pdf), and milestone blog posts are in the [blogposts](https://github.com/willjobs/regulations-public-comments/tree/master/blogposts) folder.

---

# How this works

The goal of this code is to provide an easier mechanism to query for and download data from Regulations.gov using their public API. This code submits requests to the API and parses the responses, downloading the data into either a sqlite database or a CSV.

The biggest contribution of this code is the automated handling of the API's pagination mechanism. By default, the API returns 25 records per request, which can be bumped up to 250 records. A given query returns up to 20 "pages", so with 250 records per page, that is 5,000 records per query. If your query would return more than 5,000 records (e.g., if you're querying for all comments in 2020), you need to use multiple queries, paginating over all 20 pages in each, and making sure subsequent queries filter out the earlier queries' results (typically by using `lastModifiedDate`). I explain this in detail in [post 2](https://github.com/willjobs/regulations-public-comments/tree/master/blogposts/post2).

This code also automatically handles request limits. API keys give you up to 1,000 requests per hour. After that, the API returns a status code 429 indicating you're out of requests. This code knows how to wait and retry.

Note that there are essentially two high-level APIs, what I call the "header" and "details" APIs. The "header" API is https://api.regulations.gov/v4/{data_type} (with {data_type} replaced by either "comments", "documents", or "dockets"). This API returns some general information about items (comments, etc.) matching search criteria specified using parameters. The "details" API is https://api.regulations.gov/v4/{data_type}/{itemId}, which returns detailed information about one *specific item*. For example, to see the plain-text of a comment, this details API needs to be used.

For one-off queries and understanding the API, I recommend using `get_request_json`, which returns the raw JSON associated with a request.

There are some idiosyncracies in the data itself. For example, there are comments not associated with any documents, documents not associated with a docket, many documents without comments, etc. By far, the document types with the most comments are "Proposed Rule" and "Rule" types. To query for these, one could use this filter: `filter[documentType]: 'Proposed Rule,Rule'`.

---

# Example uses:

The comments in `regulations_utils.py` are pretty thorough and explain how each function is used. The examples below show some simple examples of they might be used.


## Create a SQLite database to contain the data, and save the opened connection
        # by default, filename is "regulations.gov_{yyyymmdd}.db"
        # can specify a filename if desired
        conn = setup_database()


## Show the number of requests remaining:

        >>> get_requests_remaining("DEMO_KEY")
        999

## Get the JSON associated with a request to the header API:

        >>> get_request_json(f'https://api.regulations.gov/v4/comments',
                             api_key,
                             params={"filter[agencyId]": "EPA",
                                     "filter[postedDate][ge]": "2021-01-01",
                                     "filter[postedDate][le]": "2021-01-05",})

        {'data': [{'id': 'EPA-HQ-OPP-2009-0209-0039',
                   'type': 'comments',
                   'attributes': {'documentType': 'Public Submission',
                       'lastModifiedDate': '2021-01-04T20:31:40Z',
                       'highlightedContent': '',
                       'withdrawn': False,
                       'agencyId': 'EPA',
                       'title': 'Comment submitted by Marisa C. Ordonia and Patti A. Goldman,    Earthjustice on behalf of California Rural Legal Assistance    Foundation et al. (Part 2 of 3)',
                       'objectId': '0900006484955939',
                       'postedDate': '2021-01-04T05:00:00Z'},
                   'links': {'self': 'https://api.regulations.gov/v4/comments/   EPA-HQ-OPP-2009-0209-0039'}},
                   {'id': 'EPA-HQ-OW-2018-0640-0657',
                   'type': 'comments',
                   'attributes': {'documentType': 'Public Submission',
                    ...
                ],
                'meta': {'aggregations': {'agencyId': [{'docCount': 808, 'value': 'OCC'},
                                                       {'docCount': 766, 'value': 'FDA'},
                                                       {'docCount': 690, 'value': 'CMS'},
                                                       {'docCount': 354, 'value': 'VA'},
                                                        ...],
                                         'postedDate': [{'docCount': 463,
                                                         'label': 'Today',
                                                         'fromDate': '2021-05-14 00:00:00',
                                                         'toDate': '2021-05-14 23:59:59'},
                                                        {'docCount': 749,
                                                         'label': 'Last 3 Days',
                                                         'fromDate': '2021-05-12 00:00:00',
                                                         'toDate': '2021-05-14 23:59:59'},
                                                         ...
                                                        ]},
                         'filters': {'postedDate': {'fromDate': '2021-01-01', 'toDate': '2021-01-05'},
                                     'agencyId': [{'label': 'EPA', 'value': 'EPA'}]},
                         'hasNextPage': False,
                         'hasPreviousPage': False,
                         'numberOfElements': 116,
                         'pageNumber': 1,
                         'pageSize': 250,
                         'totalElements': 116,
                         'totalPages': 1,
                         'firstPage': True,
                         'lastPage': True}
        }


## Get the JSON associated with a request to the header API:

        >>> r = get_request_json(f'https://api.regulations.gov/v4/comments',
                             api_key,
                             params={"filter[agencyId]": "EPA",
                                     "filter[postedDate][ge]": "2021-01-01",
                                     "filter[postedDate][le]": "2021-01-05",})

        >>> data = r['data']

        >>> comments_header_cols = [x for x in pd.read_sql_query('select * from comments_header', conn).columns if x != "sqltime"]

        >>> process_data(data, cols=comments_header_cols, id_col="commentId")

        [{'documentType': 'Public Submission',
          'lastModifiedDate': '2021-01-04T20:31:40Z',
          'withdrawn': False,
          'agencyId': 'EPA',
          'title': 'Comment submitted by Marisa C. Ordonia and Patti A. Goldman, Earthjustice on behalf of California Rural Legal Assistance Foundation et al. (Part 2 of 3)',
          'objectId': '0900006484955939',
          'postedDate': '2021-01-04T05:00:00Z',
          'commentId': 'EPA-HQ-OPP-2009-0209-0039'},
         {'documentType': 'Public Submission',
          ...
        ]


## Get all header info for items (e.g., comments) matching some criteria, and save to a CSV:

    >>> comments_header_cols = [x for x in pd.read_sql_query('select * from comments_header', conn).columns if x != "sqltime"]

    >>> gather_headers(api_key,
                       data_type="comments",
                       cols=comments_header_cols,
                       id_col="commentId",
                       params={"filter[agencyId]": "EPA",
                               "filter[postedDate][ge]": "2021-01-01",
                               "filter[postedDate][le]": "2021-04-30"},
                       flatfile_name="comments.csv")

    Found 7,136 comments...

    Enter outer loop (0 comments collected)...
        250 comments retrieved
        500 comments retrieved
        750 comments retrieved
        1000 comments retrieved
        ...
        5000 comments retrieved
    12:58:03 Writing 5000 records to comments.csv...

    Enter outer loop (5000 comments collected)...
        250 comments retrieved
        ...
    ...

    Finished 7,136 comments collected


## Get detailed info for items specified by ID (e.g., comments specified by commentId) and write to existing sqlite database

    >>> comments_detail_cols = [x for x in pd.read_sql_query('select * from comments_detail', conn).columns if x != "sqltime"]

    >>> comment_ids = pd.read_sql_query('select commentId from comments_header order by postedDate', conn)['commentId'].values

    >>> gather_details(api_key,
                       data_type="comments",
                       cols=comments_detail_cols,
                       id_col="commentId",
                       ids=comment_ids,
                       conn=conn)  # note: conn is the opened SQLite database; see `setup_database`

    17:47:07: Gathering details for 7,136 comments...
    Requests left: 400
    Requests left: 400
    Requests left: 300
    Requests left: 200
    Requests left: 90
    Requests left: 80
    Requests left: 80
    Requests left: 70
    Requests left: 50
    Requests left: 40
    Requests left: 30
    Requests left: 30
    Requests left: 20
    Requests left: 20
    Requests left: 9
    Requests left: 8
    Requests left: 7
    Requests left: 8
    Requests left: 5
    Requests left: 5
    Requests left: 3
    Requests left: 3
    Requests left: 2
    Requests left: 1
    17:48:37: Hit rate limits. Waiting 20 minutes to try again (attempt 1)
    18:08:37: Hit rate limits. Waiting 20 minutes to try again (attempt 2)
    18:28:37: Hit rate limits. Waiting 20 minutes to try again (attempt 3)
    18:48:46: Inserting 500 records into database...
    Requests left: 900
    Requests left: 700
    18:50:38: Inserting 500 records into database...
    Requests left: 400
    Requests left: 300
    Requests left: 200
    Requests left: 100
    Requests left: 90
    Requests left: 90
    Requests left: 80
    Requests left: 60
    Requests left: 50
    Requests left: 40
    Requests left: 30
    Requests left: 30
    Requests left: 20
    Requests left: 20
    Requests left: 10
    Requests left: 9
    Requests left: 8
    Requests left: 7
    Requests left: 6
    Requests left: 6
    Requests left: 5
    Requests left: 3
    Requests left: 4
    Requests left: 2
    Requests left: 1
    18:52:08: Hit rate limits. Waiting 20 minutes to try again (attempt 1)
    19:12:08: Hit rate limits. Waiting 20 minutes to try again (attempt 2)
    19:32:09: Hit rate limits. Waiting 20 minutes to try again (attempt 3)
    19:52:17: Inserting 500 records into database...
    Requests left: 500
    19:54:00: Inserting 500 records into database...
    Requests left: 300
    Requests left: 200
    Requests left: 100
    Requests left: 100
    ...
    
    14:35:36: Finished: 7,136 comments collected
