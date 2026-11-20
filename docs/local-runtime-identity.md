# Local runtime identity

The UI and API expose separate identity endpoints so a running preview can be tied to its actual source and runtime.

- `GET /runtime/identity` is served by the Vite preview process. It reports its PID, current working directory, listening port, source revision/branch, tracked-source dirty state, browser origin, and the current `tailscale serve status --json` output.
- Authenticated `GET /api/runtime/identity` is served by Django. It reports the API revision/branch/source tree, container hostname, image ID, internal and published API ports, and configured Tailscale forwarding target.
- The UI's **Runtime** control queries both endpoints and compares the UI and API revisions.

For Docker Compose previews, include `deploy/runtime-identity.compose.yml` as an additional Compose file. Set `SIGMARAIL_RUNTIME_API_HOST_PORT`, `SIGMARAIL_RUNTIME_TAILSCALE_HOST`, `SIGMARAIL_RUNTIME_TAILSCALE_PORT`, `SIGMARAIL_RUNTIME_TAILSCALE_TARGET`, and `SIGMARAIL_IMAGE_ID` from the active local runtime when starting the backend. If a value cannot be determined, leave it unset; the API reports `unknown` rather than inventing a value.

These endpoints are operational diagnostics, not a trust or authorization boundary. Keep them behind the application's normal authentication and network access controls.
