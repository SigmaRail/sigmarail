# Apollo MCP for ChatGPT

SigmaRail uses the existing Apollo MCP server in `packages/mcp-server`.
ChatGPT's stable public URL is `https://turnip.tail850cb1.ts.net/sigmarail/mcp`.

## Request path

`ChatGPT -> Tailscale OAuth gateway -> AppTension ChatGPT MCP adapter -> Apollo MCP -> AppTension GraphQL`

The gateway endpoint is intentionally the same one public MCP URL. Its adapter
authenticates the Tailscale identity, maps it to an active AppTension account,
checks accepted tenant membership for tenant-scoped calls, mints a short-lived
AppTension JWT, and forwards the MCP request to Apollo. Apollo forwards that JWT
and the authorized `X-Tenant-ID` to GraphQL. Do not expose Apollo directly or
pass a shared privileged token from ChatGPT.

## Start Apollo in the primary Compose stack

From the primary SigmaRail checkout, use `deploy/compose.primary.yml`. It builds
the pinned Apollo image from `packages/mcp-server/Dockerfile`, points it at the
backend GraphQL endpoint, and defaults mutations to disabled. Apollo stays on
the private Compose network. Keep the public MCP route pointed at the
authenticated backend MCP adapter; do not publish Apollo directly.

The backend already defaults `MCP_SERVER_URL` to `http://mcp-server:4000`.
Set `CHATGPT_MCP_GATEWAY_HMAC_SECRET` on the backend and configure the same
secret in the gateway's Keychain. Configure the issuer as
`https://vera-idp.tail850cb1.ts.net` and resource audience as
`https://turnip.tail850cb1.ts.net`. The gateway route must proxy the MCP stream
to `http://127.0.0.1:5001/api/ai-assistant/chatgpt/mcp/`, not directly to
Apollo. Protect the existing `/mcp` and `/deepvue/mcp` routes from changes.

## ChatGPT custom MCP settings

- Server URL: `https://turnip.tail850cb1.ts.net/sigmarail/mcp`
- Authentication: OAuth
- Authorization server: `https://vera-idp.tail850cb1.ts.net`
- Authorization URL: `https://vera-idp.tail850cb1.ts.net/authorize`
- Token URL: `https://vera-idp.tail850cb1.ts.net/token`
- Registration URL override: `https://turnip.tail850cb1.ts.net/register`
- Scopes: `openid`, `profile`, `email`
- Registration method: Dynamic Client Registration. Tailscale Funnel blocks tsidp's
  direct `/register` endpoint, so use the SigmaRail gateway's constrained relay.

ChatGPT obtains its OAuth client credentials through DCR; do not put the
gateway's introspection client credentials into ChatGPT. Validate protected
resource metadata, DCR, OAuth login, `initialize`, `tools/list`, `get_user_tenants`,
and one tenant-scoped read before considering the integration operational.
