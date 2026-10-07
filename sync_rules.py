#!/usr/bin/env python3
import json
import re
import shutil
import subprocess
import tempfile
import urllib.request
from pathlib import Path
# ============================================================
# 基础路径
# ============================================================
ROOT = Path(__file__).resolve().parent
RULES_DIR = ROOT / "rules"
# ============================================================
# 输出目录
# ============================================================
DUSTINWIN_MIHOMO = (
    RULES_DIR /
    "DustinWin" /
    "Mihomo"
)
DUSTINWIN_SINGBOX = (
    RULES_DIR /
    "DustinWin" /
    "SingBox"
)
METACUBEX_MIHOMO_DOM = (
    RULES_DIR /
    "MetaCubeX" /
    "Mihomo" /
    "Dom"
)
METACUBEX_SINGBOX_IPC = (
    RULES_DIR /
    "MetaCubeX" /
    "SingBox" /
    "Ipc"
)
METACUBEX_SINGBOX_DOM = (
    RULES_DIR /
    "MetaCubeX" /
    "SingBox" /
    "Dom"
)
CNIP_DIR = RULES_DIR / "Cnip"
ADBLOCK_DIR = RULES_DIR / "AdBlock"
# ============================================================
# Rule-for-OCD 路径（Ipc 为合并目标目录）
# ============================================================
RULE_FOR_OCD_REPO = (
    "https://github.com/peiyingyao/"
    "Rule-for-OCD.git"
)
RULE_FOR_OCD_DIR = (
    RULES_DIR / "Mihomo"
)
RULE_FOR_OCD_DOM = (
    RULE_FOR_OCD_DIR / "Dom"
)
RULE_FOR_OCD_IPC = (
    RULE_FOR_OCD_DIR / "Ipc"
)
GITHUB_API = (
    "https://api.github.com"
)
# ============================================================
# 仓库
# ============================================================
DUSTINWIN_REPO = (
    "https://github.com/DustinWin/"
    "ruleset_geodata.git"
)
METACUBEX_REPO = (
    "https://github.com/MetaCubeX/"
    "meta-rules-dat.git"
)
CNIP_REPO = (
    "https://github.com/X-Shelby/"
    "geoip.git"
)
ADBLOCK_REPO = (
    "https://github.com/217heidai/"
    "adblockfilters.git"
)

# ============================================================
# 执行命令
# ============================================================
def run(cmd, cwd=None):
    print(
        "+",
        " ".join(
            str(x)
            for x in cmd
        )
    )
    subprocess.run(
        cmd,
        cwd=cwd,
        check=True
    )
# ============================================================
# clone
# ============================================================
def clone_repo(
    repo,
    branch=None
):
    temp = Path(
        tempfile.mkdtemp(
            prefix="rules-sync-"
        )
    )
    cmd = [
        "git",
        "clone",
        "--depth",
        "1",
    ]
    if branch:
        cmd.extend(
            [
                "--branch",
                branch
            ]
        )
    cmd.extend(
        [
            repo,
            str(temp)
        ]
    )
    run(cmd)
    return temp
# ============================================================
# GitHub API
# ============================================================
def github_api(url):
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent":
            "rules-sync"
        }
    )
    with urllib.request.urlopen(
        req,
        timeout=60
    ) as r:
        return json.loads(
            r.read()
            .decode("utf-8")
        )
# ============================================================
# 下载
# ============================================================
def download(
    url,
    target
):
    print(
        "download:",
        url
    )
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent":
            "rules-sync"
        }
    )
    with urllib.request.urlopen(
        req,
        timeout=120
    ) as r:
        data = r.read()
    target.parent.mkdir(
        parents=True,
        exist_ok=True
    )
    target.write_bytes(
        data
    )
# ============================================================
# 清理旧目录
# ============================================================
def clean_rules():
    if RULES_DIR.exists():
        print(
            "remove old rules"
        )
        shutil.rmtree(
            RULES_DIR
        )
    RULES_DIR.mkdir(
        parents=True
    )
# ============================================================
# 文件名规范化
# ============================================================
def normalize_filename(filename):
    path = Path(filename)
    stem = path.stem.lower()
    suffix = path.suffix.lower()
    if stem.endswith("_domain"):
        stem = stem[:-7]
    elif stem.endswith("_ipcidr"):
        stem = stem[:-7] + "_ip"
    return stem + suffix
