# 离线部署：两种完整流程

按现有条件选择一条流程，从该流程第一步执行到最后一步，不需要拼接另一条流程。

| 选择 | 使用场景 | 材料准备端 |
|---|---|---|
| [场景一](#场景一从已安装环境导出并迁移) | 已有能运行的 local-ai，迁移到新环境 | 旧 GPU 节点 gpu-old、旧 BCM 节点 bcm-old |
| [场景二](#场景二从联网环境下载并准备) | 没有现成安装，使用联网机器准备离线材料 | Linux 准备机 prep-host |

## 示例中固定的主机和路径

全文示例使用 `b300-tp4`：新 GPU 节点为 AMD64、4 张已分配 B300，BCM 为 Linux AMD64。
换平台时，镜像和客户端分别匹配各自目标 CPU；不能只改文件名。

| 项目 | 全文统一的值 |
|---|---|
| 各机器的安装根目录（含源码） | `/raid/local-ai` |
| 旧/新 GPU 节点的数据目录 | `/raid/local-ai` |
| 联网准备机的临时材料目录 | `/data/local-ai-prep` |
| 准备端汇总材料的目录 | `/data/local-ai-offline` |
| 离线介质在准备端和新环境的挂载目录 | `/media/local-ai-offline` |
| BCM 用户及客户端安装目录 | alice；`/home/alice/.local/state/local-ai/clients/amd64` |
| 新服务地址 | `http://GPU001:18000/v1`；实例 a，GPU 0,1,2,3 |

执行前准备好以下条件：

- 示例以 alice 执行，具备 sudo 和 Docker 权限；root 可省略 sudo。替换用户名时，也替换用户私有目录。
- 新 GPU 节点已安装 Python 3.10+、兼容驱动、Docker API 1.49+、NVIDIA Container Toolkit/CDI。
  新 BCM 已安装 Python 3.10+、Bash、Git、rg 和 util-linux 的 script。
- 复制和校验用到 rsync、tar、sha256sum、find、sort、xargs；目标能访问内网模型 API。
- `/media/local-ai-offline` 已挂载容量足够的介质。权重约 510 GB，另预留镜像、归档和复制空间。
- 新环境 /raid/local-ai 安装根目录初始为空；每批材料汇总使用空目录。旧环境保持原位置，原路径不同时导出命令填写真实路径。驱动/OS 软件包另行准备，不能从模型镜像中恢复。
- 使用外部模型配方时，把同一份 JSON 随材料携带并校验，在各端设置 LOCAL_AI_CATALOG；不要混用源码、配方和版本锁。

源码直接放在 /raid/local-ai，GPU 的 models/、images/、instances/、install.log 也在该目录下。BCM 私有客户端目录单独列于上表。

材料汇总完成后，目录应包含：

```text
/data/local-ai-offline/
  local-ai-source.tar.gz
  local-ai-source.tar.gz.sha256
  vllm-amd64.tar
  vllm-amd64.tar.lock.json
  models/
  MODELS.sha256
  client-amd64.tar.gz
  client-amd64.tar.gz.sha256
```

## 场景一：从已安装环境导出并迁移

### 1.1 在旧 GPU 节点 gpu-old 导出源码、镜像和模型

从当前使用的安装目录执行。Git 安装导出已提交源码；无 .git 的解压安装按明确清单打包源码。先审查源码修改，两个分支都不打包 models/、images/、instances/ 或整个安装目录。
下面不执行下载，也不要求停止正在使用只读模型的实例；复制时模型文件不能正在被更新。

```bash
cd /raid/local-ai
./local-ai --version
sudo install -d -o "$(id -u)" -g "$(id -g)" /data/local-ai-offline
if [ -e .git ]; then
  git archive --format=tar.gz --output=/data/local-ai-offline/local-ai-source.tar.gz HEAD
else
  tar --exclude='__pycache__' --exclude='*.pyc' --exclude='*.log' --exclude='.env*' \
    -czf /data/local-ai-offline/local-ai-source.tar.gz \
    local-ai pyproject.toml src README.md README.en.md AGENTS.md docs scripts tests
fi

./local-ai image export --profile b300-tp4 --data-dir /raid/local-ai \
  --output /data/local-ai-offline/vllm-amd64.tar

mkdir -p /data/local-ai-offline/models
rsync -aL /raid/local-ai/models/ /data/local-ai-offline/models/
cd /data/local-ai-offline
sha256sum local-ai-source.tar.gz > local-ai-source.tar.gz.sha256
find models -type f -print0 | sort -z | xargs -0 -r sha256sum > MODELS.sha256
```

成功标志：源码归档及校验文件、镜像及配套锁、完整 models/ 和 MODELS.sha256 均已生成。
`-L` 复制链接指向的实际文件，使模型材料不再依赖旧机器上的链接目标。
模型锁有就一起复制；缺锁不能自行编造 revision。不要复制 `/var/lib/docker`、
`/var/lib/containerd`、旧实例目录、日志或用户历史。

### 1.2 在旧 BCM 节点 bcm-old 导出客户端并汇总到 gpu-old

`--client-dir` 必须是当前账户已经安装的真实目录；不要导出 `~/.local/bin/opencode` 恢复入口。
本例两台旧机器不依赖共享目录，用 scp 汇总客户端包。

```bash
cd /raid/local-ai
sudo install -d -o "$(id -u)" -g "$(id -g)" /data/local-ai-offline
./local-ai client export \
  --client-dir /home/alice/.local/state/local-ai/clients/amd64 \
  --output /data/local-ai-offline/client-amd64.tar.gz
scp /data/local-ai-offline/client-amd64.tar.gz \
  /data/local-ai-offline/client-amd64.tar.gz.sha256 \
  alice@gpu-old:/data/local-ai-offline/
```

成功标志：gpu-old 的 `/data/local-ai-offline` 已有上面清单中的全部材料。
客户端包包含程序、公共缓存和 manifest，不包含聊天历史或凭据。

### 1.3 把完整材料放到离线介质

在 gpu-old 执行。确认介质已挂载后复制：

```bash
rsync -a /data/local-ai-offline/ /media/local-ai-offline/
```

将介质带到新环境，并挂载到同一个 `/media/local-ai-offline` 路径。
先在 GPU001 执行下一步，再在 bcm-headnode 执行客户端导入；同一介质可依次挂载使用。

### 1.4 在新 GPU 节点 GPU001 导入并启动

先校验和展开本文生成的源码包，再复制模型、核对目标文件的 SHA256，最后导入镜像和启动。
`local-ai-source.tar.gz` 由本文打包命令生成，解压后源码直接位于目标目录，不加 --strip-components。

```bash
cd /media/local-ai-offline
sha256sum -c local-ai-source.tar.gz.sha256
sudo install -d -o "$(id -u)" -g "$(id -g)" /raid/local-ai
tar -xzf local-ai-source.tar.gz -C /raid/local-ai

mkdir -p /raid/local-ai/models
rsync -a /media/local-ai-offline/models/ /raid/local-ai/models/
cd /raid/local-ai
sha256sum -c /media/local-ai-offline/MODELS.sha256

cd /raid/local-ai
./local-ai --version
./local-ai image import --profile b300-tp4 --data-dir /raid/local-ai \
  --archive /media/local-ai-offline/vllm-amd64.tar \
  --lock /media/local-ai-offline/vllm-amd64.tar.lock.json
./local-ai server inventory
nvidia-ctk cdi list
./local-ai server start --host 0.0.0.0 --profile b300-tp4 \
  --gpus 0,1,2,3 --name a --port 18000 --data-dir /raid/local-ai
./local-ai server status --name a
```

成功标志：所有 SHA256 校验均为 OK；image import 返回 imported=true；
启动显示 READY，status 返回 ready=true。镜像导入本身会校验归档、平台和镜像内容身份。
启动前确认 GPU 0,1,2,3 是新机器分配给本次实例的设备，CDI 列表含其 UUID；不复用旧机器 UUID。
加载或编译可能需要数分钟。尚未就绪时先查看 `/raid/local-ai/instances/a/server.log`，
安装/导入/启动过程看 `/raid/local-ai/install.log`，解决报错后再继续，不以容器存在为成功。

### 1.5 在新 BCM 节点 bcm-headnode 导入客户端并连接

在这台机器也展开同一个源码包。客户端包解压到用户可写目录，离线介质可以只读挂载。

```bash
cd /media/local-ai-offline
sha256sum -c local-ai-source.tar.gz.sha256
sha256sum -c client-amd64.tar.gz.sha256
sudo install -d -o "$(id -u)" -g "$(id -g)" /raid/local-ai
tar -xzf local-ai-source.tar.gz -C /raid/local-ai
mkdir -p /home/alice/local-ai-client-import
tar -xzf client-amd64.tar.gz -C /home/alice/local-ai-client-import

cd /raid/local-ai
./local-ai client install \
  --client-dir /home/alice/.local/state/local-ai/clients/amd64 \
  --binary /home/alice/local-ai-client-import/client/bin/opencode \
  --seed-cache /home/alice/local-ai-client-import/client/seed-cache
./local-ai chat --endpoint http://GPU001:18000/v1 \
  --client-dir /home/alice/.local/state/local-ai/clients/amd64 --check
./local-ai chat --endpoint http://GPU001:18000/v1 \
  --client-dir /home/alice/.local/state/local-ai/clients/amd64 \
  --run '请用 bash 执行 hostname 并报告实际输出。'
```

成功标志：client install 从本地程序完成，chat --check 返回 ready=true；
单次任务实际调用工具，hostname 返回新 BCM 的主机名。本例应是 bcm-headnode。
随后开始交互使用：

```bash
cd /raid/local-ai
./local-ai chat --endpoint http://GPU001:18000/v1 \
  --client-dir /home/alice/.local/state/local-ai/clients/amd64
```

### 1.6 本流程完成条件

在无外网、仅保留 BCM 到 GPU001 内网连接的条件下，完成前面的服务 READY、客户端 check
和真实 hostname 任务。客户端启动时输出的 Log 路径保存该会话完整日志。
新用户应有自己的客户端状态；SSH、Slurm、Kubernetes 凭据及项目依赖在新环境单独配置，
不从公共材料包迁移个人历史或密钥。显式启用的外部插件/MCP 或下载任务仍须具备相应资源。

## 场景二：从联网环境下载并准备

本例 prep-host 是能访问 GitHub、Docker 仓库、Hugging Face 和 NPM 的 Linux AMD64 机器，
已安装 Python 3.10+、Git、Docker API 1.49+ 和复制/校验工具；不需要 GPU。
客户端程序会在准备机执行版本检查，因此准备机也须与目标 BCM 的 Linux/CPU 兼容。
示例选择 v1.0.0；可替换为另一个选定版本，但全程使用同一份源码和配方。

### 2.1 在 prep-host 下载源码、镜像和模型并导出

```bash
sudo install -d -o "$(id -u)" -g "$(id -g)" /raid/local-ai /data/local-ai-prep
git clone --branch v1.0.0 --depth 1 https://github.com/junli-nv/local-ai.git /raid/local-ai
cd /raid/local-ai
./local-ai --version
sudo install -d -o "$(id -u)" -g "$(id -g)" /data/local-ai-offline
git archive --format=tar.gz --output=/data/local-ai-offline/local-ai-source.tar.gz HEAD

./local-ai image pull --profile b300-tp4 --data-dir /data/local-ai-prep
./local-ai model download --profile b300-tp4 --data-dir /data/local-ai-prep
./local-ai image export --profile b300-tp4 --data-dir /data/local-ai-prep \
  --output /data/local-ai-offline/vllm-amd64.tar

mkdir -p /data/local-ai-offline/models
rsync -aL /data/local-ai-prep/models/ /data/local-ai-offline/models/
cd /data/local-ai-offline
sha256sum local-ai-source.tar.gz > local-ai-source.tar.gz.sha256
find models -type f -print0 | sort -z | xargs -0 -r sha256sum > MODELS.sha256
```

成功标志：源码、镜像归档和锁、完整模型及校验清单齐全。模型下载会运行本机架构的容器，
不是仅下载镜像；本例 b300-tp4 与 AMD64 准备机匹配。

### 2.2 在同一台 prep-host 下载并导出 BCM 客户端

```bash
cd /raid/local-ai
./local-ai client install --client-dir /data/local-ai-prep/client-amd64
./local-ai client export --client-dir /data/local-ai-prep/client-amd64 \
  --output /data/local-ai-offline/client-amd64.tar.gz
```

成功标志：`/data/local-ai-offline` 已包含完整材料清单。
需要特定客户端版本时，在 install 命令中增加 `--version X.Y.Z`；导入时会识别包内程序的实际版本。

### 2.3 把完整材料放到离线介质

在 prep-host 执行。确认介质已挂载后复制：

```bash
rsync -a /data/local-ai-offline/ /media/local-ai-offline/
```

将介质带到新环境，并挂载到同一个 `/media/local-ai-offline` 路径。
先在 GPU001 执行下一步，再在 bcm-headnode 执行客户端导入；同一介质可依次挂载使用。

### 2.4 在新 GPU 节点 GPU001 导入并启动

先校验和展开本文生成的源码包，再复制模型、核对目标文件的 SHA256，最后导入镜像和启动。
`local-ai-source.tar.gz` 由本文打包命令生成，解压后源码直接位于目标目录，不加 --strip-components。

```bash
cd /media/local-ai-offline
sha256sum -c local-ai-source.tar.gz.sha256
sudo install -d -o "$(id -u)" -g "$(id -g)" /raid/local-ai
tar -xzf local-ai-source.tar.gz -C /raid/local-ai

mkdir -p /raid/local-ai/models
rsync -a /media/local-ai-offline/models/ /raid/local-ai/models/
cd /raid/local-ai
sha256sum -c /media/local-ai-offline/MODELS.sha256

cd /raid/local-ai
./local-ai --version
./local-ai image import --profile b300-tp4 --data-dir /raid/local-ai \
  --archive /media/local-ai-offline/vllm-amd64.tar \
  --lock /media/local-ai-offline/vllm-amd64.tar.lock.json
./local-ai server inventory
nvidia-ctk cdi list
./local-ai server start --host 0.0.0.0 --profile b300-tp4 \
  --gpus 0,1,2,3 --name a --port 18000 --data-dir /raid/local-ai
./local-ai server status --name a
```

成功标志：所有 SHA256 校验均为 OK；image import 返回 imported=true；
启动显示 READY，status 返回 ready=true。镜像导入本身会校验归档、平台和镜像内容身份。
启动前确认 GPU 0,1,2,3 是新机器分配给本次实例的设备，CDI 列表含其 UUID；不复用旧机器 UUID。
加载或编译可能需要数分钟。尚未就绪时先查看 `/raid/local-ai/instances/a/server.log`，
安装/导入/启动过程看 `/raid/local-ai/install.log`，解决报错后再继续，不以容器存在为成功。

### 2.5 在新 BCM 节点 bcm-headnode 导入客户端并连接

在这台机器也展开同一个源码包。客户端包解压到用户可写目录，离线介质可以只读挂载。

```bash
cd /media/local-ai-offline
sha256sum -c local-ai-source.tar.gz.sha256
sha256sum -c client-amd64.tar.gz.sha256
sudo install -d -o "$(id -u)" -g "$(id -g)" /raid/local-ai
tar -xzf local-ai-source.tar.gz -C /raid/local-ai
mkdir -p /home/alice/local-ai-client-import
tar -xzf client-amd64.tar.gz -C /home/alice/local-ai-client-import

cd /raid/local-ai
./local-ai client install \
  --client-dir /home/alice/.local/state/local-ai/clients/amd64 \
  --binary /home/alice/local-ai-client-import/client/bin/opencode \
  --seed-cache /home/alice/local-ai-client-import/client/seed-cache
./local-ai chat --endpoint http://GPU001:18000/v1 \
  --client-dir /home/alice/.local/state/local-ai/clients/amd64 --check
./local-ai chat --endpoint http://GPU001:18000/v1 \
  --client-dir /home/alice/.local/state/local-ai/clients/amd64 \
  --run '请用 bash 执行 hostname 并报告实际输出。'
```

成功标志：client install 从本地程序完成，chat --check 返回 ready=true；
单次任务实际调用工具，hostname 返回新 BCM 的主机名。本例应是 bcm-headnode。
随后开始交互使用：

```bash
cd /raid/local-ai
./local-ai chat --endpoint http://GPU001:18000/v1 \
  --client-dir /home/alice/.local/state/local-ai/clients/amd64
```

### 2.6 本流程完成条件

在无外网、仅保留 BCM 到 GPU001 内网连接的条件下，完成前面的服务 READY、客户端 check
和真实 hostname 任务。客户端启动时输出的 Log 路径保存该会话完整日志。
新用户应有自己的客户端状态；SSH、Slurm、Kubernetes 凭据及项目依赖在新环境单独配置，
不从公共材料包迁移个人历史或密钥。显式启用的外部插件/MCP 或下载任务仍须具备相应资源。

## 卡住时按失败步骤检查

| 失败位置 | 先检查什么 |
|---|---|
| 旧环境 image export 找不到材料 | --data-dir 是否为真实旧数据目录，原 images/ 锁是否还在，Docker 内是否仍有对应平台镜像；不要直接搬运行时数据库 |
| SHA256 校验失败 | 停在当前步骤，检查材料是否来自同一批导出并重新复制损坏文件 |
| 模型缺文件或 revision 冲突 | 完整 models/、目录内 model.lock.json 或匹配的旧根级锁；不只复制权重分片，不自行编造锁 |
| GPU001 缺 CDI 或启动失败 | 按[部署前置检查](deployment.zh-CN.md)完成宿主机/CDI准备，查看上文实例日志 |
| BCM 无法访问 API | GPU001 是否 READY，18000 端口、DNS、路由和防火墙是否允许新 BCM 访问；endpoint 不填 0.0.0.0 |
| 客户端不能执行 | 包内 manifest 的架构和目标 BCM 的 Linux/CPU 是否匹配；不因服务端是 ARM64 就使用 ARM64 客户端 |

本页命令不使用 --force。不要为了“验证离线”重复下载已完整的材料。
更多参数查[命令手册](commands.md)，已实测范围查[验证记录](validation.md)。

---

[English version](en/offline.md)
