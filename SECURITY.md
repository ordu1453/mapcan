# Security policy

## Supported versions

Security fixes go into the latest release of mapcan and of the VS Code extension. Older versions
are not patched; update to the [latest release](https://github.com/ordu1453/mapcan/releases/latest).

## Reporting a vulnerability

Please do not open a public issue for a security problem. Report it privately through
[GitHub Security Advisories](https://github.com/ordu1453/mapcan/security/advisories/new)
("Report a vulnerability" on the Security tab).

Include the mapcan version, the operating system, how mapcan was run (installer, `uv tool`, Docker,
VS Code extension) and the steps or a map file that reproduce the problem. You will get a reply
within a week; once a fix is released, the advisory is published with credit to the reporter unless
you ask otherwise.

## Scope

The web editor (`mapcan edit`, the desktop app) is meant to run locally: by default it listens on
`127.0.0.1` and works with the files of the user who started it. Problems that let another local
user, a web page in the browser or a crafted map file read or change files, run commands or reach
the editor's API are in scope. Exposing the editor on a network address with `--host` gives everyone
who can reach it the rights of that user, so this setup is not covered.
