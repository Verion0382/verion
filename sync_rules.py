import io
import shutil
import zipfile
import requests
from pathlib import Path


# ============================================================
# 基础配置
# ============================================================

ROOT = Path("rules")

HEADERS = {
    "User-Agent": "Mozilla/5.0 GitHub-Actions-Rules-Sync"
}

session = requests.Session()
session.headers.update(HEADERS)


# ============================================================
# 工具函数
# ============================================================

def clean_dir(path: Path):
    """删除并重新创建目录"""

    if path.exists():
        shutil.rmtree(path)

    path.mkdir(
        parents=True,
        exist_ok=True
    )


def download_file(url: str, output: Path):
    """下载单个文件"""

    print()
    print(f"DOWNLOAD: {url}")

    response = session.get(
        url,
        timeout=300,
        allow_redirects=True
    )

    response.raise_for_status()

    output.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    output.write_bytes(
        response.content
    )

    print(
        f"OK: {output} "
        f"({len(response.content) / 1024:.1f} KB)"
    )


def download_zip(url: str):
    """下载 GitHub ZIP"""

    print()
    print("=" * 70)
    print("DOWNLOAD ZIP")
    print(url)
    print("=" * 70)

    response = session.get(
        url,
        timeout=300,
        allow_redirects=True
    )

    response.raise_for_status()

    print(
        f"Downloaded: "
        f"{len(response.content) / 1024 / 1024:.2f} MB"
    )

    return zipfile.ZipFile(
        io.BytesIO(response.content)
    )


def extract_rules(
    zip_file,
    target_dir: Path,
    source_prefix=None,
    extensions=None
):
    """
    从 GitHub ZIP 提取规则。

    特点：

    1. 不保留任何子目录
    2. 文件全部直接放入 target_dir
    3. 文件名全部小写
    4. 只保存指定扩展名
    """

    clean_dir(target_dir)

    count = 0

    for info in zip_file.infolist():

        if info.is_dir():
            continue

        original_path = Path(info.filename)

        # 去掉 GitHub ZIP 第一层目录
        if len(original_path.parts) < 2:
            continue

        relative_path = Path(
            *original_path.parts[1:]
        )

        # ----------------------------------------------------
        # 限制源目录
        # ----------------------------------------------------

        if source_prefix:

            prefix = Path(source_prefix)

            try:

                relative_path = (
                    relative_path.relative_to(prefix)
                )

            except ValueError:

                continue

        # ----------------------------------------------------
        # 扩展名过滤
        # ----------------------------------------------------

        if extensions:

            suffix = (
                relative_path.suffix.lower()
            )

            if suffix not in extensions:
                continue

        # ----------------------------------------------------
        # 不保留子目录
        # 文件名全部小写
        # ----------------------------------------------------

        filename = (
            relative_path.name.lower()
        )

        output = target_dir / filename

        if output.exists():

            print(
                f"WARNING: duplicate filename: "
                f"{filename}"
            )

        print(
            f"  {relative_path} "
            f"-> {output}"
        )

        with zip_file.open(info) as source:

            with open(
                output,
                "wb"
            ) as destination:

                shutil.copyfileobj(
                    source,
                    destination
                )

        count += 1

    print()
    print(
        f"SYNC DONE: {target_dir} "
        f"({count} files)"
    )

    return count


def sync_repository(
    url,
    target_dir,
    source_prefix=None,
    extensions=None
):
    """同步 GitHub ZIP 仓库"""

    zip_file = download_zip(url)

    try:

        return extract_rules(
            zip_file=zip_file,
            target_dir=target_dir,
            source_prefix=source_prefix,
            extensions=extensions
        )

    finally:

        zip_file.close()


def get_release_assets(
    owner,
    repo,
    tag
):
    """
    获取 GitHub Release Assets。

    这里只调用 Releases API，
    不使用 Contents API，
    避免递归读取仓库导致 429。
    """

    api_url = (
        f"https://api.github.com/repos/"
        f"{owner}/{repo}/releases/tags/{tag}"
    )

    print()
    print(
        f"GET RELEASE: {owner}/{repo}"
    )

    response = session.get(
        api_url,
        timeout=120
    )

    response.raise_for_status()

    release = response.json()

    assets = release.get(
        "assets",
        []
    )

    print(
        f"Release assets: {len(assets)}"
    )

    return assets


