# 部署 / Deployment

`npm run build` 生成纯静态站点 `dist/`，可以放到任何静态托管（Nginx、Cloudflare Pages、Vercel、GitHub Pages）。

## 子路径

```bash
ATLAS_BASE=/words/ npm run build
```

## Nginx 示例

```nginx
location ^~ /words/ {
    alias /var/www/word-atlas/;
    try_files $uri $uri/ /words/index.html;
    expires 7d;
}
```

## GitHub Pages

仓库带有 `.github/workflows/pages.yml`。在仓库 Settings → Pages 选择 “GitHub Actions”，然后手动运行 “Deploy to GitHub Pages”。

## 体积

插画与音频合计约数百 MB。建议在 CDN 后部署，或按需只发布 `thumb/` 和部分音频。

## GitHub Actions → HK

`.github/workflows/deploy-hk.yml` 在 PR 中执行测试、完整词库与媒体校验、静态构建。
推送到 `main` 或在 `main` 手动运行工作流后，自动将构建产物发布到
<https://words.nivio.top>。服务器不运行 Node，也不需要安装 npm 依赖。

### 一次性配置

- DNS：`words.nivio.top` 的 A 记录指向 HK 服务器。
- Repository Actions variables：`HK_HOST`（服务器 IP）、`HK_USER`（`word-atlas`）。
- Repository Actions secrets：`HK_DEPLOY_KEY`（专用 Ed25519 私钥）、
  `HK_KNOWN_HOSTS`（经现有可信 SSH 连接核验的服务器主机公钥记录）。
- 服务器：Python 3.12+、Caddy；专用 `word-atlas` 用户拥有
  `/srv/word-atlas/releases`，不授予 sudo。
- 将 `scripts/deploy/receive.py` 安装为 root 所有、权限 755 的
  `/usr/local/bin/deploy-word-atlas`。
- 在专用用户的 `authorized_keys` 中配置
  `restrict,command="/usr/local/bin/deploy-word-atlas"`，后接部署公钥。
  该密钥只接受 `deploy <40 位 commit SHA>` 和标准输入中的 gzip tar 包。
- 将 `scripts/deploy/Caddyfile` 中的站点加入现有 Caddy 配置，校验后 reload。

### 发布与回退

GitHub 使用 Node 22 执行 `npm ci`、`npm test`、`npm run check:atlas`、
`npm run build`，将完整 `dist/` 打包，Actions artifact 保留 1 天。
部署串行执行，SSH 严格验证主机密钥。服务器先解包并检查基础文件，
再原子切换 `/srv/word-atlas/current`，保留最近 3 个版本。
解包或校验失败不会切换当前版本；发布后检查 HTTPS 的 `revision.txt`
是否等于本次 commit SHA。HTTPS 检查失败会使工作流失败，但不会自动回退。

回退时，以管理员账户在 `/srv/word-atlas` 下选择 `releases/` 中的旧目录，
创建临时软链接后使用 `mv -Tf` 替换 `current`。无需重启 Caddy。
学习进度仍存放在各浏览器中，不随站点发布迁移或跨设备同步。