# ============================================================
# classical 排除
# ============================================================
def is_classical(filename):
    """
    排除：
    xxx_classical
    xxx_classical_domain
    xxx_classical_ipcidr
    """
    stem = Path(
        filename
    ).stem.lower()
    return (
        "_classical" in stem
    )
# ============================================================
# 文件过滤
 # ============================================================
def should_keep(filename):
     """
     文件过滤
     默认同步所有文件
     仅排除：
     .md
     *_classical*
     """
     lower = filename.lower()
     # 排除 Markdown
     if lower.endswith(".md"):
         return False
     # 排除 classical
     if is_classical(filename):
         return False
     # 其他全部保留
     return True
 # ============================================================
 # MetaCubeX 专用文件过滤
 # ============================================================
def should_keep_metacubex(filename):
     """
     MetaCubeX 专用过滤：
     1. 带 @ 的文件不再同步。
     2. 其余规则沿用 should_keep()。
     """
     if "@" in filename:
         return False
     return should_keep(filename)
 # ============================================================
 # 复制文件
 # ============================================================
def normalize_dir_name(name):
     """
     普通输出目录名称首字母大写。
     """
     if not name:
         return name
     return name[0].upper() + name[1:]
def normalize_leaf_dir_name(name):
     """
     DustinWin / MetaCubeX 最里层文件目录保持小写。
     """
     return name.lower()
 def split_dir_family(name):
     """
     自动识别类似目录族：
         category-novel
         category-ntp
         category-ntp-cn
     不固定 category。
     使用第一个 '-' 前的部分作为目录族名称。
     """
     if "-" not in name:
         return None
     prefix = name.split("-", 1)[0]
     if not prefix:
         return None
     return prefix
 def build_relative_destination(source, source_root, destination):
     """
     将源目录结构转换为输出目录结构。
     规则：
     1. 所有目录首字母大写。
     2. 同一父目录下存在两个或以上相同前缀的
        xxx-* 目录时，自动归并到 Xxx。
     3. 归并后文件直接放入 Xxx，不保留 xxx-* 子目录。
     """
     relative_parent = source.parent.relative_to(source_root)
     parts = list(relative_parent.parts)
     if not parts:
         return destination
     current = parts[-1]
     family = split_dir_family(current)
     if family:
         parent = source.parent.parent
         sibling_dirs = [
             p for p in parent.iterdir()
             if p.is_dir() and ".git" not in p.parts
         ]
         family_members = [
             p for p in sibling_dirs
             if split_dir_family(p.name) == family
         ]
         if len(family_members) >= 2:
             parts[-1] = normalize_dir_name(family)
         else:
             parts[-1] = normalize_dir_name(current)
     else:
         parts[-1] = normalize_dir_name(current)
     # 所有上级目录首字母大写
     for i in range(len(parts) - 1):
         parts[i] = normalize_dir_name(parts[i])
     return destination.joinpath(*parts)
 def copy_rule(
     source,
     destination,
     source_root=None,
     create_folder=False,
     keep_func=should_keep,
     folder_name_func=normalize_dir_name
 ):
     if not source.is_file():
         return
     # 排除 .git
     if ".git" in source.parts:
         return
     # 排除 .md / classical
     if not keep_func(source.name):
         return
     new_name = normalize_filename(source.name)
     if source_root is not None:
         target_dir = build_relative_destination(
             source,
             source_root,
             destination
         )
     elif create_folder:
         folder_name = Path(new_name).stem.lower()
         if folder_name.endswith("_ip"):
             folder_name = folder_name[:-3]
         target_dir = destination / folder_name
     else:
         target_dir = destination
     target_dir.mkdir(
         parents=True,
         exist_ok=True
     )
     target = target_dir / new_name
     shutil.copy2(
         source,
         target
     )
     print(
         source.name,
         "->",
         target.relative_to(ROOT)
     )
 # ============================================================
 # DustinWin
 # ============================================================
