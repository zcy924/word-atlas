# 个人多设备同步

在「我的 → 多设备同步 → 首次开启」设置至少 5 字符的密码，保存生成的
12 位同步码。其他设备选择「连接已有同步空间」，输入相同同步码和密码。
同步码和密码丢失后暂不提供找回；本机文件备份仍可独立使用。

## 数据与冲突

同步开放词库的 FSRS 记忆状态、收藏、每日统计、打字记录、错词和设置。
不传输进行中的答题会话，也不传输本机开发用的私人词库。
修改后约 2 秒上传；页面可见时每 30 秒检查一次，恢复网络或切回页面时也会检查。
断网继续本机保存，服务器不可用不影响学习。

新设备没有学习记录时采用云端数据；已有本机记录且与云端不同时，提示选择
完整保留本机或云端版本，不自动拼接统计或覆盖。两台设备从同一版本各自离线
修改时同样提示冲突。服务器使用事务和 revision 比较阻止并发覆盖。
应用云端数据时会清除本机进行中的答题；自动同步会等当前练习结束。
清空记录或导入备份也属于需要同步的修改。断开设备保留其本机数据。

## 服务部署

Python 3.12+ 标准库服务位于 `server/sync.py`，只监听 `127.0.0.1:8322`。
Caddy 将 `/api/sync/*` 反向代理到此服务。API 不允许跨域访问，必须通过 HTTPS。
密码使用带随机盐的 PBKDF2-SHA256 哈希；30 天登录会话通过 Secure、HttpOnly、
SameSite=Strict Cookie 保存，服务器只保存会话令牌哈希。学习数据不是端到端加密，
服务器管理员可以读取；SQLite 必须保存在静态站点目录之外。

首次安装：创建无 sudo 的系统用户 `word-atlas-sync`，将 `sync.py` 以 root 所有、
644 权限安装到 `/opt/word-atlas-sync/sync.py`，将配套 service 文件安装到
`/etc/systemd/system/word-atlas-sync.service`，然后 daemon-reload 并 enable --now。
systemd 自动创建权限 700 的 `/var/lib/word-atlas-sync`，数据库持久化于该目录，
不随静态站点发布或回退删除。加入 Caddy 代理规则并校验、reload。

GitHub Actions 会测试 API 和前端，再按原有流程部署静态页面。
API 服务独立发布：修改 `server/` 时，管理员需要同步安装脚本并重启服务。
备份数据库应使用 SQLite backup API 或停服后复制，避免复制到未提交的事务状态。

## 本地验证

```sh
SYNC_DB=/tmp/word-atlas-sync-test.sqlite3 SYNC_ORIGIN=http://localhost:5188 python3 server/sync.py
npm run dev
```

使用 `http://localhost:5188` 测试，开发服务器代理 API。部署使用 HTTPS 域名。
测试：`npm test`、`npm run build`、`python3 -m unittest discover -s server -p 'test_*.py'`。
