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

COPY keys/host_keys/ /etc/ssh/

# 复制密钥和配置
COPY keys/admin.pub /tmp/admin.pub
COPY keys/readonly.pub /tmp/readonly.pub
COPY conf/gitolite.conf /tmp/gitolite.conf

# 仓库源文件（运行时通过 SSH 推送到 gitolite）
COPY repo/builtin_skills/ /tmp/repos/builtin_skills/
COPY repo/builtin_scripts/ /tmp/repos/builtin_scripts/
COPY repo/builtin_sub_agents_def/ /tmp/repos/builtin_sub_agents_def/

COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

EXPOSE 22

ENTRYPOINT ["/entrypoint.sh"]
