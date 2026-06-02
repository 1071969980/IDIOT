FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive
ENV LC_ALL=C.UTF-8

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        git \
        openssh-server \
        ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# 创建 git 用户，从源码安装 gitolite（安装到系统路径）
RUN useradd -m -s /bin/bash git && \
    cd /opt && \
    git clone https://codeberg.org/sitaramc/gitolite.git && \
    cd gitolite && \
    /opt/gitolite/install -ln /usr/local/bin && \
    echo 'export GL_LIBDIR="/opt/gitolite/src/lib"' >> /home/git/.profile

# 配置 sshd + 注入稳定的 host keys
RUN mkdir -p /run/sshd && \
    sed -i 's/#PasswordAuthentication yes/PasswordAuthentication no/' /etc/ssh/sshd_config && \
    sed -i 's/#PermitRootLogin prohibit-password/PermitRootLogin no/' /etc/ssh/sshd_config && \
    sed -i 's/^AcceptEnv LANG LC_\*/#AcceptEnv LANG LC_*/' /etc/ssh/sshd_config && \
    echo "AllowUsers git" >> /etc/ssh/sshd_config

COPY api/git_server/keys/host_keys/ /etc/ssh/

# 复制密钥和配置
COPY api/git_server/keys/admin.pub /tmp/admin.pub
COPY api/git_server/keys/readonly.pub /tmp/readonly.pub
COPY api/git_server/conf/gitolite.conf /tmp/gitolite.conf

# 将子模块的 git 数据复制到暂存目录，克隆为独立仓库（保留完整历史）
COPY .git/modules/api/git_server/repo/builtin_skills/ /tmp/git-src/builtin_skills/
COPY .git/modules/api/git_server/repo/builtin_scripts/ /tmp/git-src/builtin_scripts/
COPY .git/modules/api/git_server/repo/builtin_sub_agents_def/ /tmp/git-src/builtin_sub_agents_def/

RUN git config --global --add safe.directory '*' && \
    git clone --no-hardlinks /tmp/git-src/builtin_skills /tmp/repos/builtin_skills && \
    git clone --no-hardlinks /tmp/git-src/builtin_scripts /tmp/repos/builtin_scripts && \
    git clone --no-hardlinks /tmp/git-src/builtin_sub_agents_def /tmp/repos/builtin_sub_agents_def && \
    rm -rf /tmp/git-src

COPY api/git_server/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

EXPOSE 22

ENTRYPOINT ["/entrypoint.sh"]
