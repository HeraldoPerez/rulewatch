# Changelog

Notable changes go here. Format loosely follows [Keep a Changelog](https://keepachangelog.com/).

## [Unreleased]

- Project started.
- `watches.yml` config. Each watch has a name plus agencies, keywords and document types. Every problem in the file is reported at once, including unknown document types, which the API would otherwise silently ignore.
- Federal Register API client. Builds the search from a watch (any keyword matches; phrases match exactly), follows every result page, and turns API errors into readable messages.
- `python -m rulewatch.fetch`: saves the last `--days` days of documents for each watch to `data/<name>.json`. One failing watch doesn't stop the others, and a failed fetch never overwrites the previous file.
- Tests for the config, the API client and the fetch command, using recorded API responses.
