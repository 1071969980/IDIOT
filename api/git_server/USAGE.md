# Git 服务器使用指南

本目录包含一个基于 Gitolite 的 Git 服务器 Docker 镜像配置。

## 架构概述

- **构建阶段**：安装 Gitolite + sshd，将子模块 git 数据复制到暂存目录并通过 `git clone --no-hardlinks` 克隆为独立仓库（保留完整历史）
- **运行时初始化**（entrypoint 首次启动）：生成临时密钥 → 启动 sshd → 通过 SSH 完成 Gitolite 初始化 → 推送仓库内容 → 清理临时密钥 → 前台启动 sshd
- **所有 git 操作都通过 SSH**，完全符合 Gitolite 设计

## 目录结构

```
api/git_server/
├── Dockerfile              # 镜像构建文件
├── entrypoint.sh           # 容器入口脚本（SSH-to-self 初始化 + sshd）
├── USAGE.md                # 本文档
├── conf/
│   └── gitolite.conf       # 仓库权限配置（最终生效版本）
├── keys/                   # 密钥（随代码库分发，构建时打入镜像）
│   ├── admin.pub
│   ├── readonly.pub
│   └── host_keys/          # SSH 服务端 host keys（保证重建镜像后指纹不变）
│       ├── ssh_host_ed25519_key
│       ├── ssh_host_ecdsa_key
│       └── ssh_host_rsa_key
├── keys_gen/               # 密钥对生成目录（已在 .gitignore 中，不提交）
│   ├── admin               # admin 私钥
│   ├── admin.pub
│   ├── readonly            # readonly 私钥
│   └── readonly.pub
└── repo/                   # 本地仓库（运行时通过 SSH 推送到 gitolite）
    ├── builtin_skills/
    ├── builtin_scripts/
    └── builtin_sub_agents_def/
```

## 内置仓库

| 仓库名                  | 说明 |
| ----------------------- | ---- |
| `builtin_skills`        | 内置技能 |
| `builtin_scripts`       | 内置脚本 |
| `builtin_sub_agents_def`| 内置子代理定义 |

每个仓库均配置两个用户：
- `admin` — 完整读写权限（RW+）
- `readonly` — 只读权限（R）

## 快速开始

### 1. 生成 SSH 密钥

密钥在 `keys_gen/` 目录中生成，该目录已在 `.gitignore` 中排除（私钥不会提交到仓库）。

```bash
cd api/git_server/keys_gen

ssh-keygen -t ed25519 -f admin -N "" -C "admin@idiot"
ssh-keygen -t ed25519 -f readonly -N "" -C "readonly@idiot"
```

将公钥复制到 `keys/` 目录：

```bash
cp admin.pub ../keys/admin.pub
cp readonly.pub ../keys/readonly.pub
```

生成 SSH host keys（随代码库分发，保证重建镜像后客户端指纹验证不变）：

```bash
cd api/git_server/keys/host_keys

ssh-keygen -t ed25519 -f ssh_host_ed25519_key -N "" -C "idiot-git-server"
ssh-keygen -t ecdsa -f ssh_host_ecdsa_key -N "" -C "idiot-git-server"
ssh-keygen -t rsa -b 4096 -f ssh_host_rsa_key -N "" -C "idiot-git-server"
```

**注意**：`keys_gen/` 中的用户私钥（`admin`、`readonly`）需妥善保管，用于克隆仓库。

### 2. 构建镜像

构建上下文为项目根目录，需通过 `-f` 指定 Dockerfile 路径：

```bash
docker build -t idiot-git-server -f api/git_server/Dockerfile .
```

构建时会将子模块的 git 数据复制到暂存目录，再通过 `git clone --no-hardlinks` 克隆为独立仓库，保留完整提交历史。

### 3. 运行容器

```bash
docker run -d --name idiot-git-server -p 2222:22 idiot-git-server
```

首次启动时，entrypoint 会自动完成 Gitolite 初始化（约需几秒）。

### 4. 验证服务

使用 admin 私钥查看可用仓库：

```bash
ssh -i keys_gen/admin -p 2222 git@localhost info
```

克隆内置仓库：

