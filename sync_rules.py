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

    path.mkdir(parents=True, exist_ok=True)


def download_zip(url: str):
    """下载 GitHub ZIP"""

    print()
    print("=" * 70)
    print("DOWNLOAD")
    print(url)
    print("=" * 70)

    response = session.get(
        url,
        timeout=300,
        allow_redirects=True
    )

    response.raise_for_status()

    size = len(response.content) / 1024 / 1024

    print(f"Downloaded: {size:.2f} MB")

    return zipfile.ZipFile(
        io.BytesIO(response.content)
    )


def extract_rules(
    zip_file,
    target_dir: Path,
    source_prefix=None,
    extensions=None,
    flatten=False
):
    """
    从 GitHub ZIP 中提取指定规则。

    source_prefix:
        指定 ZIP 内的目录，例如：
        rules/mihomo

    extensions:
        例如：
        {".mrs"}
        {".srs"}

    flatten:
        True  -> 所有文件放到同一目录
        False -> 保留原来的目录结构
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
        # 去掉这一层
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
                relative_path = relative_path.relative_to(prefix)

            except ValueError:
                continue

        # --------------------------------------------------------
        # 文件扩展名过滤
        # --------------------------------------------------------

        if extensions:

            suffix = relative_path.suffix.lower()

            if suffix not in extensions:
                continue

        # --------------------------------------------------------
        # 输出路径
        # --------------------------------------------------------

        if flatten:

            output = (
                target_dir /
                relative_path.name
            )

        else:

            output = (
                target_dir /
                relative_path
            )

        output.parent.mkdir(
            parents=True,
            exist_ok=True
        )

        print(
            f"  {relative_path} "
            f"-> {output}"
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
    extensions=None,
    flatten=False
):
    """同步一个 GitHub 仓库"""

    zip_file = download_zip(url)

    try:

        return extract_rules(
            zip_file=zip_file,
            target_dir=target_dir,
            source_prefix=source_prefix,
            extensions=extensions,
            flatten=flatten
        )

    finally:

        zip_file.close()


# ============================================================
# 1. Milangree Mihomo
#
# https://github.com/milangree/rules
#
# 源：
#
# rules/mihomo/
#
# 只保存 .mrs
#
# 目标：
#
# rules/Mihomo/
# ├── Claude/
# │   └── *.mrs
# ├── Google/
# │   └── *.mrs
# └── ...
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

    extensions={".mrs"},

    flatten=False
)


# ============================================================
# 2. Milangree SingBox
#
# https://github.com/milangree/rules
#
# 源：
#
# rules/singbox/
#
# 只保存 .srs
#
# 目标：
#
# rules/SingBox/
# ├── Claude/
# │   └── *.srs
# ├── Google/
# │   └── *.srs
# └── ...
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

    extensions={".srs"},

    flatten=False
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
# 目标：
#
# rules/DustinWin/
# └── *.mrs
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

    extensions={".mrs"},

    flatten=True
)


# ============================================================
# 4. MetaCubeX GeoIP
#
# https://github.com/MetaCubeX/meta-rules-dat
#
# meta 分支
#
# 源：
#
# geo/geoip/
#
# 只保存 .mrs
#
# 目标：
#
# rules/geoip/
# └── *.mrs
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

    extensions={".mrs"},

    flatten=False
)


# ============================================================
# 5. X-Shelby CNIP
#
# 目标：
#
# rules/cnip/
# ├── cn.mrs
# ├── cn_v4.mrs
# ├── cn_v6.mrs
# └── cnip_all.mrs
#
# 注意：
# 如果 X-Shelby 仓库实际名称/分支不同，
# 只修改下面的 URL。
# ============================================================

print()
print("#" * 70)
print("# 5. X-Shelby CNIP")
print("#" * 70)

try:

    sync_repository(
        url=(
            "https://github.com/"
            "X-Shelby/cnip/"
            "archive/refs/heads/main.zip"
        ),

        target_dir=ROOT / "cnip",

        extensions={".mrs"},

        flatten=True
    )

except Exception as error:

    print()
    print("WARNING: X-Shelby CNIP failed")
    print(error)
    print()
    print("Continue with other rule sources...")


# ============================================================
# 6. 217heidai AdBlock
#
# https://github.com/217heidai/adblockfilters
#
# 只保存 .mrs
#
# 目标：
#
# rules/AdBlock/
# ├── *.mrs
# └── ...
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

    extensions={".mrs"},

    flatten=True
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
print("FINAL RULE DIRECTORY")
print("=" * 70)

total = 0

if ROOT.exists():

    for path in sorted(ROOT.rglob("*")):

        if path.is_file():

            print(path)

            total += 1


# ============================================================
# 9. 检查文件类型
# ============================================================

print()
print("=" * 70)
print("FILE TYPE CHECK")
print("=" * 70)

invalid = []

for path in ROOT.rglob("*"):

    if not path.is_file():
        continue

    parent = path.parent.name
    suffix = path.suffix.lower()

    # Mihomo 只能有 MRS
    if "Mihomo" in path.parts:

        if suffix != ".mrs":
            invalid.append(str(path))

    # SingBox 只能有 SRS
    elif "SingBox" in path.parts:

        if suffix != ".srs":
            invalid.append(str(path))

    # 其他目录只能有 MRS
    else:

        if suffix != ".mrs":
            invalid.append(str(path))


if invalid:

    print("INVALID FILES:")

    for item in invalid:
        print(item)

    raise RuntimeError(
        "Invalid rule files detected."
    )

else:

    print("All rule files are valid.")


# ============================================================
# 10. 最终统计
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

    if not directory.exists():
        count = 0

    else:
        count = sum(
            1
            for path in directory.rglob("*")
            if path.is_file()
        )

    print(
        f"{str(directory):25} {count:5} files"
    )


print()
print("=" * 70)
print(f"TOTAL FILES: {total}")
print("SYNC ALL RULES FINISHED")
print("=" * 70)
