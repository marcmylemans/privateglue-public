#!/usr/bin/env bash
_CS_DEFAULT_URL="https://raw.githubusercontent.com/marcmylemans/privateglue-public/main"
_cs_boot="${COMMUNITY_SCRIPTS_CORE_DIR:-$(dirname "${BASH_SOURCE[0]}")/../../core}/core/build.func"
source "$_cs_boot" 2>/dev/null || source <(curl -fsSL "${COMMUNITY_SCRIPTS_CORE_URL:-https://raw.githubusercontent.com/community-scripts/core/main}/core/build.func")

# PrivateGlue as a Proxmox VE LXC container, built on the community-scripts engine.
# Run on the Proxmox host:
#   bash -c "$(curl -fsSL https://raw.githubusercontent.com/marcmylemans/privateglue-public/main/ct/privateglue.sh)"
# Inside the container, "update" brings PrivateGlue to the newest release.
#
# Author: Marc Mylemans (marcmylemans)
# License: MIT
# Source: https://github.com/marcmylemans/privateglue-public

APP="PrivateGlue"
var_tags="${var_tags:-documentation;inventory}"
var_cpu="${var_cpu:-1}"
var_ram="${var_ram:-1024}"
var_disk="${var_disk:-4}"
var_os="${var_os:-debian}"
var_version="${var_version:-13}"
var_unprivileged="${var_unprivileged:-1}"

header_info "$APP"
variables
color
catch_errors

function update_script() {
  header_info
  check_container_storage
  check_container_resources

  if [[ ! -d /opt/privateglue/backend ]]; then
    msg_error "No ${APP} Installation Found!"
    exit
  fi

  if check_for_gh_release "privateglue" "marcmylemans/privateglue-public"; then
    msg_info "Stopping PrivateGlue"
    systemctl stop privateglue
    msg_ok "Stopped PrivateGlue"

    CLEAN_INSTALL=1 CLEAN_INSTALL_KEEP="data notes backups secret" \
      fetch_and_deploy_gh_release "privateglue" "marcmylemans/privateglue-public" "prebuild" "latest" "/opt/privateglue" "privateglue-*.tar.gz"

    msg_info "Updating PrivateGlue Python Environment"
    rm -rf /opt/privateglue/.venv
    $STD uv venv --python /usr/bin/python3 /opt/privateglue/.venv
    $STD uv pip install -r /opt/privateglue/requirements.txt -p /opt/privateglue/.venv/bin/python
    chown -R privateglue:privateglue /opt/privateglue
    msg_ok "Updated PrivateGlue Python Environment"

    msg_info "Starting PrivateGlue"
    systemctl start privateglue
    msg_ok "Started PrivateGlue"
    msg_ok "Updated successfully!"
  fi
  exit
}

start
build_container
description

msg_ok "Completed Successfully!\n"
echo -e "${CREATING}${GN}${APP} setup has been successfully initialized!${CL}"
echo -e "${INFO}${YW}Access it using the following URL:${CL}"
echo -e "${GATEWAY}${BGN}http://${IP}:5000${CL}"
echo -e "${INFO}${YW}Open it soon: the first visitor creates the administrator account.${CL}"