def sync_release_assets(
    owner,
    repo,
    tag,
    target_dir,
    extension
):
    """
    同步 Release 中指定扩展名的全部 Assets。

    文件直接放入 target_dir。
    不保留任何子目录。
    文件名全部小写。
    """

    clean_dir(target_dir)

    assets = get_release_assets(
        owner=owner,
        repo=repo,
        tag=tag
    )

    selected = []

    for asset in assets:

        name = asset.get(
            "name",
            ""
        )

        if name.lower().endswith(
            extension.lower()
        ):

            selected.append(asset)

    print()
    print(
        f"Selected {extension} assets: "
        f"{len(selected)}"
    )

    if not selected:

        raise RuntimeError(
            f"No {extension} assets found "
            f"in {owner}/{repo}:{tag}"
        )

    count = 0

    for asset in selected:

        name = asset["name"]

        url = asset["browser_download_url"]

        output = (
            target_dir /
            name.lower()
        )

        download_file(
            url,
            output
        )

        count += 1

    print()
    print(
        f"RELEASE SYNC DONE: "
        f"{target_dir} "
        f"({count} files)"
    )

    return count


# ============================================================
# 1. Milangree Mihomo
#
# rules/mihomo/
# *.mrs
# ============================================================

print()
print("#" * 70)
print("# 1. Milangree Mihomo")
print("#" * 70)


sync_repository(

    url=(
        "https://github.com/"
        "milangree/rules/"
        "archive/refs/heads/main.zip"
    ),

    target_dir=(
        ROOT /
        "Mihomo"
    ),

    source_prefix=(
        "rules/mihomo"
    ),

    extensions={
        ".mrs"
    }
)


# ============================================================
# 2. Milangree SingBox
#
# rules/singbox/
# *.srs
# ============================================================

print()
print("#" * 70)
print("# 2. Milangree SingBox")
print("#" * 70)


sync_repository(

    url=(
        "https://github.com/"
        "milangree/rules/"
        "archive/refs/heads/main.zip"
    ),

    target_dir=(
        ROOT /
        "SingBox"
    ),

    source_prefix=(
        "rules/singbox"
    ),

    extensions={
        ".srs"
    }
)


# ============================================================
# 3. DustinWin Mihomo
#
# mihomo-ruleset 分支
# *.mrs
# ============================================================

print()
print("#" * 70)
print("# 3. DustinWin Mihomo")
print("#" * 70)


sync_repository(

    url=(
        "https://github.com/"
        "DustinWin/ruleset_geodata/"
        "archive/refs/heads/"
        "mihomo-ruleset.zip"
    ),

    target_dir=(
        ROOT /
        "DustinWin"
    ),

    extensions={
        ".mrs"
    }
)


# ============================================================
# 4. DustinWin SingBox
#
# Release:
#
# https://github.com/DustinWin/ruleset_geodata/releases/tag/sing-box-ruleset-compatible
#
# 自动获取该 Release 下全部 .srs Assets
# ============================================================

print()
print("#" * 70)
print("# 4. DustinWin SingBox")
print("#" * 70)


sync_release_assets(

    owner="DustinWin",

    repo="ruleset_geodata",

    tag="sing-box-ruleset-compatible",

    target_dir=(
        ROOT /
        "DustinWin"
    ),

    extension=".srs"
)


# ============================================================
# 5. MetaCubeX GeoIP
#
# geo/geoip/
# *.mrs
# ============================================================

print()
print("#" * 70)
print("# 5. MetaCubeX GeoIP")
print("#" * 70)


sync_repository(

    url=(
        "https://github.com/"
        "MetaCubeX/meta-rules-dat/"
        "archive/refs/heads/"
        "meta.zip"
    ),

    target_dir=(
        ROOT /
        "geoip"
    ),

    source_prefix=(
        "geo/geoip"
    ),

    extensions={
        ".mrs"
    }
)


