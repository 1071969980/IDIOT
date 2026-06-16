# I.D.I.O.T, Intelligent Development Integrated & Operations Toolkit

# 项目结构
```
IDIOT
├── api # 绝大多数 python 代码
|   ├── app # FASTapi 应用的代码
|   ├── llm # 对LLM服务调用的包装
|   ├── load_balance # 负载均衡模块，用于防止机器学习模型的服务触发限流
|   ├── logger.py # 日志模块,使用logfire发送opentelemetry数据到日志追踪链路。
|   ├── run.sh # 镜像入口文件
|   ├── s3_FS # S3对象存储服务 python 接口
|   └── workflow # 图执行的定义，遵从无状态设计
├── k8s # Kubernetes 部署配置（Helm Chart）
├── docs # 项目文档
├── pip_resources # 构建镜像时的pip离线安装包
├── ... # 其他组件的配置文件，基本无代码。文件夹名为组件名。
└── uv.lock 本项目使用 uv 进行依赖管理
```

# 环境配置与部署 

## 安装工具

- 本项目使用 uv 管理python环境 : https://github.com/astral-sh/uv

- 本项目要求python版本为至少为3.13

```bash
uv python install 3.13
```

## 创建并同步虚拟环境

从uv锁文件创建虚拟环境

```bash
uv sync
```

激活环境并安装包
```bash
# cd ./pip_resources
source ./.venv/bin/activate
uv pip install *.whl
```

## 构建镜像

拉取基础镜像

```bash
docker pull python:3.13
docker pull otel/opentelemetry-collector-contrib:0.128.0
docker pull postgres:17.5
docker pull redis:8.2.0
```

导出requirements.txt
```bash
# path/to/idiot
uv export --format requirements-txt > ./requirements.txt
```

构建镜像

```bash
# path/to/idiot
docker build ./ -f ./api/Dockerfile -t idiot-api:latest
```

## 部署

项目部署至 Kubernetes 集群，详见 `k8s/helm/README.md`。

## 项目文档

项目的所有类型的文档文件都保存于 `./docs` 文件夹中。项目说明，api文档，图解，开发规范文档等等。
