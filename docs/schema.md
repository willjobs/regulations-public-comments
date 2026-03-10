# Database Schema

When saving to SQLite, the library creates six tables — two for each of dockets, documents, and comments. The "header" tables contain the fields returned by the bulk search endpoint; the "detail" tables contain all fields returned by the per-item details endpoint.

The `sqltime` column in each table records when each row was inserted.

For field definitions, see the [official Regulations.gov API documentation](https://open.gsa.gov/api/regulationsgov/#api-calls).

## dockets_header

| Column | Type |
|--------|------|
| docketId | TEXT NOT NULL UNIQUE |
| agencyId | TEXT |
| docketType | TEXT |
| title | TEXT |
| lastModifiedDate | TEXT NOT NULL |
| objectId | TEXT |
| sqltime | TIMESTAMP |

## dockets_detail

| Column | Type |
|--------|------|
| docketId | TEXT NOT NULL UNIQUE |
| agencyId | TEXT |
| category | TEXT |
| dkAbstract | TEXT |
| docketType | TEXT |
| effectiveDate | TEXT |
| field1 | TEXT |
| field2 | TEXT |
| generic | TEXT |
| keywords | TEXT |
| legacyId | TEXT |
| modifyDate | TEXT NOT NULL |
| objectId | TEXT |
| organization | TEXT |
| petitionNbr | TEXT |
| program | TEXT |
| rin | TEXT |
| shortTitle | TEXT |
| subType | TEXT |
| subType2 | TEXT |
| title | TEXT |
| sqltime | TIMESTAMP |

## documents_header

| Column | Type |
|--------|------|
| documentId | TEXT NOT NULL UNIQUE |
| commentEndDate | TEXT |
| commentStartDate | TEXT |
| docketId | TEXT |
| documentType | TEXT |
| frDocNum | TEXT |
| lastModifiedDate | TEXT NOT NULL |
| objectId | TEXT |
| postedDate | TEXT |
| subtype | TEXT |
| title | TEXT |
| withdrawn | INTEGER |
| sqltime | TIMESTAMP |

## documents_detail

48 columns. Key fields: `documentId`, `agencyId`, `docketId`, `documentType`, `title`, `docAbstract`, `comment`, `postedDate`, `modifyDate`, and more. See the [source code](https://github.com/willjobs/regulations-public-comments/blob/master/src/regulations_public_comments/downloader.py) or the [official API docs](https://open.gsa.gov/api/regulationsgov/#api-calls) for the full list.

## comments_header

| Column | Type |
|--------|------|
| commentId | TEXT NOT NULL UNIQUE |
| agencyId | TEXT |
| documentType | TEXT |
| lastModifiedDate | TEXT NOT NULL |
| objectId | TEXT |
| postedDate | TEXT |
| title | TEXT |
| withdrawn | INTEGER |
| sqltime | TIMESTAMP NOT NULL |

## comments_detail

40 columns. Key fields: `commentId`, `docketId`, `commentOnDocumentId`, `firstName`, `lastName`, `organization`, `city`, `stateProvinceRegion`, `country`, `comment` (full text), `attachmentLinks`, `postedDate`, and more.