def sync_dustinwin():
     print("\n")
     print("=" * 60)
     print("DUSTINWIN")
     print("=" * 60)
     # -------------------------
     # Mihomo
     # -------------------------
     print(
         "\n[DustinWin Mihomo]"
     )
     mihomo_repo = clone_repo(
         DUSTINWIN_REPO,
         branch="mihomo-ruleset"
     )
     for file in mihomo_repo.rglob("*"):
         copy_rule(
             file,
             DUSTINWIN_MIHOMO,
             create_folder=True,
             folder_name_func=normalize_leaf_dir_name
         )
     # -------------------------
     # SingBox release
     # -------------------------
     print(
         "\n[DustinWin SingBox]"
     )
     release_url = (
         GITHUB_API
         +
         "/repos/DustinWin/"
         "ruleset_geodata/"
         "releases/tags/"
         "sing-box-ruleset"
     )
     release = github_api(
         release_url
     )
     assets = release.get(
         "assets",
         []
     )
     if not assets:
         raise RuntimeError(
             "DustinWin sing-box-ruleset "
             "没有找到release文件"
         )
     for asset in assets:
         name = asset.get(
             "name",
             ""
         )
         if not should_keep(
             name
         ):
             continue
         url = asset.get(
             "browser_download_url"
         )
         if not url:
             continue
         new_name = normalize_filename(name)
         folder_name = Path(new_name).stem.lower()
         if folder_name.endswith("_ip"):
             folder_name = folder_name[:-3]
         target = (
             DUSTINWIN_SINGBOX
             /
             normalize_leaf_dir_name(folder_name)
             /
             new_name
         )
         download(
             url,
             target
         )
 # ============================================================
 # MetaCubeX
 # ============================================================
def sync_metacubex():
     print("\n")
     print("=" * 60)
     print("METACUBEX")
     print("=" * 60)
     # ========================================================
     # Mihomo
     # branch meta
     #
     # geo/
     # ├── geoip → 合并到 Rule-for-OCD 的 Ipc 目录（优先）
     # └── geosite → Dom 保持原目录
     # ========================================================
     print(
         "\n[MetaCubeX Mihomo]"
     )
     repo = clone_repo(
         METACUBEX_REPO,
         branch="meta"
     )
     geo = repo / "geo"
     # geoip -> 合并到 Rule-for-OCD Ipc 目录（优先同步）
     geoip = geo / "geoip"
     if geoip.exists():
         for file in geoip.rglob("*"):
             copy_rule(
                 file,
                 RULE_FOR_OCD_IPC,
                 create_folder=True,
                 keep_func=should_keep_metacubex,
                 folder_name_func=normalize_leaf_dir_name
             )
     # geosite -> dom（保持原 MetaCubeX 目录）
     geosite = geo / "geosite"
     if geosite.exists():
         for file in geosite.rglob("*"):
             copy_rule(
                 file,
                 METACUBEX_MIHOMO_DOM,
                 create_folder=True,
                 keep_func=should_keep_metacubex,
                 folder_name_func=normalize_leaf_dir_name
             )
     # ========================================================
     # SingBox
     # branch sing
     # ========================================================
     print(
         "\n[MetaCubeX SingBox]"
     )
     repo_sing = clone_repo(
         METACUBEX_REPO,
         branch="sing"
     )
     geo_sing = repo_sing / "geo"
     # geoip -> ipc
     geoip_sing = geo_sing / "geoip"
     if geoip_sing.exists():
         for file in geoip_sing.rglob("*"):
             copy_rule(
                 file,
                 METACUBEX_SINGBOX_IPC,
                 create_folder=True,
                 keep_func=should_keep_metacubex,
                 folder_name_func=normalize_leaf_dir_name
             )
     # geosite -> dom
     geosite_sing = geo_sing / "geosite"
     if geosite_sing.exists():
         for file in geosite_sing.rglob("*"):
             copy_rule(
                 file,
                 METACUBEX_SINGBOX_DOM,
                 create_folder=True,
                 keep_func=should_keep_metacubex,
                 folder_name_func=normalize_leaf_dir_name
             )
 # ============================================================
 # cnip
 # ============================================================
