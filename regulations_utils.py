import os
import requests
import sqlite3
import pandas as pd
from datetime import datetime
from dateutil import tz
import time
import csv
import urllib3

# we are ignoring the HTTPS check because the server occasionally returns malformed certificates (missing EOF)
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

def get_requests_remaining(api_key=None, request=None):
    """Get the number of requests remaining. An API key usually gives you 1000 requests/hour.

    Args:
        api_key (str, optional): When given, used to make a request and get the number of requests left
            based on the headers returned. Defaults to None.
        request (requests.models.Response, optional): A response to a previous request from the API,
             whose headers can be used to get the number of remaining responses at the time of the
             request, rather than making a new request. Defaults to None.

    Returns:
        int: number of requests remaining
    """
    if request is None and api_key is None:
        raise ValueError("Must specify api_key or request")

    if request is not None:
        pass
    else:
        request = requests.get('https://api.regulations.gov/v4/documents/FDA-2009-N-0501-0012',
                         headers={'X-Api-Key': api_key},
                         verify=False)
        if request.status_code != 200:
            print(request.json())
            request.raise_for_status()

    return int(request.headers['X-RateLimit-Remaining'])


def get_request_json(endpoint, api_key, params=None, print_remaining_requests=False, wait_for_rate_limits=False):
    """Used to return the JSON associated with a request to the API

    Args:
        endpoint (str): URL of the API to access (e.g., https://api.regulations.gov/v4/documents)
        api_key (str): API key
        params (dict, optional): Parameters to specify to the endpoint request. Defaults to None, in
            which case no parameters are specified and it is assumed we are accessing the "Details" endpoint.
            If params is not None, we also append the "page[size]" parameter so that we always get
            the maximum page size of 250 elements per page.
        print_remaining_requests (bool, optional): Whether to print out the number of remaining
            requests this hour, based on the response headers. Defaults to False.
        wait_for_rate_limits (bool, optional): Determines whether to wait to re-try if we run out of
            requests in a given hour. Defaults to False.

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

    tries = 1
    while tries <= int(60 / WAIT_MINUTES) + 2:
        if params is not None:  # querying the search endpoint (e.g., /documents)
            r = requests.get(endpoint,
                             headers={'X-Api-Key': api_key},
                             params={**params,
                                     'page[size]': 250}, # always get max page size
                             verify=False)
        else:  # querying the "detail" endpoint (e.g., /documents/{documentId})
            r = requests.get(endpoint, headers={'X-Api-Key': api_key}, verify=False)

        if r.status_code != 200:
            if r.status_code == STATUS_CODE_OVER_RATE_LIMIT and wait_for_rate_limits:
                the_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                print(f'{the_time}: Hit rate limits. Waiting {WAIT_MINUTES} minutes to try again (attempt {tries})', flush=True)
                # We ran out of requests. Wait for a bit.
                for i in range(int(WAIT_MINUTES * 60 / POLL_SECONDS)):
                    time.sleep(POLL_SECONDS)

            else:  # some other kind of error
                print([r, r.status_code])
                print(r.json())
                r.raise_for_status()
        else:
            # SUCCESS! Return the JSON of the request
            num_requests_left = int(r.headers['X-RateLimit-Remaining'])
            if print_remaining_requests or \
                (num_requests_left < 10) or \
                (num_requests_left <= 100 and num_requests_left % 10 == 0) or \
                (num_requests_left % 100 == 0 and num_requests_left < 1000):
                print(f"Requests left: {r.headers['X-RateLimit-Remaining']}", flush=True)

            return r.json()

        tries += 1

    print(r.json())
    raise RuntimeError(f"Unrecoverable error; status code = {r.status_code}")


def process_data(data, cols, id_col):
    """Used to take the data contained in a response (e.g., the data for a bunch of comments)
    and remove unnecessary columns (i.e., those not specified in `cols`). Also adds the ID
    associated with the items and flattens lists contained in each item's data.

    Args:
        data (list of dict): List of items to process from a request (e.g., a bunch of comments).
            Each dict is expected to be formatted like: {'id': '...', 'attributes': {'attrib1': 'data', ...}, <other keys:values>}
        cols (list of str): List of columns desired in the output
        id_col (str): Name of the ID column for this data type, i.e., 'documentId' or 'commentId'

    Returns:
        list of dict: processed dataset, ready for input into sqlite or output to flat file
    """
    output = []
    for item in data:
        # get fields we want
        cols = [x for x in cols if x not in [id_col, 'sqltime']]

        # get just the dict of columns we want, and if one of the values is a list, flatten it
        out = {k:(' '.join(v) if type(v) == list else v) for (k,v) in item['attributes'].items() if k in cols}

        # also, the item's ID
        out[id_col] = item['id']
        output.append(out)

    return output


def insert_data(data, table_name, cols, conn, cur=None):
    """Add data to a specified sqlite table

    Args:
        data (list of dict): Data to be inserted into database
        table_name (str): "documents_header", "documents_detail", "comments_header", or "comments_detail" -- specifies table to insert into
        cols (list of str): columns to be inserted, can be a subset of the columns in data
        conn (sqlite3.Connection): Open connection to database
        cur (sqlite3.Cursor): Open cursor into the database
    """
    # upload into staging table, then insert, skipping any rows that violate key constraints
    if conn is None:
        raise ValueError("conn cannot be None")
    if table_name is None or cols is None:
        raise ValueError("Need to specify both table_name and cols")
    if cur is None:
        cur = conn.cursor()

    the_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    print(f"{the_time}: Inserting {len(data)} records into database...", flush=True)
    pd.DataFrame(data).to_sql("tmp", conn, if_exists="replace", index=False)
    cur.execute(f"INSERT OR IGNORE INTO {table_name} ({','.join(cols)}) SELECT {','.join(cols)} FROM tmp")
    conn.commit()


def write_to_flatfile(data, flatfile_name):
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
    if "comment" in df.columns:
        df["comment"] = df["comment"].str.replace("\n", " ")
    
    df.to_csv(flatfile_name, index=False, mode='a', quoting=csv.QUOTE_ALL,
              header=(not os.path.isfile(flatfile_name)))

    print("Done", flush=True)


def output_data(data, table_name=None, cols=None, conn=None, cur=None, flatfile_name=None):
    """Routes the output call to either database or the flatfile, depending on parameters

    Args:
        data (list of dict): Data to write out
        table_name (str): For sqlite database, "documents_header", "documents_detail",  "comments_header", 
            or "comments_detail". Can be None if using flat file.
        cols (list of str): For sqlite database, columns to be inserted, can be a subset of the columns in data.
            Can be None if using flat file.
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
        insert_data(data, table_name, cols, conn, cur)
    
    if flatfile_name is not None:
        write_to_flatfile(data, flatfile_name)


