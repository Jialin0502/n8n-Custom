#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
n8n-privacy-patch.py

跨版本、幂等地在源码层面移除 n8n 前后端对 RudderStack / PostHog / License SDK
的集成（不依赖环境变量）。

License 部分采用“直接内联编辑”而非单独 shim 文件：
  1) packages/cli/src/license.ts
     - 移除对 @n8n_io/license-sdk 的 import；
     - 内联一个离线、无网络的 LicenseManager，默认即“Registered Community”
       (Community Plus)：只开启 n8n 免费授予注册社区版的功能
       (Folders / Debug in editor / Custom execution data + 1 天工作流历史)，
       付费企业功能 (SSO/SAML/LDAP/外部密钥/日志流/RBAC...) 保持锁定；
     - planName 设为 'Registered Community'，与前端 UI 契约精确吻合：标题显示
       “Community Edition” + “Registered” 徽章，不再弹注册提示；
     - activate() 接受任意 key 且为 no-op：不校验、不联网、不收集邮箱，
       activate 端点返回后 UI 显示激活成功。
  2) packages/cli/src/license/license.service.ts
     - 在 requestEnterpriseTrial / registerCommunityEdition 方法体首注入守卫，
       阻断把邮箱发往 enterprise.n8n.io（原网络代码保留为不可达，确保跨版本
       可应用且不引入未用 import）。
  3) packages/cli/package.json
     - 移除 @n8n_io/license-sdk 依赖（已无人 import）。

遥测部分：
  4) DiagnosticsConfig.enabled 默认改 false（同时关后端 Rudder+PostHog 与前端下发）。
  5) Telemetry.init / PostHogClient.init 注入早 return（双保险；两 SDK 为动态 import）。
  6) 物理中和前端 posthog.init.js（window.posthog 永不存在）。
  7) 前端 telemetry 插件 best-effort 注入早 return（RudderStack）。

设计原则：幂等（重复运行安全）、跨版本（锚点定位、缺锚点只 WARNING）、可审计
(--dry-run / --verify，默认写 .bak)。注入的早返回统一用 `if (Date.now() >= 0)`
包裹，避免触发 tsc/eslint 的 no-unreachable。

用法:
  python3 n8n-privacy-patch.py /path/to/n8n            # 应用
  python3 n8n-privacy-patch.py /path/to/n8n --dry-run  # 预览
  python3 n8n-privacy-patch.py /path/to/n8n --verify   # 应用后校验
