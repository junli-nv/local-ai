# 更新已有安装

本页适用于已经安装、只需更新 local-ai 程序的机器。首次安装见 [README](../README.md)，整套资源迁移见[离线指南](offline.md)。更新脚本只下载小型源码包，不执行 install、Docker、模型下载或 OpenCode 安装。

GPU001 与 bcm-headnode 分别更新各自的程序目录。以下沿用 /raid/local-ai；若旧安装在其他位置，将 --root 改成实际包含 local-ai 和 src/ 的目录，不能填写只有模型的数据目录。更新需要该目录及其父目录写权限、Python 3.10+；在线下载脚本时需要 curl。

## 首次取得脚本并升级

v1.3.1 已包含 scripts/update.py；旧安装没有脚本时，先按下面的方法单独获取。先结束本机聊天，避免更新期间启动新的管理命令；GPU 推理容器可保持运行。

在 GPU001 执行；在 BCM 按相同过程更新它自己的目录：

```bash
curl -fL --retry 3 https://raw.githubusercontent.com/junli-nv/local-ai/v1.3.1/scripts/update.py -o /tmp/local-ai-update.py
python3 /tmp/local-ai-update.py --root /raid/local-ai --version v1.3.1
/raid/local-ai/local-ai --version
```

--version 显式选择 Git 标签，后续将它替换为目标版本。脚本不自动追 main，也不把 v1.3.1 作为版本白名单。成功应输出 state=updated、version=1.3.1、resources_changed=false、service_restarted=false，以及实际 backup 路径；命令退出 0。

运行后脚本保留在安装目录 scripts/update.py，后续可以直接使用：

```bash
cd /raid/local-ai
python3 scripts/update.py --root /raid/local-ai --version v1.3.1
```

上例仍指定 v1.3.1；升级下一版时显式替换版本号。再次执行会重新校验源码并创建新的程序备份，不处理模型等大资源。旧标签没有脚本时也会保留当前运行的更新脚本，便于以后更新和导出。

## 检查结果

GPU001 检查原实例：

```bash
cd /raid/local-ai
./local-ai server status --name a
```

BCM 检查原连接：

```bash
cd /raid/local-ai
./local-ai chat --check
```

应分别为 ready=true。更新程序不会切换现有实例配方、端口或启动参数。启用 DSpark 等新配置按[实例重建与预热步骤](deployment.zh-CN.md#单用户-dspark-与显式预热)另行处理。新版本若改用其他模型或镜像，资源准备也是独立操作；程序更新本身不会下载它们。

## 已保留什么

- models/、images/、clients/、instances/、dist/ 和 config/ 不参与程序替换；个人聊天历史也不处理。已有 OpenCode 版本保持原样。
- installation.json 保留角色、endpoint、model、默认配方及其他字段，只更新程序版本并移除旧 bundle_sha256。
- 更新替换普通程序文件与 src/、docs/、scripts/、tests/ 等源码目录。自定义源码改动保存在备份中，不自动合并；不要把业务文件放在这些程序目录中。
- 旧 bundle.json 保存到备份后从当前目录移除，因为它描述更新前的源码校验。需要新离线部署包时重新 export；不能把旧清单当作更新后的源码验收。
- 备份位于安装根的同级 local-ai-backup-随机名/，只包含程序及安装元数据，不复制模型、镜像、客户端资源或运行缓存。program/ 存旧程序，metadata/ 存原安装记录和离线清单，update.json 记录来源、目标和源码包 SHA256。
- 终端 stderr 显示下载和备份位置，stdout 保留 JSON；成功更新/回退另记入安装根 install.log。参数解析错误退出 2；执行或校验错误退出 1；中断退出 130。文件替换过程中捕获的失败会恢复旧程序；进程被强制终止或机器断电时用备份回退。

保留自定义 config/catalog.json 或 LOCAL_AI_CATALOG 时，它们仍完整替代内置配方。若看不到新增配方，应按[开发指南](development.md#模型与客户端兼容性)合并配置，而不是覆盖自定义目录。

## 离线更新程序

在联网准备机将脚本、小型源码包和校验清单放到介质，不必再次导出模型：

```bash
mkdir -p /media/local-ai/update
cd /media/local-ai/update
curl -fL --retry 3 https://raw.githubusercontent.com/junli-nv/local-ai/v1.3.1/scripts/update.py -o update.py
curl -fL --retry 3 https://github.com/junli-nv/local-ai/archive/refs/tags/v1.3.1.tar.gz -o local-ai-v1.3.1-source.tar.gz
sha256sum update.py local-ai-v1.3.1-source.tar.gz > SHA256SUMS
```

将介质挂载到目标机 /media/local-ai，然后执行：

```bash
cd /media/local-ai/update
sha256sum -c SHA256SUMS
python3 update.py --root /raid/local-ai --archive local-ai-v1.3.1-source.tar.gz
/raid/local-ai/local-ai --version
```

--archive 不访问网络，只接收源码 tar 归档。包含 models/、images/ 等资源的完整部署包会被拒绝。--sha256 HEX 可额外提供可信清单中的源码包 SHA256；不指定时仍计算并记录实际哈希，不宣称外部来源已验证。检查服务/客户端的方法与上节相同。

## 回退

将下例 /raid/local-ai-backup-EXAMPLE 替换为更新结果中的实际 backup 路径。先把脚本复制到 /tmp，避免回退到旧版时脚本本身被移除：

```bash
cp /raid/local-ai/scripts/update.py /tmp/local-ai-update.py
python3 /tmp/local-ai-update.py --root /raid/local-ai --rollback /raid/local-ai-backup-EXAMPLE
/raid/local-ai/local-ai --version
```

若中断导致启动文件或 scripts/ 缺失，使用首次保存在 /tmp 的引导脚本；脚本也丢失时先按首节重新获取。回退不要求已安装程序能正常运行，离线时可直接使用介质中的脚本。

成功为 state=rolled-back。回退恢复更新前的程序、installation.json 与 bundle.json；模型、镜像和运行容器不变。更新后修改过 endpoint/model 时先记录当前配置，回退后按需用 config set 恢复。使用这份安装的原备份；脚本核对根目录路径，不验证节点身份，不要跨节点混用备份。

脚本帮助及全部参数：

```bash
python3 /raid/local-ai/scripts/update.py --help
```

| 参数 | 含义 |
|---|---|
| --root | 必填，实际安装根目录 |
| --version | 从本仓库下载指定数字版本标签，可带 v |
| --archive | 使用本地源码 tar 包，不联网 |
| --rollback | 从脚本生成的备份恢复 |
| --sha256 | 可选，源码包预期 SHA256；不能与 --rollback 同用 |

--version、--archive、--rollback 三选一。此脚本更新源码安装目录，不更新系统驱动、容器运行时或 Python 环境。

---

[English version](en/update.md)
