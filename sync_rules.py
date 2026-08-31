#!/usr/bin/env python3

import json
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

MIHOMO_DIR = RULES_DIR / "Mihomo"
SINGBOX_DIR = RULES_DIR / "SingBox"
DUSTINWIN_DIR = RULES_DIR / "DustinWin"
GEOIP_DIR = RULES_DIR / "geoip"
CNIP_DIR = RULES_DIR / "cnip"
ADBLOCK_DIR = RULES_DIR / "AdBlock"


# ============================================================
# 上游仓库
# ============================================================

MILANGREE_REPO = "https://github.com/milangree/rules.git"

DUSTINWIN_REPO = "https://github.com/DustinWin/ruleset_geodata.git"

METACUBEX_REPO = "https://github.com/MetaCubeX/meta-rules-dat.git"

ADBLOCK_REPO = "https://github.com/217heidai/adblockfilters.git"


# ============================================================
# GitHub API
# ============================================================

GITHUB_API = "https://api.github.com"


# ============================================================
# 工具函数
# ============================================================

def run(command, cwd=None):
    """
    执行命令。
    """

    print("+", " ".join(str(x) for x in command))

    subprocess.run(
        command,
        cwd=cwd,
        check=True,
    )


def download(url, destination):
    """
    下载文件。
    """

    print(f"Downloading: {url}")

    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "verion-rules-sync",
            "Accept": "*/*",
        },
    )

    with urllib.request.urlopen(
        request,
        timeout=120,
    ) as response:

        data = response.read()

    destination.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    destination.write_bytes(data)


def github_api(url):
    """
    GitHub API 请求。
    """

    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": "verion-rules-sync",
        },
    )

    with urllib.request.urlopen(
        request,
        timeout=60,
    ) as response:

        return json.loads(
            response.read().decode("utf-8")
        )


def clone_repo(repo, branch=None):
    """
    浅克隆 GitHub 仓库。
    """

    temp_dir = Path(
        tempfile.mkdtemp(
            prefix="verion-rules-"
        )
    )

    command = [
        "git",
        "clone",
        "--depth",
        "1",
    ]

    if branch:
        command.extend(
            [
                "--branch",
                branch,
            ]
        )

    command.extend(
        [
            repo,
            str(temp_dir),
        ]
    )

    run(command)

    return temp_dir


# ============================================================
# 清理规则
# ============================================================

def clean_rules():
    """
    完全删除旧 rules。
    
    防止：
    - 上游删除规则后本地残留
    - 文件改名后旧文件残留
    - 大小写改名后出现重复文件
    """

    if RULES_DIR.exists():

        print("\nRemoving old rules/ ...")

        shutil.rmtree(RULES_DIR)

    directories = [
        MIHOMO_DIR,
        SINGBOX_DIR,
        DUSTINWIN_DIR,
        GEOIP_DIR,
        CNIP_DIR,
        ADBLOCK_DIR,
    ]

    for directory in directories:
        directory.mkdir(
            parents=True,
            exist_ok=True,
        )


# ============================================================
# 文件名规范化
# ============================================================

def normalize_filename(filename):
    path = Path(filename)

    stem = path.stem.lower()
    suffix = path.suffix.lower()

    # xxx_domain → xxx
    if stem.endswith("_domain"):
        stem = stem[:-7]

    # xxx_ipcidr → xxx_ip
    elif stem.endswith("_ipcidr"):
        stem = stem[:-7] + "_ip"

    return stem + suffix

    # --------------------------------------------
    # Domain
    # --------------------------------------------

    if stem in {
        "domain",
        "domains",
        "ads_domain",
    }:

        stem = "ads_merge"

    # --------------------------------------------
    # IPCIDR
    # --------------------------------------------

    elif stem in {
        "ipcidr",
        "ip-cidr",
        "ip_cidr",
        "ads_ipcidr",
    }:

        stem = "ads_mergeip"

    return stem + suffix


# ============================================================
# 文件过滤
# ============================================================

def is_classical(filename):
    """
    classical 文件全部排除。
    """

    return "classical" in filename.lower()


def should_keep(filename, extensions):
    """
    判断文件是否允许同步。
    """

    lower = filename.lower()

    # --------------------------------------------
    # 永久排除 Markdown
    # --------------------------------------------

    if lower.endswith(".md"):
        return False

    # --------------------------------------------
    # 永久排除 classical
    # --------------------------------------------

    if is_classical(lower):
        return False

    # --------------------------------------------
    # 只允许指定扩展名
    # --------------------------------------------

    return any(
        lower.endswith(ext)
        for ext in extensions
    )


# ============================================================
# 复制规则
# ============================================================

def copy_rule(
    source,
    destination_dir,
    extensions,
):
    """
    复制规则并规范化文件名。
    """

    if not source.is_file():
        return False

    if not should_keep(
        source.name,
        extensions,
    ):
        return False

    new_name = normalize_filename(
        source.name
    )

    destination = (
        destination_dir / new_name
    )

    destination_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    shutil.copy2(
        source,
        destination,
    )

    print(
        f"  {source.name}"
        f" -> "
        f"{destination.relative_to(ROOT)}"
    )

    return True


