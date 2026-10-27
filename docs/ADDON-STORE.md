# NVDA Add-on Store submission

## Initial submission

- Add-on ID: `bookAudio`.
- Version: `0.1.2`.
- Channel: `beta`, matching the published preview.
- Publisher: Denis Skripnik (`denis-skripnik`).
- Registration issue: https://github.com/nvaccess/addon-datastore/issues/12540
- Automatically generated PR: https://github.com/nvaccess/addon-datastore/pull/12541

The metadata validation succeeded. At submission time, the request was waiting for first-time publisher approval for this specific add-on; the PR had not been merged. The links above, not this static document, show the current status. Creating a request is not the same as being listed in the Store.

## Current official procedure

Submit the **Add-on registration** issue form in `nvaccess/addon-datastore`; the automation creates the metadata pull request. A new add-on needs publisher approval even if the same publisher already maintains another listed add-on. The guide advises allowing up to two weeks for that approval.[1]

The form requires a direct immutable HTTPS download URL ending in `.nvda-addon`, a source URL, publisher, release channel and license information. The exact field headings are defined by the official form.[5]

For Book Audio 0.1.2, the submitted links are:

- Download: https://github.com/denis-skripnik/nvda-book-audio/releases/download/v0.1.2/bookAudio-0.1.2.nvda-addon
- Source: https://github.com/denis-skripnik/nvda-book-audio/tree/v0.1.2
- License: https://github.com/denis-skripnik/nvda-book-audio/blob/v0.1.2/LICENSE
- License name: `GPL-2.0-or-later`.

The downloaded package SHA-256 in the generated Store metadata matches the published package: `e0254b6f9e54b5dd4123c4785bf8421fcec77937354ddf16f3204547556c1017`.

## Future versions

1. Recheck the official guide and NVDA API version list.
2. Build and test the new add-on version, and run `python tools/audit_privacy.py`.
3. Publish a new versioned release asset; do not replace the bytes behind a previously submitted download URL.
4. Submit the registration form again with the new release links and intended channel.
5. Inspect validation comments, PR checks and publisher/security approval gates. Do not confuse a first-submitter approval failure with an invalid package.

Versions must be unique across channels. Do not submit `0.1.2` again as stable; use a new version for a later stable release.[6]

## Sources

[1] https://github.com/nvaccess/addon-datastore/blob/master/docs/submitters/submissionGuide.md
[5] https://github.com/nvaccess/addon-datastore/blob/master/.github/ISSUE_TEMPLATE/registerAddon.yml
[6] https://github.com/nvaccess/addon-datastore/blob/master/docs/design/jsonMetadata.md
