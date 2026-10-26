#!/bin/sh
set -eu
if [ "$(id -u)" != 0 ]; then
  echo 'Run with sudo: sudo sh install-service.sh [port]' >&2
  exit 1
fi
project_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
port=${1:-12890}
python_bin=$(command -v python3)
command -v openssl >/dev/null || { echo 'Please install openssl first.' >&2; exit 1; }
case "$project_dir" in *' '*|*'%'*|*'"'*) echo 'Use a project directory without spaces, percent signs or quotes.' >&2; exit 1;; esac
"$python_bin" "$project_dir/deploy.py" install
"$python_bin" "$project_dir/deploy.py" run --help >/dev/null
# Validate before writing the unit.
"$python_bin" -c 'import sys; p=int(sys.argv[1]); assert 1024 <= p <= 65534' "$port"
cat > /etc/systemd/system/subnest-x-preview.service <<EOF
[Unit]
Description=SubNest X isolated reference preview
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=$project_dir
ExecStart=$python_bin $project_dir/deploy.py run --port $port
Restart=on-failure
RestartSec=5
UMask=0077

[Install]
WantedBy=multi-user.target
EOF
systemctl daemon-reload
systemctl enable subnest-x-preview
systemctl restart subnest-x-preview
if ! "$python_bin" "$project_dir/deploy.py" wait --port "$port"; then
  systemctl --no-pager -l status subnest-x-preview || true
  journalctl -u subnest-x-preview -n 40 --no-pager -o cat || true
  exit 1
fi
systemctl --no-pager status subnest-x-preview

echo "网页维护口令（仅在你自己的服务器终端查看）："
cat "$project_dir/runtime/update-key" 2>/dev/null || echo "服务启动后执行：cat $project_dir/runtime/update-key"
