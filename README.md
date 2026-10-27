# vat-whitelist-mcp

<!-- mcp-name: io.github.SmartMobileHouse/vat-whitelist-mcp -->

A [Model Context Protocol](https://modelcontextprotocol.io) server project for the
**Polish VAT White List** (Wykaz podatników VAT). Designed to give AI assistants
structured taxpayer lookups by **NIP**, **REGON**, or **bank account**, together
with account verification for a specified date.

The official [VAT White List API](https://www.gov.pl/web/kas/api-wykazu-podatnikow-vat)
provides taxpayer details and confirmation identifiers for lookups and checks.

> Built and maintained by [Smart Mobile House](https://smartmobilehouse.com) —
> secure AI implementation for enterprise.

**Status:** In development. The VAT API integration is pending; the tools and
configuration below describe the intended interface and are not available yet.

## Tools

| Planned tool | Description |
| --- | --- |
| `search_by_nip(nip, date)` | Look up a taxpayer by 10-digit NIP (tax id). |
| `search_by_regon(regon, date)` | Look up a taxpayer by REGON. |
| `search_by_bank_account(bank_account, date)` | Look up taxpayers associated with an account. |
| `search_bulk(identifiers, id_type, date)` | Look up multiple identifiers of one type. |
| `check_bank_account(identifier, id_type, bank_account, date)` | Verify an account's association with a NIP or REGON. |

Each tool will require an explicit `YYYY-MM-DD` date. Responses will retain the
API's confirmation identifiers and include a `source` block identifying the
register, environment, and UTC retrieval time.

## Quick start

Once the VAT integration is available, run it directly from the repository with
[uv](https://docs.astral.sh/uv/):

```bash
uvx --from git+https://github.com/SmartMobileHouse/vat-whitelist-mcp vat-whitelist-mcp
```

### Use it in Claude Desktop / Claude Code

Planned MCP configuration (e.g. `claude_desktop_config.json` or `.mcp.json`):

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

During development, the local checkout path can replace the Git URL in `--from`.

## Configuration

Planned environment variables:

| Variable | Default | Description |
| --- | --- | --- |
| `VAT_ENV` | `test` | `test` for the sandbox or `prod` for live data. |
| `VAT_TIMEOUT` | `30` | HTTP timeout in seconds. |

## Development

```bash
git clone https://github.com/SmartMobileHouse/vat-whitelist-mcp
cd vat-whitelist-mcp
uv sync                 # create the venv and install dependencies
uv run pytest           # offline tests; live tests are skipped by default
uv build                # build source and wheel distributions
```

The project uses Python, the MCP SDK, httpx, and pytest, with stdio as the MCP
transport. Current tests cover the development scaffold; they do not yet verify
the VAT API integration.

## Notes & limitations

- VAT lookups and account checks are not implemented yet. Installation does not
  currently provide the planned VAT tools.
- Respect the Ministry of Finance's API terms and request limits. See the
  [official API documentation](https://www.gov.pl/web/kas/api-wykazu-podatnikow-vat)
  for current endpoints, quotas, and supported query dates.
- This project is independent and is not affiliated with or endorsed by the
  Ministry of Finance or the National Revenue Administration.

## License

[MIT](LICENSE) © Smart Mobile House