```bash
GIT_SSH_COMMAND="ssh -i keys_gen/admin -p 2222 -o StrictHostKeyChecking=no" \
    git clone git@localhost:builtin_skills
```

使用 readonly 私钥验证只读权限（可克隆，push 会被拒绝）：

```bash
GIT_SSH_COMMAND="ssh -i keys_gen/readonly -p 2222 -o StrictHostKeyChecking=no" \
    git clone git@localhost:builtin_skills
```

## 初始化流程详解

容器首次启动时，`entrypoint.sh` 执行以下步骤：

1. 生成临时 ed25519 密钥对
2. 用临时公钥初始化 Gitolite（临时密钥成为初始管理员）
3. 后台启动 sshd
4. 通过 SSH（临时密钥）克隆 gitolite-admin，推送包含 admin/readonly 的初始配置
5. 通过 SSH 将 `repo/` 中的仓库内容推送到 Gitolite 管理的仓库
6. 推送最终配置，移除临时密钥的权限
7. 停止后台 sshd，清理临时文件
8. 前台启动 sshd（容器主进程）

整个过程所有 git 操作都经过 SSH + gitolite-shell，完全符合 Gitolite 预期的工作方式。

## 用户与权限

| 用户      | 权限              | 公钥文件          | 私钥（keys_gen/ 中） |
| --------- | ----------------- | ----------------- | -------------------- |
| `admin`   | `RW+`（读写删除） | `keys/admin.pub`  | `keys_gen/admin`     |
| `readonly`| `R`（只读）       | `keys/readonly.pub`| `keys_gen/readonly` |

## 日常操作

### 通过 SSH 配置简化命令

在 `~/.ssh/config` 中添加：

```
Host git-server-admin
    HostName localhost
    Port 2222
    User git
    IdentityFile ~/path/to/keys_gen/admin
    StrictHostKeyChecking no

Host git-server-readonly
    HostName localhost
    Port 2222
    User git
    IdentityFile ~/path/to/keys_gen/readonly
    StrictHostKeyChecking no
```

之后可以直接：

```bash
git clone git-server-admin:builtin_skills
git clone git-server-readonly:builtin_scripts
```

### 查看服务器上的仓库列表

```bash
ssh -i keys_gen/admin -p 2222 git@localhost info
```

## 添加新仓库

### 方式一：修改配置后重新构建

1. 在 `repo/` 下创建并初始化新仓库：

```bash
cd api/git_server/repo
mkdir my-new-repo && cd my-new-repo
git init
git commit --allow-empty -m "init: my-new-repo"
```

2. 在 `conf/gitolite.conf` 中添加：

```
repo my-new-repo
    RW+     =   admin
    R       =   readonly
```

3. 在 `Dockerfile` 的仓库克隆区域添加：

```dockerfile
COPY .git/modules/api/git_server/repo/my-new-repo/ /tmp/git-src/my-new-repo/
```

并在 `RUN git clone ...` 块中添加：

```dockerfile
git clone --no-hardlinks /tmp/git-src/my-new-repo /tmp/repos/my-new-repo && \
```

4. 在 `entrypoint.sh` 的临时配置（步骤 5）和仓库推送循环（步骤 6）中添加新仓库名。

5. 重新构建并运行：

```bash
docker build -t idiot-git-server -f api/git_server/Dockerfile .
```

### 方式二：通过 gitolite-admin 仓库动态添加

适用于**正在运行的容器**，无需重新构建：

```bash
# 克隆管理仓库
GIT_SSH_COMMAND="ssh -i keys_gen/admin -p 2222 -o StrictHostKeyChecking=no" \
    git clone git@localhost:gitolite-admin

# 编辑 conf/gitolite.conf 添加新仓库，然后提交推送
cd gitolite-admin
# ... 编辑配置 ...
git add conf/gitolite.conf
git commit -m "Add my-new-repo"
git push
```

## 权限配置参考

| 权限 | 说明                                            |
| ---- | ----------------------------------------------- |
| `R`  | 只读（可克隆）                                   |
| `RW` | 读写（可推送，但不能强制推送/删除分支）            |
| `RW+`| 完整权限（读写、强制推送、删除分支）               |

更多高级配置（分支级权限、正则匹配等）参见 [Gitolite 官方文档](https://gitolite.com/gitolite/).
