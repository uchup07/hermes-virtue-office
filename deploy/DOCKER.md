# Keep the office online with Docker

The embedded viewer lives inside a Hermes process. It starts on the first hook and stops when that process exits. It does **not** stop merely because a living Hermes process is idle. A proxy returns 502 when its office upstream is unavailable; closing or restarting the Hermes container can cause that with embedded mode.

Run the web viewer in its own container. The Hermes plugin writes to a shared SQLite directory; the viewer stays online even with no active sessions. This deployment keeps password login enabled.

## 1. Identify the existing Hermes data directory

`HERMES_HOME_HOST` must be the **host directory mounted as HERMES_HOME in your Hermes container**, not a path existing only inside the container. Both containers must use the same `virtue-office` subdirectory. Do not copy the SQLite file between containers.

Examples below use `/srv/hermes` as the host data directory. Replace it with your actual path. Configure the UID/GID to match the account that writes Hermes state (check `id` in the Hermes container). The office container runs as that UID/GID so it can read the password file and write the shared SQLite WAL files.

```sh
cd /path/to/hermes-virtue-office
git pull
export HERMES_HOME_HOST=/srv/hermes
export OFFICE_PASSWORD_FILE=/srv/hermes/virtue-office-password
export OFFICE_UID=1000
export OFFICE_GID=1000
mkdir -p "$HERMES_HOME_HOST/virtue-office"
```

Create the password file using the password instructions in README if you have not already done so. Its owner and the shared data directory's owner must match OFFICE_UID/OFFICE_GID; keep the password file readable only by its owner (`chmod 600`). If Hermes runs as another UID, set those values accordingly. Set `OFFICE_PASSWORD_FILE` to the **host path** of your existing password file. These variables can be placed in a local `.env` file (ignored by Git); only paths and IDs go there, not the password itself.

## 2. Make the plugin a state writer

In the Hermes container's `config.yaml`, merge:

```yaml
plugins:
  enabled:
    - virtue-office
  entries:
    virtue-office:
      server_mode: external
```

Alternatively set `VIRTUE_OFFICE_SERVER_MODE=external` in that container's environment. Restart Hermes so it loads the updated plugin/configuration. External mode still records sessions, tools, subagents and approvals but does not start an embedded HTTP server.

The plugin checkout inside Hermes must also be updated to include this change. An update on the host only affects Hermes if the plugin directory is bind-mounted there.

## 3. Start the independent viewer

```sh
docker compose up -d --build
docker compose ps
curl -f http://127.0.0.1:8114/health
```

Docker publishes the viewer on the VPS loopback interface. It restarts on process failure and host reboot (with Docker enabled), except after an explicit stop. No Hermes session or tool call is required for startup. The viewer reads `/data`, mapped to the same directory written by the plugin.

## 4. Point the existing public proxy at this viewer

For Nginx **running directly on the VPS**, use this upstream in your existing HTTPS virtual host:

```nginx
location / {
    proxy_pass http://127.0.0.1:8114;
    proxy_set_header Host 127.0.0.1:8114;
    proxy_set_header X-Forwarded-Proto $scheme;
}
```

For a proxy **inside Docker**, `127.0.0.1` points to the proxy container itself. Attach that proxy and `virtue-office` to the same Docker network and use `http://virtue-office:8114` as the upstream, while keeping the upstream Host header `127.0.0.1:8114`. Forward `X-Forwarded-Proto: https` from the HTTPS proxy. Route all pages, assets, `/state`, `/login` and `/logout` to the Python viewer.

The Compose file creates its default network; you can attach the proxy to it or add your existing proxy network through a Compose override. Keep password login and HTTPS active.

## Check an idle office

After stopping only the Hermes container, `/health` and `/login` should still respond from the office container. Ended sessions eventually disappear, leaving an empty office rather than 502.

If it still returns 502, inspect:

```sh
docker compose logs --tail=100 virtue-office
docker compose ps
curl -i http://127.0.0.1:8114/health
```

- Viewer exited: check password file, mounted directory, UID/GID and bind permissions in its logs.
- `/health` works but public URL returns 502: check proxy upstream address and Docker network membership.
- Office online but no activity appears: verify both containers share the same host state directory and the Hermes plugin is enabled.
