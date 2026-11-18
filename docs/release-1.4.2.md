# v1.4.2：服务器地址与本地会话历史解耦

同一用户使用固定本地历史身份，默认与临时 endpoint 均只决定推理路由，不改变历史库。项目和会话 ID 保留，程序安装目录变化也不改变历史身份；独立 --state-dir 可显式隔离。

- client history list：只读查看历史地址、会话数量及默认标记；支持 --json。
- client history update-endpoint --old URL --new URL：找回旧版本按地址隔离的历史。目标有独立会话时拒绝覆盖。
- opencode -s ID：保留原会话 ID、工作目录和历史，默认历史使用当前保存的服务地址。
- 中英文开发约定要求每次修改前同步远端代码与标签，保全已有修改，合并后重测，发布前再次核对。

历史数据库、快照及工具输出保留原位；连接元数据私有备份，捕获写入失败时回滚。旧服务器无需在线。关联操作不修改 installation.json；默认地址用 config set endpoint 设置。正常更换默认服务器无需重复更新历史。

操作步骤与忘记旧地址的处理见[命令手册](commands.md#更换服务器并保留会话)。验证范围见[验证记录](validation.md)。不包含跨 BCM 迁移、非空历史合并或 GPU 后端变更；沿用 OpenCode 1.19.5 二进制。保留已有标签，本次仅按用户要求新增标签，不自动创建 GitHub Release。

[English](en/release-1.4.2.md)
