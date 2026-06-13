# Changelog

All notable project changes should be documented in this file.

This project uses human-readable release notes grouped by version. Dates use
`YYYY-MM-DD`.

## [0.2.0](https://github.com/extencil/agmh/compare/v0.1.0...v0.2.0) (2026-06-13)


### Features

* add notification system with webhooks for events ([174db38](https://github.com/extencil/agmh/commit/174db38ae36085ec69bf55d5e6ddc59a7faa259c))
* enhance project structure with CI workflows, release automation, and packaging improvements ([dceb257](https://github.com/extencil/agmh/commit/dceb2573c32944a04ef2af54ee14cfeb772ceb34))
* update project metadata, add templates, and enhance documentation ([5ecef83](https://github.com/extencil/agmh/commit/5ecef83d860032a08cf809337ae267b883e76b8b))

## [Unreleased]

### Added

- Security reporting policy.
- Contribution and support guidelines.
- Project maintenance files and GitHub issue/PR templates.
- PyPI/TestPyPI publishing workflows using Trusted Publishing.
- Release Please configuration for automated version bumps, changelog updates,
  Git tags, and GitHub Releases.
- CI workflow for Python tests and distribution checks.

### Changed

- Package metadata now identifies `extencil <extencil@segfault.net>` as author
  and maintainer.

## [0.1.0] - 2026-06-13

### Added

- Initial AGMH CLI package.
- Repository discovery from GitHub, GitLab, Forgejo/Codeberg, Bitbucket, and
  SourceHut sources.
- Local mirror, remote mirror, full mirror, and watching workflows.
- Destination support for GitHub, GitLab, Forgejo/Codeberg, Bitbucket, and
  SourceHut.
- Optional marker commits before remote mirrors.
- Optional webhook notifications for generic endpoints, Discord, and Telegram.