# ============================================================
# ① milangree
#
# Mihomo:
#   *.mrs
#
# SingBox:
#   *.srs
#
# 不进行合并。
# ============================================================

def sync_milangree():

    print("\n")
    print("=" * 60)
    print("MILANGREE")
    print("=" * 60)

    repo = clone_repo(
        MILANGREE_REPO,
        branch="main",
    )

    source = repo / "rules"

    if not source.exists():

        raise RuntimeError(
            "milangree/rules 中没有找到 rules/"
        )

    # --------------------------------------------
    # Mihomo
    # --------------------------------------------

    print("\n[Mihomo]")

    for file in source.rglob("*"):

        if not file.is_file():
            continue

        copy_rule(
            file,
            MIHOMO_DIR,
            [".mrs"],
        )

    # --------------------------------------------
    # SingBox
    # --------------------------------------------

    print("\n[SingBox]")

    for file in source.rglob("*"):

        if not file.is_file():
            continue

        copy_rule(
            file,
            SINGBOX_DIR,
            [".srs"],
        )


# ============================================================
# ② DustinWin
#
# MRS:
#   mihomo-ruleset branch
#
# SRS:
#   sing-box-ruleset-compatible release
# ============================================================

def sync_dustinwin():

    print("\n")
    print("=" * 60)
    print("DUSTINWIN")
    print("=" * 60)

    # ========================================================
    # MRS
    #
    # https://github.com/DustinWin/ruleset_geodata/
    # tree/mihomo-ruleset
    # ========================================================

    print("\n[DustinWin MRS]")

    mrs_repo = clone_repo(
        DUSTINWIN_REPO,
        branch="mihomo-ruleset",
    )

    for file in mrs_repo.rglob("*"):

        if not file.is_file():
            continue

        copy_rule(
            file,
            DUSTINWIN_DIR,
            [".mrs"],
        )

    # ========================================================
    # SRS
    #
    # sing-box-ruleset-compatible
    # ========================================================

    print("\n[DustinWin SRS]")

    release_url = (
        f"{GITHUB_API}/repos/"
        f"DustinWin/ruleset_geodata/"
        f"releases/tags/"
        f"sing-box-ruleset-compatible"
    )

    release = github_api(
        release_url
    )

    assets = release.get(
        "assets",
        [],
    )

    if not assets:

        raise RuntimeError(
            "DustinWin "
            "sing-box-ruleset-compatible "
            "没有找到 Release Assets"
        )

    for asset in assets:

        name = asset.get(
            "name",
            "",
        )

        if not should_keep(
            name,
            [".srs"],
        ):
            continue

        url = asset.get(
            "browser_download_url"
        )

        if not url:
            continue

        filename = normalize_filename(
            name
        )

        destination = (
            DUSTINWIN_DIR / filename
        )

        download(
            url,
            destination,
        )

        print(
            f"  {name}"
            f" -> "
            f"{destination.relative_to(ROOT)}"
        )


# ============================================================
# ③ MetaCubeX geoip
#
# meta branch
#
# geo/geoip/*.mrs
# ============================================================

def sync_geoip():

    print("\n")
    print("=" * 60)
    print("METACUBEX GEOIP")
    print("=" * 60)

    repo = clone_repo(
        METACUBEX_REPO,
        branch="meta",
    )

    source = (
        repo
        / "geo"
        / "geoip"
    )

    if not source.exists():

        raise RuntimeError(
            "MetaCubeX/meta-rules-dat "
            "中没有找到 geo/geoip/"
        )

    for file in source.rglob("*"):

        if not file.is_file():
            continue

        copy_rule(
            file,
            GEOIP_DIR,
            [".mrs"],
        )


# ============================================================
# ④ X-Shelby
#
# latest release
#
# *.mrs
# *.srs
# ============================================================

def sync_cnip():

    print("\n")
    print("=" * 60)
    print("X-SHELBY CNIP")
    print("=" * 60)

    release_url = (
        f"{GITHUB_API}/repos/"
        f"X-Shelby/geoip/"
        f"releases/latest"
    )

    release = github_api(
        release_url
    )

    assets = release.get(
        "assets",
        [],
    )

    if not assets:

        raise RuntimeError(
            "X-Shelby/geoip "
            "latest release 没有 Assets"
        )

    for asset in assets:

        name = asset.get(
            "name",
            "",
        )

        if not should_keep(
            name,
            [
                ".mrs",
                ".srs",
            ],
        ):
            continue

        url = asset.get(
            "browser_download_url"
        )

        if not url:
            continue

        filename = normalize_filename(
            name
        )

        destination = (
            CNIP_DIR / filename
        )

        download(
            url,
            destination,
        )

        print(
            f"  {name}"
            f" -> "
            f"{destination.relative_to(ROOT)}"
        )


