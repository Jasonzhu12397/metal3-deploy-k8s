#!/usr/bin/env python3
"""
Shared by setup-https-selfsigned.sh and setup-https-letsencrypt.sh:
removes direct port exposure for postgres/redis/api/frontend and adds an
nginx service in front of everything. Exact-string-match based (not a
real YAML merge) -- deliberately mirrors the original hand-rolled
version of this patch rather than introducing a YAML library dependency,
but that means it silently does nothing if docker-compose.yml's
structure has drifted from what's expected here. Always check the
"Current exposed ports" output the calling script prints after this
runs -- if postgres/redis/api ports are still listed, this didn't match
and you're still directly exposed.
"""
import sys
from pathlib import Path

NGINX_SERVICE_NAME = "nginx"


def patch(compose_path: Path, nginx_service_yaml: str) -> None:
    text = compose_path.read_text()

    # Remove the obsolete top-level `version:` field (compose v2 doesn't
    # want it and warns about it).
    lines = [line for line in text.splitlines() if not line.strip().startswith("version:")]
    text = "\n".join(lines).rstrip() + "\n"

    # ----------------------------------------------------------
    # Replace frontend ports with expose (still reachable from other
    # containers on the compose network, just not bound to the host).
    # ----------------------------------------------------------
    old_frontend = '''  frontend:
    build:
      context: ./frontend
    restart: unless-stopped
    ports:
      - "8080:80"
    depends_on:
      - api'''
    new_frontend = '''  frontend:
    build:
      context: ./frontend
    restart: unless-stopped
    expose:
      - "80"
    depends_on:
      - api'''
    if old_frontend in text:
        text = text.replace(old_frontend, new_frontend)
    elif '    ports:\n      - "8080:80"' in text:
        text = text.replace('    ports:\n      - "8080:80"', '    expose:\n      - "80"')
    else:
        print("WARNING: frontend 8080 port block was not found -- frontend may still be directly exposed.")

    # ----------------------------------------------------------
    # Remove externally exposed API port.
    # ----------------------------------------------------------
    before = text
    text = text.replace(
        '    ports:\n      - "8000:8000"\n    depends_on:',
        "    depends_on:",
        1,
    )
    if text == before:
        print("WARNING: api 8000 port block was not found -- api may still be directly exposed.")

    # ----------------------------------------------------------
    # Remove externally exposed PostgreSQL port.
    # ----------------------------------------------------------
    before = text
    text = text.replace(
        '    ports:\n      - "5432:5432"\n    healthcheck:',
        "    healthcheck:",
        1,
    )
    if text == before:
        print("WARNING: postgres 5432 port block was not found -- postgres may still be directly exposed.")

    # ----------------------------------------------------------
    # Remove externally exposed Redis port.
    # ----------------------------------------------------------
    before = text
    text = text.replace(
        '    ports:\n      - "6379:6379"\n\n  api:',
        "\n  api:",
        1,
    )
    if text == before:
        print("WARNING: redis 6379 port block was not found -- redis may still be directly exposed.")

    # ----------------------------------------------------------
    # Add the nginx service if not already present.
    # ----------------------------------------------------------
    if f"\n  {NGINX_SERVICE_NAME}:\n" not in text:
        marker = "\nvolumes:\n"
        if marker in text:
            text = text.replace(marker, "\n" + nginx_service_yaml + "\nvolumes:\n", 1)
        else:
            text = text.rstrip() + "\n\n" + nginx_service_yaml

    compose_path.write_text(text)


if __name__ == "__main__":
    compose_file = Path(sys.argv[1])
    # Default: the self-signed nginx service (bind-mounts a static
    # nginx.conf + certs directory, no certbot involved).
    default_nginx_service = '''
  nginx:
    image: nginx:1.27-alpine
    restart: unless-stopped
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./deploy/nginx/nginx.conf:/etc/nginx/nginx.conf:ro
      - ./deploy/nginx/certs:/etc/nginx/certs:ro
    depends_on:
      - frontend
'''
    patch(compose_file, default_nginx_service)
