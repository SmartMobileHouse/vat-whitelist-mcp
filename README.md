<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="assets/logo-dark.svg">
    <img src="assets/logo.svg" alt="vat-whitelist-mcp logo" width="96" height="96">
  </picture>
</p>
<h1 align="center">vat-whitelist-mcp</h1>
<p align="center">
  <strong>An MCP server for the Polish VAT White List (Wykaz podatników VAT).</strong><br>
  Check a taxpayer by NIP, REGON or bank account, and verify an account against an active VAT taxpayer on a given date.
</p>

<!-- mcp-name: io.github.SmartMobileHouse/vat-whitelist-mcp -->

<div align="center">

[![PyPI](https://img.shields.io/pypi/v/vat-whitelist-mcp)](https://pypi.org/project/vat-whitelist-mcp/)
[![Python](https://img.shields.io/pypi/pyversions/vat-whitelist-mcp)](https://pypi.org/project/vat-whitelist-mcp/)
[![CI](https://github.com/SmartMobileHouse/vat-whitelist-mcp/actions/workflows/publish.yml/badge.svg)](https://github.com/SmartMobileHouse/vat-whitelist-mcp/actions/workflows/publish.yml)
[![License](https://img.shields.io/github/license/SmartMobileHouse/vat-whitelist-mcp)](LICENSE)
[![Smart Mobile House](https://img.shields.io/badge/built%20by-Smart%20Mobile%20House-1F3A38)](https://smartmobilehouse.com)

</div>

## What it does

A [Model Context Protocol](https://modelcontextprotocol.io) server that gives AI
assistants clean, typed access to the **Polish VAT White List** (Wykaz podatników
VAT). Look up taxpayers by **NIP**, **REGON**, or **bank account** and verify
whether an account is associated with an active taxpayer on a specified date.

The official [VAT White List API](https://www.gov.pl/web/kas/api-wykazu-podatnikow-vat)
returns taxpayer details, VAT status, bank accounts, and confirmation identifiers.
`vat-whitelist-mcp` exposes its REST search and check methods as five simple tools.

| Tool | Description |
| --- | --- |
| `search_by_nip(nip, date)` | Look up a taxpayer by 10-digit NIP (tax id). |
| `search_by_regon(regon, date)` | Look up a taxpayer by 9- or 14-digit REGON. |
| `search_by_bank_account(bank_account, date)` | Find taxpayers associated with an account. |
| `search_bulk(identifiers, id_type, date)` | Look up 1–30 identifiers of one type in a single API request. |
| `check_bank_account(identifier, id_type, bank_account, date)` | Check an account's association with an active taxpayer by NIP or REGON. |

Every tool requires an explicit `YYYY-MM-DD` date. NIP, REGON, and Polish bank
account checksums are validated locally. Bank accounts accept a 26-digit NRB or
its `PL` IBAN form, with common grouping separators.

Search responses contain `count`, `results`, `date`, and a `source` block naming
the register, environment, and UTC `retrieved_at` time. The API's `requestId` and
`requestDateTime` are retained, along with the original taxpayer fields.

Bulk `id_type` is `nip`, `regon`, or `bank_account`; check `id_type` is `nip` or
`regon`. Bulk `results` contain one entry per identifier, with either `subjects`
or an upstream `error`; `count` counts entries. `requested` contains normalized
inputs, and `unmatched` lists successful entries with no subjects. Failed entries
are never treated as missing taxpayers. Checks preserve `accountAssigned` as
`TAK` or `NIE`; API failures raise errors rather than returning `NIE`.

Design notes: [the vat-whitelist-mcp write-up](https://smartmobilehouse.com/blog/open-source-mcp-server-vat-whitelist/).

## Quick start

No install needed — run it straight from the repo with
[uv](https://docs.astral.sh/uv/):

```bash
uvx --from git+https://github.com/SmartMobileHouse/vat-whitelist-mcp vat-whitelist-mcp
```

By default it uses the **sandbox**, with no API key or account required. Set
`VAT_ENV=prod` for live data. For example, ask your assistant to look up a NIP
using today's explicit date.

It is also published on [PyPI](https://pypi.org/project/vat-whitelist-mcp/), so `uvx vat-whitelist-mcp` works too.

### Use it in Claude Desktop / Claude Code

Add to your MCP config (e.g. `claude_desktop_config.json` or `.mcp.json`):

```json
{
  "mcpServers": {
    "vat-whitelist": {
      "command": "uvx",
      "args": ["--from", "git+https://github.com/SmartMobileHouse/vat-whitelist-mcp", "vat-whitelist-mcp"],
      "env": {
        "VAT_ENV": "prod"
      }
    }
  }
}
```

During development, point it at a local checkout instead:

```json
{
  "mcpServers": {
    "vat-whitelist": {
      "command": "uvx",
      "args": ["--from", "/absolute/path/to/vat-whitelist-mcp", "vat-whitelist-mcp"],
      "env": { "VAT_ENV": "test" }
    }
  }
}
```

## Status

- [x] Search by NIP, REGON and bank account
- [x] Bulk search of 1–30 identifiers of one type in a single request
- [x] Account check against an active taxpayer by NIP or REGON, keeping `TAK` / `NIE` as returned
- [x] Local NIP, REGON and bank-account checksum validation
- [x] A `source` block with the register, environment and UTC retrieval time in every response
- [x] Runs on the sandbox with no key; live data with `VAT_ENV=prod`
- [x] Released through GitHub Actions with PyPI Trusted Publishing and MCP Registry metadata

## Configuration

| Variable | Default | Description |
| --- | --- | --- |
| `VAT_ENV` | `test` | `test` for the sandbox or `prod` for live data. |
| `VAT_TIMEOUT` | `30` | Positive finite HTTP timeout in seconds. |

Set these in the shell or MCP configuration. `.env.example` is a reference;
`.env` files are not loaded automatically.

The API base URLs are `https://wykazpodatnikowvat-test.mf.gov.pl/api/` for the
sandbox and `https://wykazpodatnikowvat.mf.gov.pl/api/` for production.

## Development

```bash
git clone https://github.com/SmartMobileHouse/vat-whitelist-mcp
cd vat-whitelist-mcp
uv sync --locked        # create the venv and install dependencies
uv run pytest           # offline validation, mocked HTTP, MCP discovery and stdio tests
                        # (network tests are skipped by default)
uv run vat-whitelist-mcp # run the server over stdio
uv build                # build source and wheel distributions
uvx twine check dist/*  # validate package metadata

# Live tests against the official sandbox (opt-in; no production requests):
VAT_RUN_NETWORK=1 uv run pytest -m network
```

The client is a small REST layer over `httpx` (see
`src/vat_whitelist_mcp/client.py`), with no authentication session or automatic
retries. Python 3.10 or newer is required.

### Releases

GitHub Actions runs the offline tests, validates versions, builds the wheel and
source distribution, and checks metadata on pull requests and pushes to `main`.
Pushing a version tag such as `v0.1.0` publishes the tested artifacts to PyPI
using Trusted Publishing, then publishes the matching MCP Registry metadata.
The workflow can also be dispatched manually from `main`.

Before the first release, add a [pending Trusted Publisher](https://pypi.org/manage/account/publishing/)
in the maintainer's PyPI account with these values:

| Field | Value |
| --- | --- |
| PyPI project name | `vat-whitelist-mcp` |
| GitHub owner | `SmartMobileHouse` |
| Repository | `vat-whitelist-mcp` |
| Workflow filename | `publish.yml` |
| Environment | `pypi` |

The GitHub `pypi` environment must exist. No PyPI API token is needed. See
[PyPI's setup guide](https://docs.pypi.org/trusted-publishers/creating-a-project-through-oidc/).
Keep versions in `pyproject.toml`, `src/vat_whitelist_mcp/__init__.py`, and
`server.json` aligned before tagging. A failed MCP Registry job can be retried
independently after PyPI succeeds.

## Notes & limitations

- Sandbox data is synthetic. Use `VAT_ENV=prod` for live taxpayer information.
- Dates must be no later than today in Poland and fall within the current year
  or the five preceding calendar years, no earlier than 1 September 2019.
  The API may impose additional historical-data restrictions.
- The published limits are 100 search requests per day, up to 30 identifiers per
  request, and 5,000 check verifications per day. Quotas apply to the requesting
  IP; exhausting a quota can block access until midnight. See the
  [official API documentation](https://www.gov.pl/web/kas/api-wykazu-podatnikow-vat)
  for current terms and limits.
- WL2 status queries and flat-file verification are outside this tool set.
- This project is independent and is not affiliated with or endorsed by the
  Ministry of Finance or the National Revenue Administration.

## Contributing

Issues and pull requests are welcome.

## Why vat-whitelist-mcp?

### Checks need a date and an audit trail

The official VAT White List API answers for a specific date, and every check should show where and when the data came from.

### Raw API calls leave the details to every integration

- Identifier formats and checksums are easy to get wrong.
- API failures must not be mistaken for a missing taxpayer.

### This server keeps the checks strict

- Explicit `YYYY-MM-DD` dates on every tool.
- Checksums validated locally before any request.
- API failures raise errors instead of returning `NIE`; request ids and timestamps are kept.

## License

[MIT](LICENSE) © Smart Mobile House. Built and maintained by [Smart Mobile House](https://smartmobilehouse.com).