# ============================================================
# ⑤ 217heidai AdBlock
#
# rules/
#
# *.mrs
# *.srs
# ============================================================

def sync_adblock():

    print("\n")
    print("=" * 60)
    print("217HEIDAI ADBLOCK")
    print("=" * 60)

    repo = clone_repo(
        ADBLOCK_REPO,
        branch="main",
    )

    source = repo / "rules"

    if not source.exists():

        raise RuntimeError(
            "217heidai/adblockfilters "
            "中没有找到 rules/"
        )

    for file in source.rglob("*"):

        if not file.is_file():
            continue

        copy_rule(
            file,
            ADBLOCK_DIR,
            [
                ".mrs",
                ".srs",
            ],
        )


# ============================================================
# 最终验证
# ============================================================

def validate():

    print("\n")
    print("=" * 60)
    print("VALIDATE")
    print("=" * 60)

    expected = {
        MIHOMO_DIR: {
            ".mrs",
        },

        SINGBOX_DIR: {
            ".srs",
        },

        DUSTINWIN_DIR: {
            ".mrs",
            ".srs",
        },

        GEOIP_DIR: {
            ".mrs",
        },

        CNIP_DIR: {
            ".mrs",
            ".srs",
        },

        ADBLOCK_DIR: {
            ".mrs",
            ".srs",
        },
    }

    errors = []

    # --------------------------------------------
    # 检查目录
    # --------------------------------------------

    for directory in expected:

        if not directory.exists():

            errors.append(
                f"Missing directory: {directory}"
            )

    # --------------------------------------------
    # 检查文件
    # --------------------------------------------

    for directory, extensions in expected.items():

        if not directory.exists():
            continue

        for file in directory.rglob("*"):

            if not file.is_file():
                continue

            filename = file.name
            lower = filename.lower()

            # ----------------------------------------
            # MD
            # ----------------------------------------

            if lower.endswith(".md"):

                errors.append(
                    f"MD file: {file}"
                )

            # ----------------------------------------
            # classical
            # ----------------------------------------

            if "classical" in lower:

                errors.append(
                    f"classical file: {file}"
                )

            # ----------------------------------------
            # 扩展名
            # ----------------------------------------

            if file.suffix.lower() not in extensions:

                errors.append(
                    f"Invalid extension: {file}"
                )

            # ----------------------------------------
            # 文件名必须全部小写
            # ----------------------------------------

            if filename != lower:

                errors.append(
                    f"Uppercase filename: {file}"
                )

    # --------------------------------------------
    # 检查是否出现空目录
    # --------------------------------------------

    for directory in expected:

        if not directory.exists():
            continue

        files = [
            f
            for f in directory.rglob("*")
            if f.is_file()
        ]

        if not files:

            errors.append(
                f"Empty directory: {directory}"
            )

    # --------------------------------------------
    # 输出结果
    # --------------------------------------------

    if errors:

        print("\nValidation FAILED:\n")

        for error in errors:

            print(
                "ERROR:",
                error,
            )

        raise RuntimeError(
            "Rules validation failed."
        )

    print(
        "\nValidation PASSED."
    )


# ============================================================
# 统计
# ============================================================

def show_statistics():

    print("\n")
    print("=" * 60)
    print("STATISTICS")
    print("=" * 60)

    directories = [
        MIHOMO_DIR,
        SINGBOX_DIR,
        DUSTINWIN_DIR,
        GEOIP_DIR,
        CNIP_DIR,
        ADBLOCK_DIR,
    ]

    total = 0

    for directory in directories:

        count = sum(
            1
            for file in directory.rglob("*")
            if file.is_file()
        )

        total += count

        print(
            f"{directory.relative_to(ROOT)}: "
            f"{count}"
        )

    print(
        "-" * 60
    )

    print(
        f"Total: {total}"
    )


# ============================================================
# Main
# ============================================================

def main():

    print(
        "=" * 60
    )

    print(
        "       VERION RULES SYNCHRONIZER"
    )

    print(
        "=" * 60
    )

    # --------------------------------------------
    # 1. 删除旧规则
    # --------------------------------------------

    clean_rules()

    # --------------------------------------------
    # 2. milangree
    # --------------------------------------------

    sync_milangree()

    # --------------------------------------------
    # 3. DustinWin
    # --------------------------------------------

    sync_dustinwin()

    # --------------------------------------------
    # 4. MetaCubeX
    # --------------------------------------------

    sync_geoip()

    # --------------------------------------------
    # 5. X-Shelby
    # --------------------------------------------

    sync_cnip()

    # --------------------------------------------
    # 6. 217heidai
    # --------------------------------------------

    sync_adblock()

    # --------------------------------------------
    # 7. 验证
    # --------------------------------------------

    validate()

    # --------------------------------------------
    # 8. 统计
    # --------------------------------------------

    show_statistics()

    print("\n")
    print(
        "=" * 60
    )

    print(
        "             SYNC COMPLETED"
    )

    print(
        "=" * 60
    )


if __name__ == "__main__":
    main()
