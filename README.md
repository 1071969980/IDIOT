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
docker pull jaegertracing/jaeger:2.7.0
```

导出requirements.txt
```bash
# path/to/contract-review
uv export --format requirements-txt > ./requirements.txt
```

构建镜像

```bash
# path/to/contract-review
docker build ./ -f ./api/Dockerfile -t contract-review-api:latest
```

## 通过docker compose运行

```bash
cd ./docker
mkdir ./volumes/jaeger
sudo chmod 777 ./volumes/jaeger # 解决jaeger镜像用户权限问题，其默认不以root运行

docker compose -p contract-review up -d
# 查看日志
docker compose -p contract-review logs -f
# 停止容器
docker compose -p contract-review down
```
通过https协议在8143端口访问
访问地址：https://0.0.0.0:8143
api文档地址：https://0.0.0.0:8143/docs


## 本地调试运行

vscode 使用python调试器运行 ```path/to/contract-review/api/app/main.py```

## 容器内调试运行

```bash
cd ./docker
API_DEBUG="1" \
API_DEBUG_PORT="5678" \
API_DEBUG_EXPOSED_PORT="5678" \
docker compose -p contract-review up -d
```

随后用 vscode python调试器（debugpy）附加到本地5678端口

程序会在 ```path/to/contract-review/api/app/main.py``` 执行前阻塞直到调试器连接成功