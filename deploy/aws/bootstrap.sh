#!/usr/bin/env bash
# Run once on an Amazon Linux 2023 x86_64 host, after explicitly creating it.
set -euo pipefail

if [[ $(uname -m) != x86_64 || ! -f /etc/amazon-linux-release ]]; then
  echo 'This script requires Amazon Linux 2023 on x86_64.' >&2
  exit 1
fi
if ! grep -q 'Amazon Linux release 2023' /etc/amazon-linux-release; then
  echo 'Unsupported Amazon Linux release.' >&2
  exit 1
fi

sudo dnf install -y docker
sudo systemctl enable --now docker
sudo usermod -aG docker ec2-user

# Pin Compose; verify the release checksum before installing the plugin.
compose_version=v5.6.0
download_dir=$(mktemp -d)
trap 'rm -rf "$download_dir"' EXIT
asset=docker-compose-linux-x86_64
release="https://github.com/docker/compose/releases/download/$compose_version"
curl --fail --location --retry 3 "$release/$asset" -o "$download_dir/$asset"
curl --fail --location --retry 3 "$release/$asset.sha256" -o "$download_dir/$asset.sha256"
(cd "$download_dir" && sha256sum --check "$asset.sha256")
sudo install -D -m 0755 "$download_dir/$asset" /usr/local/lib/docker/cli-plugins/docker-compose
echo 'Docker is installed. Log out and reconnect before running deploy.sh.'