# ============================================================
# 6. X-Shelby CNIP
#
# Release:
#
# https://github.com/X-Shelby/geoip/releases/tag/latest
#
# 直接下载：
#
# cn.mrs
# cn_v4.mrs
# cn_v6.mrs
# cnip_all.mrs
#
# cn.srs
# cn_v4.srs
# cn_v6.srs
# cnip_all.srs
#
# 全部放入 rules/cnip/
# ============================================================

print()
print("#" * 70)
print("# 6. X-Shelby CNIP")
print("#" * 70)


X_SHELBY_RELEASE = (
    "https://github.com/"
    "X-Shelby/geoip/"
    "releases/download/latest/"
)


CNIP_FILES = [

    "cn.mrs",
    "cn_v4.mrs",
    "cn_v6.mrs",
    "cnip_all.mrs",

    "cn.srs",
    "cn_v4.srs",
    "cn_v6.srs",
    "cnip_all.srs",

]


cnip_dir = (
    ROOT /
    "cnip"
)


clean_dir(
    cnip_dir
)


for filename in CNIP_FILES:

    url = (
        X_SHELBY_RELEASE +
        filename
    )

    output = (
        cnip_dir /
        filename.lower()
    )

    download_file(
        url,
        output
    )


print()
print(
    "X-Shelby CNIP MRS/SRS sync finished."
)


# ============================================================
# 7. 217heidai AdBlock
#
# *.mrs + *.srs
# ============================================================

print()
print("#" * 70)
print("# 7. 217heidai AdBlock")
print("#" * 70)


sync_repository(

    url=(
        "https://github.com/"
        "217heidai/adblockfilters/"
        "archive/refs/heads/main.zip"
    ),

    target_dir=(
        ROOT /
        "AdBlock"
    ),

    extensions={
        ".mrs",
        ".srs"
    }
)


# ============================================================
# 8. 删除空目录
# ============================================================

print()
print("#" * 70)
print("# CLEAN EMPTY DIRECTORIES")
print("#" * 70)


if ROOT.exists():

    for path in sorted(
        ROOT.rglob("*"),
        reverse=True
    ):

        if path.is_dir():

            try:

                path.rmdir()

            except OSError:

                pass


# ============================================================
# 9. 检查目录结构
# ============================================================

print()
print("=" * 70)
print("CHECK DIRECTORY STRUCTURE")
print("=" * 70)


allowed_directories = {

    "Mihomo",
    "SingBox",
    "DustinWin",
    "geoip",
    "cnip",
    "AdBlock",

}


unexpected_directories = []


if ROOT.exists():

    for path in ROOT.rglob("*"):

        if not path.is_dir():
            continue

        relative = (
            path.relative_to(ROOT)
        )

        # 只允许 rules/ 下一级目录
        if len(relative.parts) == 1:

            if (
                relative.name
                not in allowed_directories
            ):

                unexpected_directories.append(
                    str(path)
                )

        else:

            unexpected_directories.append(
                str(path)
            )


if unexpected_directories:

    print(
        "ERROR: Unexpected directories:"
    )

    for path in unexpected_directories:

        print(
            f"  {path}"
        )

    raise RuntimeError(
        "Unexpected subdirectories detected."
    )

else:

    print(
        "OK: No rule subdirectories."
    )


# ============================================================
# 10. 检查文件名
# ============================================================

print()
print("=" * 70)
print("CHECK LOWERCASE FILENAMES")
print("=" * 70)


uppercase_files = []


if ROOT.exists():

    for path in ROOT.rglob("*"):

        if not path.is_file():
            continue

        if (
            path.name
            != path.name.lower()
        ):

            uppercase_files.append(
                str(path)
            )


if uppercase_files:

    print(
        "ERROR: Uppercase filenames:"
    )

    for path in uppercase_files:

        print(
            f"  {path}"
        )

    raise RuntimeError(
        "Uppercase filenames detected."
    )

else:

    print(
        "OK: All filenames are lowercase."
    )


# ============================================================
# 11. 检查文件类型
#
# Mihomo:
#   .mrs
#
# SingBox:
#   .srs
#
# DustinWin:
#   .mrs + .srs
#
# geoip:
#   .mrs
#
# cnip:
#   .mrs + .srs
#
# AdBlock:
#   .mrs + .srs
# ============================================================

