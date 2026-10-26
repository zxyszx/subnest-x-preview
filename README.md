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

私有仓库需要先通过 GitHub 登录或配置有权限的 SSH Key；也可从 GitHub 下载 ZIP 后解压到服务器。

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
