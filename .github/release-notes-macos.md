<!--
  macOS install note appended to every GitHub release by .github/workflows/release.yml.

  根因：开源项目没有 Apple Developer ID 证书 → `package.json` 的 `build.mac.identity = null`
  → 打包产物既无签名也无公证 → macOS Catalina+ 浏览器/下载器会打 `com.apple.quarantine` 扩展属性
  → Gatekeeper + XProtect 在 macOS Sequoia (15) 对完全未签名的隔离 App 走最严路径：
    弹"XProtect 检查了它认为是恶意软件的项目"，并自动移到废纸篓。

  这是 Gatekeeper 的标准误报，与代码无关。下面只解释怎么绕过，不解释原理，
  原理请看仓库 README 的 macOS 安装小节。
-->

---

## 📦 macOS 安装提示

> **macOS 用户必读：** PurrCat 桌面端 **暂未做 Apple Developer ID 签名与公证**（项目是开源的，没有付费证书）。从 macOS Catalina 起 —— 尤其 **macOS Sequoia (15)** —— 打开下载的 `.app` 时可能被 **XProtect** 直接视为恶意程序并自动移到废纸篓（提示类似 "PurrCat will damage your computer"）。**这是 Gatekeeper 因缺失签名产生的误报，与代码无关。**

### 首次运行：二选一

**方案 A — 终端一行命令去除隔离标签（推荐）：**

```bash
xattr -dr com.apple.quarantine "/Applications/PurrCat.app"
open "/Applications/PurrCat.app"
```

每发一个新版本都需要重新执行一次。

**方案 B — 不开终端，首次启动手动信任：**

1. 把 `PurrCat.app` 从 dmg 拖进 `/Applications`。
2. 在 Finder 中 **右键**（或按住 Control 点击）应用 → **打开**。
3. 在系统弹窗里点 **打开**。之后再次双击即可正常启动。

### 详细说明与原理

见 [README 的 macOS 安装小节](../../blob/v${VERSION}/README.md#-installing-a-pre-built-release-macos)（含长期解决方案说明：正式签名 + 公证需要注册 Apple Developer 账号，$99/年）。
