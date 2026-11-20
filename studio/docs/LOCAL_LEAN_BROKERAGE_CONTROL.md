# Local LEAN brokerage control

Studio can manage up to two isolated local LEAN Docker deployments. Each run gets
a private snapshot of the `VeraTradingLab` Python sources and its own LEAN output
directory, so stop/liquidate commands can target the selected algorithm.

## Supported account profiles

The Deploy panel currently exposes these installed-CLI adapters:

- Alpaca, Interactive Brokers, Tradier, and TradeStation (paper and live)
- OANDA (Practice and Trade)
- Binance, Bybit, and dYdX (paper/testnet and live)
- Kraken, Bitfinex, Coinbase Advanced Trade, Charles Schwab, Eze, Zerodha, and Samco (live)

This catalog is intentionally explicit. A CLI brokerage option alone does not
prove the broker account, local LEAN image, regional availability, market-data
subscription, or algorithm asset class will work. Those conditions must be
validated for each account before routine use. Brokerage and live data feed are
separate profile fields. Feed options include each listed brokerage feed plus
Polygon, IQFeed, CoinAPI, Databento, ThetaData, and custom-data-only. Brokerage-only
connections such as Webull, Public, and Clear Street are intentionally not offered
because the current requirement is to use brokers that also provide live data.
Tastytrade's LEAN CLI flow requires an OAuth/browser handoff, so it is not exposed
until Studio supports that authorization lifecycle.

Choosing a live-capable feed does not grant market-data entitlements. Real-time
coverage depends on the provider's account plan, exchange permissions, and the
algorithm's subscribed instruments. A paper brokerage can be paired with a separate
live-data provider; the Deploy form shows the broker and data provider separately.

## Credential and runtime handling

- Account label, brokerage, live-data feed, environment, and optional account identifier are in
  Studio's local SQLite database (`LiveAccountProfile`).
- Broker credential fields are stored as one profile-specific entry in the OS
  credential vault: macOS Keychain, Windows Credential Manager, or Linux Secret
  Service/KWallet. Insecure file/null keyring backends are rejected.
- Studio builds a mode-0600 temporary LEAN config overlay. It removes unrelated
  provider secrets from the workspace config, adds only the selected profile's
  credentials, and passes no credential values in CLI arguments. LEAN needs the
  selected credentials while its engine is running, so its private Docker-mounted
  runtime config must be treated as a secret.
- The original single Alpaca-paper profile remains readable. Saving its new
  credentials migrates the legacy Alpaca values out of `LeanProjects/lean.json`.

## Enable local controls

Install Studio dependencies (`pip install -e .`), run `python manage.py migrate`,
and start the Studio API with `SIGMARAIL_ENABLE_LOCAL_LEAN_CONTROL=1`. Control requests
must originate from an allowed same-origin browser on the local machine. Do not
expose this unauthenticated API through a public or Tailscale reverse proxy.

Choose a saved broker profile, select a passing backtest, then start the
deployment. Paper profiles use a normal confirmation. A live profile requires
typing `LIVE <account label>` at launch. Stopping or liquidating a live algorithm
also requires typing an action-specific confirmation that includes the selected
deployment ID suffix. Liquidation submits market orders; it does not merely stop
the algorithm. Stopping leaves positions at the broker and does not liquidate.

This changes no production systems by itself. A first validation should use a
broker's no-money paper/test account, confirm orders and fills at that broker, and
verify recovery after container restart before enabling any live profile. Studio
does not automatically restart containers after a host reboot.

## Algorithm monitoring

The Monitor page reads LEAN's per-algorithm result snapshot for each managed
deployment. It displays LEAN's allowlisted runtime and summary statistics,
holdings, orders, and snapshot time; Studio does not recompute the strategy
metrics. LEAN persists snapshots less often than the UI polls, so the UI shows
the snapshot `as_of` time and does not imply tick-by-tick updates.