def sync_cnip():
     print("\n")
     print("=" * 60)
     print("CNIP")
     print("=" * 60)
     release_url = (
         GITHUB_API
         +
         "/repos/X-Shelby/"
         "geoip/releases/latest"
     )
     release = github_api(
         release_url
     )
     assets = release.get(
         "assets",
         []
     )
     if not assets:
         raise RuntimeError(
             "X-Shelby geoip "
             "latest release 无文件"
         )
     for asset in assets:
         name = asset.get(
             "name",
             ""
         )
         # 过滤格式
         if not should_keep(
             name
         ):
             continue
         url = asset.get(
             "browser_download_url"
         )
         if not url:
             continue
         target = (
             CNIP_DIR
             /
             normalize_filename(
                 name
             )
         )
         download(
             url,
             target
         )
         print(
             name,
             "->",
             target.relative_to(ROOT)
         )
 # ============================================================
 # AdBlock
 # ============================================================
def should_keep_adblock(filename):
     """AdBlock 仅同步 .list / .mrs / .srs / .json。"""
     lower = filename.lower()
     return lower.endswith((".list", ".mrs", ".srs", ".json"))
 def sync_adblock():
     print("\n")
     print("=" * 60)
     print("ADBLOCK")
     print("=" * 60)
     repo = clone_repo(
         ADBLOCK_REPO,
         branch="main"
     )
     source = (
         repo /
         "rules"
     )
     if not source.exists():
         raise RuntimeError(
             "AdBlock rules目录不存在"
         )
     for file in source.rglob("*"):
         copy_rule(
             file,
             ADBLOCK_DIR,
             create_folder=False,
             keep_func=should_keep_adblock
         )
 # ============================================================
 # Rule-for-OCD
 #
 # Ipc：MetaCubeX 优先，已存在则跳过
 # Dom：正常同步
 # ============================================================
def sync_rule_for_ocd():
     print("\n")
     print("=" * 60)
     print("RULE-FOR-OCD")
     print("=" * 60)
     repo = clone_repo(
         RULE_FOR_OCD_REPO
     )
     source = repo / "rule" / "Clash"
     if not source.exists():
         raise RuntimeError(
             f"Rule-for-OCD source directory not found: {source}"
         )
     copied = 0
     skipped = 0
     domain_pattern = re.compile(
         r"^(.+?)_OCD_Domain\.(mrs|yaml)$",
         re.IGNORECASE
     )
     ip_pattern = re.compile(
         r"^(.+?)_OCD_IP\.(mrs|yaml)$",
         re.IGNORECASE
     )
     for file in source.rglob("*"):
         if not file.is_file():
             continue
         match = domain_pattern.match(file.name)
         if match:
             name = match.group(1).lower()
             ext = match.group(2).lower()
             target_dir = RULE_FOR_OCD_DOM / name
             target = target_dir / f"{name}.{ext}"
         else:
             match = ip_pattern.match(file.name)
             if match:
                 name = match.group(1).lower()
                 ext = match.group(2).lower()
                 target_dir = RULE_FOR_OCD_IPC / name
                 target = target_dir / f"{name}.{ext}"
                 # ===== 修改点：MetaCubeX 已存在的同类型文件跳过 =====
                 if target.exists():
                     skipped += 1
                     continue
             else:
                 skipped += 1
                 continue
         target_dir.mkdir(
             parents=True,
             exist_ok=True
         )
         shutil.copy2(
             file,
             target
         )
         print(
             file.name,
             "->",
             target.relative_to(ROOT)
         )
         copied += 1
     print(
         "Rule-for-OCD copied:",
         copied
     )
     print(
         "Rule-for-OCD skipped:",
         skipped
     )
 # ============================================================
 # 输出目录名称规范化
 # ============================================================
def normalize_output_directories():
     """
     将 rules 下所有目录的首字母统一大写。
     特殊：
     1. DustinWin / MetaCubeX 最里层文件夹保持小写
     2. 所有 Ipc 目录下的子文件夹全部小写
     """
     if not RULES_DIR.exists():
         return
     directories = sorted(
         [p for p in RULES_DIR.rglob("*") if p.is_dir()],
         key=lambda p: len(p.parts),
         reverse=True
     )
     for directory in directories:
         old_name = directory.name
         try:
             rel = directory.relative_to(RULES_DIR)
             top = rel.parts[0] if rel.parts else ""
             is_leaf = not any(child.is_dir() for child in directory.iterdir())
         except (ValueError, OSError):
             top = ""
             is_leaf = False
         # ===== 修改点：Ipc 目录下的子文件夹强制小写 =====
         keep_lower = False
         if top in ("DustinWin", "MetaCubeX") and is_leaf:
             keep_lower = True
         # 父目录是 Ipc 则保持小写
         try:
             if directory.parent.name.lower() == "ipc":
                 keep_lower = True
         except (OSError, ValueError):
             pass
         if keep_lower:
             new_name = old_name.lower()
         else:
             new_name = normalize_dir_name(old_name)
         if old_name == new_name:
             continue
         target = directory.parent / new_name
         if target.exists() and target != directory:
             # 合并到已经存在的目标目录
             for item in directory.iterdir():
                 destination = target / item.name
                 if item.is_dir():
                     if destination.exists():
                         shutil.copytree(
                             item,
                             destination,
                             dirs_exist_ok=True
                         )
                     else:
                         shutil.move(
                             str(item),
                             str(destination)
                         )
                 else:
                     shutil.move(
                         str(item),
                         str(destination)
                     )
             directory.rmdir()
         else:
             directory.rename(target)
 # ============================================================
 # 验证目录
 # ============================================================
