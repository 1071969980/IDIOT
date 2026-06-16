# 镜像构建与验证

镜像概览：

| 镜像 | Dockerfile | 构建上下文 | 构建命令 |
|------|-----------|-----------|---------|
| `idiot-api` | `api/Dockerfile` | 项目根目录 `.` | `docker build -f ./api/Dockerfile -t idiot-api:latest .` |
| `idiot-git-server` | `api/git_server/Dockerfile` | `api/git_server/` | `docker build -f ./api/git_server/Dockerfile -t idiot-git-server:latest ./api/git_server/` |

## 变更分析：判断哪些镜像需要重新构建

根据变更的文件路径，确定需要重新构建的镜像。使用以下命令检查变更：

```bash
# 检查暂存区和未暂存的变更文件
git diff --name-only HEAD~1
# 或者检查工作目录相对于某个基准的所有变更
git diff --name-only <base-commit>
```

### 重构触发路径映射表

以下路径变更**需要重新构建对应镜像**：

**idiot-api 触发路径：**

| 变更路径 | 影响的构建层 |
|---------|------------|
| `requirements.txt` | 依赖安装层（重建较慢） |
| `python_wheels/juicefs-0.1.0-py3-none-any.whl` | JuiceFS 安装层 |
| `pyproject.toml` | 项目元数据，可能影响依赖解析 |
| `uv.lock` | 锁文件，影响依赖版本 |
| `api/` 目录下任何文件 | 应用代码层（含 37,000+ 文件） |
| `api/Dockerfile` | Dockerfile 自身变更 |

**idiot-git-server 触发路径：**

| 变更路径 | 影响的构建层 |
|---------|------------|
| `api/git_server/Dockerfile` | Dockerfile 自身变更 |
| `api/git_server/entrypoint.sh` | 入口脚本层 |
| `api/git_server/conf/gitolite.conf` | Gitolite 配置层 |
| `api/git_server/keys/host_keys/` | SSH host keys 层 |
| `api/git_server/keys/admin.pub` | 管理员公钥层 |
| `api/git_server/keys/readonly.pub` | 只读公钥层 |
| `api/git_server/repo/builtin_skills/` | 内置技能仓库层 |
| `api/git_server/repo/builtin_scripts/` | 内置脚本仓库层 |
| `api/git_server/repo/builtin_sub_agents_def/` | 内置子 Agent 定义层 |

### 无需重新构建的路径

以下路径变更**不需要**重新构建任何镜像：

- `docs/`、`k8s/`、`scripts/`
- `.git/`、`.venv/`、`*.md`、`.env*`、`logs/`、`volumes/`
- `api/git_server/keys_gen/`、`api/git_server/USAGE.md`

### 判断逻辑

```
对每个变更文件:
  如果路径匹配 "api/git_server/" 前缀且在触发路径表中 → 标记 idiot-git-server
  如果路径匹配 "api/"、"requirements.txt"、"pyproject.toml"、"uv.lock"、
     "python_wheels/" → 标记 idiot-api
  如果路径在无需重建列表中 → 跳过
  其他情况 → 提醒用户人工确认
```

## 第二步：构建镜像

只构建被标记的镜像。执行构建命令前，确认当前目录为项目根目录。

### 构建 idiot-api

```bash
docker build -f ./api/Dockerfile -t idiot-api:latest .
```

注意：构建上下文为项目根目录，`api/` 含 37,000+ 文件且无 `.dockerignore`，COPY 层较慢属正常。可建议创建 `.dockerignore` 排除 `.venv/`、`.git/`、`docs/`、`logs/` 以加速。

### 构建 idiot-git-server

```bash
docker build -f ./api/git_server/Dockerfile -t idiot-git-server:latest ./api/git_server/
```

注意：构建上下文为 `api/git_server/`，基础镜像 `ubuntu:22.04`，首次构建需下载。

## 第三步：验证构建结果

构建完成后，验证镜像是否正常生成：

```bash
# 检查镜像是否存在并查看大小
docker images idiot-api:latest
docker images idiot-git-server:latest

# 验证镜像基本信息
docker inspect --format='{{.Created}}' idiot-api:latest
docker inspect --format='{{.Created}}' idiot-git-server:latest
```

判断标准：
- 构建命令退出码为 0
- 镜像存在且大小合理（idiot-api 通常 > 1GB，idiot-git-server 通常 > 500MB）
- 创建时间为刚刚构建的时间

## 第四步：执行冒烟测试

对成功构建的镜像运行基本健康检查。

### idiot-api 冒烟测试

```bash
# 测试 1：验证 Python 环境和基本导入
docker run --rm idiot-api:latest bash -c ". .venv/bin/activate && python -c 'import api; print(\"api module imported successfully\")'"

# 测试 2：验证依赖安装完整性
docker run --rm idiot-api:latest bash -c ". .venv/bin/activate && python -c 'import fastapi; print(\"fastapi OK\")'"

# 测试 3：验证 uv 环境
docker run --rm idiot-api:latest bash -c ". .venv/bin/activate && python --version"
```

### idiot-git-server 冒烟测试

```bash
# 测试 1：验证容器可启动并执行基本命令
docker run --rm idiot-git-server:latest echo "container started successfully"

# 测试 2：验证 git 已安装
docker run --rm idiot-git-server:latest git --version

# 测试 3：验证 gitolite 已安装
docker run --rm idiot-git-server:latest bash -c "which gitolite && gitolite version 2>/dev/null || echo 'gitolite binary found'"

# 测试 4：验证 sshd 配置
docker run --rm idiot-git-server:latest bash -c "sshd -t 2>&1 && echo 'sshd config valid'"

# 测试 5：验证入口脚本存在且可执行
docker run --rm idiot-git-server:latest bash -c "test -x /entrypoint.sh && echo 'entrypoint OK'"
```

## 第五步：报告结果

以清晰的格式汇总所有测试结果。报告模板：

```
=== Docker 镜像构建与测试报告 ===

变更分析：
  - 检测到变更文件：N 个
  - 需要重建的镜像：[idiot-api / idiot-git-server / 无]

构建结果：
  [镜像名] [成功/失败]
    - 构建耗时：Xs
    - 镜像大小：XMB
    - 错误信息：（如有）

冒烟测试：
  [镜像名]
    - [测试名]：通过/失败
    - [测试名]：通过/失败

总结：X 个镜像构建，Y 个冒烟测试通过，Z 个失败
```

## 故障排查

- **依赖下载失败**：检查网络和 `requirements.txt` 中的包版本
- **COPY 层失败**：确认文件路径存在，特别是 `python_wheels/` 目录
- **基础镜像拉取失败**：检查 Docker 网络，尝试手动 `docker pull python:3.13`
- **模块导入失败**：检查 `requirements.txt` 是否缺少依赖
- **sshd 配置错误**：检查 `host_keys/` 目录下密钥文件是否完整
- **权限错误**：检查 `entrypoint.sh` 执行权限和 gitolite 配置
