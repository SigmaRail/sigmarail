# SigmaRail MCP for ChatGPT

## Runtime

`mcp-gateway` is a separate Compose service on loopback port 8003. Tailscale Funnel
routes `/sigmarail/mcp`, its OAuth protected-resource metadata path, and `/register`
to this gateway.
The existing `/` handler and `/mcp` and `/deepvue/mcp` paths continue through the old
gateway on host port 8002. MCP calls go to the authenticated AppTension adapter at
`http://backend:80/api/ai-assistant/chatgpt/mcp/`. Apollo remains private on Compose
port 4000.

The laptop Funnel routes are:

```sh
tailscale funnel --bg --https=443 --set-path=/sigmarail/mcp http://127.0.0.1:8003/sigmarail/mcp
tailscale funnel --bg --https=443 --set-path=/.well-known/oauth-protected-resource/sigmarail/mcp http://127.0.0.1:8003/.well-known/oauth-protected-resource/sigmarail/mcp
tailscale funnel --bg --https=443 --set-path=/register http://127.0.0.1:8003/register
```

The gateway validates access tokens with the Tailscale identity provider, obtains the
OIDC profile from `userinfo`, checks that the profile subject matches token
introspection, then signs a two-minute identity assertion for AppTension. Tailscale's
`tsidp` does not emit `email_verified` by default; the authenticated issuer/subject is
the identity proof, while initial email linking is limited to an existing active,
confirmed AppTension account. An explicit issuer/subject link takes precedence. The
HMAC assertion key is independent of the OAuth introspection client secret. AppTension
checks accepted tenant membership on every tenant-scoped call.

## ChatGPT connector

- Server URL: `https://turnip.tail850cb1.ts.net/sigmarail/mcp`
- Authentication: OAuth
- Authorization server / issuer: `https://vera-idp.tail850cb1.ts.net`
- Authorization endpoint: `https://vera-idp.tail850cb1.ts.net/authorize`
- Token endpoint: `https://vera-idp.tail850cb1.ts.net/token`
- Registration URL override: `https://turnip.tail850cb1.ts.net/register`
- Discovery: `https://vera-idp.tail850cb1.ts.net/.well-known/openid-configuration`
- Scopes: `openid profile email`; request `offline_access` only if the provider adds it
  to discovery and issues refresh tokens for it.

Tailscale Funnel intentionally rejects direct requests to tsidp's `/register`
endpoint. Its public discovery metadata now advertises the SigmaRail gateway's
`/register` relay instead. The gateway forwards allowed ChatGPT DCR requests to tsidp
from inside the tailnet. It accepts only HTTPS ChatGPT callback URLs,
authorization-code clients, and the client-auth methods and scopes advertised by
tsidp. Keep the authorization and token endpoints pointed at the issuer above.

The tsidp image is built from the pinned upstream revision with
`deploy/tsidp/metadata.patch`; the patch changes only the advertised registration
endpoint in its two discovery documents. Build with
`docker build -f deploy/tsidp/Dockerfile -t sigmarail/tsidp-dcr-relay:local .`.
When replacing `vera-tsidp`, preserve its `vera-tsidp-state` volume and existing
environment (`TSIDP_ENABLE_STS=1`, `TSIDP_USE_FUNNEL=1`, `TAILSCALE_USE_WIP_CODE=1`,
`TS_STATE_DIR=/data`, `TS_HOSTNAME=vera-idp`).

The IdP advertises authorization-code and refresh-token grants and DCR. It does not
advertise `offline_access`, but its authorization-code flow issues refresh tokens and
its refresh-token grant is available. Use `openid profile email`; confirm ChatGPT
actually renews a token after connector authorization before relying on long-lived access.

## SigmaRail read tool

`get_sigmarail_stock_snapshot` returns latest or as-of daily price, sector, RS rating,
ATR, stage and moving averages. It is a read-only ClickHouse query through the
SigmaRail query adapter. `tenantContext` is a proxy-only selector; the backend resolves
it only against the signed-in user's accepted tenant memberships. Apollo is configured
with mutation mode `none`.
