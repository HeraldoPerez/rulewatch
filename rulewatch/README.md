# RuleWatch

Get alerts when the Federal Register publishes something that matters to you.

You set up a watch (an agency, some keywords, or both) and RuleWatch checks the Federal Register every day. Matches will show up in an RSS feed, and comment deadlines can go straight into your calendar as an .ics file.

I'm building it for small organizations that don't have someone whose job is to read the Federal Register every morning.

## Status

Early. The fetcher works: it reads your watches from `watches.yml`, searches the Federal Register for each one, and saves the matches as JSON, including comment deadlines and links to comment on regulations.gov. RSS feeds, the calendar export, the website and the daily run are next. What's planned and what's done is in [ROADMAP.md](ROADMAP.md).

## How it works

1. A scheduled job queries the public Federal Register API for each watch. *(works, run by hand for now)*
2. Results matching each watch are saved as JSON. *(works)*
3. The site turns them into a results page, an RSS feed, and a calendar file of comment deadlines. *(planned)*

There are no accounts and nothing personal is stored. Watches are just a config file.

## Example watch

```yaml
# watches.yml
- name: small-business-labor
  agencies: [labor-department]
  keywords: ["small business", "overtime"]
  types: [PRORULE, RULE]
```

| Setting | Meaning |
| --- | --- |
| `name` | Lowercase letters, numbers and hyphens. Used as the output file name. |
| `agencies` | Federal Register agency slugs, the last part of the agency's URL on [federalregister.gov/agencies](https://www.federalregister.gov/agencies). |
| `keywords` | A document matches if it contains **any** of them. Keywords with more than one word match as an exact phrase. |
| `types` | Optional. `RULE`, `PRORULE` (proposed rule), `NOTICE` or `PRESDOCU` (presidential document). Leave it out to get all four. |

Each watch needs at least one agency or keyword. If something in the file is wrong, every problem is listed at once before anything is fetched.

## Running it locally

Needs Python 3.10 or newer.

```bash
git clone https://github.com/Khalick/rulewatch.git
cd rulewatch

python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt

pytest                             # tests use recorded responses, no network needed
python -m rulewatch.fetch --config watches.yml --out data --days 30
```

Output looks like this:

```
small-business-labor: 2 documents, 0 with comment periods still open
epa-proposed-rules: 16 documents, 16 with comment periods still open
```

| Option | Default | Meaning |
| --- | --- | --- |
| `--config` | `watches.yml` | The watches file |
| `--out` | `data` | Folder for the JSON files |
| `--days` | `30` | How many days back to search |

The command exits with 0 when every watch was fetched, 1 when at least one failed (the others are still saved), and 2 when `watches.yml` has problems.

## Output

One file per watch, `data/<name>.json`. Each run replaces it with the documents from the last `--days` days, newest first. A failed fetch leaves the previous file alone.

```json
{
  "watch": { "name": "epa-proposed-rules", "agencies": ["environmental-protection-agency"], "keywords": [], "types": ["PRORULE"] },
  "fetched_at": "2026-11-09T12:50:16+00:00",
  "since": "2026-10-10",
  "total": 16,
  "complete": true,
  "documents": [
    {
      "document_number": "2026-22592",
      "title": "Air Plan Approval; District of Columbia; Enhanced Vehicle Emission Inspection and Maintenance (I/M) Program Revision ...",
      "type": "Proposed Rule",
      "publication_date": "2026-11-05",
      "html_url": "https://www.federalregister.gov/documents/2026/11/05/2026-22592/...",
      "abstract": "The Environmental Protection Agency (EPA) is proposing to approve ...",
      "comments_close_on": "2026-12-07",
      "effective_on": null,
      "pdf_url": "https://www.govinfo.gov/content/pkg/FR-2026-11-05/pdf/2026-22592.pdf",
      "comment_url": "http://www.regulations.gov/commenton/EPA-R03-OAR-2026-1024-0001",
      "agencies": ["Environmental Protection Agency"],
      "docket_ids": ["EPA-R03-OAR-2026-1024", "FRL-12072-01-R3"],
      "regulation_id_numbers": []
    }
  ]
}
```

`complete` is `false` if a watch matched more than 1,000 documents and only the newest were saved. Narrow the watch or use a smaller `--days`.

## Built with

Python with httpx and PyYAML, tested with pytest. Planned: a React (Vite) site on GitHub Pages, rebuilt daily by GitHub Actions.

## Data

Documents come from the [Federal Register API](https://www.federalregister.gov/developers/documentation/api/v1), which is free and needs no key. This isn't an official Federal Register product and doesn't use the NARA or Office of the Federal Register logos. Always check the official document before relying on a deadline.

## License

MIT, see [LICENSE](LICENSE).
