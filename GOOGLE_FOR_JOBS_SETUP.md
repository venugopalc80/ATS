# AQERITH — Google for Jobs setup

## Implemented in the application

- Public careers listing at `/careers`.
- Public job detail pages at `/careers/{jobId}`.
- Server-rendered `JobPosting` JSON-LD on each job detail page.
- Dynamic sitemap at `/sitemap.xml` with active public job URLs.
- Robots rules that allow public careers pages and disallow dashboard, login, and API paths.
- AQERITH canonical domain defaults to `https://aqerith.com`.

## Required Vercel frontend environment variables

Confirm these are configured for **Production** and Preview as appropriate:

- `NEXT_PUBLIC_SITE_URL=https://aqerith.com`
- `NEXT_PUBLIC_API_URL=https://ats-mu-azure.vercel.app`
- `NEXT_PUBLIC_ORGANIZATION_ID=<the organisation UUID used for the public careers feed>`
- `NEXT_PUBLIC_JOB_POSTING_ORGANIZATION_NAME=<actual hiring organisation name>`
- `NEXT_PUBLIC_JOB_POSTING_ORGANIZATION_URL=<official hiring organisation website>` (optional)
- `NEXT_PUBLIC_JOB_POSTING_SALARY_UNIT=YEAR` only if salary values are annual; otherwise set the correct Schema.org unit supported by the implementation.

**Important:** the current public careers configuration reads one organisation UUID from the environment. Before opening this feature to multiple AQERITH customer organisations, public job URLs and the hiring organisation must become tenant-aware; do not expose a customer’s vacancies by changing a public query parameter alone.

The structured-data organisation name must identify the real hiring organisation. Use `Confidential` only for genuinely confidential/anonymous employers, not as a universal default. The current implementation uses a configurable value because the public job API does not yet expose the employer’s display name.

## Google setup checklist

1. Deploy the frontend to `aqerith.com`.
2. Verify the domain property in [Google Search Console](https://search.google.com/search-console/).
3. Open `https://aqerith.com/robots.txt` and `https://aqerith.com/sitemap.xml`.
4. Test a real public job URL in [Rich Results Test](https://search.google.com/test/rich-results).
5. Inspect the job URL in Search Console and request indexing where appropriate.
6. Monitor Search Console for structured-data and indexing issues.

## Indexing API credentials and automatic notifications

The backend includes a best-effort notification service. When enabled, creating an open job or updating an open job queues `URL_UPDATED`; moving an open job out of the open state or deleting an open job queues `URL_DELETED`. Notifications run after the API response in a FastAPI background task and failures are logged without failing the ATS job operation. This is a lightweight first implementation, not a durable retry queue.

Set these **backend-only** Vercel environment variables after completing Google's setup:

- `GOOGLE_INDEXING_ENABLED=true`
- `GOOGLE_INDEXING_SERVICE_ACCOUNT_JSON=<complete service-account JSON contents>`
- `NEXT_PUBLIC_SITE_URL=https://aqerith.com` (used by the backend helper to form canonical URLs; ensure it is set in the backend project too)

Keep the service-account JSON private; do not commit it to GitHub or use a `NEXT_PUBLIC_` prefix for the credentials.

Google's Indexing API requires a Google Cloud project, the API enabled, a service account, Search Console access for the site, and production quota/approval as required by Google. Keep service-account credentials in backend-only Vercel environment variables or a secrets manager; never expose them as `NEXT_PUBLIC_*` values or commit credentials to GitHub.

Official docs:
- https://developers.google.com/search/docs/appearance/structured-data/job-posting
- https://developers.google.com/search/apis/indexing-api/v3/quickstart
- https://developers.google.com/search/apis/indexing-api/v3/using-api

Google's Indexing API is for eligible job-posting pages and does not guarantee crawling, indexing, or display in Google for Jobs.
