#!/usr/bin/env bash
# ops/deploy_web.sh — funding-tool Web UI 首次部署 / 升级 / 密码哈希工具
#
# 用法:
#   sudo ops/deploy_web.sh deploy           # 全量部署（idempotent，可重复运行）
#   ops/deploy_web.sh hash-password         # 交互生成 bcrypt 哈希，贴到 web.env
#
# 假设仓库已 rsync 到 /opt/funding-tool（即 REPO_DIR 下有 src/ frontend/ ops/）。

set -euo pipefail

REPO_DIR="${REPO_DIR:-/opt/funding-tool}"
DATA_DIR="/var/lib/funding-tool"
LOG_DIR="/var/log/funding-tool"
ETC_DIR="/etc/funding-tool"
TASKS_DIR="${DATA_DIR}/tasks"
MASTER_KEY="${ETC_DIR}/master.key"
MASTER_KEY_PREV="${ETC_DIR}/master.key.prev"
ENV_FILE="${ETC_DIR}/web.env"

# ---------- subcommand: hash-password ---------------------------------------
hash_password() {
    if ! command -v python3 >/dev/null; then
        echo "需要 python3" >&2; exit 1
    fi
    python3 - <<'PY'
import getpass
try:
    import bcrypt
except ImportError:
    raise SystemExit("缺少 bcrypt。pip install bcrypt 或 uv add bcrypt 后再试。")
pw1 = getpass.getpass("Password: ")
pw2 = getpass.getpass("Confirm:  ")
if pw1 != pw2:
    raise SystemExit("两次输入不一致")
if len(pw1) < 12:
    raise SystemExit("密码至少 12 字符")
print(bcrypt.hashpw(pw1.encode(), bcrypt.gensalt(rounds=12)).decode())
PY
}

# ---------- subcommand: deploy ----------------------------------------------
deploy() {
    if [[ "${EUID}" -ne 0 ]]; then
        echo "deploy 需要 root（sudo ops/deploy_web.sh deploy）" >&2; exit 1
    fi

    # 1) user + dirs
    if ! id funding >/dev/null 2>&1; then
        useradd --system --no-create-home --shell /usr/sbin/nologin funding
    fi
    install -d -m 0750 -o funding -g funding "${DATA_DIR}"
    install -d -m 0750 -o funding -g funding "${TASKS_DIR}"
    install -d -m 0750 -o funding -g funding "${LOG_DIR}"
    install -d -m 0750 -o root    -g funding "${ETC_DIR}"

    # 2) master key — 首次生成；已存在则不动
    if [[ ! -f "${MASTER_KEY}" ]]; then
        umask 0277
        openssl rand 32 > "${MASTER_KEY}"
        chmod 0400 "${MASTER_KEY}"
        chown root:root "${MASTER_KEY}"
        echo "已生成 ${MASTER_KEY} (32 bytes)"
    fi
    # systemd 单元里 LoadCredential=master_key_prev 必须读到文件，否则单元启动失败。
    # 首次部署时让 prev 指向当前 active；后续 key rotation 时此文件保存上一代真值。
    if [[ ! -f "${MASTER_KEY_PREV}" ]]; then
        install -m 0400 -o root -g root "${MASTER_KEY}" "${MASTER_KEY_PREV}"
        echo "已 placeholder ${MASTER_KEY_PREV}（=active）。轮换时覆盖为旧 key。"
    fi

    # 3) env 样板 — 缺失则复制，存在不覆盖
    if [[ ! -f "${ENV_FILE}" ]]; then
        cp "${REPO_DIR}/ops/systemd/web.env.example" "${ENV_FILE}"
        chmod 0640 "${ENV_FILE}"
        chown root:funding "${ENV_FILE}"
        echo "已复制 ${ENV_FILE}" >&2
        echo "  编辑：FUNDING_AUTH_PASSWORD_HASH（用 'ops/deploy_web.sh hash-password' 生成）" >&2
        echo "  编辑：FUNDING_PUBLIC_ORIGIN（须与 nginx server_name 一致）" >&2
    fi

    # 4) Python 依赖（uv）
    cd "${REPO_DIR}"
    sudo -u funding -H uv sync --extra web

    # 5) 前端构建
    cd "${REPO_DIR}/frontend"
    sudo -u funding -H npm ci
    sudo -u funding -H npm run build

    # 6) systemd
    install -m 0644 "${REPO_DIR}/ops/systemd/funding-tool-web.service" /etc/systemd/system/
    systemctl daemon-reload
    systemctl enable funding-tool-web.service
    systemctl restart funding-tool-web.service

    # 7) nginx site — 不覆盖已 enable 的链接
    if [[ ! -L /etc/nginx/sites-enabled/funding.conf ]]; then
        install -m 0644 "${REPO_DIR}/ops/nginx/funding.conf" /etc/nginx/sites-available/
        ln -s /etc/nginx/sites-available/funding.conf /etc/nginx/sites-enabled/funding.conf
    fi
    nginx -t
    systemctl reload nginx

    echo
    echo "部署完成。验证："
    echo "  systemctl status funding-tool-web.service --no-pager"
    echo "  curl -fsS -u admin:<pw> https://<server_name>/funding/api/csrf"
}

# ---------- dispatch --------------------------------------------------------
case "${1:-}" in
    deploy)        deploy ;;
    hash-password) hash_password ;;
    *)
        cat <<EOF >&2
用法:
  sudo $0 deploy           全量部署（首次/升级 idempotent）
  $0 hash-password         交互生成 bcrypt 哈希
EOF
        exit 2
        ;;
esac
