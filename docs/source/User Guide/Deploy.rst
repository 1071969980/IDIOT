Deploy
======

环境配置与部署
--------------

安装工具
~~~~~~~~

- 本项目使用 uv 管理python环境: https://github.com/astral-sh/uv
- 本项目要求python版本为至少为3.13

.. code-block:: bash

   uv python install 3.13

创建并同步虚拟环境
~~~~~~~~~~~~~~~~~~

1. 从uv锁文件创建虚拟环境

.. code-block:: bash

   uv sync

2. 下载并安装spaCy的模型包

下载模型:

.. code-block:: bash

   cd ./pip_resources
   ./download_spacy_model.sh

激活环境并安装包:

.. code-block:: bash

   # cd ./pip_resources
   source ./.venv/bin/activate
   uv pip install *.whl

构建镜像
~~~~~~~~

拉取基础镜像:

.. code-block:: bash

   docker pull nginx:latest
   docker pull python:3.13
   docker pull otel/opentelemetry-collector-contrib:0.128.0
   docker pull jaegertracing/jaeger:2.8.0
   docker pull prom/prometheus:v3.4.2
   docker pull postgres:17.5
   docker pull chrislusf/seaweedfs:3.92

导出 requirements.txt:

.. code-block:: bash

   # path/to/idiot
   uv export --format requirements-txt > ./requirements.txt

构建镜像:

.. code-block:: bash

   # path/to/idiot
   docker build ./ -f ./api/Dockerfile -t idiot-api:latest

通过 docker compose 运行
~~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: bash

   cd ./docker
   cp ./example.env ./.env
   mkdir ./volumes/jaeger
   sudo chmod 777 ./volumes/jaeger # 解决jaeger镜像用户权限问题，其默认不以root运行

   docker compose -p idiot up -d
   # 查看日志
   docker compose -p idiot logs -f
   # 停止容器
   docker compose -p idiot down

通过 https 协议在 8143 端口访问:

- 访问地址：https://0.0.0.0:8143
- API 文档地址：https://0.0.0.0:8143/docs
- Jaeger UI 地址：https://0.0.0.0:8143/jaeger
- prometheus UI地址：https://0.0.0.0:8143/prometheus

容器内调试运行
~~~~~~~~~~~~~~

.. code-block:: bash

   cd ./docker
   API_DEBUG="1" \\
   API_DEBUG_PORT="5678" \\
   API_DEBUG_EXPOSED_PORT="5678" \\
   docker compose -p idiot up -d

随后用 vscode python 调试器（debugpy）附加到本地 5678 端口。

程序会在 ``path/to/idiot/api/app/main.py`` 执行前阻塞直到调试器连接成功。

代码更改后重新运行容器可执行：

.. code-block:: bash

    docker compose -p idiot up -d --build --force-recreate api

如何为docker容器添加环境变量
-------------------------

首先，在docker/docker-compose.yml的中添加新的环境变量：

.. code-block:: text

    x-shared-api-worker-env: &shared-api-worker-env
        API_DEBUG: ${API_DEBUG:-0}
        ...
        NEW_ENV_VAR: ${NEW_ENV_VAR:-default_value}
    
然后，在docker/.env中添加新的环境变量：

.. code-block:: text

    ...
    NEW_ENV_VAR=new_value

持久化存储
---------

容器挂载目录全部位于 ``docker/volumes`` 目录