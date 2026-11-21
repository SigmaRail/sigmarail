# SigmaRail MCP for ChatGPT

## Request path

`ChatGPT → shared Tailscale OAuth gateway → SigmaRail MCP endpoint → AppTension-backed service`

The gateway introspects ChatGPT's bearer token with the configured Tailscale IdP, fetches the authenticated user's profile from the IdP `userinfo` endpoint, then signs a short-lived identity assertion. The SigmaRail service verifies the HMAC and maps the verified `(issuer, subject)` to an existing confirmed account by the IdP-provided email on first use. It stores that link in PostgreSQL and checks the user's accepted tenant membership on every request. Tenant IDs select a scope; they do not grant access.

Use one ChatGPT MCP server URL per tenant:

`https://<tailnet-host>/sigmarail/mcp/<tenant-id>`

The gateway must remove caller-supplied `X-MCP-Gateway-Identity` headers before attaching its own. The HMAC key is separate from the Tailscale introspection client secret and must be installed in the gateway Keychain and in the backend's `CHATGPT_MCP_GATEWAY_HMAC_SECRET` environment variable. Never commit either value.

Backend settings:

- `CHATGPT_MCP_GATEWAY_HMAC_SECRET`
- `CHATGPT_MCP_IDP_ISSUER` (exact issuer URL)
- `CHATGPT_MCP_RESOURCE_AUDIENCE` (resource URI advertised to ChatGPT)

Gateway settings:

- `SIGMARAIL_MCP_UPSTREAM` (private AppTension API listener)
- `SIGMARAIL_MCP_IDENTITY_KEYCHAIN_SERVICE`
- `SIGMARAIL_MCP_IDENTITY_KEYCHAIN_ACCOUNT`
- `SIGMARAIL_MCP_RESOURCE_URL` (defaults to `https://<tailnet-host>/sigmarail/mcp`)

The identity assertion is accepted only on the dedicated ChatGPT endpoint. The existing browser-facing MCP route continues using AppTension JWT/session authentication. The gateway does not forward ChatGPT's OAuth bearer token to the backend; the Django proxy uses the authenticated account and tenant authorization for downstream MCP requests.

## Before enabling the Tailscale route

1. Configure one random HMAC key in the gateway Keychain and the SigmaRail backend environment; restart both services.
2. Confirm Tailscale introspection returns `iss`, `aud`, and `exp`, and its `userinfo` endpoint returns a stable `sub` and email for the ChatGPT access token. The gateway rejects missing profile identity and expired tokens.
3. Apply the SigmaRail backend migration and confirm the intended user has an accepted membership in the target tenant.
4. Add the SigmaRail gateway resource metadata and exact `/sigmarail/mcp/<tenant-id>` route. Do not point the existing `/mcp` route at AppTension; it remains Vera's compatibility route.
5. Verify user A can call only tenants where A has accepted membership, user B cannot reuse A's access, and invalid/expired signatures are rejected. Then configure the custom MCP server in ChatGPT and refresh its tool list.

The checked-in gateway source is not the same file as the currently launched `~/.vera/mcp_oauth_gateway.py`; these changes do not alter the live Tailscale route. A separate reviewed cutover is required to install the new route in the active gateway.
