# 更新已有安装

v1.4.2 起用户本地历史与服务器地址、安装目录解耦，临时 --endpoint 也沿用历史。旧版记录缺失时按[恢复步骤](commands.md#更换服务器并保留会话)查询和关联一次；日常切服务器只需选择 endpoint。

v2.0.0 更新包含 templates/，它属于可替换程序文件；个人 AGENTS.md 位于用户配置目录，不被更新器覆盖。旧更新器没有 templates 白名单时，先从同一目标源码包取得新版 scripts/update.py。更新器本身不应用规则；更新客户端程序后以实际聊天用户运行 ./local-ai install --role client（BCM 可加 --instructions bcm）即可自动应用新版模板，不需要重新下载已验证的二进制。自管规则加 --instructions none；应用后退出并恢复 OpenCode。配置与备份恢复见 [持久工作指令配置](../templates/opencode/agent-instructions.md)。

本页适用于已经安装、只需更新 local-ai 程序的机器。首次安装见 [README](../README.md)，整套资源迁移见[离线指南](offline.md)。更新脚本只下载小型源码包，不执行 install、Docker、模型下载或 OpenCode 安装。

GPU001 与 bcm-headnode 分别更新各自的程序目录。以下沿用 /raid/local-ai；若旧安装在其他位置，将 --root 改成实际包含 local-ai 和 src/ 的目录，不能填写只有模型的数据目录。更新需要该目录及其父目录写权限、Python 3.10+；在线下载脚本时需要 curl。

## 升级前检查活动客户端

以下能力包含于 v2.0.0；旧更新器需先从目标源码取得新版 scripts/update.py。在程序所在机器执行：

    python3 scripts/update.py --root /raid/local-ai --check

检查只读，不下载、不创建更新锁或备份，不读取聊天正文。JSON 的 activity_check 列出本安装的 PID、类别、可执行路径和 UID；ready=true 退出 0，发现活动客户端或检测不完整时退出 3（不可用时 ready=null）。它是进程快照，不是持续锁住会话启动；成功后仍可能有人启动客户端。

实际更新/回退会在下载前检测，更新还在替换前再检查一次。默认发现活动进程即退出 1，保留原程序，不发送信号。确需保留会话更新程序时，向原更新/回退命令加 --allow-active-clients；它不终止、后台托管或重启进程，也不升级原生 OpenCode。稍后退出并恢复客户端以加载新程序/指令。

Linux 检测依赖 /proc 可见性，识别本安装 clients/ 下的 OpenCode 和 Bash/Python 启动器，不混淆相似路径前缀。外部 --client-dir、其他机器、权限不可见进程和检测后新启动的进程不在完整保证范围内。不可用/不完整会警告；实际更新不会仅因看不到无关进程就宣称安全或停止它们，须自行确认。

新备份另存 backup/update.py。成功 JSON 返回 rollback_command 参数数组，stderr 打印带引号的完整命令；安装根 launcher/scripts 缺失仍可运行。backup_scope=program-and-installation-metadata、history_backed_up=false、native_client_changed=false。程序备份不包含私人聊天数据库或个人 AGENTS.md；原生 OpenCode 升级是独立操作，须退出会话并单独保护完整私有状态，程序回退不能降级数据库。

## 首次取得脚本并升级

v2.0.0 已包含 scripts/update.py；旧安装没有脚本时，先按下面的方法单独获取。先结束本机聊天，避免更新期间启动新的管理命令；GPU 推理容器可保持运行。

在 GPU001 执行；在 BCM 按相同过程更新它自己的目录：

```bash
curl -fL --retry 3 https://raw.githubusercontent.com/junli-nv/local-ai/v2.1.2/scripts/update.py -o /tmp/local-ai-update.py
python3 /tmp/local-ai-update.py --root /raid/local-ai --version v2.1.2
/raid/local-ai/local-ai --version
```

--version 显式选择 Git 标签，后续将它替换为目标版本。脚本不自动追 main，也不把 v2.0.0 作为版本白名单。成功应输出 state=updated、version=2.1.2、resources_changed=false、service_restarted=false，以及实际 backup 路径；命令退出 0。

运行后脚本保留在安装目录 scripts/update.py，后续可以直接使用：

```bash
cd /raid/local-ai
python3 scripts/update.py --root /raid/local-ai --version v2.1.2
```

上例指定 v2.1.2；升级下一版时显式替换版本号。再次执行会重新校验源码并创建新的程序备份，不处理模型等大资源。旧标签没有脚本时也会保留当前运行的更新脚本，便于以后更新和导出。

## 检查结果

v2.0.0 包含 GB200 四卡候选和 Rubin 两卡框架；保留外部 catalog 的安装须显式合并
新配方。更新不会解除 Rubin 的
planning_only 或补齐镜像，边界见[专项指南](gb200-rubin.md)。

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

v2.0.0 包含 `server benchmark` 与客户端诊断；请同时更新两端程序以使用各自新增命令。
部署包含该功能的源码后，仅在 GPU001 执行[本机性能测试](commands.md#本机性能测试)，无需更新 BCM 或重新下载模型/镜像。
更新本身不运行测试；instances/ 下的历史 benchmark JSON 保留，程序/镜像等条件改变后应重新测量。

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
curl -fL --retry 3 https://raw.githubusercontent.com/junli-nv/local-ai/v2.1.2/scripts/update.py -o update.py
curl -fL --retry 3 https://github.com/junli-nv/local-ai/archive/refs/tags/v2.1.2.tar.gz -o local-ai-v2.1.2-source.tar.gz
sha256sum update.py local-ai-v2.1.2-source.tar.gz > SHA256SUMS
```

将介质挂载到目标机 /media/local-ai，然后执行：

```bash
cd /media/local-ai/update
sha256sum -c SHA256SUMS
python3 update.py --root /raid/local-ai --archive local-ai-v2.1.2-source.tar.gz
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
| --sha256 | 可选，源码包预期 SHA256；不能与 --rollback/--check 同用 |
| --check | v2.0.0：只读检查，不下载或替换；未就绪退出 3 |
| --allow-active-clients | v2.0.0：更新/回退时显式允许检测到的活动进程，不停止或升级原生客户端 |

更新/回退时 --version、--archive、--rollback 三选一；v2.0.0 --check 为单独互斥的只读模式。此脚本更新源码安装目录，不更新系统驱动、容器运行时或 Python 环境。

---

[English version](en/update.md)


私有会话需另行[备份/恢复](automation.md)，不能依赖程序备份。v2.0.0 保留 OpenCode 1.19.5，退出并恢复聊天加载新插件，无需重启推理。
