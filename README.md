# Downloading public comment data from Regulations.gov

## **Preface**

📚 [Documentation](https://htmlpreview.github.io/?https://github.com/willjobs/regulations-public-comments/blob/master/documentation.html) of the source code.

More information on the Regulations.gov API that this code abstracts away and simplifies, including a description and examples of the API responses and how to parse it, can be found in [this blog post](https://github.com/willjobs/public-comments-project/blob/main/blogposts/post2/README.md). The official Regulations.gov API documentation is here: https://open.gsa.gov/api/regulationsgov/. To sign up for an API key to access Regulations.gov data, go to [this link](https://open.gsa.gov/api/regulationsgov/#getting-started). You can also use `DEMO_KEY` as an API key for up to 25 requests per hour. This is what the documentation at Regulations.gov uses in their examples.

This code came about as the result of a final project for a course I took at UMass Amherst ("Text as Data"). The results are in [this repo](https://github.com/willjobs/public-comments-project), which has [the final poster](https://github.com/willjobs/public-comments-project/blob/main/poster.pdf), and [milestone blog posts](https://github.com/willjobs/public-comments-project/tree/main/blogposts) folder.

---
## **What is this?**

The goal of this code is to provide an easier mechanism to query for and download data from Regulations.gov using their public API. This code submits requests to the API and parses the responses, downloading the data into either a sqlite database or a CSV.

The biggest contributions of this code are (1) a simple way to download all comments for a given docket or document, and (2) its automated handling of the API's pagination mechanism. By default, the Regulations.gov API returns 25 records per request, which can be bumped up to 250 records. A given query returns up to 20 "pages", so with 250 records per page, that is 5,000 records per query. If your query would return more than 5,000 records (e.g., if you're querying for all comments in 2020), you need to use multiple queries, paginating over all 20 pages in each, and making sure subsequent queries filter out the earlier queries' results (typically by using `lastModifiedDate`). I explain this in detail in [blog post 2](https://github.com/willjobs/public-comments-project/blob/main/blogposts/post2/README.md).

The code here also automatically handles request limits. An API key gives you up to 1,000 requests per hour. After that, the API returns a status code 429 indicating you're out of requests. The code here knows how to wait and retry.

Note that there are essentially two high-level APIs, what I call the "header" and "details" APIs. The "header" API is https://api.regulations.gov/v4/{data_type} (with {data_type} replaced by either "comments", "documents", or "dockets"). This API returns some general information about items (comments, etc.) matching search criteria specified using parameters. The "details" API is https://api.regulations.gov/v4/{data_type}/{itemId}, which returns detailed information about one *specific item*. For example, to see the plain-text of a comment, this details API needs to be used.

For one-off queries and to gain a better understanding of the API, I recommend using `get_request_json`, which returns the raw JSON associated with a request.

Note that there are some idiosyncracies in the data itself. For example, there are comments not associated with any documents, documents not associated with a docket, many documents without comments, etc. By far, the document types with the most comments are "Proposed Rule" and "Rule" types. To query for these, one could use this filter: `filter[documentType]: 'Proposed Rule,Rule'`. 

---

## **Examples**

See [the documentation](https://htmlpreview.github.io/?https://github.com/willjobs/regulations-public-comments/blob/master/documentation.html) for more detail on each function and its parameters. The examples below show some simple examples of this project might be used.

If you just need to download comments for one docket or document, you can use the command-line:

        # download all comments for docket FDA-2021-N-0270 (across all its documents)
        python comments_downloader.py --key DEMO_KEY --docket FDA-2021-N-0270

        # download all comments for document FDA-2009-N-0501-0012
        python comments_downloader.py --key DEMO_KEY --document FDA-2009-N-0501-0012

For more functionality and customization, see [Examples.ipynb](https://github.com/willjobs/regulations-public-comments/blob/master/Examples.ipynb) for example code and output for the following questions:

* How do I download all comments associated with a docket?
* How do I download all comments associated with *multiple* dockets?
* How do I download all comments associated with a document?
* How do I download all comments associated with *multiple* documents?
* How do I find out the number of [dockets/documents/comments] that would be returned by a query using some parameters?
* How do I download all [dockets/documents/comments] associated with some parameters?

---

## **Database Schema**

There are six tables, two each for dockets, documents, and comments. One of each pair is the "header" table and the the other is the "detail" table. The "header" table is what is returned by the Regulations.gov [dockets/documents/comments] endpoint, and is a query for possibly multiple of these items. It contains a small number of metadata fields. The "detail" table is what is returned by the Regulations.gov endpoint for a specific item (e.g., `dockets/EXAMPLE-DOCKET-ID`). It contains more fields with data like the plain-text of a comment.

The six tables are: `dockets_header`, `dockets_detail`, `documents_header`, `documents_detail`, `comments_header`, and `comments_detail`. The schema is shown below. For definitions of these fields, see the [Regulations.gov API documentation](https://open.gsa.gov/api/regulationsgov/#api-calls). `sqltime` is a field I added indicating when a given row was inserted into the table.

### **dockets_header**

        docketId            TEXT    NOT NULL UNIQUE,
        agencyId            TEXT,
        docketType          TEXT,
        title               TEXT,
        lastModifiedDate    TEXT NOT NULL,
        objectId            TEXT,
        sqltime             TIMESTAMP DEFAULT CURRENT_TIMESTAMP

### **dockets_detail**

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

### **documents_header**

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

### **documents_detail**

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

### **comments_header**

        commentId               TEXT    NOT NULL UNIQUE,
        agencyId                TEXT,
        documentType            TEXT,
        lastModifiedDate        TEXT NOT NULL,
        objectId                TEXT,
        postedDate              TEXT,
        title                   TEXT,
        withdrawn               INTEGER,
        sqltime                 TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL


### **comments_detail**

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
