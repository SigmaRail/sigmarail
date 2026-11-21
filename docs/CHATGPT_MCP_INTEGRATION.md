# AppTension MCP for ChatGPT

## Request path

`ChatGPT → Tailscale OAuth gateway → AppTension Django MCP proxy → Apollo MCP → AppTension GraphQL`

The gateway introspects ChatGPT's bearer token with the configured Tailscale IdP, fetches the authenticated user's profile from the IdP `userinfo` endpoint, then signs a short-lived identity assertion. AppTension verifies the HMAC and maps the verified `(issuer, subject)` to an existing confirmed AppTension user by the IdP-provided email on first use. It stores that link in PostgreSQL. AppTension then checks that user's accepted membership in the tenant named in the MCP URL on every request. Tenant IDs select a scope; they do not grant access.

Use one ChatGPT MCP server URL per tenant:

`https://<tailnet-host>/apptension/mcp/<tenant-id>`

The gateway must remove caller-supplied `X-MCP-Gateway-Identity` headers before attaching its own. The HMAC key is separate from the Tailscale introspection client secret and must be installed in the gateway Keychain and in the backend's `CHATGPT_MCP_GATEWAY_HMAC_SECRET` environment variable. Never commit either value.

Backend settings:

- `CHATGPT_MCP_GATEWAY_HMAC_SECRET`
- `CHATGPT_MCP_IDP_ISSUER` (exact issuer URL)
- `CHATGPT_MCP_RESOURCE_AUDIENCE` (resource URI advertised to ChatGPT)

Gateway settings:

- `APPTENSION_MCP_UPSTREAM` (private AppTension API listener)
- `APPTENSION_MCP_IDENTITY_KEYCHAIN_SERVICE`
- `APPTENSION_MCP_IDENTITY_KEYCHAIN_ACCOUNT`

The identity assertion is accepted only on the dedicated ChatGPT endpoint. The existing browser-facing AppTension MCP route continues using AppTension JWT/session authentication. The bridge does not forward the external bearer token to AppTension or ClickHouse; the Django proxy issues a short-lived internal AppTension JWT for Apollo and GraphQL.

## Before enabling the Tailscale route

1. Configure one random HMAC key in the gateway Keychain and the AppTension backend environment; restart both services.
2. Confirm Tailscale introspection returns `iss`, `aud`, and `exp`, and its `userinfo` endpoint returns a stable `sub` and email for the ChatGPT access token. The gateway rejects missing profile identity and expired tokens.
3. Apply the AppTension migration and confirm the intended user has an accepted membership in the target tenant.
4. Add the gateway resource metadata and exact `/apptension/mcp/<tenant-id>` route. Do not point the existing `/mcp` route at AppTension; it remains Vera's compatibility route.
5. Verify user A can call only tenants where A has accepted membership, user B cannot reuse A's access, and invalid/expired signatures are rejected. Then configure the custom MCP server in ChatGPT and refresh its tool list.

The checked-in gateway source is not the same file as the currently launched `~/.vera/mcp_oauth_gateway.py`; these changes do not alter the live Tailscale route. A separate reviewed cutover is required to install the new route in the active gateway.
