# SubNest X 服务器对比预览

独立测试环境，供核对妙妙屋 X 原版界面、主题、壁纸、导航和设置，之后逐步迁移 SubNest。**当前还没有接入 SubNest 业务，也不是 X 的完整源代码仓库。**

此仓库只包含我们编写的部署工具；安装时直接下载官方 **v0.6.0** 二进制并核验固定 SHA-256。没有上传本机测试账号、数据库、许可证、密钥或提取的第三方前端资源。X 功能及 PRO 限制沿用官方程序，不绕过授权。

## Linux 服务器部署

支持 Linux amd64 / arm64，使用 Python **3.9 或更新版本**；常驻服务需要 systemd。建议使用独立测试服务器或目录，默认端口 **12890**，避免与原项目的 12889 冲突。

```sh
git clone https://github.com/zxyszx/subnest-x-preview.git
cd subnest-x-preview
sudo sh install-service.sh
```

公开仓库可直接克隆，无需 GitHub 登录或 Token；也可下载发布 ZIP 后解压到服务器。

访问 `http://服务器IP:12890`，按官方初始化页面创建新的管理员。服务器安全组需要允许你访问 12890。正式通过域名使用时请配置 HTTPS；Passkey 等浏览器安全功能需要安全上下文。此服务是独立测试安装，不会自动带入本机的账号或数据。

自定义端口：`sudo sh install-service.sh 12990`。

查看日志、重启及状态：

```sh
sudo journalctl -u subnest-x-preview -n 100 --no-pager
sudo systemctl restart subnest-x-preview
sudo systemctl status subnest-x-preview
python3 deploy.py check
```

`check` 默认检查 12890，自定义端口时增加 `--port 12990`。HTTP 检查成功不代表证书、Agent、推送、部署和 PRO 功能已验证。

不安装系统服务，前台运行：

```sh
python3 deploy.py install
python3 deploy.py run --port 12890
```

保持终端运行；Ctrl+C 停止。macOS 也支持此方式，可用于本机验证。

## 数据和更新

数据保存在本仓库目录下的 `runtime/`，已被 Git 忽略。备份时先停止服务，再备份整个目录，以保留数据库及其配套密钥。请勿将此目录提交到仓库。

此版本固定官方 v0.6.0，不会运行不确定的 latest 版本。不要在原项目工作目录中运行，也不要直接导入生产数据库。后续升级需要先备份并单独核对数据库兼容性。

服务以 root 运行，以支持官方服务器部署与证书相关能力；当前仓库只验证面板启动。若仅核对 UI，可直接用普通用户前台运行。初次安装与后续修改的业务验证应使用测试数据。

## 来源和范围

- 官方项目：[iluobei/miaomiaowuX](https://github.com/iluobei/miaomiaowuX)
- 固定版本：[v0.6.0](https://github.com/iluobei/miaomiaowuX/releases/tag/v0.6.0)
- 官方程序的授权、许可证和更新规则以其项目说明为准。
- Linux systemd 实机部署与远程业务流程仍需在服务器验证。提交本仓库不等于已完成 SubNest 迁移。

## 更新与导航修复

原版“检查更新”继续保留入口名称，更新本仓库文件，**不更新官方二进制**。更新 UI 与安全边界见 [流程说明](docs/UPDATE-FLOW.md)。

ZIP 安装的目录可能没有 `.git`，不能用 `git pull` 更新。已有 v0.2.4 安装可使用网页导入签名包，或在项目目录通过现有校验器手动安装（将 ZIP 路径改成实际下载的签名包）：

```sh
python3 -c 'from pathlib import Path; import updater; print(updater.apply(Path.cwd(), Path("/root/subnest-x-preview-0.2.6.zip").read_bytes()))' &&
systemctl restart subnest-x-preview &&
python3 deploy.py wait --port 12890
```

签名校验、备份和安装成功后才会执行重启。管理员、主题和数据保留。不要直接解压覆盖正在运行的项目。

v0.2.6 起提供统一命令入口：

```sh
python3 updater.py install --latest --restart
```

也可用 `python3 updater.py inspect /path/update.zip` 仅校验，或用 `python3 updater.py install /path/update.zip --restart` 安装指定签名包。自定义端口增加 `--port`；省略 `--restart` 只安装并标记待重启。只有运行版本、磁盘版本和待重启状态全部核对通过才报告成功。

之后打开用户菜单 → **检查更新**：

1. 使用现有管理员账号登录，打开弹窗自动检查版本。
2. 有新版时点击“立即更新”；已是最新版时保留“强制重新安装”。
3. 后台自动完成签名校验、数据备份、安装和重启，页面确认目标版本恢复后刷新。

网页不再提供维护口令、ZIP 文件选择和分步安装控件。需要终端恢复时仍可使用上面的签名包命令。更新源固定为本仓库公开 Releases，无需 GitHub Token；网页安装必须通过现有管理员会话和同源检查。应通过 HTTPS 域名或 SSH 隧道访问面板。

新版仍使用公开端口 12890，官方后台改用相邻端口 12891。**只放行 12890，不要公开 12891**；自定义端口时同样保留下一端口给后台。网关透传 SSE、WebSocket、原 Host 与动态 HTML 设置。运行需要系统中的 `openssl`（Debian 12 默认 OpenSSL 3）。

更新备份位于 `runtime/backups/`，自动写文件失败会恢复代码；不承诺自动启动回滚。服务器部署成功后请再次检查主题、登录和远程功能。

网页安装使用固定运行程序的 SQLite 管理员会话；不读取或更改会员许可证。终端签名包安装方式继续保留。

本仓库的部署与更新代码采用 MIT 许可；妙妙屋 X 官方程序不包含在仓库内，其许可证与授权要求保持不变。

v0.2.1 补充：更新弹窗始终居中，更新说明区域独立滚动，避免说明过长将维护口令和安装按钮推到远处。

v0.2.2：端口预检查使用与 HTTP 服务一致的 SO_REUSEADDR，避免关闭连接后的端口被误判占用；仍拒绝实际监听冲突。安装脚本最长等待 120 秒，核对版本接口返回的运行版本，超时输出日志并以失败退出。

v0.2.3：更新入口恢复为“检查更新”，更新弹窗对齐妙妙屋 X 的深色背景、中文字体和稳定版/预发布版结构；菜单版本显示本项目运行版本，不再把官方 v0.6.0 当作本项目版本。


v0.2.5：更新弹窗继承当前主题和原版字体，维护选项默认收起，修复底部空白和动态菜单版本号。更新说明可展开查看。预发布通道暂未接入，明确禁用；实际更新源为本仓库稳定版。


v0.2.6：内容哈希前端资源启用缓存和 ETag，减少重复下载；统一更新弹窗遮罩和图标，支持关闭后的焦点恢复。手动与网页更新共用安装锁、签名校验与备份，并补充异常状态确认。原版主题图标未替换，主题切换仍使用原版整页刷新逻辑。

v0.2.7：检查更新直接复用固定运行程序的原版弹窗与按钮组件，恢复一致的遮罩、字体、图标和主题。移除网页维护口令、ZIP 选择和分步安装控件；改用现有管理员登录，一键完成签名校验、备份、安装和重启确认。同版强制重装仍验证签名，禁止降级。
