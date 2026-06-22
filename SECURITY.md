# Security Policy

## Reporting a Vulnerability

The tracecat-operator project takes security bugs seriously. We appreciate
your efforts to responsibly disclose your findings and will make every effort
to acknowledge your contributions.

**Please report security vulnerabilities to [security@ubuntu.com](mailto:security@ubuntu.com)**
rather than opening a public GitHub issue.

Do not include sensitive information in the initial report. We will reply with
instructions for secure communication if further detail is required.

## Expected Response Time

* Initial acknowledgement of your report: within **5 business days**.
* A triage decision and severity assessment: within **10 business days**.
* Coordinated public disclosure occurs **after a patch is available** and
  downstream operators have had a reasonable window to upgrade.

## Scope

This policy covers the **charm (operator) code** in this repository, which is
licensed under Apache 2.0. Vulnerabilities in the upstream **Tracecat
workload** (AGPL-3.0) should be reported to the TracecatHQ maintainers via
their security channels — see https://github.com/TracecatHQ/tracecat.

## Supported Versions

Only the latest published release on the `1.0/stable` Charmhub track receives
security fixes. Older tracks are supported on a best-effort basis.

## Disclosure Process

We follow the [Ubuntu security disclosure policy](https://ubuntu.com/security/disclosure-policy).
A CVE may be requested for materially impactful issues. Once a fix is released,
a GitHub Security Advisory is published and the CHANGELOG is updated.