"""

import argparse
import os
import re
import sys

MARK = "N8N_PRIVACY_PATCH"

STATS = {"applied": 0, "skipped": 0, "warned": 0}


def log(kind, msg):
    color = {"OK": "\033[32m", "SKIP": "\033[33m", "WARN": "\033[31m",
             "INFO": "\033[36m"}.get(kind, "")
    reset = "\033[0m" if color else ""
    print(f"{color}[{kind:4}]{reset} {msg}")
    if kind == "OK":
        STATS["applied"] += 1
    elif kind == "SKIP":
        STATS["skipped"] += 1
    elif kind == "WARN":
        STATS["warned"] += 1


def find_one(root, *relpaths):
    for rp in relpaths:
        p = os.path.join(root, rp)
        if os.path.isfile(p):
            return p
    return None


def read(path):
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def write(path, content, dry, backup):
    if dry:
        return
    if backup and not os.path.exists(path + ".bak"):
        with open(path + ".bak", "w", encoding="utf-8") as f:
            f.write(read(path))
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)


# ──────────────────────────────────────────────────────────────────────────
# 内联到 license.ts 的离线 Community Plus manager（注释里刻意不含 SDK 包名字符串，
# 以免干扰 verify 的“不再 import SDK 包”检查）。
# 依赖 license.ts 顶部已 import 的 LICENSE_FEATURES / LICENSE_QUOTAS。
# ──────────────────────────────────────────────────────────────────────────
INLINE_LICENSE_BLOCK = '''// ── %MARK%: license SDK package removed; inline offline Community Plus manager ──
// Network-free LicenseManager that defaults to "Registered Community" (Community
// Plus): only the features n8n grants free to registered self-hosters are on.
// No server is ever contacted, no email is collected, paid Enterprise features
// stay locked.
type TLicenseBlock = string;
type TEntitlement = {
\tid: string;
\tproductId: string;
\tproductMetadata: { terms?: Record<string, unknown> } & Record<string, unknown>;
\tfeatures: Record<string, boolean | number | string | undefined>;
\tfeatureOverrides: Record<string, boolean | number | string | undefined>;
\tvalidFrom: Date;
\tvalidTo: Date;
\tisFloatable: boolean;
};

const COMMUNITY_PLUS_FEATURES = new Set<string>([
\tLICENSE_FEATURES.FOLDERS,
\tLICENSE_FEATURES.DEBUG_IN_EDITOR,
\tLICENSE_FEATURES.ADVANCED_EXECUTION_FILTERS,
]);
// Must be exactly 'Registered Community' so the frontend renders name "Community"
// + badge "Registered" and treats the instance as a registered community edition.
const COMMUNITY_PLUS_PLAN_NAME = 'Registered Community';
const COMMUNITY_PLUS_WORKFLOW_HISTORY_PRUNE_MINUTES = 24 * 60;

class LicenseManager {
\tconstructor(_config?: unknown) {}
\tget isInitialized(): boolean {
\t\treturn true;
\t}
\tasync initialize(): Promise<void> {}
\tasync reload(): Promise<void> {}
\tasync reset(): Promise<void> {}
\tasync renew(): Promise<void> {}
\tasync clear(): Promise<void> {}
\tasync shutdown(): Promise<void> {}
\tenableAutoRenewals(): void {}
\tdisableAutoRenewals(): void {}
\t// Accepts ANY key and is a no-op: no validation, no network, no email.
\tasync activate(_reservationId?: string, _options?: { eulaUri?: string; email?: string }): Promise<void> {}
\thasFeatureEnabled(feature: string, _requireValidCert?: boolean): boolean {
\t\treturn COMMUNITY_PLUS_FEATURES.has(feature);
\t}
\thasFeatureDefined(feature: string, _requireValidCert?: boolean): boolean {
\t\treturn COMMUNITY_PLUS_FEATURES.has(feature);
\t}
\thasQuotaLeft(_quotaFeatureName?: string, _currentConsumption?: number): boolean {
\t\treturn true;
\t}
\tisValid(_useLogger?: boolean): boolean {
\t\treturn true;
\t}
\tisTerminated(): boolean {
\t\treturn false;
\t}
\tisRenewalDue(): boolean {
\t\treturn false;
\t}
\tgetCurrentEntitlements(): TEntitlement[] {
\t\treturn [];
\t}
\tgetFeatureValue(feature: string, _requireValidCert?: boolean): undefined | boolean | number | string {
\t\tif (feature === 'planName') return COMMUNITY_PLUS_PLAN_NAME;
\t\tif (feature === LICENSE_QUOTAS.WORKFLOW_HISTORY_PRUNE_LIMIT) {
\t\t\treturn COMMUNITY_PLUS_WORKFLOW_HISTORY_PRUNE_MINUTES;
\t\t}
\t\tif (COMMUNITY_PLUS_FEATURES.has(feature)) return true;
\t\treturn undefined;
\t}
\tgetManagementJwt(): string {
\t\treturn '';
\t}
\tgetConsumerId(): string | undefined {
\t\treturn undefined;
\t}
\tasync getCertStr(): Promise<TLicenseBlock> {
\t\treturn '';
\t}
\t// License wraps these in try/catch and falls back to null => "no expiry".
\tgetExpiryDate(): Date {
\t\tthrow new Error('no expiry');
\t}
\tgetTerminationDate(): Date {
\t\tthrow new Error('no termination');
\t}
\ttoString(): string {
\t\treturn `${COMMUNITY_PLUS_PLAN_NAME} (offline, license SDK removed)`;
\t}
}
'''.replace("%MARK%", MARK)


# ──────────────────────────────────────────────────────────────────────────
# 1) license.ts: 移除 SDK import + 内联 Community Plus manager
# ──────────────────────────────────────────────────────────────────────────
def patch_license_inline(root, dry, backup):
    lic = find_one(root, "packages/cli/src/license.ts")
    if not lic:
        log("WARN", "找不到 license.ts, 跳过 License 内联")
        return
    src = read(lic)
    if "COMMUNITY_PLUS_FEATURES" in src:
        log("SKIP", "license.ts 已内联 Community Plus manager")
        return
    # 删除所有从 license SDK 包导入的行
    import_pat = re.compile(r"^import[^\n]*from '@n8n_io/license-sdk';\n", re.MULTILINE)
    if not import_pat.search(src):
        log("WARN", "license.ts 未找到 SDK import 锚点")
        return
    new = import_pat.sub("", src)
    # 在 `type LicenseRefreshCallback` 前插入内联块; 备选锚 `export class License `
    if "type LicenseRefreshCallback" in new:
        new = new.replace("type LicenseRefreshCallback",
                          INLINE_LICENSE_BLOCK + "\ntype LicenseRefreshCallback", 1)
    elif "export class License " in new:
        new = new.replace("export class License ",
                          INLINE_LICENSE_BLOCK + "\nexport class License ", 1)
    else:
        log("WARN", "license.ts 未找到插入锚点 (类型/类声明)")
        return
    write(lic, new, dry, backup)
    log("OK", "license.ts: 移除 SDK import 并内联离线 Community Plus manager")


# ──────────────────────────────────────────────────────────────────────────
# 2) license.service.ts: 阻断 enterprise.n8n.io 邮箱外发
# ──────────────────────────────────────────────────────────────────────────
def patch_license_service(root, dry, backup):
    svc = find_one(root, "packages/cli/src/license/license.service.ts")
    if not svc:
        log("WARN", "找不到 license.service.ts, 跳过邮箱外发处理")
        return
    src = read(svc)
    if f"{MARK}: no email" in src:
        log("SKIP", "license.service.ts 邮箱外发已阻断")
        return

    changed = False
    # requestEnterpriseTrial: 方法体首注入 throw（原 axios 代码变为不可达）
    m = re.search(r"(async requestEnterpriseTrial\s*\([^)]*\)\s*\{)", src)
    if m:
        guard = (m.group(1) +
                 "\n\t\tif (Date.now() >= 0) throw new BadRequestError("
                 "'Enterprise trial requests are disabled on this instance.'); "
                 f"// {MARK}: no email sent")
        src = src[:m.start()] + guard + src[m.end():]
        changed = True
    else:
        log("WARN", "未匹配 requestEnterpriseTrial 锚点")

    # registerCommunityEdition: 方法体首注入 return（原 axios + emit 变为不可达）
    m = re.search(r"(async registerCommunityEdition\b[\s\S]*?Promise<[\s\S]*?>\s*\{)", src)
    if m:
        guard = (m.group(1) +
                 "\n\t\tif (Date.now() >= 0) return { title: 'Community features already enabled', "
                 "text: 'Free registered-community features are enabled by default. No email was sent.' }; "
                 f"// {MARK}: no email sent")
        src = src[:m.start()] + guard + src[m.end():]
        changed = True
    else:
        log("WARN", "未匹配 registerCommunityEdition 锚点")

    if changed:
        write(svc, src, dry, backup)
        log("OK", "license.service.ts: 阻断邮箱外发 (enterprise-trial + community-registered)")


# ──────────────────────────────────────────────────────────────────────────
# 3) 从 cli/package.json 移除 @n8n_io/license-sdk 依赖
# ──────────────────────────────────────────────────────────────────────────
def patch_remove_dep(root, dry, backup):
    pkg = find_one(root, "packages/cli/package.json")
    if not pkg:
        log("WARN", "找不到 packages/cli/package.json, 跳过依赖移除")
        return
    src = read(pkg)
    pat = re.compile(r'[ \t]*"@n8n_io/license-sdk"\s*:\s*"[^"]*"\s*,?\s*\n')
    if not pat.search(src):
        log("SKIP", "package.json 中无 @n8n_io/license-sdk 依赖")
        return
    new = pat.sub("", src, count=1)
    write(pkg, new, dry, backup)
    log("OK", "从 cli/package.json 移除 @n8n_io/license-sdk 依赖")


# ──────────────────────────────────────────────────────────────────────────
# 4) 后端遥测总开关默认值: DiagnosticsConfig.enabled = false
# ──────────────────────────────────────────────────────────────────────────
def patch_diagnostics_default(root, dry, backup):
    cfg = find_one(
        root,
        "packages/@n8n/config/src/configs/diagnostics.config.ts",
        "packages/cli/src/config/diagnostics.config.ts",
    )
    if not cfg:
        log("WARN", "找不到 diagnostics.config.ts, 跳过遥测默认值")
        return
    src = read(cfg)
    if re.search(r"enabled\s*:\s*boolean\s*=\s*false", src):
        log("SKIP", "diagnostics enabled 默认值已为 false")
        return
    pat = re.compile(
        r"(@Env\(\s*'N8N_DIAGNOSTICS_ENABLED'\s*\)\s*\n\s*enabled\s*:\s*boolean\s*=\s*)true",
    )
    new, n = pat.subn(r"\1false", src)
    if n == 0:
        log("WARN", "diagnostics.config.ts 未匹配 enabled 默认值锚点")
        return
    write(cfg, new, dry, backup)
    log("OK", "DiagnosticsConfig.enabled 默认值改为 false")


# ──────────────────────────────────────────────────────────────────────────
# 5) 在 async init() 方法体首注入早 return (Telemetry / PostHogClient)
# ──────────────────────────────────────────────────────────────────────────
def inject_init_return(root, relpaths, label, dry, backup):
    path = find_one(root, *relpaths)
    if not path:
        log("WARN", f"找不到 {label} 文件, 跳过 init 短路")
        return
    src = read(path)
    if f"{MARK}: init short-circuit" in src:
        log("SKIP", f"{label} init 已短路")
        return
    pat = re.compile(r"(\n(\t+)async init\(\)\s*\{\n)")
    m = pat.search(src)
    if not m:
        log("WARN", f"{label} 未匹配 `async init() {{` 锚点")
        return
    indent = m.group(2) + "\t"
    inject = (f"{m.group(1)}{indent}if (Date.now() >= 0) return;"
              f" // {MARK}: init short-circuit (telemetry disabled)\n")
    new = src[:m.start()] + inject + src[m.end():]
    write(path, new, dry, backup)
    log("OK", f"{label}.init() 注入早 return")


# ──────────────────────────────────────────────────────────────────────────
# 5b) --strip-deps: 物理移除后端遥测 SDK (RudderStack / posthog-node)
#     - 把 SDK 的 import 换成本地 `type X = any` 别名 (字段/参数名不变);
#     - 清空 init() 体 (删掉动态 import + new SDK), 使打包器不再解析 SDK 包;
#     - telemetry 清空 init 后 axios 仅在 init 用过, 一并删其 import;
#     - 从 cli/package.json 删除两个 SDK 依赖。
# 这是比 inject_init_return(中和) 更彻底的方案: SDK 不在依赖、源码不 import SDK。
# ──────────────────────────────────────────────────────────────────────────
def strip_telemetry_sdk(root, dry, backup):
    # ---- telemetry/index.ts (RudderStack) ----
    tel = find_one(root, "packages/cli/src/telemetry/index.ts")
    if not tel:
        log("WARN", "找不到 telemetry/index.ts, 跳过 RudderStack 物理移除")
    else:
        s = read(tel)
        if f"{MARK}: SDK stripped" in s:
            log("SKIP", "telemetry/index.ts SDK 已物理移除")
        else:
            orig = s
            s = re.sub(
                r"^import type RudderStack from '@rudderstack/rudder-sdk-node';\n",
                f"/* {MARK}: SDK stripped */\n"
                "type RudderStack = any; // eslint-disable-line @typescript-eslint/no-explicit-any\n",
                s, count=1, flags=re.MULTILINE)
            # 清空 init 后 axios 不再使用 -> 删其 import
            s = re.sub(r"^import axios from 'axios';\n", "", s, count=1, flags=re.MULTILINE)
            # 清空 init() 体 (匹配到 1-tab 缩进的方法结束 })
            s = re.sub(r"(async init\(\)\s*\{)[\s\S]*?(\n\t\})", r"\1\2", s, count=1)
            if s != orig and f"{MARK}: SDK stripped" in s:
                write(tel, s, dry, backup)
                log("OK", "telemetry/index.ts: 物理移除 RudderStack (import/类型/init/axios)")
            else:
                log("WARN", "telemetry/index.ts 未匹配 RudderStack 锚点")

    # ---- posthog/index.ts (posthog-node) ----
    ph = find_one(root, "packages/cli/src/posthog/index.ts")
    if not ph:
        log("WARN", "找不到 posthog/index.ts, 跳过 posthog-node 物理移除")
    else:
        s = read(ph)
        if f"{MARK}: SDK stripped" in s:
            log("SKIP", "posthog/index.ts SDK 已物理移除")
        else:
            orig = s
            s = re.sub(
                r"^import type \{[^}]*\} from 'posthog-node';\n",
                f"/* {MARK}: SDK stripped */\n"
                "type PostHog = any; // eslint-disable-line @typescript-eslint/no-explicit-any\n"
                "type FeatureFlagEvaluations = any; // eslint-disable-line @typescript-eslint/no-explicit-any\n",
                s, count=1, flags=re.MULTILINE)
            s = re.sub(r"(async init\(\)\s*\{)[\s\S]*?(\n\t\})", r"\1\2", s, count=1)
            if s != orig and f"{MARK}: SDK stripped" in s:
                write(ph, s, dry, backup)
                log("OK", "posthog/index.ts: 物理移除 posthog-node (import/类型/init)")
            else:
                log("WARN", "posthog/index.ts 未匹配 posthog-node 锚点")

    # ---- cli/package.json: 删两个 SDK 依赖 ----
    pkg = find_one(root, "packages/cli/package.json")
    if pkg:
        s = read(pkg)
        new = s
        removed = []
        for dep in ["@rudderstack/rudder-sdk-node", "posthog-node"]:
            n2 = re.sub(rf'[ \t]*"{re.escape(dep)}"\s*:\s*"[^"]*"\s*,?\s*\n', "", new, count=1)
            if n2 != new:
                removed.append(dep)
                new = n2
        if removed:
            write(pkg, new, dry, backup)
            log("OK", f"cli/package.json: 移除 {', '.join(removed)}")
        else:
            log("SKIP", "package.json 中无遥测 SDK 依赖")


# ──────────────────────────────────────────────────────────────────────────
# 5c) --strip-deps: 清除 telemetry/posthog 之外其它文件里对两个 SDK 包的 import
#     (例如 services/hooks.service.ts 的 `import RudderStack, { type
#      constructorOptions } from '@rudderstack/rudder-sdk-node'`)。
#     做法: 把 import 行整体替换为本地 stub —— default/namespace 绑定生成
#     `type X = any` + 可 new 且运行时 no-op 的 `const X`(Proxy), named 绑定
#     生成 `type N = any`。这样既能当类型又能 `new`, 且被调用也不抛错。
#     全仓库扫描确保不漏任何引用点(跨版本面向未来)。
# ──────────────────────────────────────────────────────────────────────────
SDK_PKGS = ["@rudderstack/rudder-sdk-node", "posthog-node"]
_SDK_HANDLED = {  # 已由专门函数处理(含 init 清空), 这里跳过
    "packages/cli/src/telemetry/index.ts",
    "packages/cli/src/posthog/index.ts",
}


def _sdk_stub_for_import(clause):
    """根据 import 子句生成等价的本地 any-stub 声明块。"""
    off = "/* eslint-disable @typescript-eslint/no-explicit-any */"
    on = "/* eslint-enable @typescript-eslint/no-explicit-any */"
    lines = [f"/* {MARK}: SDK stripped */", off]
    clause = clause.strip()
    type_only = clause.startswith("type ")
    if type_only:
        clause = clause[len("type "):].strip()
    named = None
    nm = re.search(r"\{([^}]*)\}", clause)
    if nm:
        named = nm.group(1)
        head = clause[:nm.start()].rstrip().rstrip(",").strip()
    else:
        head = clause
    default_name = ns_name = None
    if head:
        if head.startswith("* as"):
            ns_name = head[len("* as"):].strip()
        else:
            default_name = head.strip()
    proxy_val = ("class { constructor() { "
                 "return new Proxy(this, { get: () => () => {} }); } } as any")
    if default_name:
        lines.append(f"type {default_name} = any;")
        if not type_only:
            lines.append(f"const {default_name} = {proxy_val};")
    if ns_name:
        lines.append(f"type {ns_name} = any;")
        if not type_only:
            lines.append(f"const {ns_name} = new Proxy({{}}, {{ get: () => () => {{}} }}) as any;")
    if named:
        for n in named.split(","):
            n = n.replace("type ", "").strip()
            if " as " in n:
                n = n.split(" as ")[1].strip()
            if n:
                lines.append(f"type {n} = any;")
    lines.append(on)
    return "\n".join(lines)


def strip_residual_sdk_imports(root, dry, backup):
    pkgs_dir = os.path.join(root, "packages")
    if not os.path.isdir(pkgs_dir):
        return
    found = False
    for dirpath, dirs, files in os.walk(pkgs_dir):
        dirs[:] = [d for d in dirs if d not in ("node_modules", "dist", ".turbo")]
        for fn in files:
            if not fn.endswith(".ts") or ".test." in fn or ".spec." in fn:
                continue
            path = os.path.join(dirpath, fn)
            rel = os.path.relpath(path, root).replace("\\", "/")
            if rel in _SDK_HANDLED:
                continue
            s = read(path)
            if not any(f"'{p}'" in s for p in SDK_PKGS):
                continue
            if f"{MARK}: SDK stripped" in s:
                log("SKIP", f"{rel}: SDK import 已清除")
                continue
            orig = s
            for pkg in SDK_PKGS:
                pat = re.compile(rf"import\s+([^;]+?)\s+from\s+'{re.escape(pkg)}';")
                s = pat.sub(lambda m: _sdk_stub_for_import(m.group(1)), s)
            if s != orig:
                write(path, s, dry, backup)
                found = True
                log("OK", f"{rel}: 替换 SDK import 为本地 stub")
    if not found:
        log("SKIP", "telemetry/posthog 之外无残留 SDK import")


# ──────────────────────────────────────────────────────────────────────────
# 6) 前端: 物理中和 posthog.init.js
# ──────────────────────────────────────────────────────────────────────────
def patch_frontend_posthog(root, dry, backup):
    path = find_one(
        root,
        "packages/frontend/editor-ui/public/static/posthog.init.js",
        "packages/editor-ui/public/static/posthog.init.js",
    )
    if not path:
        log("WARN", "找不到 posthog.init.js, 跳过前端 PostHog 中和")
        return
    src = read(path)
    if MARK in src:
        log("SKIP", "前端 posthog.init.js 已中和")
        return
    stub = (f"/* {MARK}: PostHog bootstrap neutralized. window.posthog is left "
            f"undefined so the frontend PostHog store never initializes. */\n")
    write(path, stub, dry, backup)
    log("OK", "中和前端 posthog.init.js (window.posthog 永不定义)")


# ──────────────────────────────────────────────────────────────────────────
# 7) 前端 RudderStack telemetry 插件: best-effort 注入早 return
# ──────────────────────────────────────────────────────────────────────────
def patch_frontend_rudder(root, dry, backup):
    path = find_one(
        root,
        "packages/frontend/editor-ui/src/app/plugins/telemetry/index.ts",
        "packages/editor-ui/src/plugins/telemetry/index.ts",
        "packages/frontend/editor-ui/src/plugins/telemetry/index.ts",
    )
    if not path:
        log("WARN", "找不到前端 telemetry 插件 (RudderStack 仍受后端开关连带关闭)")
        return
    src = read(path)
    if f"{MARK}: fe " in src:
        log("SKIP", "前端 telemetry 插件已处理")
        return
    changed = False
    # 1) 物理移除 RudderStack CDN 加载 URL (前端唯一硬编码遥测外联)
    if "cdn-rs.n8n.io" in src:
        src = re.sub(r"'https://cdn-rs\.n8n\.io/[^']*'",
                     f"'' /* {MARK}: fe RudderStack CDN removed */", src)
        changed = True
    # 2) init 注入早 return (确保整个遥测流程不启动 / 不注入任何脚本)
    pat = re.compile(r"(\n(\t+))(if\s*\(\s*!telemetrySettings\.enabled[^\n]*return;)")
    m = pat.search(src)
    if m:
        inject = (f"{m.group(1)}if (Date.now() >= 0) return; // {MARK}: fe telemetry disabled"
                  f"{m.group(1)}{m.group(3)}")
        src = src[:m.start()] + inject + src[m.end():]
        changed = True
    else:
        log("WARN", "前端 telemetry init guard 锚点未匹配 (CDN URL 已移除即可)")
    if changed:
        write(path, src, dry, backup)
        log("OK", "前端 telemetry: 移除 RudderStack CDN(cdn-rs.n8n.io) + init 早 return")
    else:
        log("WARN", "前端 telemetry 插件无可处理项")


# ──────────────────────────────────────────────────────────────────────────
# 校验
# ──────────────────────────────────────────────────────────────────────────
def verify(root):
    print("\n──────── 校验 ────────")
    checks = []

    lic = find_one(root, "packages/cli/src/license.ts")
    if lic:
        s = read(lic)
        checks.append(("license.ts 内联 Community Plus manager", "COMMUNITY_PLUS_FEATURES" in s))
        checks.append(("license.ts 不再 import license SDK 包",
                       not re.search(r"^import[^\n]*from '@n8n_io/license-sdk';", s, re.MULTILINE)))
        checks.append(("planName = 'Registered Community'", "'Registered Community'" in s))

    svc = find_one(root, "packages/cli/src/license/license.service.ts")
    if svc:
        checks.append(("license.service.ts 阻断邮箱外发", f"{MARK}: no email" in read(svc)))

    pkg = find_one(root, "packages/cli/package.json")
    if pkg:
        checks.append(("cli/package.json 已移除 license-sdk",
                       "@n8n_io/license-sdk" not in read(pkg)))

    cfg = find_one(root, "packages/@n8n/config/src/configs/diagnostics.config.ts")
    if cfg:
        checks.append(("diagnostics enabled 默认 false",
                       bool(re.search(r"enabled\s*:\s*boolean\s*=\s*false", read(cfg)))))

    tel = find_one(root, "packages/cli/src/telemetry/index.ts")
    if tel:
        st = read(tel)
        stripped = "SDK stripped" in st
        checks.append(("Telemetry SDK 物理移除" if stripped else "Telemetry.init 已短路", MARK in st))
        if stripped:
            checks.append(("telemetry/index.ts 不含 RudderStack 动态 import",
                           "import('@rudderstack/rudder-sdk-node')" not in st))

    ph = find_one(root, "packages/cli/src/posthog/index.ts")
    if ph:
        sp = read(ph)
        stripped = "SDK stripped" in sp
        checks.append(("PostHog SDK 物理移除" if stripped else "PostHogClient.init 已短路", MARK in sp))
        if stripped:
            checks.append(("posthog/index.ts 不含 posthog-node import",
                           "from 'posthog-node'" not in sp))
            pkg2 = find_one(root, "packages/cli/package.json")
            if pkg2:
                pj = read(pkg2)
                checks.append(("cli/package.json 已删 RudderStack+posthog-node 依赖",
                               "@rudderstack/rudder-sdk-node" not in pj and "posthog-node" not in pj))
            # 全仓库扫描: 确保没有任何源码文件仍 import 这两个 SDK 包
            residual = []
            pkgs_dir = os.path.join(root, "packages")
            for dp, ds, fls in os.walk(pkgs_dir):
                ds[:] = [d for d in ds if d not in ("node_modules", "dist", ".turbo")]
                for fn in fls:
                    if not fn.endswith(".ts") or ".test." in fn or ".spec." in fn:
                        continue
                    fp = os.path.join(dp, fn)
                    c = read(fp)
                    if "from '@rudderstack/rudder-sdk-node'" in c or "from 'posthog-node'" in c:
                        residual.append(os.path.relpath(fp, root))
            checks.append((f"全仓库无残留 SDK import (扫描到 {len(residual)} 处)" +
                           (": " + ", ".join(residual) if residual else ""), not residual))

    fe = find_one(root, "packages/frontend/editor-ui/public/static/posthog.init.js")
    if fe:
        checks.append(("前端 posthog.init.js 已中和", MARK in read(fe)))

    fer = find_one(root, "packages/frontend/editor-ui/src/app/plugins/telemetry/index.ts",
                   "packages/editor-ui/src/plugins/telemetry/index.ts")
    if fer:
        sf = read(fer)
        checks.append(("前端 telemetry 已处理", f"{MARK}: fe " in sf))
        checks.append(("前端不含 cdn-rs.n8n.io 外联", "cdn-rs.n8n.io" not in sf))

    ok = True
    for name, passed in checks:
        print(f"  {'✓' if passed else '✗'} {name}")
        ok = ok and passed
    print(f"\n结果: {'全部通过' if ok else '存在未通过项'}")
    return ok


# ──────────────────────────────────────────────────────────────────────────
def main():
    ap = argparse.ArgumentParser(description="n8n 去遥测 + License 内联 Community Plus 跨版本 patch")
    ap.add_argument("root", help="n8n 仓库根目录")
    ap.add_argument("--dry-run", action="store_true", help="仅预览, 不写入")
    ap.add_argument("--no-backup", action="store_true", help="不写 .bak 备份")
    ap.add_argument("--verify", action="store_true", help="结束后校验")
    ap.add_argument("--strip-deps", action="store_true",
                    help="物理移除后端遥测 SDK 依赖与引用(更彻底), 而非仅中和 init")
    args = ap.parse_args()

    root = os.path.abspath(args.root)
    if not os.path.isdir(root):
        print(f"错误: 目录不存在 {root}")
        sys.exit(1)
    if not os.path.isfile(os.path.join(root, "package.json")):
        print(f"错误: {root} 看起来不是 n8n 仓库根目录")
        sys.exit(1)

    dry = args.dry_run
    backup = not args.no_backup
    log("INFO", f"目标: {root}{'  (dry-run)' if dry else ''}")
    print("──────── 应用补丁 ────────")

    # License (内联 Community Plus + 去邮箱)
    patch_license_inline(root, dry, backup)
    patch_license_service(root, dry, backup)
    patch_remove_dep(root, dry, backup)
    # 后端遥测
    patch_diagnostics_default(root, dry, backup)
    if args.strip_deps:
        strip_telemetry_sdk(root, dry, backup)  # telemetry/posthog: 物理移除 SDK + 清空 init
        strip_residual_sdk_imports(root, dry, backup)  # 其它文件(hooks.service.ts 等)残留 import
    else:
        inject_init_return(root, ["packages/cli/src/telemetry/index.ts"], "Telemetry", dry, backup)
        inject_init_return(root, ["packages/cli/src/posthog/index.ts"], "PostHogClient", dry, backup)
    # 前端遥测
    patch_frontend_posthog(root, dry, backup)
    patch_frontend_rudder(root, dry, backup)

    print("\n──────── 汇总 ────────")
    print(f"  应用 {STATS['applied']} / 跳过 {STATS['skipped']} / 警告 {STATS['warned']}")

    if args.verify and not dry:
        verify(root)


if __name__ == "__main__":
    main()
