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
# 基础工具
# ============================================================

def clean_dir(path: Path):
    """清空目录并重新创建"""

    if path.exists():
        shutil.rmtree(path)

    path.mkdir(
        parents=True,
        exist_ok=True
    )


def ensure_dir(path: Path):
    """确保目录存在"""

    path.mkdir(
        parents=True,
        exist_ok=True
    )


def download_file(
    url: str,
    output: Path
):
    """下载文件"""

    print()
    print(f"DOWNLOAD: {url}")

    response = session.get(
        url,
        timeout=300,
        allow_redirects=True
    )

    response.raise_for_status()

    ensure_dir(
        output.parent
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
        io.BytesIO(
            response.content
        )
    )


# ============================================================
# 通用 ZIP 同步
# ============================================================

def extract_rules(
    zip_file,
    target_dir: Path,
    source_prefix=None,
    extensions=None,
    clean=True
):
    """
    从 ZIP 中提取规则。

    特性：

    1. 不保留子目录
    2. 文件名全部小写
    3. 只保存指定扩展名
    4. 支持指定源目录
    """

    if clean:
        clean_dir(target_dir)
    else:
        ensure_dir(target_dir)

    count = 0

    for info in zip_file.infolist():

        if info.is_dir():
            continue

        original_path = Path(
            info.filename
        )

        # GitHub ZIP 第一层通常是：
        #
        # repository-branch/
        #
        # 去掉第一层

        if len(
            original_path.parts
        ) < 2:
            continue

        relative_path = Path(
            *original_path.parts[1:]
        )

        # ----------------------------------------------------
        # 限制源目录
        # ----------------------------------------------------

        if source_prefix:

            prefix = Path(
                source_prefix
            )

            try:

                relative_path = (
                    relative_path
                    .relative_to(prefix)
                )

            except ValueError:

                continue

        # ----------------------------------------------------
        # 扩展名过滤
        # ----------------------------------------------------

        if extensions:

            suffix = (
                relative_path
                .suffix
                .lower()
            )

            if suffix not in extensions:
                continue

        # ----------------------------------------------------
        # 只保留文件名
        # 不保留子目录
        # ----------------------------------------------------

        filename = (
            relative_path.name
            .lower()
        )

        output = (
            target_dir /
            filename
        )

        print(
            f"  {relative_path}"
            f" -> {filename}"
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
        f"SYNC DONE: "
        f"{target_dir} "
        f"({count} files)"
    )

    return count


def sync_repository(
    url,
    target_dir,
    source_prefix=None,
    extensions=None,
    clean=True
):
    """同步 GitHub ZIP"""

    zip_file = download_zip(url)

    try:

        return extract_rules(

            zip_file=zip_file,

            target_dir=target_dir,

            source_prefix=source_prefix,

            extensions=extensions,

            clean=clean

        )

    finally:

        zip_file.close()


# ============================================================
# 1. Milangree Mihomo
#
# https://github.com/milangree/rules/tree/main/rules/mihomo
#
# 只同步 .mrs
#
# 文件名全部小写
#
# 例如：
#
# YouTube.mrs
#     ↓
# youtube.mrs
#
# YouTube_IP.mrs
#     ↓
# youtube_ip.mrs
#
# 不保留子目录
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
    },

    clean=True

)


# ============================================================
# 2. Milangree SingBox
#
# rules/singbox/
#
# 只同步 .srs
# 文件名全部小写
# 不保留子目录
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
    },

    clean=True

)


# ============================================================
# GitHub Release API
# ============================================================

def get_release_assets(
    owner,
    repo,
    tag
):
    """获取 Release Assets"""

    api_url = (
        f"https://api.github.com/repos/"
        f"{owner}/{repo}/releases/tags/{tag}"
    )

    print()
    print(
        f"GET RELEASE: "
        f"{owner}/{repo}:{tag}"
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
        f"Release assets: "
        f"{len(assets)}"
    )

    return assets


