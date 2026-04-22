#!/bin/bash
set -e

GIT_HOME="/home/git"
SSH_OPTS="-o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null"

# 首次启动：通过 SSH-to-self 初始化 Gitolite
# 使用 projects.list 作为标记判断是否已初始化
if [ ! -f "${GIT_HOME}/projects.list" ]; then
    echo "=== 首次启动，初始化 Gitolite ==="

    # 1. 生成临时密钥对（用于初始化期间的 SSH 连接）
    ssh-keygen -t ed25519 -f /tmp/throwaway -N "" -C "throwaway@init" -q

    # 2. 用临时密钥初始化 gitolite（throwaway 成为初始管理员）
    su - git -c "gitolite setup -pk /tmp/throwaway.pub"

    # 3. 生成 host keys 并后台启动 sshd
    ssh-keygen -A 2>/dev/null
    /usr/sbin/sshd
    sleep 1

    # 4. 配置 git 使用临时密钥通过 SSH 操作
    export GIT_SSH_COMMAND="ssh -i /tmp/throwaway ${SSH_OPTS}"

    # 5. 克隆 gitolite-admin，写入临时配置（给 throwaway 加权限用于推送仓库内容）
    cd /tmp
    git clone git@localhost:gitolite-admin gitolite-admin-setup
    cd gitolite-admin-setup
    git config user.email 'init@idiot'
    git config user.name 'init'

    cat > conf/gitolite.conf << 'EOF'
repo gitolite-admin
    RW+     =   throwaway
    RW+     =   admin

repo builtin_skills
    RW+     =   throwaway
    RW+     =   admin
    R       =   readonly

repo builtin_scripts
    RW+     =   throwaway
    RW+     =   admin
    R       =   readonly

repo builtin_sub_agents_def
    RW+     =   throwaway
    RW+     =   admin
    R       =   readonly
EOF

    cp /tmp/admin.pub keydir/admin.pub
    cp /tmp/readonly.pub keydir/readonly.pub
    git add -A
    git commit -m 'Initial gitolite configuration'
    git push

    echo "=== 配置推送完成，开始推送仓库内容 ==="

    # 6. 通过 SSH 推送各仓库内容
    for repo in builtin_skills builtin_scripts builtin_sub_agents_def; do
        cd /tmp/repos/${repo}
        git remote remove gitolite 2>/dev/null || true
        git remote add gitolite git@localhost:${repo}
        git push gitolite --all
        git push gitolite --tags
        echo "  ${repo} 推送完成"
    done

    # 7. 推送最终配置（移除 throwaway）
    cd /tmp/gitolite-admin-setup
    cp /tmp/gitolite.conf conf/gitolite.conf
    rm -f keydir/throwaway.pub
    git add -A
    git diff --cached --quiet || git commit -m 'Remove throwaway key, finalize configuration'
    git push

    # 8. 停止后台 sshd
    pkill -f "/usr/sbin/sshd" || true
    sleep 1

    # 9. 清理
    rm -f /tmp/throwaway /tmp/throwaway.pub
    rm -rf /tmp/gitolite-admin-setup

    echo "=== Gitolite 初始化完成 ==="
fi

# 清理临时文件
rm -f /tmp/admin.pub /tmp/readonly.pub /tmp/gitolite.conf
rm -rf /tmp/repos

echo "=== 启动 sshd ==="
exec /usr/sbin/sshd -D
