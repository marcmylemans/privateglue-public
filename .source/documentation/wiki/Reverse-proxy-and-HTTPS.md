# Reverse proxy and HTTPS

PrivateGlue speaks plain HTTP on its port. To reach it over HTTPS, and for anything reachable from outside your own network, put a reverse proxy in front: Caddy, Nginx Proxy Manager, Traefik, nginx or similar.

## Two settings

When PrivateGlue sits behind a reverse proxy with HTTPS, add both to `.env` and apply with `docker compose up -d`:

```ini
FORCE_HTTPS=true
TRUSTED_PROXIES=1
```

| Setting | Why |
|---|---|
| `FORCE_HTTPS=true` | Login cookies are only sent over HTTPS, and browsers are told to always use HTTPS for this address. Only set it when HTTPS really works, otherwise you cannot sign in over plain HTTP any more. |
| `TRUSTED_PROXIES=1` | Tells PrivateGlue to believe the proxy about the visitor's real address. Without it, all visitors share one login rate limit, so one person failing to sign in can lock everyone out for a minute. Use the number of proxies in the chain, usually 1. |

Leave `TRUSTED_PROXIES` at `0` when there is no proxy. Otherwise anyone could fake their address.

## What the proxy must do

Forward requests to `http://<privateglue host>:5000` and pass these headers on: `Host`, `X-Forwarded-For`, `X-Forwarded-Proto`. Most proxies do this by themselves.

### Caddy

```
glue.example.com {
    reverse_proxy 127.0.0.1:5000
}
```

### nginx

```nginx
server {
    listen 443 ssl;
    server_name glue.example.com;
    # ssl_certificate and ssl_certificate_key go here

    client_max_body_size 10m;

    location / {
        proxy_pass http://127.0.0.1:5000;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

### Nginx Proxy Manager

Add a proxy host with your domain, scheme `http`, the address of the PrivateGlue machine and port `5000`. Request a certificate on the SSL tab and turn on **Force SSL**.

## Keep the plain port private

Once the proxy works, visitors should not be able to skip it. Either block the PrivateGlue port in the firewall, or publish it on the local address only by changing the port line in `docker-compose.yml`:

```yaml
    ports:
      - "127.0.0.1:${PRIVATEGLUE_PORT:-5000}:5000"
```

This works when the proxy runs on the same machine.

## Check it

- The address bar shows a padlock.
- Signing in works.
- The network probe, if you use it, has the `https://` address.
