# OpenASI 自动签到

Windows 图形配置 + 每日静默签到，使用 Python 标准库，发布 Python 源码。

在窗口中输入邮箱和密码，选择签到时间，一键启用。自动执行不打开终端、配置窗口、任务窗口或通知，不抢焦点。成功与失败均记录到本机，用户主动打开配置窗口后可查看结果。

## 下载后如何使用

1. 安装 **Windows Python 3.10 或更高版本**，包含 **Tcl/Tk、Python Launcher**。可从 [Python 官网](https://www.python.org/downloads/windows/) 获取。已有支持 Tkinter 的 Python 可以跳过。
2. 下载本仓库的源码 ZIP，**完整解压**到一个长期保留的文件夹，例如 `D:\Tools\OpenASICheckin`。
3. 双击 **`启动配置.vbs`**，打开配置窗口。也可以双击 `configure.pyw`。
4. 输入 OpenASI 邮箱和密码，点击 **测试登录**。此操作不会提交签到。
5. 选择每日时间，点击 **启用 / 更新时间**。程序会验证账号、加密保存密码并自动注册 Windows 计划任务。
6. 显示“每日签到已启用”后，关闭窗口即可。

**无需编辑 `.env`、运行 pip、手工填写任务计划参数或一直开着终端。** 源码版仍需要预先安装 Python；未找到 Python 时，启动器会提示安装。

如果所在电脑禁用 VBScript，使用 `configure.pyw` 的 Python 窗口程序关联打开，或用下面的命令启动：

```powershell
pythonw.exe "D:\Tools\OpenASICheckin\configure.pyw"
```

## 窗口操作

| 操作 | 效果 |
| --- | --- |
| 测试登录 | 验证输入的账号并查询签到状态，不签到、不保存密码 |
| 保存账号 | 加密保存邮箱和密码，不启用或改变任务时间 |
| 立即签到 | 使用当前输入的账号签到一次，并更新本机运行记录 |
| 启用 / 更新时间 | 验证并保存账号，创建或更新每日后台任务 |
| 停用自动签到 | 停用后续任务，保留配置和历史记录 |
| 刷新状态 / 查看日志 | 查看任务状态、最近结果和运行日志 |

密码保存后，输入框保持空白；留空即可使用已保存的密码，输入新密码后再保存即可更新。更换邮箱需重新输入密码。

## 静默执行的实现

- Windows 任务计划程序直接启动 `pythonw.exe`，调用独立的 `background.pyw`，不加载 Tkinter。
- 任务管理的 PowerShell 子进程使用 `CREATE_NO_WINDOW`、`SW_HIDE` 和非交互模式。
- 自动执行不调用弹窗或通知。网络断开、登录失败和配置损坏也只记录结果。
- 自动任务每次执行完成后退出；启用期间可以关闭配置界面。
- 同一个计划任务运行时忽略新的实例，失败后按 15 分钟间隔再尝试最多两次。
- 签到前查询服务器状态，当天已签到时直接结束。

“任务隐藏”属性本身不能保证不弹终端，因此静默模式依靠窗口型 Python 解释器和独立后台入口。任务仍可在 Windows 任务计划程序中管理。

## 开机、锁屏和补运行

- 电脑需要开机，配置任务的 Windows 用户需要处于登录状态；**锁屏也可以运行**。
- 关机、睡眠或退出登录期间不能执行。任务设置了错过计划时间后补运行；登录后也会检查是否已到当天签到时间，已到则补执行。
- 不需要输入 Windows 登录密码，不请求管理员权限，不会唤醒休眠电脑。
- 时间采用本机设置；签到日期以 OpenASI 服务器返回的状态为准，不能补领过去日期。

## 账号与日志保存位置

```text
%LOCALAPPDATA%\OpenASICheckin\
├─ settings.json    邮箱、每日时间、DPAPI 加密后的密码
├─ last_run.json    最近一次签到结果
└─ checkin.log      运行日志（自动轮转）
```

密码由 Windows **用户级 DPAPI** 加密，通常只能在原电脑和原 Windows 用户下解密。它不会保护账号免受当前用户权限下的其他程序读取。任务参数和运行日志不保存账号密码或 Token，日志会过滤凭据。

## 升级、迁移和停用

升级时保留源码目录位置，替换程序源码即可；用户数据保存在目录之外。**移动源码目录或更换 Python 后，重新打开配置窗口，点击“启用 / 更新时间”**，更新任务中的路径。

停用时点击“停用自动签到”。如果以前手工创建过旧版计划任务，应在 Windows 任务计划程序中停用它；此程序只管理自己创建的任务。

## 调试与可选安装

源码直接运行即可。开发者也可以安装标准 Python 包：

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install -e .
.venv\Scripts\openasi-checkin-gui.exe
```

旧版命令行入口保留用于调试，`.env.example` 仅用于此入口：

```powershell
python .\checkin.py --env-file .env --dry-run
```

图形版独立使用已加密的配置，**不会自动读取旧 `.env` 或环境变量中的账号**。

## 测试

安装包后执行：

```powershell
python -m unittest discover -s tests -v
```

GitHub Actions 在 Windows 和 Linux 上使用 Python 3.10、3.12、3.14 运行离线测试。Windows 测试包含 DPAPI 加密、Tkinter 窗口构建和实际 `pythonw.exe` 后台入口；测试仅使用虚构凭据和临时目录。

本机额外验证真实任务执行时，可以启用以下测试。它只注册一个随机命名的临时任务，运行不带账号的后台入口，并在结束后移除临时任务：

```powershell
$env:OPENASI_TEST_TASKS = "1"
python -m unittest discover -s tests -p test_scheduler_integration.py -v
Remove-Item Env:OPENASI_TEST_TASKS
```

## 常见问题

- **打开后没有窗口**：确认 ZIP 已完整解压，并安装 Python 的 Tcl/Tk。用 `python configure.pyw` 可以查看启动诊断信息。
- **密码或邮箱错误**：在窗口中重新输入，点击“测试登录”，成功后重新启用任务。
- **邮箱未验证**：先完成 OpenASI 邮箱验证。
- **创建任务失败**：确认 Windows 任务计划服务可用；组织策略可能限制任务创建。
- **没有按时签到**：打开配置窗口刷新状态，检查是否已启用、电脑是否开机且用户已登录，并查看运行日志。

## 技术参考

- [Windows DPAPI CryptProtectData](https://learn.microsoft.com/en-us/windows/win32/api/dpapi/nf-dpapi-cryptprotectdata)
- [Windows 计划任务设置](https://learn.microsoft.com/en-us/powershell/module/scheduledtasks/new-scheduledtasksettingsset)
- [Windows 计划任务主体](https://learn.microsoft.com/en-us/powershell/module/scheduledtasks/new-scheduledtaskprincipal)

项目为第三方工具，不绕过验证码或登录限制。

## 版权与许可

本软件及其文档采用 **MIT License**，详见 [LICENSE](LICENSE)。
