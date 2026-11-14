#!/usr/bin/env bash

# Runs inside the new container. Installs PrivateGlue without Docker: the release archive
# in /opt/privateglue, a Python environment next to it, and a systemd service that runs
# the app as its own unprivileged user.
#
# Author: Marc Mylemans (marcmylemans)
# License: MIT
# Source: https://github.com/marcmylemans/privateglue-public

source /dev/stdin <<<"$FUNCTIONS_FILE_PATH"
color
verb_ip6
catch_errors
setting_up_container
network_check
update_os

msg_info "Installing Dependencies"
$STD apt install -y python3 iputils-ping iproute2 openssl
msg_ok "Installed Dependencies"

fetch_and_deploy_gh_release "privateglue" "marcmylemans/privateglue-public" "prebuild" "latest" "/opt/privateglue" "privateglue-*.tar.gz"
setup_uv

msg_info "Setting up PrivateGlue"
$STD uv venv --python /usr/bin/python3 /opt/privateglue/.venv
$STD uv pip install -r /opt/privateglue/requirements.txt -p /opt/privateglue/.venv/bin/python
if ! id privateglue >/dev/null 2>&1; then
  useradd --system --home-dir /opt/privateglue --no-create-home --shell /usr/sbin/nologin privateglue
fi
mkdir -p /opt/privateglue/{data,notes,backups,secret}
chown -R privateglue:privateglue /opt/privateglue
mkdir -p /etc/privateglue
cat <<ENVFILE >/etc/privateglue/privateglue.env
# Settings for PrivateGlue. Change a value, then: systemctl restart privateglue
# SECRET_KEY signs the sign-in sessions. Keep it; changing it signs everyone out.
SECRET_KEY=$(openssl rand -hex 32)
PRIVATEGLUE_HOME=/opt/privateglue
PYTHONPATH=/opt/privateglue
PYTHONUNBUFFERED=1
TRUSTED_PROXIES=0
FORCE_HTTPS=false
ALLOW_SERVER_SCAN=false
INTEGRATIONS_SCHEDULER=on
ENVFILE
chown root:privateglue /etc/privateglue/privateglue.env
chmod 640 /etc/privateglue/privateglue.env
msg_ok "Set up PrivateGlue"

msg_info "Creating Service"
cat <<UNITFILE >/etc/systemd/system/privateglue.service
[Unit]
Description=PrivateGlue
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=privateglue
Group=privateglue
WorkingDirectory=/opt/privateglue
EnvironmentFile=/etc/privateglue/privateglue.env
ExecStart=/opt/privateglue/.venv/bin/gunicorn --bind 0.0.0.0:5000 --workers 2 --access-logfile - --error-logfile - backend.app:app
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
UNITFILE
systemctl enable -q --now privateglue
msg_ok "Created Service"

motd_ssh
customize
cleanup_lxc