def validate():
     print("\n")
     print("=" * 60)
     print("VALIDATE")
     print("=" * 60)
     dirs = [
         DUSTINWIN_MIHOMO,
         DUSTINWIN_SINGBOX,
         METACUBEX_MIHOMO_DOM,
         METACUBEX_SINGBOX_IPC,
         METACUBEX_SINGBOX_DOM,
         CNIP_DIR,
         ADBLOCK_DIR,
         RULE_FOR_OCD_DOM,
         RULE_FOR_OCD_IPC,
     ]
     errors = []
     for directory in dirs:
         if not directory.exists():
             errors.append(
                 f"Missing directory: {directory}"
             )
             continue
         files = list(
             directory.rglob("*")
         )
         if not any(
             f.is_file()
             for f in files
         ):
             errors.append(
                 f"Empty directory: {directory}"
             )
         for file in files:
             if not file.is_file():
                 continue
             name = file.name.lower()
             # Rule-for-OCD 只允许 .mrs / .yaml
             if (
                 RULE_FOR_OCD_DIR in file.parents
                 and not name.endswith((".mrs", ".yaml"))
             ):
                 errors.append(
                     f"Invalid Rule-for-OCD file: {file}"
                 )
             # md
             if name.endswith(
                 ".md"
             ):
                 errors.append(
                     f"Markdown file: {file}"
                 )
             # classical
             if is_classical(
                 file.name
             ):
                 errors.append(
                     f"Classical file: {file}"
                 )
             # 文件名大小写
             if file.name != name:
                 errors.append(
                     f"Uppercase filename: {file}"
                 )
     if errors:
         print(
             "\nValidation FAILED"
         )
         for e in errors:
             print(
                 "ERROR:",
                 e
             )
         raise RuntimeError(
             "validation failed"
         )
     print(
         "Validation PASSED"
     )
 # ============================================================
 # 统计
 # ============================================================
def statistics():
     print("\n")
     print("=" * 60)
     print("STATISTICS")
     print("=" * 60)
     dirs = [
         DUSTINWIN_MIHOMO,
         DUSTINWIN_SINGBOX,
         METACUBEX_MIHOMO_DOM,
         METACUBEX_SINGBOX_IPC,
         METACUBEX_SINGBOX_DOM,
         CNIP_DIR,
         ADBLOCK_DIR,
         RULE_FOR_OCD_DOM,
         RULE_FOR_OCD_IPC,
     ]
     total = 0
     for directory in dirs:
         count = sum(
             1
             for f in directory.rglob("*")
             if f.is_file()
         )
         total += count
         print(
             directory.relative_to(ROOT),
             ":",
             count
         )
     print(
         "Total:",
         total
     )
 # ============================================================
 # MAIN
 # ============================================================
def main():
     print(
         "=" * 60
     )
     print(
         "RULES SYNC START"
     )
     print(
         "=" * 60
     )
     # 清理旧目录
     clean_rules()
     # 同步（MetaCubeX 优先于 Rule-for-OCD）
     sync_dustinwin()
     sync_metacubex()
     sync_cnip()
     sync_adblock()
     sync_rule_for_ocd()
     # 统一输出目录名称
     normalize_output_directories()
     # 验证
     validate()
     # 统计
     statistics()
     print(
         "\nSYNC COMPLETED"
     )
 if __name__ == "__main__":
     main()