def sync_release_assets(
    owner,
    repo,
    tag,
    target_dir,
    extension,
    clean=True
):
    """
    同步 Release 中指定扩展名。

    clean=True：
        清空目标目录

    clean=False：
        保留已有文件
    """

    if clean:
        clean_dir(target_dir)
    else:
        ensure_dir(target_dir)

    assets = get_release_assets(
        owner,
        repo,
        tag
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

            selected.append(
                asset
            )

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

        url = (
            asset[
                "browser_download_url"
            ]
        )

        # 文件名全部小写

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
# 3. DustinWin Mihomo
#
# mihomo-ruleset 分支
#
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
    },

    clean=True

)


# ============================================================
# 4. DustinWin SingBox
#
# Release：
#
# sing-box-ruleset-compatible
#
# *.srs
#
# 重要：
#
# clean=False
#
# 防止删除 DustinWin 的 .mrs
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

    extension=".srs",

    clean=False

)


# ============================================================
# 5. MetaCubeX GeoIP
#
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
        "archive/refs/heads/meta.zip"
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
    },

    clean=True

)


# ============================================================
# 6. X-Shelby CNIP
#
# MRS + SRS
#
# 文件名全部小写
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
    "X-Shelby CNIP MRS/SRS "
    "sync finished."
)


# ============================================================
# 7. 217heidai AdBlock
#
# MRS + SRS
#
# 文件名全部小写
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
    },

    clean=True

)


# ============================================================
# 8. 删除空目录
# ============================================================

print()
print("#" * 70)
print("# 8. CLEAN EMPTY DIRECTORIES")
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


ALLOWED_DIRECTORIES = {

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

        # rules/下面只允许一级目录

        if len(
            relative.parts
        ) == 1:

            if (
                relative.name
                not in ALLOWED_DIRECTORIES
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
# 10. 检查文件名全部小写
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
# 11. 检查扩展名
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


        if "Mihomo" in path.parts:

            allowed = {
                ".mrs"
            }


        elif "SingBox" in path.parts:

            allowed = {
                ".srs"
            }


        elif "DustinWin" in path.parts:

            allowed = {
                ".mrs",
                ".srs"
            }


        elif "geoip" in path.parts:

            allowed = {
                ".mrs"
            }


        elif "cnip" in path.parts:

            allowed = {
                ".mrs",
                ".srs"
            }


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
        "OK: All file extensions "
        "are valid."
    )


# ============================================================
# 12. 检查 CNIP
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

    for path
    in cnip_dir.iterdir()

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
# 13. 检查规则目录
# ============================================================

print()
print("=" * 70)
print("CHECK RULE DIRECTORIES")
print("=" * 70)


for directory_name in sorted(
    ALLOWED_DIRECTORIES
):

    directory = (
        ROOT /
        directory_name
    )

    if not directory.exists():

        raise RuntimeError(
            f"Missing directory: "
            f"{directory}"
        )

    files = [

        path

        for path
        in directory.iterdir()

        if path.is_file()

    ]

    print(
        f"{directory_name:15} "
        f"{len(files):5} files"
    )

    if not files:

        raise RuntimeError(
            f"Empty rule directory: "
            f"{directory}"
        )


# ============================================================
# 14. 最终统计
# ============================================================

print()
print("=" * 70)
print("FINAL STATISTICS")
print("=" * 70)


total = 0


for directory_name in [

    "Mihomo",
    "SingBox",
    "DustinWin",
    "geoip",
    "cnip",
    "AdBlock"

]:

    directory = (
        ROOT /
        directory_name
    )

    mrs_count = 0
    srs_count = 0


    if directory.exists():

        for path in directory.iterdir():

            if not path.is_file():
                continue

            suffix = (
                path.suffix
                .lower()
            )

            if suffix == ".mrs":

                mrs_count += 1

            elif suffix == ".srs":

                srs_count += 1


    total += (
        mrs_count +
        srs_count
    )


    print(
        f"{directory_name:15} "
        f"MRS={mrs_count:4} "
        f"SRS={srs_count:4}"
    )


print()
print(
    f"TOTAL FILES: {total}"
)

print()
print(
    "SYNC ALL RULES FINISHED"
)

print("=" * 70)
