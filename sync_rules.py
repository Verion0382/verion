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
    从 GitHub ZIP 中提取规则。

    特点：

    1. 不保留任何子目录
    2. 所有文件直接放到 target_dir
    3. 文件名全部小写
    4. 只保存指定扩展名
    """

    clean_dir(target_dir)

    count = 0

    for info in zip_file.infolist():

        if info.is_dir():
            continue

        original_path = Path(info.filename)

        # GitHub ZIP 第一层通常是：
        #
        # repository-main/
        #
        # 去掉第一层
        if len(original_path.parts) < 2:
            continue

        relative_path = Path(
            *original_path.parts[1:]
        )

        # --------------------------------------------------------
        # 限制源目录
        # --------------------------------------------------------

        if source_prefix:

            prefix = Path(source_prefix)

            try:

                relative_path = (
                    relative_path.relative_to(prefix)
                )

            except ValueError:

                continue

        # --------------------------------------------------------
        # 扩展名过滤
        # --------------------------------------------------------

        if extensions:

            suffix = relative_path.suffix.lower()

            if suffix not in extensions:
                continue

        # --------------------------------------------------------
        # 不保留子目录
        # 文件名全部小写
        # --------------------------------------------------------

        filename = relative_path.name.lower()

        output = target_dir / filename

        # --------------------------------------------------------
        # 写入
        # --------------------------------------------------------

        print(
            f"  {relative_path} "
            f"-> {output}"
        )

        output.parent.mkdir(
            parents=True,
            exist_ok=True
        )

        with zip_file.open(info) as source:

            with open(output, "wb") as destination:

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
    """同步 GitHub 仓库"""

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


# ============================================================
# 1. Milangree Mihomo
#
# https://github.com/milangree/rules
#
# rules/mihomo/
#
# 只保存 .mrs
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

    target_dir=ROOT / "Mihomo",

    source_prefix="rules/mihomo",

    extensions={".mrs"}
)


# ============================================================
# 2. Milangree SingBox
#
# https://github.com/milangree/rules
#
# rules/singbox/
#
# 只保存 .srs
#
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

    target_dir=ROOT / "SingBox",

    source_prefix="rules/singbox",

    extensions={".srs"}
)


# ============================================================
# 3. DustinWin
#
# https://github.com/DustinWin/ruleset_geodata
#
# mihomo-ruleset 分支
#
# 只保存 .mrs
#
# 不保留子目录
# ============================================================

print()
print("#" * 70)
print("# 3. DustinWin")
print("#" * 70)

sync_repository(
    url=(
        "https://github.com/"
        "DustinWin/ruleset_geodata/"
        "archive/refs/heads/mihomo-ruleset.zip"
    ),

    target_dir=ROOT / "DustinWin",

    extensions={".mrs"}
)


# ============================================================
# 4. MetaCubeX GeoIP
#
# https://github.com/MetaCubeX/meta-rules-dat
#
# meta 分支
#
# geo/geoip/
#
# 只保存 .mrs
#
# 不保留子目录
# ============================================================

print()
print("#" * 70)
print("# 4. MetaCubeX GeoIP")
print("#" * 70)

sync_repository(
    url=(
        "https://github.com/"
        "MetaCubeX/meta-rules-dat/"
        "archive/refs/heads/meta.zip"
    ),

    target_dir=ROOT / "geoip",

    source_prefix="geo/geoip",

    extensions={".mrs"}
)


# ============================================================
# 5. X-Shelby CNIP
#
# https://github.com/X-Shelby/geoip/releases/tag/latest
#
# Mihomo MRS:
#
# cn.mrs
# cn_v4.mrs
# cn_v6.mrs
# cnip_all.mrs
#
# SingBox SRS:
#
# cn.srs
# cn_v4.srs
# cn_v6.srs
# cnip_all.srs
#
# MRS -> rules/cnip/
# SRS -> rules/SingBox/
#
# 不使用 GitHub API
# 直接使用 Release 固定下载地址
# ============================================================

print()
print("#" * 70)
print("# 5. X-Shelby CNIP")
print("#" * 70)


X_SHELBY_RELEASE = (
    "https://github.com/"
    "X-Shelby/geoip/"
    "releases/download/latest/"
)


CNIP_MRS = [
    "cn.mrs",
    "cn_v4.mrs",
    "cn_v6.mrs",
    "cnip_all.mrs",
]


CNIP_SRS = [
    "cn.srs",
    "cn_v4.srs",
    "cn_v6.srs",
    "cnip_all.srs",
]


# ------------------------------------------------------------
# CNIP MRS
# ------------------------------------------------------------

cnip_dir = ROOT / "cnip"

clean_dir(cnip_dir)


for filename in CNIP_MRS:

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


# ------------------------------------------------------------
# CNIP SRS
#
# 放入 SingBox
# ------------------------------------------------------------

singbox_dir = ROOT / "SingBox"

singbox_dir.mkdir(
    parents=True,
    exist_ok=True
)


for filename in CNIP_SRS:

    url = (
        X_SHELBY_RELEASE +
        filename
    )

    output = (
        singbox_dir /
        filename.lower()
    )

    download_file(
        url,
        output
    )


# ============================================================
# 6. 217heidai AdBlock
#
# https://github.com/217heidai/adblockfilters
#
# 只保存 .mrs
#
# 不保留子目录
# ============================================================

print()
print("#" * 70)
print("# 6. 217heidai AdBlock")
print("#" * 70)

sync_repository(
    url=(
        "https://github.com/"
        "217heidai/adblockfilters/"
        "archive/refs/heads/main.zip"
    ),

    target_dir=ROOT / "AdBlock",

    extensions={".mrs"}
)


# ============================================================
# 7. 删除空目录
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
# 8. 检查最终目录
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

        relative = path.relative_to(ROOT)

        # rules/下面第一层目录允许
        if len(relative.parts) == 1:

            if relative.name not in allowed_directories:

                unexpected_directories.append(
                    str(path)
                )

        # 不允许第二层及以上目录
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
# 9. 检查文件名
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

        if path.name != path.name.lower():

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
# 10. 检查文件扩展名
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

        suffix = path.suffix.lower()

        # ----------------------------------------------------
        # Mihomo
        # ----------------------------------------------------

        if "Mihomo" in path.parts:

            if suffix != ".mrs":

                invalid_files.append(
                    str(path)
                )


        # ----------------------------------------------------
        # SingBox
        # ----------------------------------------------------

        elif "SingBox" in path.parts:

            if suffix != ".srs":

                invalid_files.append(
                    str(path)
                )


        # ----------------------------------------------------
        # 其他目录
        # ----------------------------------------------------

        else:

            if suffix != ".mrs":

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
# 11. 检查 CNIP 必须存在的文件
# ============================================================

print()
print("=" * 70)
print("CHECK CNIP FILES")
print("=" * 70)


required_mrs = {
    "cn.mrs",
    "cn_v4.mrs",
    "cn_v6.mrs",
    "cnip_all.mrs",
}


required_srs = {
    "cn.srs",
    "cn_v4.srs",
    "cn_v6.srs",
    "cnip_all.srs",
}


actual_mrs = {
    path.name
    for path in (ROOT / "cnip").glob("*.mrs")
}


actual_srs = {
    path.name
    for path in (ROOT / "SingBox").glob("*.srs")
}


missing_mrs = (
    required_mrs -
    actual_mrs
)


missing_srs = (
    required_srs -
    actual_srs
)


if missing_mrs:

    print(
        "Missing CNIP MRS:"
    )

    for filename in sorted(missing_mrs):

        print(
            f"  {filename}"
        )

    raise RuntimeError(
        "CNIP MRS files are incomplete."
    )


if missing_srs:

    print(
        "Missing CNIP SRS:"
    )

    for filename in sorted(missing_srs):

        print(
            f"  {filename}"
        )

    raise RuntimeError(
        "CNIP SRS files are incomplete."
    )


print(
    "OK: CNIP MRS/SRS complete."
)


# ============================================================
# 12. 输出最终目录
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
# 13. 分类统计
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
            for path in directory.iterdir()
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
