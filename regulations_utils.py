import sys
import os
import requests
from requests.adapters import HTTPAdapter
import sqlite3
import pandas as pd
from datetime import datetime
from dateutil import tz
import time
import csv
import urllib3

# we are ignoring the HTTPS check because the server occasionally returns malformed certificates (missing EOF)
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


class CommentsDownloader:
    """This class is used for downloading dockets, documents, and comments from Regulations.gov

    It can be used in very general ways, by getting the raw JSON from the API, or in a more common way,
    downloading the "headers" and "details" of items in bulk.

    Typically, you will instantiate this object, specifying its API key, then call either `gather_headers` or `gather_details`.

    Example:
        downloader = Comments_Downloader("DEMO_KEY")
        conn = downloader.setup_database("mycomments.db")

        downloader.gather_headers(data_type="comments",
                                  params={"filter[agencyId]": "EPA",
                                          "filter[postedDate][ge]": "2021-01-01",
                                          "filter[postedDate][le]": "2021-04-30"},
                                  conn=conn)
                                  # alternatively, specify a CSV:
                                  # csv_filename="comments.csv"

        comment_ids = pd.read_sql_query('select commentId from comments_header order by postedDate', conn)['commentId'].values

        downloader.gather_details(data_type="comments, ids=comment_ids, conn=conn)

    Note: be careful when filtering by lastModifiedDate. gather_headers and gather_details both use lastModifiedDate
    for pagination, so any filter on that will be overridden. This is an unfortunate consequence of how the Regulations.gov
    server's pagination works.
    """

    def __init__(self, api_key):
        self.api_key = api_key


    def get_requests_remaining(self):
        """Get the number of requests remaining. An API key usually gives you 1000 requests/hour.

        Returns:
            int: number of requests remaining
        """
        # this is a document that we know exists; it was chosen arbitrarily
        r = requests.get('https://api.regulations.gov/v4/documents/FDA-2009-N-0501-0012',
                        headers={'X-Api-Key': self.api_key},
                        verify=False)
        if r.status_code != 200:
            print(r.json())
            r.raise_for_status()

        return int(r.headers['X-RateLimit-Remaining'])


    def get_request_json(self, endpoint, params=None, print_remaining_requests=False,
                         wait_for_rate_limits=False, skip_duplicates=False):
        """Used to return the JSON associated with a request to the API

        Args:
            endpoint (str): URL of the API to access (e.g., https://api.regulations.gov/v4/documents)
            params (dict, optional): Parameters to specify to the endpoint request. Defaults to None, in
                which case no parameters are specified and it is assumed we are accessing the "Details" endpoint.
                If params is not None, we also append the "page[size]" parameter so that we always get
                the maximum page size of 250 elements per page.
            print_remaining_requests (bool, optional): Whether to print out the number of remaining
                requests this hour, based on the response headers. Defaults to False.
            wait_for_rate_limits (bool, optional): Determines whether to wait to re-try if we run out of
                requests in a given hour. Defaults to False.
            skip_duplicates (bool, optional): If a request returns multiple items when only 1 was expected,
                should we skip that request? Defaults to False.

        Returns:
            dict: JSON-ified request response
        """

        # Our API key has a rate limit of 1,000 requests/hour. If we hit that limit, we can
        # retry every WAIT_MINUTES minutes (more frequently than once an hour, in case our request limit
        # is updated sooner). We will sleep for POLL_SECONDS seconds at a time to see if we've been
        # interrupted. Otherwise we'd have to wait a while before getting interrupted. We could do this
        # with threads, but that gets more complicated than it needs to be.
        STATUS_CODE_OVER_RATE_LIMIT = 429
        WAIT_MINUTES = 20  # time between attempts to get a response
        POLL_SECONDS = 10  # run time.sleep() for this long, so we can check if we've been interrupted

        # Rather than do requests.get(), use this approach to (attempt to) gracefully handle noisy connections to the server
        # We sometimes get SSL errors (unexpected EOF or ECONNRESET), so this should hopefully help us retry.
        session = requests.Session()
        session.mount('https', HTTPAdapter(max_retries=8))

        def poll_for_response(api_key, else_func):
            if params is not None:  # querying the search endpoint (e.g., /documents)
                r = session.get(endpoint,
                                headers={'X-Api-Key': api_key},
                                params={**params,
                                        'page[size]': 250}, # always get max page size
                                verify=False)
            else:  # querying the "detail" endpoint (e.g., /documents/{documentId})
                r = session.get(endpoint, headers={'X-Api-Key': api_key}, verify=False)

            if r.status_code == 200:
                # SUCCESS! Return the JSON of the request
                num_requests_left = int(r.headers['X-RateLimit-Remaining'])
                if print_remaining_requests or \
                    (num_requests_left < 10) or \
                    (num_requests_left <= 100 and num_requests_left % 10 == 0) or \
                    (num_requests_left % 100 == 0 and num_requests_left < 1000):
                    print(f"(Requests left: {r.headers['X-RateLimit-Remaining']})")

                return [True, r.json()]
            else:
                if r.status_code == STATUS_CODE_OVER_RATE_LIMIT and wait_for_rate_limits:
                    else_func()
                elif self._is_duplicated_on_server(r.json()) and skip_duplicates:
                    print("****Duplicate entries on server. Skipping.")
                    print(r.json()['errors'][0]['detail'])
                else:  # some other kind of error
                    print([r, r.status_code])
                    print(r.json())
                    r.raise_for_status()

            return [False, r.json()]

        def wait_for_requests():
            the_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            print(f'{the_time}: Hit rate limits. Waiting {WAIT_MINUTES} minutes to try again', flush=True)
            # We ran out of requests. Wait for WAIT_MINUTES minutes, but poll every POLL_SECONDS seconds for interruptions
            for i in range(int(WAIT_MINUTES * 60 / POLL_SECONDS)):
                time.sleep(POLL_SECONDS)

        for _ in range(1, int(60 / WAIT_MINUTES) + 3):
            success, r_json = poll_for_response(self.api_key, wait_for_requests)

            if success or (self._is_duplicated_on_server(r_json) and skip_duplicates):
                return r_json

        print(r_json)
        raise RuntimeError(f"Unrecoverable error; {r_json}")


    def get_items_count(self, data_type, params):
        """Gets the number of items returned by a request in the totalElements attribute.

        Args:
            data_type (str): One of "dockets", "documents", or "comments".
            params (dict): Parameters to specify to the endpoint request for the query. See details
                on available parameters at https://open.gsa.gov/api/regulationsgov/.

        Returns:
            int: Number of items returned by request
        """
        # make sure the data_type is plural
        data_type = data_type if data_type[-1:] == "s" else data_type + "s"

        r_items = self.get_request_json(f'https://api.regulations.gov/v4/{data_type}', params=params)
        totalElements = r_items['meta']['totalElements']
        return totalElements


    def gather_headers(self, data_type, params, db_filename=None, csv_filename=None, max_items=None, verbose=True):
        """This function is meant to get the header data for the item returned by the query defined by
        params. The API returns these data in "pages" of up to 250 items at a time, and up to 20 pages are
        available per query. If the query would return more than 250*20 = 5000 items, the recommended way
        to retrieve the full dataset is to sort the data by lastModifiedDate and save the largest value
        from the last page of a given query, then use that to filter the next batch to all those with a
        lastModifiedDate greater than or equal to the saved date. Unfortunately, this also means it's
        you'll retrieve some of the same headers multiple times, but this is unavoidable because there is no
        uniqueness constraint on lastModifiedDate.

        The data retrieved are output either to a database (db_filename), or a CSV (csv_filename),
        or both. These data do not include more specific detail that would be retrieved in a "Details" query,
        which returns that data (e.g., plain-text of a comment). That kind of data can be gathered
        using the gather_details function below.

        An example call is:
            gather_headers(data_type='comments', db_filename="comments_2020", params={'filter[postedDate][ge]': '2020-01-01'})

        Args:
            data_type (str): One of "dockets", "documents", or "comments".
            params (dict): Parameters to specify to the endpoint request for the query. See details
                on available parameters at https://open.gsa.gov/api/regulationsgov/.
            db_filename (str): Name (optionally with path) of the sqlite database to write to. If it doesn't yet exist,
                it will be created automatically. If it does exist, we will add to it. Can be None, in which
                case a CSV file should be specified.
            csv_filename (str): Name (optionally with path) of the CSV file to write to. Can be None, in which
                case a database file should be specified.
            max_items (int, optional): If this is specified, limits to this many items. Note that this
                is an *approximate* limit. Because of how we have to query with pagination, we will inevitably
                end up with duplicate records being pulled, so we will hit this limit sooner than we should,
                but we shouldn't be off by very much. Defaults to None.
            verbose (bool, optional): Whether to print more detailed info. Defaults to True.
        """

        if db_filename is None and csv_filename is None:
            raise ValueError("Must specify either a database file name or CSV filename")

        # make sure the data_type is plural
        data_type = data_type if data_type[-1:] == "s" else data_type + "s"

        n_retrieved = 0
        prev_query_max_date = '1900-01-01 00:00:00'  # placeholder value for first round of 5000
        EASTERN_TIME = tz.gettz('America/New_York')

        # remove the trailing s before adding "Id"; e.g., "dockets" --> "docketId"
        id_col = data_type[:len(data_type)-1] + "Id"

        if db_filename is not None:
            conn = self._get_database_connection(db_filename)
            cur = conn.cursor()
        else:
            conn = cur = None

        # first request, to ensure there are documents and to get a total count
        totalElements = self.get_items_count(data_type, params)
        print(f'Found {totalElements} {data_type}...', flush=True)

        if max_items is not None and max_items < totalElements:
            print(f'...but limiting to {max_items} {data_type}...', flush=True)
            totalElements = max_items

        while n_retrieved < totalElements:
            # loop over 5000 in each request (20 pages of 250 each)
            if verbose: print(f'\nEnter outer loop ({n_retrieved} {data_type} collected)...', flush=True)
            page = 1
            data = []

            while (n_retrieved < totalElements) and (page == 1 or (not r_items['meta']['lastPage'])):
                ## note: this will NOT lead to an off-by-one error because at the start of the loop
                # r_items is from the *previous* request. If the *previous* request was the last page
                # then we exit the loop (unless we're on the first page, in which case get the data then exit)
                retries = 5
                while retries > 0:
                    try:
                        r_items = self.get_request_json(f'https://api.regulations.gov/v4/{data_type}',
                                                        params={**params,
                                                                'filter[lastModifiedDate][ge]': prev_query_max_date,
                                                                'page[number]': str(page),
                                                                'sort': f'lastModifiedDate'},
                                                        wait_for_rate_limits=True)
                        break
                    except:
                        retries -= 1

                n_retrieved += len(r_items['data'])
                data.extend(r_items['data'])  # add all items from this request
                page += 1

                ## There may be duplicates due to pagination, so the commented out code here doesn't apply,
                ## but I'm leaving it in so I know not to "fix" this issue later on.
                #if n_retrieved > totalElements:
                #    data = data[:-(n_retrieved - totalElements)]  # remove the extras
                #    assert len(data) == totalElements
                #    n_retrieved = totalElements

                if verbose: print(f'    {n_retrieved} {data_type} retrieved', flush=True)

            # get our query's final record's lastModifiedDate, and convert to eastern timezone for filtering via URL
            prev_query_max_date = r_items['data'][-1]['attributes']['lastModifiedDate'].replace('Z', '+00:00')
            prev_query_max_date = datetime.fromisoformat(prev_query_max_date).astimezone(EASTERN_TIME).strftime('%Y-%m-%d %H:%M:%S')

            data = self._get_processed_data(data, id_col)
            self._output_data(data,
                              table_name=(data_type + "_header"),
                              conn=conn,
                              cur=cur,
                              csv_filename=csv_filename)

        # Note: the count in n_retrieved may not reflect what's in the database because there may be
        # duplicates downloaded along the way due to the pagination mechanism on Regulations.gov's API.
        # The sqlite database uses a unique constraint to avoid duplicates, so the final count printed
        # below may not match what is shown in the database. For CSVs, the count here should match
        # the number of rows in the output.

        self._close_database_connection(conn)
        the_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        print(f'{the_time}: Finished: {n_retrieved} {data_type} collected', flush=True)


    def gather_details(self, data_type, ids, db_filename=None, csv_filename=None, insert_every_n_rows=500, skip_duplicates=True):
        """This function is meant to get the Details data for each item in ids, one at a time. The data
        for each item is output either to a database (specified by db_filename) or a CSV (specified by csv_filename).

        An example call is:
            gather_details(data_type='documents', cols=documents_cols, id_col='documentId', ids=document_ids, csv_filename="documents_2020.csv")

        Args:
            data_type (str): One of "dockets", "documents", or "comments".
            ids (list of str): List of IDs for items for which you are querying details. These IDs are
                appended to the URL directly, e.g., https://api.regulations.gov/v4/comments/FWS-R8-ES-2008-0006-0003
            db_filename (str): Name (optionally with path) of the sqlite database to write to. If it doesn't yet exist,
                it will be created automatically. If it does exist, we will add to it. Can be None, in which
                case a CSV should be specified.
            csv_filename (str): Name (optionally with path) of the CSV file to write to. Can be None, in which
                case a database file should be specified.
            insert_every_n_rows (int): How often to write to the database or CSV. Defaults to every 500 rows.
            skip_duplicates (bool, optional): If a request returns multiple items when only 1 was expected,
                should we skip that request? Defaults to True.

        """
        if db_filename is None and csv_filename is None:
            raise ValueError("Must specify either a database file name or CSV filename")

        # make sure the data_type is plural
        data_type = data_type if data_type[-1:] == "s" else data_type + "s"

        n_retrieved = 0
        data = []

        # remove the trailing s before adding "Id"; e.g., "dockets" --> "docketId"
        id_col = data_type[:len(data_type)-1] + "Id"

        if db_filename is not None:
            conn = self._get_database_connection(db_filename)
            cur = conn.cursor()
        else:
            conn = cur = None

        the_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        print(f'{the_time}: Gathering details for {len(ids)} {data_type}...', flush=True)

        for item_id in ids:
            r_item = self.get_request_json(f'https://api.regulations.gov/v4/{data_type}/{item_id}',
                                           wait_for_rate_limits=True,
                                           skip_duplicates=skip_duplicates)

            if(skip_duplicates and self._is_duplicated_on_server(r_item)):
                print(f"Skipping for {item_id}\n")
                continue

            n_retrieved += 1
            data.append(r_item['data'])  # only one item from the Details endpoint, not a list, so use append (not extend)

            if n_retrieved > 0 and n_retrieved % insert_every_n_rows == 0:
                data = self._get_processed_data(data, id_col)
                self._output_data(data,
                                  table_name=(data_type + "_detail"),
                                  conn=conn,
                                  cur=cur,
                                  csv_filename=csv_filename)
                data = []  # reset for next batch

        if len(data) > 0:  # insert any remaining in final batch
            data = self._get_processed_data(data, id_col)
            self._output_data(data,
                              table_name=(data_type + "_detail"),
                              conn=conn,
                              cur=cur,
                              csv_filename=csv_filename)

        self._close_database_connection(conn)
        the_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        print(f'{the_time}: Finished: {n_retrieved} {data_type} collected', flush=True)


    def gather_comments_by_document(self, document_id, db_filename=None, csv_filename=None):
        """User-friendly function for downloading all of the comments on a single document, using
        the documentId visible on the Regulations.gov website. This abstracts away all the details around
        filtering and paginating through the API and downloads the data into either a CSV or sqlite database
        or both.

        Note that if a database is used (i.e., db_filename is not None), the "header" information for comments 
        will be saved, in addition to the "details" of each comment. In other words, the table comments_header 
        will be populated in addition to comments_detail.

        Args:
            document_id (str): document ID, as visible in either the URL or on the website. Note, this is
                distinct from the docket ID and from the API's internal objectId.
            db_filename (str): Name (optionally with path) of the sqlite database to write to. If it doesn't yet exist,
                it will be created automatically. If it does exist, we will add to it. Can be None, in which
                case a CSV should be specified.
            csv_filename (str): Name (optionally with path) of the CSV file to write to. Can be None, in which
                case a database file should be specified.
        """
        if db_filename is None and csv_filename is None:
            raise ValueError("Need to specify either a database filename or CSV filename or both")

        def get_object_id(document_id):
            # first, get the objectId for the document, which we use to filter to its comments
            the_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            print(f"{the_time}: Getting objectId for document {document_id}...", end="", flush=True)

            r_json = self.get_request_json(f'https://api.regulations.gov/v4/documents/{document_id}')
            object_id = r_json['data']['attributes']['objectId']

            print(f"Got it ({object_id})", flush=True)
            return object_id
        
        def get_comment_ids(object_id):
            # We need to create a temporary CSV so we can read back in the commentIds. This is because the
            # comment headers do not include the associated documentId or objectId, so if we append the 
            # comment headers to an existing file or database, we won't be able to tell which comments
            # correspond to this document.
            the_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            print(f"{the_time}: Getting comment headers associated with document {document_id}...\n", flush=True)

            temp_filename = f"comment_headers_{datetime.now().strftime('%H%M%S')}.csv"
            self.gather_headers(data_type="comments", 
                                params={'filter[commentOnId]': object_id}, 
                                db_filename=db_filename,
                                csv_filename=temp_filename,
                                verbose=False)
            
            # if file didn't get created, we found 0 comments
            if os.path.isfile(temp_filename):
                comment_ids = self.get_ids_from_csv(temp_filename, "comments", unique=True)

                try:
                    os.remove(temp_filename)
                except:
                    pass
            else:
                return []

            print("\nDone getting comment IDs----------------\n", flush=True)
            return comment_ids

        object_id = get_object_id(document_id)
        comment_ids = get_comment_ids(object_id)

        if len(comment_ids) > 0:
            the_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            print(f"{the_time}: Getting comments associated with document {document_id}...\n", flush=True)

            self.gather_details("comments", comment_ids, db_filename=db_filename, csv_filename=csv_filename)

            # Get the total number of comments retrieved. This may differ from what we expect if there 
            # are issues during the download process or the database prevents importing duplicates from pagination.
            n_comments = self._get_comment_count(csv_filename, db_filename, "commentOnDocumentId", document_id)
        else:
            n_comments = 0

        print(f"\nDone getting all {n_comments} comments for document {document_id}----------------\n", flush=True)


    def gather_comments_by_docket(self, docket_id, db_filename=None, csv_filename=None):
        """User-friendly function for downloading all of the comments in a docket, using the docketId visible 
        on the Regulations.gov website. This abstracts away all the details around finding all the documents
        in a given docket and getting their individual comments, including filtering and paginating through 
        the API. It downloads the comments into either a CSV or sqlite database or both.

        Note that if a database is used (i.e., db_filename is not None), the "header" information for documents
        and comments will be saved, in addition to the "details" of each comment. In other words, the table 
        comments_header will be populated in addition to comments_detail, and the table documents_header will
        be populated as well.

        Args:
            document_id (str): document ID, as visible in either the URL or on the website. Note, this is
                distinct from the docket ID and from the API's internal objectId.
            db_filename (str): Name (optionally with path) of the sqlite database to write to. If it doesn't yet exist,
                it will be created automatically. If it does exist, we will add to it. Can be None, in which
                case a CSV should be specified.
            csv_filename (str): Name (optionally with path) of the CSV file to write to. Can be None, in which
                case a database file should be specified.
        """
        if db_filename is None and csv_filename is None:
            raise ValueError("Need to specify either a database filename or CSV filename or both")

        def get_document_ids(docket_id): 
            the_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            print(f"{the_time}: Getting documents associated with docket...\n", flush=True)
       
            temp_filename = f"document_headers_{datetime.now().strftime('%H%M%S')}.csv"
            self.gather_headers(data_type="documents", 
                                params={'filter[docketId]': docket_id}, 
                                db_filename=db_filename,
                                csv_filename=temp_filename,
                                verbose=False)
            document_ids = self.get_ids_from_csv(temp_filename, "documents", unique=True)
            try:
                os.remove(temp_filename)
            except:
                pass

            print(f"\nDone----------------\n", flush=True)
            return document_ids

        document_ids = get_document_ids(docket_id)

        for document_id in document_ids:
            the_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            print(f"******************************\n{the_time}: Getting comments for document {document_id}...\n", flush=True)
            self.gather_comments_by_document(document_id, db_filename, csv_filename)

        # get the total number of comments retrieved
        n_comments = self._get_comment_count(csv_filename, db_filename, "docketId", docket_id)
        print(f"DONE retrieving all {n_comments} comments from {len(document_ids)} document(s) for docket {docket_id}----------------\n", flush=True)


    def get_ids_from_csv(self, csv_filename, data_type, unique=False):
        """Get IDs for dockets, documents, or comments in a given CSV. Assumes that the header row
        exists in the file and that the ID column is named one of docketId, documentId, or commentId.

        Note: the CSV could be very large, so we don't load the whole thing into memory, but instead
        loop over it one row at a time.

        Args:
            csv_filename (str): Name (optionally with path) of the CSV file with the data
            data_type (str): One of "dockets", "documents", or "comments".
            unique (bool, optional): Whether to remove duplicates, making the list of IDs unique.
                Defaults to False so that the IDs are returned in the same order and number as the
                input file.

        Returns:
            list of str: IDs for the given data_type from the specified csv_filename
        """
        # make sure the data_type is NOT plural before adding Id
        id_column = (data_type[:-1] if data_type[-1:] == "s" else data_type) + "Id"
        id_column_index = None
        ids = []

        with open(csv_filename, 'r', encoding='utf8') as f:
            reader = csv.reader(f)
            for row in reader:
                if id_column_index is None:
                    try:
                        id_column_index = row.index(id_column)
                    except ValueError:
                        raise ValueError(f"Missing id column {id_column} in {csv_filename}")
                else:
                    ids.append(row[id_column_index])

        if unique:
            ids = list(set(ids))

        return ids


    def _get_database_connection(self, filename, drop_if_exists=False):
        """Get a connection to the database in the file at filename. If the database does not
        exist it will be created with the necessary tables. If it does exist, tables are kept as-is
        unless drop_if_exists is specified, in which case existing tables are dropped before creating
        the necessary tables.

        Args:
            filename (str): Filename of database, optionally including path.
            drop_if_exists (bool, optional): Whether to drop the necessary tables if they exist.
                Defaults to False, in which case if the tables exist, they will be left as-is and
                new data will be appended.

        Returns:
            sqlite.Connection: open connection to the database
        """
        # If the database exists already, this just ensures all the necessary tables exist
        self._setup_database(filename, drop_if_exists=drop_if_exists)
        return sqlite3.connect(filename)


    def _setup_database(self, filename=None, drop_if_exists=False):
        """Set up a sqlite database with the tables and columns necessary for the data returned
        by the Regulations.gov API.

        Args:
            filename (str): Filename, optionally including path.
            drop_if_exists (bool, optional): Whether to drop the six tables used here if they already exist.
                Defaults to False so that we don't delete any information.
        """
        if filename is None:
            filename = 'regulations.gov_' + datetime.now().strftime('%Y%m%d') + ".db"

        # make the path if necessary
        if len(os.path.dirname(filename)) > 0:
            os.makedirs(os.path.dirname(filename), exist_ok=True)

        conn = sqlite3.connect(filename)
        cur = conn.cursor()

        if drop_if_exists:
            cur.execute('drop table if exists dockets_header')
            cur.execute('drop table if exists dockets_detail')
            cur.execute('drop table if exists documents_header')
            cur.execute('drop table if exists documents_detail')
            cur.execute('drop table if exists comments_header')
            cur.execute('drop table if exists comments_detail')

        cur.execute("""
        CREATE TABLE IF NOT EXISTS dockets_header (
            docketId            TEXT    NOT NULL UNIQUE,
            agencyId            TEXT,
            docketType          TEXT,
            title               TEXT,
            lastModifiedDate    TEXT NOT NULL,
            objectId            TEXT,
            sqltime             TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )""")


        cur.execute("""
        CREATE TABLE IF NOT EXISTS dockets_detail (
            docketId        TEXT    NOT NULL UNIQUE,
            agencyId        TEXT,
            category        TEXT,
            dkAbstract      TEXT,
            docketType      TEXT,
            effectiveDate   TEXT,
            field1          TEXT,
            field2          TEXT,
            generic         TEXT,
            keywords        TEXT,
            legacyId        TEXT,
            modifyDate      TEXT NOT NULL,
            objectId        TEXT,
            organization    TEXT,
            petitionNbr     TEXT,
            program         TEXT,
            rin             TEXT,
            shortTitle      TEXT,
            subType         TEXT,
            subType2        TEXT,
            title           TEXT,
            sqltime         TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )""")

        cur.execute("""
        CREATE TABLE IF NOT EXISTS documents_header (
            documentId          TEXT    NOT NULL UNIQUE,
            commentEndDate      TEXT,
            commentStartDate    TEXT,
            docketId            TEXT,
            documentType        TEXT,
            frDocNum            TEXT,
            lastModifiedDate    TEXT NOT NULL,
            objectId            TEXT,
            postedDate          TEXT,
            subtype             TEXT,
            title               TEXT,
            withdrawn           INTEGER,
            sqltime             TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )""")

        cur.execute("""
        CREATE TABLE IF NOT EXISTS documents_detail (
            documentId              TEXT    NOT NULL UNIQUE,
            additionalRins          TEXT,
            agencyId                TEXT,
            allowLateComments       INTEGER,
            authorDate              TEXT,
            authors                 TEXT,
            category                TEXT,
            cfrPart                 TEXT,
            city                    TEXT,
            comment                 TEXT,
            commentEndDate          TEXT,
            commentStartDate        TEXT,
            country                 TEXT,
            docAbstract             TEXT,
            docketId                TEXT,
            documentType            TEXT,
            effectiveDate           TEXT,
            exhibitLocation         TEXT,
            exhibitType             TEXT,
            field1                  TEXT,
            field2                  TEXT,
            firstName               TEXT,
            frDocNum                TEXT,
            frVolNum                TEXT,
            govAgency               TEXT,
            govAgencyType           TEXT,
            implementationDate      TEXT,
            lastName                TEXT,
            legacyId                TEXT,
            media                   TEXT,
            modifyDate              TEXT NOT NULL,
            objectId                TEXT,
            ombApproval             TEXT,
            openForComment          INTEGER,
            organization            TEXT,
            originalDocumentId      TEXT,
            pageCount               TEXT,
            paperLength             INTEGER,
            paperWidth              INTEGER,
            postedDate              TEXT,
            postmarkDate            TEXT,
            reasonWithdrawn         TEXT,
            receiveDate             TEXT,
            regWriterInstruction    TEXT,
            restrictReason          TEXT,
            restrictReasonType      TEXT,
            sourceCitation          TEXT,
            startEndPage            TEXT,
            stateProvinceRegion     TEXT,
            subject                 TEXT,
            submitterRep            TEXT,
            submitterRepCityState   TEXT,
            subtype                 TEXT,
            title                   TEXT,
            topics                  TEXT,
            trackingNbr             TEXT,
            withdrawn               INTEGER,
            zip                     TEXT,
            sqltime                 TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )""")

        cur.execute("""
        CREATE TABLE IF NOT EXISTS comments_header (
            commentId               TEXT    NOT NULL UNIQUE,
            agencyId                TEXT,
            documentType            TEXT,
            lastModifiedDate        TEXT NOT NULL,
            objectId                TEXT,
            postedDate              TEXT,
            title                   TEXT,
            withdrawn               INTEGER,
            sqltime                 TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL
        )""")

        cur.execute("""
        CREATE TABLE IF NOT EXISTS comments_detail (
            commentId               TEXT    NOT NULL UNIQUE,
            agencyId                TEXT,
            category                TEXT,
            city                    TEXT,
            comment                 TEXT,
            commentOn               TEXT,
            commentOnDocumentId     TEXT,
            country                 TEXT,
            docAbstract             TEXT,
            docketId                TEXT,
            documentType            TEXT,
            duplicateComments       INTEGER,
            field1                  TEXT,
            field2                  TEXT,
            firstName               TEXT,
            govAgency               TEXT,
            govAgencyType           TEXT,
            lastName                TEXT,
            legacyId                TEXT,
            modifyDate              TEXT NOT NULL,
            objectId                TEXT,
            openForComment          INTEGER,
            organization            TEXT,
            originalDocumentId      TEXT,
            pageCount               TEXT,
            postedDate              TEXT,
            postmarkDate            TEXT,
            reasonWithdrawn         TEXT,
            receiveDate             TEXT,
            restrictReason          TEXT,
            restrictReasonType      TEXT,
            stateProvinceRegion     TEXT,
            submitterRep            TEXT,
            submitterRepCityState   TEXT,
            subtype                 TEXT,
            title                   TEXT,
            trackingNbr             TEXT,
            withdrawn               INTEGER,
            zip                     TEXT,
            sqltime                 TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )""")

        conn.close()


    def _close_database_connection(self, conn):
        """Close a database connection

        Args:
            conn (sqlite3.Connection): Try to close the connection. If there are any errors, ignore them.
        """
        if conn is not None and type(conn) == sqlite3.Connection:
            try:
                conn.close()
            except:
                pass


    def _is_duplicated_on_server(self, response_json):
        """Used to determine whether a given response indicates a duplicate on the server. This is
        because there is a bug in the server: there are some commentIds, like NRCS-2009-0004-0003,
        which correspond to multiple actual comments! This function determines whether the
        returned JSON has an error indicating this issue

        Args:
            response_json (dict): JSON from request to API (usually, from get_request_json)

        Returns:
            bool: whether the response indicates a duplicate issue or not
        """
        return ('errors' in response_json.keys()) \
                and (response_json['errors'][0]['status'] == "500") \
                and (response_json['errors'][0]['detail'][:21] == "Incorrect result size")


    def _get_comment_count(self, csv_filename=None, db_filename=None, filter_column=None, filter_value=None):
        """Simple helper function used to get the number of comments retrieved, as stored in either
        a CSV file or a sqlite database.

        Args:
            csv_filename (str): File name (optionally with path) where comments are stored. Defaults to 
                None, in which case a db_filename should be specified.
            db_filename (str): File name (optionally with path) where database, containing comments, is located.
                Defaults to None, in which case a csv_filename should be specified.
            filter_column (str): Identifies the column used to filter the database to get the count. Defaults to 
                None for the case when we are using a CSV.
            filter_value (str): The value used in filter_column to filter the database to get the count. Defaults to 
                None for the case when we are using a CSV.

        Returns:
            int: Number of comments stored in either comments_detail (contained in the database db_filename) or the CSV
        """
        if csv_filename is None and (db_filename is None or filter_column is None or filter_value is None):
            raise ValueError("Must specify either a csv_filename or a db_filename and its filter_column and filter_value")

        if db_filename is not None:
            conn = sqlite3.connect(db_filename)
            cur = conn.cursor()
            n_comments = cur.execute(f"select count(*) from comments_detail where {filter_column}=?", (filter_value,)).fetchone()[0]
            conn.close()
        else:
            n_comments = len(self.get_ids_from_csv(csv_filename, "comments"))
        
        return n_comments


    def _get_processed_data(self, data, id_col):
        """Used to take the data contained in a response (e.g., the data for a bunch of comments)
        and remove unnecessary columns (i.e., those not specified in `cols`). Also adds the ID
        associated with the items and flattens lists contained in each item's data.

        Args:
            data (list of dict): List of items to process from a request (e.g., a bunch of comments).
                Each dict is expected to be formatted like: {'id': '...', 'attributes': {'attrib1': 'data', ...}, <other keys:values>}
            id_col (str): Name of the ID column for this data type, i.e., 'docketId', 'documentId', or 'commentId'

        Returns:
            list of dict: processed dataset, ready for input into sqlite or output to CSV
        """
        output = []
        cols = [x for x in data[0]['attributes'].keys() if x not in \
                    ['id', 'displayProperties', 'highlightedContent', 'fileFormats']]

        for item in data:
            # get just the dict of columns we want, and if one of the values is a list, flatten it
            out = {k:(' '.join(v) if type(v) == list else v) for (k,v) in item['attributes'].items() if k in cols}

            # also, the item's ID
            out[id_col] = item['id']
            output.append(out)

        return output


    def _insert_data(self, data, table_name, conn, cur=None):
        """Add data to a specified sqlite table

        Args:
            data (list of dict): Data to be inserted into database
            table_name (str): specifies table to insert into (one of: "dockets_header", "dockets_detail",
                "documents_header", "documents_detail", "comments_header", or "comments_detail")
            conn (sqlite3.Connection): Open connection to database
            cur (sqlite3.Cursor): Open cursor into the database
        """
        # upload into staging table, then insert, skipping any rows that violate key constraints
        if conn is None:
            raise ValueError("conn cannot be None")
        if table_name is None:
            raise ValueError("Need to specify table_name")
        if cur is None:
            cur = conn.cursor()

        the_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        cols = [x for x in pd.read_sql_query(f'select * from {table_name} limit 1', conn).columns if x != "sqltime"]

        print(f"{the_time}: Inserting {len(data)} records into database...", flush=True)
        pd.DataFrame(data).to_sql("tmp", conn, if_exists="replace", index=False)
        cur.execute(f"INSERT OR IGNORE INTO {table_name} ({','.join(cols)}) SELECT {','.join(cols)} FROM tmp")
        conn.commit()


    def _write_to_csv(self, data, csv_filename):
        """Write out data to a CSV file. Data will be appended to an existing file, or if the file does
        not exist, the file will be created with headers. Subsequent appends do not include the header row.

        Args:
            data (list of dict): Data to write out
            csv_filename (str): Name (optionally with path) of the CSV file to write to
        """
        if csv_filename is None:
            raise ValueError("csv_filename cannot be None")

        the_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        print(f"{the_time}: Writing {len(data)} records to {csv_filename}...", end="", flush=True)

        df = pd.DataFrame(data)

        # remove line breaks in each field so that the rows of the CSV correspond to one record
        df.replace(r"\n", " ", regex=True, inplace=True)

        # make the path if necessary
        if len(os.path.dirname(csv_filename)) > 0:
            os.makedirs(os.path.dirname(csv_filename), exist_ok=True)

        df.to_csv(csv_filename, index=False, mode='a', quoting=csv.QUOTE_ALL,
                  header=(not os.path.isfile(csv_filename)))

        print("Done", flush=True)


    def _output_data(self, data, table_name=None, conn=None, cur=None, csv_filename=None):
        """Routes the output call to either database or the CSV, depending on parameters

        Args:
            data (list of dict): Data to write out
            table_name (str): For sqlite database, specifies table to insert into (one of: "dockets_header", "dockets_detail",
                "documents_header", "documents_detail", "comments_header", or "comments_detail"). Can be None if using CSV.
            conn (sqlite3.Connection): Open connection to database. Can be None, in which case a CSV should be specified.
                Can be None if using a CSV.
            cur (sqlite3.Cursor): Open cursor into the database. Can be None, in which case a CSV should be specified.
                Can be None if using a CSV.
            csv_filename (str): Name (optionally with path) of the CSV file to write to. Can be None, in which
                case a database file should be specified.
        """
        if conn is None and csv_filename is None:
            raise ValueError("Need to specify either conn or csv_filename")

        if conn is not None:
            self._insert_data(data, table_name, conn, cur)

        if csv_filename is not None:
            self._write_to_csv(data, csv_filename)
