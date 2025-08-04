# I.D.I.O.T, Intelligent Development Integrated & Operations Toolkit

# 项目结构
```
IDIOT
├── api # 绝大多数 python 代码
|   ├── app # FASTapi 应用的代码
|   ├── graph_executor # 图执行器，见其README
|   ├── llm # 对LLM服务调用的包装
|   ├── load_balance # 负载均衡模块，用于防止机器学习模型的服务触发限流
|   ├── run.sh # 镜像入口文件
|   ├── s3_FS # S3对象存储服务 python 接口
|   ├── vector_db # 知识库（向量数据库）的抽象与实现。
|   └── workflow # 图执行的定义，遵从无状态设计
├── docker # 容器配置文件和挂载目录
├── testcase # 单元测试
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

1. 从uv锁文件创建虚拟环境

```bash
uv sync
```

2. 下载并安装spaCy的模型包

下载模型
```bash
cd ./pip_resources
./download_spacy_model.sh
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
docker pull nginx:latest
docker pull python:3.13
docker pull otel/opentelemetry-collector-contrib:0.128.0
docker pull jaegertracing/jaeger:2.8.0
docker pull prom/prometheus:v3.4.2
docker pull postgres:17.5
docker pull chrislusf/seaweedfs:3.92
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

## 通过docker compose运行

```bash
cd ./docker
mkdir ./volumes/jaeger
sudo chmod 777 ./volumes/jaeger # 解决jaeger镜像用户权限问题，其默认不以root运行

docker compose -p idiot up -d
# 查看日志
docker compose -p idiot logs -f
# 停止容器
docker compose -p idiot down
```
通过https协议在8143端口访问

访问地址：https://0.0.0.0:8143

api文档地址：https://0.0.0.0:8143/docs

jaeger UI地址：https://0.0.0.0:8143/jaeger


## 本地调试运行

启动jaeger容器（vscode 任务 Start Jaeger Container）

vscode 使用python调试器运行 ```path/to/idiot/api/app/main.py```

api 文档地址：http://localhost:8000/docs

调试时访问jaegerUI地址：http://localhost:16686/jaeger

## 容器内调试运行

```bash
cd ./docker
API_DEBUG="1" \
API_DEBUG_PORT="5678" \
API_DEBUG_EXPOSED_PORT="5678" \
docker compose -p idiot up -d
```

随后用 vscode python调试器（debugpy）附加到本地5678端口

程序会在 ```path/to/idiot/api/app/main.py``` 执行前阻塞直到调试器连接成功