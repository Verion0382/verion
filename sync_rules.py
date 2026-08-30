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
    2. 所有文件直接放入 target_dir
    3. 文件名全部转换为小写
    4. 只保留指定扩展名
    """

    clean_dir(target_dir)

    count = 0
    names = {}

    for info in zip_file.infolist():

        if info.is_dir():
            continue

        original_path = Path(info.filename)

        # GitHub ZIP 第一层：
        #
        # repository-main/
        #
        # 去掉第一层目录
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
        # 只使用文件名
        #
        # 不保留任何子目录
        # --------------------------------------------------------

        filename = relative_path.name.lower()

        # --------------------------------------------------------
        # 防止大小写转换后出现重名
        #
        # 例如：
        #
        # Google.mrs
        # google.mrs
        #
        # 转换后都会变成：
        #
        # google.mrs
        #
        # 如果发生冲突，保留最后一个文件。
        # --------------------------------------------------------

        if filename in names:

            print(
                f"WARNING: duplicate filename: {filename}"
            )

        names[filename] = str(relative_path)

        output = target_dir / filename

        # --------------------------------------------------------
        # 写入文件
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
# 源：
#
# rules/mihomo/
#
# 只保存 .mrs
#
# 不保留子目录
#
# 最终：
#
# rules/Mihomo/
# ├── claude.mrs
# ├── google.mrs
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

    extensions={".mrs"}
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
# 不保留子目录
#
# 最终：
#
# rules/SingBox/
# ├── claude.srs
# ├── google.srs
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

    extensions={".srs"}
)


# ============================================================
# 3. DustinWin
#
# https://github.com/DustinWin/ruleset_geodata
#
# mihomo-ruleset
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
# 只保存 .mrs
#
# 不保留子目录
#
# 文件名全部小写
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

        extensions={".mrs"}
    )

except Exception as error:

    print()
    print("=" * 70)
    print("WARNING: X-Shelby CNIP sync failed")
    print("=" * 70)

    print(error)

    print()
    print(
        "Other rule sources will continue."
    )


# ============================================================
# 6. 217heidai AdBlock
#
# https://github.com/217heidai/adblockfilters
#
# 只保存 .mrs
#
# 不保留子目录
#
# 文件名全部小写
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
# 7. 清理空目录
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
# 8. 检查是否存在子目录
#
# 理论上最终 rules 下只有六个目录。
# ============================================================

print()
print("=" * 70)
print("CHECK SUBDIRECTORIES")
print("=" * 70)

unexpected_dirs = []

for path in ROOT.rglob("*"):

    if not path.is_dir():
        continue

    relative = path.relative_to(ROOT)

    # 第一层目录允许存在
    if len(relative.parts) > 1:

        unexpected_dirs.append(
            str(path)
        )


if unexpected_dirs:

    print("ERROR: Unexpected subdirectories found:")

    for path in unexpected_dirs:
        print(path)

    raise RuntimeError(
        "Subdirectories detected."
    )

else:

    print(
        "OK: No rule subdirectories."
    )


# ============================================================
# 9. 检查文件名是否全部小写
# ============================================================

print()
print("=" * 70)
print("CHECK LOWERCASE FILENAMES")
print("=" * 70)

uppercase_files = []

for path in ROOT.rglob("*"):

    if not path.is_file():
        continue

    if path.name != path.name.lower():

        uppercase_files.append(
            str(path)
        )


if uppercase_files:

    print("ERROR: Uppercase filenames found:")

    for path in uppercase_files:
        print(path)

    raise RuntimeError(
        "Uppercase filenames detected."
    )

else:

    print(
        "OK: All rule filenames are lowercase."
    )


# ============================================================
# 10. 检查规则文件类型
# ============================================================

print()
print("=" * 70)
print("CHECK FILE EXTENSIONS")
print("=" * 70)

invalid_files = []

for path in ROOT.rglob("*"):

    if not path.is_file():
        continue

    suffix = path.suffix.lower()

    # Mihomo
    if "Mihomo" in path.parts:

        if suffix != ".mrs":

            invalid_files.append(
                str(path)
            )

    # SingBox
    elif "SingBox" in path.parts:

        if suffix != ".srs":

            invalid_files.append(
                str(path)
            )

    # 其他目录
    else:

        if suffix != ".mrs":

            invalid_files.append(
                str(path)
            )


if invalid_files:

    print(
        "ERROR: Invalid rule files:"
    )

    for path in invalid_files:
        print(path)

    raise RuntimeError(
        "Invalid file extension detected."
    )

else:

    print(
        "OK: All rule file extensions are valid."
    )


# ============================================================
# 11. 输出最终目录
# ============================================================

print()
print("=" * 70)
print("FINAL RULE DIRECTORY")
print("=" * 70)

total = 0

for path in sorted(ROOT.rglob("*")):

    if path.is_file():

        print(path)

        total += 1


# ============================================================
# 12. 分类统计
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
        f"{directory}: {count} files"
    )


# ============================================================
# 完成
# ============================================================

print()
print("=" * 70)
print(f"TOTAL FILES: {total}")
print("SYNC ALL RULES FINISHED")
print("=" * 70)