def gather_headers(api_key, data_type, cols, id_col, params, max_items=None, conn=None, flatfile_name=None):
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
        gather_headers(api_key, data_type='comments', cols=comments_cols, id_col='commentId', conn=conn
                       params={'filter[postedDate][ge]': '2020-01-01'})

    Args:
        api_key (str): API key
        data_type (str): Either "comments" or "documents".
        cols (list of str): columns to save; can be a subset of the columns in data
        id_col (str): Name of the ID column for this data type, i.e., 'documentId' or 'commentId'
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

    n_retrieved = 0
    prev_query_max_date = '1900-01-01 00:00:00'  # placeholder value for first round of 5000
    EASTERN_TIME = tz.gettz('America/New_York')

    cur = None if conn is None else conn.cursor()

    # first request, to ensure there are documents and to get a total count
    r_items = get_request_json(f'https://api.regulations.gov/v4/{data_type}',
                               api_key,
                               params=params,
                               wait_for_rate_limits=True)

    totalElements = r_items['meta']['totalElements']
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
                    r_items = get_request_json(f'https://api.regulations.gov/v4/{data_type}',
                                               api_key,
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

        data = process_data(data, cols, id_col)
        output_data(data, 
                    table_name=(data_type + "_header"), 
                    cols=cols, 
                    conn=conn, 
                    cur=cur, 
                    flatfile_name=flatfile_name)

    print(f'\nFinished: {n_retrieved} {data_type} collected', flush=True)


def gather_details(api_key, data_type, cols, id_col, ids, conn=None, flatfile_name=None):
    """This function is meant to get the Details data for each item in ids, one at a time. The data 
    for each item is output either to a database (specified by conn) or a flatfile (specified by flatfile_name). 
    
    An example call is:
        gather_details(api_key, data_type='documents', cols=documents_cols, id_col='documentId', ids=document_ids, conn=conn)

    Args:
        api_key (str): API key
        data_type (str): Either "comments" or "documents"
        cols (list of str): columns to save; can be a subset of the columns in data
        id_col (str): Name of the ID column for this data type, i.e., 'documentId' or 'commentId'
        ids (list of str): List of IDs for items for which you are querying details. These IDs are
            appended to the URL directly, e.g., https://api.regulations.gov/v4/comments/FWS-R8-ES-2008-0006-0003
        conn (sqlite3.Connection): Open connection to database. Can be None, in which case a flat file should be specified
        flatfile_name (str): Name (optionally with path) of the CSV file to write to. Can be None, in which 
            case a connection should be specified.

    """
    if conn is None and flatfile_name is None:
        raise ValueError("Must specify either a connection (conn) or the name of a file to write to (flatfile)")

    INSERT_EVERY = 500
    n_retrieved = 0
    data = []

    cur = None if conn is None else conn.cursor()

    the_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    print(f'{the_time}: Gathering details for {len(ids)} {data_type}...', flush=True)

    for item_id in ids:
        r_item = get_request_json(f'https://api.regulations.gov/v4/{data_type}/{item_id}',
                                  api_key,
                                  wait_for_rate_limits=True)
        n_retrieved += 1
        data.append(r_item['data'])  # only one item from the Details endpoint, not a list, so use append (not extend)

        if n_retrieved > 0 and n_retrieved % INSERT_EVERY == 0:
            data = process_data(data, cols, id_col)
            output_data(data, 
                        table_name=(data_type + "_detail"), 
                        cols=cols, 
                        conn=conn, 
                        cur=cur, 
                        flatfile_name=flatfile_name)
            data = []  # reset for next batch

    if len(data) > 0:  # insert any remaining in final batch
        data = process_data(data, cols, id_col)
        output_data(data, 
                    table_name=(data_type + "_detail"), 
                    cols=cols, 
                    conn=conn, 
                    cur=cur, 
                    flatfile_name=flatfile_name)

    the_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    print(f'\n{the_time}: Finished: {n_retrieved} {data_type} collected', flush=True)


def setup_database(filename=None, return_conn=True):
    """Set up a sqlite database with the tables and columns necessary for the data returned
    by the Regulations.gov API.

    Args:
        filename (str): Filename, optionally including path.
        return_conn (bool, optional): [description]. Defaults to True.

    Returns:
        [type]: [description]
    """
    if filename is None:
        filename = 'regulations.gov_' + datetime.now().strftime('%Y%m%d') + ".db"

    conn = sqlite3.connect(filename)
    cur = conn.cursor()

    cur.execute('drop table if exists documents_header')
    cur.execute('drop table if exists documents_detail')
    cur.execute('drop table if exists comments_header')
    cur.execute('drop table if exists comments_detail')

    cur.execute("""
    CREATE TABLE documents_header (
        documentId          TEXT    NOT NULL UNIQUE,
        commentEndDate      TEXT,
        commentStartDate    TEXT,
        docketId            TEXT,
        documentType        TEXT,
        frDocNum            TEXT,
        lastModifiedDate    TEXT    NOT NULL,
        objectId            TEXT    NOT NULL,
        postedDate          TEXT    NOT NULL,
        subtype             TEXT,
        title               TEXT,
        withdrawn           INTEGER,
        sqltime             TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL
    )""")

    cur.execute("""
    CREATE TABLE documents_detail (
        documentId              TEXT    NOT NULL UNIQUE,
        additionalRins          TEXT,
        agencyId                TEXT    NOT NULL,
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
        modifyDate              TEXT    NOT NULL,
        objectId                TEXT    NOT NULL UNIQUE,
        ombApproval             TEXT,
        openForComment          INTEGER,
        organization            TEXT,
        originalDocumentId      TEXT,
        pageCount               TEXT,
        paperLength             INTEGER,
        paperWidth              INTEGER,
        postedDate              TEXT    NOT NULL,
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
        sqltime                 TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL
    )""")

    cur.execute("""
    CREATE TABLE comments_header (
        commentId               TEXT    NOT NULL UNIQUE,
        agencyId                TEXT    NOT NULL,
        documentType            TEXT,
        lastModifiedDate        TEXT    NOT NULL,
        objectId                TEXT    NOT NULL UNIQUE,
        postedDate              TEXT    NOT NULL,
        title                   TEXT,
        withdrawn               INTEGER,
        sqltime                 TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL
    )""")

    cur.execute("""
    CREATE TABLE comments_detail (
        commentId               TEXT    NOT NULL UNIQUE,
        agencyId                TEXT    NOT NULL,
        category                TEXT,
        city                    TEXT,
        comment                 TEXT,
        commentOn               TEXT    NOT NULL,
        commentOnDocumentId     TEXT    NOT NULL,
        country                 TEXT,
        docAbstract             TEXT,
        docketId                TEXT    NOT NULL,
        documentType            TEXT,
        duplicateComments       INTEGER,
        field1                  TEXT,
        field2                  TEXT,
        firstName               TEXT,
        govAgency               TEXT,
        govAgencyType           TEXT,
        lastName                TEXT,
        legacyId                TEXT,
        modifyDate              TEXT    NOT NULL,
        objectId                TEXT    NOT NULL UNIQUE,
        openForComment          INTEGER,
        organization            TEXT,
        originalDocumentId      TEXT,
        pageCount               TEXT,
        postedDate              TEXT    NOT NULL,
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
        sqltime                 TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL
    )""")

    return conn
