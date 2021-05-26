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
                                  # alternatively, specify a flatfile: 
                                  # flatfile_name="comments.csv"

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


    def is_duplicated_on_server(self, response_json):
            # there is a bug in the server: there are some commentIds, like NRCS-2009-0004-0003, 
            # which correspond to multiple actual comments! This function determines whether the
            # returned JSON has an error indicating this issue
            return ('errors' in response_json.keys()) \
                    and (response_json['errors'][0]['status'] == "500") \
                    and (response_json['errors'][0]['detail'][:21] == "Incorrect result size")


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
                    print(f"Requests left: {r.headers['X-RateLimit-Remaining']}")

                return [True, r.json()]
            else:
                if r.status_code == STATUS_CODE_OVER_RATE_LIMIT and wait_for_rate_limits:
                    else_func()
                elif self.is_duplicated_on_server(r.json()) and skip_duplicates:
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

            if success or (self.is_duplicated_on_server(r_json) and skip_duplicates):
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


    def _get_database_connection(self, filename=None, drop_if_exists=False):
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


    def gather_headers(self, data_type, params, max_items=None, conn=None, flatfile_name=None):
        """This function is meant to get the header data for the item returned by the query defined by 
        params. The API returns these data in "pages" of up to 250 items at a time, and up to 20 pages are
        available per query. If the query would return more than 250*20 = 5000 items, the recommended way
        to retrieve the full dataset is to sort the data by lastModifiedDate and save the largest value
        from the last page of a given query, then use that to filter the next batch to all those with a 
        lastModifiedDate greater than or equal to the saved date. Unfortunately, this also means it's
        you'll retrieve some of the same headers multiple times, but this is unavoidable because there is no
        uniqueness constraint on lastModifiedDate.

        The data retrieved are output either to a database (specified by conn) or a flatfile 
        (specified by flatfile_name). These data do not include more specific detail that would be 
        retrieved in a "Details" query, which returns that data (e.g., plain-text of a comment). 
        That kind of data can be gathered using the gather_details function below. 
        
        An example call is:
            gather_headers(data_type='comments', conn=conn, params={'filter[postedDate][ge]': '2020-01-01'})

        Args:
            data_type (str): One of "dockets", "documents", or "comments".
            params (dict): Parameters to specify to the endpoint request for the query. See details 
                on available parameters at https://open.gsa.gov/api/regulationsgov/.
            max_items (int, optional): If this is specified, limits to this many items. Note that this
                is an *approximate* limit. Because of how we have to query with pagination, we will inevitably
                end up with duplicate records being pulled, so we will hit this limit sooner than we should,
                but we shouldn't be off by very much. Defaults to None.
            conn (sqlite3.Connection): Open connection to database. Can be None, in which case a flat file should be specified
            flatfile_name (str): Name (optionally with path) of the CSV file to write to. Can be None, in which 
                case a connection should be specified.

        Raises:
            ValueError: [description]
        """

        if conn is None and flatfile_name is None:
            raise ValueError("Must specify either a connection (conn) or the name of a file to write to (flatfile)")

        # make sure the data_type is plural
        data_type = data_type if data_type[-1:] == "s" else data_type + "s"

        n_retrieved = 0
        prev_query_max_date = '1900-01-01 00:00:00'  # placeholder value for first round of 5000
        EASTERN_TIME = tz.gettz('America/New_York')
        
        # remove the trailing s before adding "Id"; e.g., "dockets" --> "docketId"
        id_col = data_type[:len(data_type)-1] + "Id"

        cur = None if conn is None else conn.cursor()

        # first request, to ensure there are documents and to get a total count
        totalElements = self.get_items_count(data_type, params)
        print(f'Found {totalElements} {data_type}...', flush=True)

        if max_items is not None and max_items < totalElements:
            print(f'...but limiting to {max_items} {data_type}...', flush=True)
            totalElements = max_items

        while n_retrieved < totalElements:
            # loop over 5000 in each request (20 pages of 250 each)
            print(f'\nEnter outer loop ({n_retrieved} {data_type} collected)...', flush=True)
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

                print(f'    {n_retrieved} {data_type} retrieved', flush=True)

            # get our query's final record's lastModifiedDate, and convert to eastern timezone for filtering via URL
            prev_query_max_date = r_items['data'][-1]['attributes']['lastModifiedDate'].replace('Z', '+00:00')
            prev_query_max_date = datetime.fromisoformat(prev_query_max_date).astimezone(EASTERN_TIME).strftime('%Y-%m-%d %H:%M:%S')

            data = self._get_processed_data(data, id_col)
            self._output_data(data, 
                              table_name=(data_type + "_header"), 
                              conn=conn, 
                              cur=cur, 
                              flatfile_name=flatfile_name)

        # this may not reflect what's in the database because of unique constraint; due to pagination,
        # there may be duplicates downloaded along the way
        print(f'\nFinished: {n_retrieved} {data_type} collected', flush=True)


    def gather_details(self, data_type, ids, conn=None, flatfile_name=None, insert_every_n_rows=500, skip_duplicates=True):
        """This function is meant to get the Details data for each item in ids, one at a time. The data 
        for each item is output either to a database (specified by conn) or a flatfile (specified by flatfile_name). 
        
        An example call is:
            gather_details(data_type='documents', cols=documents_cols, id_col='documentId', ids=document_ids, conn=conn)

        Args:
            data_type (str): One of "dockets", "documents", or "comments".
            ids (list of str): List of IDs for items for which you are querying details. These IDs are
                appended to the URL directly, e.g., https://api.regulations.gov/v4/comments/FWS-R8-ES-2008-0006-0003
            conn (sqlite3.Connection): Open connection to database. Can be None, in which case a flat file should be specified
            flatfile_name (str): Name (optionally with path) of the CSV file to write to. Can be None, in which 
                case a connection should be specified.
            insert_every_n_rows (int): How often to write to the database or flat file. Defaults to every 500 rows.
            skip_duplicates (bool, optional): If a request returns multiple items when only 1 was expected,
                should we skip that request? Defaults to True.

        """
        if conn is None and flatfile_name is None:
            raise ValueError("Must specify either a connection (conn) or the name of a file to write to (flatfile)")

        # make sure the data_type is plural
        data_type = data_type if data_type[-1:] == "s" else data_type + "s"

        n_retrieved = 0
        data = []

        cur = None if conn is None else conn.cursor()
        
        # remove the trailing s before adding "Id"; e.g., "dockets" --> "docketId"
        id_col = data_type[:len(data_type)-1] + "Id"

        the_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        print(f'{the_time}: Gathering details for {len(ids)} {data_type}...', flush=True)

        for item_id in ids:
            r_item = self.get_request_json(f'https://api.regulations.gov/v4/{data_type}/{item_id}',
                                           wait_for_rate_limits=True,
                                           skip_duplicates=skip_duplicates)
            
            if(skip_duplicates and self.is_duplicated_on_server(r_item)):
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
                                  flatfile_name=flatfile_name)
                data = []  # reset for next batch

        if len(data) > 0:  # insert any remaining in final batch
            data = self._get_processed_data(data, id_col)
            self._output_data(data, 
                              table_name=(data_type + "_detail"),
                              conn=conn, 
                              cur=cur, 
                              flatfile_name=flatfile_name)

        the_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        print(f'\n{the_time}: Finished: {n_retrieved} {data_type} collected', flush=True)

    
    def _get_processed_data(self, data, id_col):
        """Used to take the data contained in a response (e.g., the data for a bunch of comments)
        and remove unnecessary columns (i.e., those not specified in `cols`). Also adds the ID
        associated with the items and flattens lists contained in each item's data.

        Args:
            data (list of dict): List of items to process from a request (e.g., a bunch of comments).
                Each dict is expected to be formatted like: {'id': '...', 'attributes': {'attrib1': 'data', ...}, <other keys:values>}
            id_col (str): Name of the ID column for this data type, i.e., 'docketId', 'documentId', or 'commentId'

        Returns:
            list of dict: processed dataset, ready for input into sqlite or output to flat file
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


    def _write_to_flatfile(self, data, flatfile_name):
        """Write out data to a CSV file. Data will be appended to an existing file, or if the file does
        not exist, the file will be created with headers. Subsequent appends do not include the header row.

        Args:
            data (list of dict): Data to write out
            flatfile_name (str): Name (optionally with path) of the CSV file to write to
        """
        if flatfile_name is None:
            raise ValueError("flatfile_name cannot be None")

        the_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        print(f"{the_time}: Writing {len(data)} records to {flatfile_name}...", end="", flush=True)

        df = pd.DataFrame(data)
        
        # remove line breaks in each field so that the rows of the CSV correspond to one record
        df.replace(r"\n", " ", regex=True, inplace=True)
        df.to_csv(flatfile_name, index=False, mode='a', quoting=csv.QUOTE_ALL,
                  header=(not os.path.isfile(flatfile_name)))

        print("Done", flush=True)


    def _output_data(self, data, table_name=None, conn=None, cur=None, flatfile_name=None):
        """Routes the output call to either database or the flatfile, depending on parameters

        Args:
            data (list of dict): Data to write out
            table_name (str): For sqlite database, specifies table to insert into (one of: "dockets_header", "dockets_detail", 
                "documents_header", "documents_detail", "comments_header", or "comments_detail"). Can be None if using flat file.
            conn (sqlite3.Connection): Open connection to database. Can be None, in which case a flat file should be specified.
                Can be None if using flat file.
            cur (sqlite3.Cursor): Open cursor into the database. Can be None, in which case a flat file should be specified.
                Can be None if using flat file.
            flatfile_name (str): Name (optionally with path) of the CSV file to write to. Can be None, in which 
                case a connection and cursor should be specified.
        """
        if conn is None and flatfile_name is None:
            raise ValueError("Need to specify either conn or flatfile_name")

        if conn is not None:
            self._insert_data(data, table_name, conn, cur)
        
        if flatfile_name is not None:
            self._write_to_flatfile(data, flatfile_name)
