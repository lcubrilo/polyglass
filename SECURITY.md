# Security policy

## Reporting a vulnerability

Please report security problems **privately**, through GitHub's
[private vulnerability reporting](https://docs.github.com/en/code-security/security-advisories/guidance-on-reporting-and-writing-information-about-vulnerabilities/privately-reporting-a-security-vulnerability)
on this repository (Security tab → "Report a vulnerability"), not as a public issue.

Include what an attacker could do, the steps to reproduce it and the Polyglass version. You should get an
answer within a week. Once a fix is released, the report can be published with credit to you if you like.

## Supported versions

Only the latest release receives fixes.

## Scope notes

Polyglass reads the screen area you pick and sends the recognised text to the translation service you
chose. Things that are in scope include API keys leaking (to logs, files or other processes), text being
sent somewhere the user did not choose, and code execution through crafted on-screen content or settings
files.
