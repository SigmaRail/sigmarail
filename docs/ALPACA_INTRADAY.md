# Alpaca intraday bars

SigmaRail stores the optional Alpaca feed in the `ext_alpaca_*` namespace. It does
not add Alpaca objects to the Sharadar-owned core schema manifest. The extension
contains raw five-minute bars, Alpaca's regular-session calendar, and a view of
session-open-anchored 65-minute bars.

## Credentials

The loader reads an existing SigmaRail Studio Alpaca profile by UUID. Studio keeps
the non-secret profile record in its local application database and stores the
credential JSON in the operating-system credential vault under
`sigmarail-studio/broker/<profile UUID>`, account `credentials`. SigmaRail reads that
existing Keychain/credential-manager item; it does not accept an API key or secret
in configuration, a command argument, a data file, or logs. The vault adapter
rejects insecure keyring backends.

The profile UUID is not an API secret. Select an active Alpaca profile in Studio
and provide its UUID to the CLI. The reader checks that the UUID is well formed
and that a credential entry exists; Studio remains the source of profile status
and account metadata. No account name or user identifier is copied into the bars.

## Schema setup

The normal `sigmarail-schema` command remains limited to core SigmaRail tables.
Preview the Alpaca extension DDL with:

```sh
sigmarail-alpaca-schema --mode test
```

Apply it explicitly to the selected test database with:

```sh
sigmarail-alpaca-schema --mode test --apply
```

`--apply` is required to execute the extension's three idempotent ClickHouse
statements. Production remains an explicit operator action using `--mode prod
--apply`; it is not run as part of automated validation.

## Import

The loader requires an explicit symbol list or file. It deliberately does not
derive a historical universe from Alpaca's current active-asset catalog, which
would silently exclude delisted symbols and introduce survivorship bias.

Example: fetch (without writing) the final 65 minutes for SPY:

```sh
sigmarail-load-alpaca \
  --mode test \
  --environment paper \
  --session-date YYYY-MM-DD \
  --symbols SPY \
  --studio-profile-id <studio-profile-uuid>
```

Add `--write` to insert into the ClickHouse database selected by `--mode`. A date
range imports full regular sessions by default and uses the Alpaca calendar for
holidays and early closes:

```sh
sigmarail-load-alpaca \
  --mode test \
  --environment paper \
  --start-date YYYY-MM-DD \
  --end-date YYYY-MM-DD \
  --symbols-file /path/to/symbols.txt \
  --studio-profile-id <studio-profile-uuid> \
  --write
```

The feed defaults to IEX and adjustment defaults to raw; both are explicit
columns in the data key. Choose `--feed sip` only for profiles with SIP data
entitlement. Reimporting a bar writes a newer `ingested_at` version, allowing
`ReplacingMergeTree`/`FINAL` reads to expose provider corrections.

## Data objects and caveats

- `ext_alpaca_price`: five-minute OHLCV, trade count, VWAP, feed, adjustment, and
  ingestion time. The timestamp is the start of the Alpaca bar, in UTC.
- `ext_alpaca_market_calendar`: official regular-session open/close in UTC,
  including early closes.
- `ext_alpaca_price_65m`: 65-minute bars anchored to the session open. A shortened
  last interval is marked; `observed_5m_bars` and `expected_5m_time_slots` show
  coverage. Missing/no-trade bars are not synthesized.

The explicit symbol list is not itself a point-in-time universe. Historical
research must supply and retain the point-in-time universe manifest separately.
No intraday indicator, query API projection, or strategy integration is claimed
by this import package.