print()
print("=" * 70)
print("CHECK FILE EXTENSIONS")
print("=" * 70)


invalid_files = []


if ROOT.exists():

    for path in ROOT.rglob("*"):

        if not path.is_file():
            continue

        suffix = (
            path.suffix
            .lower()
        )


        # ----------------------------------------------------
        # Mihomo
        # ----------------------------------------------------

        if "Mihomo" in path.parts:

            allowed = {
                ".mrs"
            }


        # ----------------------------------------------------
        # SingBox
        # ----------------------------------------------------

        elif "SingBox" in path.parts:

            allowed = {
                ".srs"
            }


        # ----------------------------------------------------
        # DustinWin
        # ----------------------------------------------------

        elif "DustinWin" in path.parts:

            allowed = {
                ".mrs",
                ".srs"
            }


        # ----------------------------------------------------
        # geoip
        # ----------------------------------------------------

        elif "geoip" in path.parts:

            allowed = {
                ".mrs"
            }


        # ----------------------------------------------------
        # cnip
        # ----------------------------------------------------

        elif "cnip" in path.parts:

            allowed = {
                ".mrs",
                ".srs"
            }


        # ----------------------------------------------------
        # AdBlock
        # ----------------------------------------------------

        elif "AdBlock" in path.parts:

            allowed = {
                ".mrs",
                ".srs"
            }


        else:

            allowed = set()


        if suffix not in allowed:

            invalid_files.append(
                str(path)
            )


if invalid_files:

    print(
        "ERROR: Invalid files:"
    )

    for path in invalid_files:

        print(
            f"  {path}"
        )

    raise RuntimeError(
        "Invalid rule file extension detected."
    )

else:

    print(
        "OK: All file extensions are valid."
    )


# ============================================================
# 12. 检查 CNIP 8 个文件
# ============================================================

print()
print("=" * 70)
print("CHECK CNIP FILES")
print("=" * 70)


required_cnip = {

    "cn.mrs",
    "cn_v4.mrs",
    "cn_v6.mrs",
    "cnip_all.mrs",

    "cn.srs",
    "cn_v4.srs",
    "cn_v6.srs",
    "cnip_all.srs",

}


cnip_dir = (
    ROOT /
    "cnip"
)


if not cnip_dir.exists():

    raise RuntimeError(
        "CNIP directory does not exist."
    )


actual_cnip = {

    path.name.lower()

    for path in cnip_dir.iterdir()

    if path.is_file()

}


missing_cnip = (
    required_cnip -
    actual_cnip
)


if missing_cnip:

    print(
        "ERROR: Missing CNIP files:"
    )

    for filename in sorted(
        missing_cnip
    ):

        print(
            f"  {filename}"
        )

    raise RuntimeError(
        "CNIP MRS/SRS files are incomplete."
    )


print(
    "OK: All 8 CNIP files exist."
)


# ============================================================
# 13. 输出最终文件
# ============================================================

print()
print("=" * 70)
print("FINAL RULE DIRECTORY")
print("=" * 70)


total = 0


if ROOT.exists():

    for path in sorted(
        ROOT.rglob("*")
    ):

        if path.is_file():

            print(
                path
            )

            total += 1


# ============================================================
# 14. 分类统计
# ============================================================

print()
print("=" * 70)
print("RULE STATISTICS")
print("=" * 70)


directories = [

    ROOT / "Mihomo",
    ROOT / "SingBox",
    ROOT / "DustinWin",
    ROOT / "geoip",
    ROOT / "cnip",
    ROOT / "AdBlock",

]


for directory in directories:

    if directory.exists():

        count = sum(

            1

            for path
            in directory.iterdir()

            if path.is_file()

        )

    else:

        count = 0


    print(
        f"{str(directory):25} "
        f"{count:5} files"
    )


# ============================================================
# 完成
# ============================================================

print()
print("=" * 70)
print(
    f"TOTAL FILES: {total}"
)
print(
    "SYNC ALL RULES FINISHED"
)
print("=" * 70)
