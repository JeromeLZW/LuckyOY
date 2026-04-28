# 供应商资质对比看板

[➡️ **下载页**](https://jeromelzw.github.io/LuckyOY/%E4%BE%9B%E5%BA%94%E5%95%86%E7%9C%8B%E6%9D%BF/) · [📦 **直接下载分发包 (v1.0)**](https://github.com/JeromeLZW/LuckyOY/releases/download/v1.0/%E4%BE%9B%E5%BA%94%E5%95%86%E8%B5%84%E8%B4%A8%E7%9C%8B%E6%9D%BF-v1.0.zip)

基于「寻源效率表」模板的供应商资质对比看板，集成风鸟数据自动抓取。

## 特性
- ✅ **解压即用** — 对方电脑无需 Python、Chromium 或任何依赖
- ✅ **看板内一键登录风鸟** — 登录态自动保存复用
- ✅ **自动抓取 9 项资质** — 地址/成立时间/注册资本/员工人数/年销售额/主要产品/联系人/电话
- ✅ **多家供应商列对比** — 横向比较，单元格可编辑
- ✅ **导出 Excel** — 一键合并到寻源效率表

## 使用
1. 下载 zip（约 350MB），解压到任意位置
2. 双击 `供应商看板.exe`
3. 浏览器自动打开看板 → 点「🔐 登录风鸟」→ 登录一次
4. 输入公司名按 Enter，自动抓取并加入对比表

## 系统要求
- Windows 10 / 11 (64位)
- 约 1GB 磁盘空间

## 技术栈
- Python 3.12 + Flask + Playwright + Chromium（全部内置）
- PyInstaller `--onedir` 打包
- HTML/CSS/JS 看板，localStorage 持久化

## 文件
- `index.html` — Pages 下载落地页
- 实际可执行包在 [Releases v1.0](https://github.com/JeromeLZW/LuckyOY/releases/tag/v1.0)
