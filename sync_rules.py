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

session.headers.update(
    HEADERS
)


# ============================================================
# 基础工具
# ============================================================

def clean_dir(path: Path):
    """
    清空目录并重新创建
    """

    if path.exists():

        shutil.rmtree(
            path
        )

    path.mkdir(
        parents=True,
        exist_ok=True
    )


def ensure_dir(path: Path):
    """
    确保目录存在
    """

    path.mkdir(
        parents=True,
        exist_ok=True
    )


def download_file(
    url: str,
    output: Path
):
    """
    下载文件
    """

    print()
    print(
        f"DOWNLOAD: {url}"
    )

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


def download_zip(
    url: str
):
    """
    下载 GitHub ZIP
    """

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

        clean_dir(
            target_dir
        )

    else:

        ensure_dir(
            target_dir
        )

    count = 0

    for info in zip_file.infolist():

        if info.is_dir():

            continue

        original_path = Path(
            info.filename
        )

        # GitHub ZIP 第一层：
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
                    .relative_to(
                        prefix
                    )
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
            f" -> {output.name}"
        )

        with zip_file.open(
            info
        ) as source:

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
    """
    同步 GitHub ZIP
    """

    zip_file = download_zip(
        url
    )

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
# Rule-for-OCD Mihomo
#
# https://github.com/peiyingyao/Rule-for-OCD
#
# rule/Clash/
#
# 只同步 .mrs
#
# 命名转换：
#
# YouTube_OCD_Domain.mrs
#       ↓
# youtube.mrs
#
# YouTube_OCD_IP.mrs
#       ↓
# youtubeip.mrs
#
# Google_OCD_Domain.mrs
#       ↓
# google.mrs
#
# Google_OCD_IP.mrs
#       ↓
# googleip.mrs
#
# 不保留子目录
# ============================================================

def sync_rule_for_ocd_mihomo():

    print()
    print("#" * 70)
    print("# 1. Rule-for-OCD Mihomo")
    print("#" * 70)

    target_dir = (
        ROOT /
        "Mihomo"
    )

    clean_dir(
        target_dir
    )

    zip_file = download_zip(

        "https://github.com/"
        "peiyingyao/Rule-for-OCD/"
        "archive/refs/heads/master.zip"

    )

    count = 0

    try:

        for info in zip_file.infolist():

            if info.is_dir():

                continue

            original_path = Path(
                info.filename
            )

            parts = (
                original_path.parts
            )

            # ------------------------------------------------
            # 必须在 rule/Clash 下
            # ------------------------------------------------

            try:

                rule_index = (
                    parts.index(
                        "rule"
                    )
                )

                clash_index = (
                    parts.index(
                        "Clash"
                    )
                )

            except ValueError:

                continue

            # Clash 必须位于 rule 后
            if clash_index <= rule_index:

                continue

            # 必须存在文件
            if (
                len(parts)
                <= clash_index + 1
            ):

                continue

            # ------------------------------------------------
            # 只同步 .mrs
            # ------------------------------------------------

            filename = (
                original_path.name
            )

            if not filename.lower().endswith(
                ".mrs"
            ):

                continue

            stem = Path(
                filename
            ).stem

            stem_lower = (
                stem.lower()
            )

            # ------------------------------------------------
            # Domain
            #
            # xxx_OCD_Domain.mrs
            # ↓
            # xxx.mrs
            # ------------------------------------------------

            if stem_lower.endswith(
                "_ocd_domain"
            ):

                new_name = (
                    stem[
                        :-len(
                            "_OCD_Domain"
                        )
                    ]
                    + ".mrs"
                )

            # ------------------------------------------------
            # IP
            #
            # xxx_OCD_IP.mrs
            # ↓
            # xxxip.mrs
            # ------------------------------------------------

            elif stem_lower.endswith(
                "_ocd_ip"
            ):

                new_name = (
                    stem[
                        :-len(
                            "_OCD_IP"
                        )
                    ]
                    + "ip.mrs"
                )

            else:

                # 其他 .mrs
                # 直接小写文件名

                new_name = (
                    stem
                    + ".mrs"
                )

            # ------------------------------------------------
            # 全部小写
            # ------------------------------------------------

            new_name = (
                new_name.lower()
            )

            output = (
                target_dir /
                new_name
            )

            # ------------------------------------------------
            # 同名文件处理
            # ------------------------------------------------

            if output.exists():

                print(
                    f"WARNING: "
                    f"duplicate file: "
                    f"{new_name}"
                )

            print(
                f"  {filename}"
                f" -> {new_name}"
            )

            with zip_file.open(
                info
            ) as source:

                with open(
                    output,
                    "wb"
                ) as destination:

                    shutil.copyfileobj(
                        source,
                        destination
                    )

            count += 1

    finally:

        zip_file.close()

    print()
    print(
        f"Rule-for-OCD Mihomo "
        f"SYNC DONE: {count} files"
    )

    return count


# ============================================================
# 1. Rule-for-OCD Mihomo
# ============================================================

sync_rule_for_ocd_mihomo()


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
    },

    clean=True

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
# 全部 .srs
#
# clean=False
#
# 防止删除上面的 .mrs
# ============================================================

print()
print("#" * 70)
print("# 4. DustinWin SingBox")
print("#" * 70)


def get_release_assets(
    owner,
    repo,
    tag
):

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

    return release.get(
        "assets",
        []
    )


def sync_release_assets(
    owner,
    repo,
    tag,
    target_dir,
    extension,
    clean=True
):

    if clean:

        clean_dir(
            target_dir
        )

    else:

        ensure_dir(
            target_dir
        )

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

            selected.append(
                asset
            )

    print(
        f"Selected "
        f"{extension} assets: "
        f"{len(selected)}"
    )

    if not selected:

        raise RuntimeError(
            f"No {extension} assets "
            f"found in Release."
        )

    count = 0

    for asset in selected:

        name = asset["name"]

        url = (
            asset[
                "browser_download_url"
            ]
        )

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


# ============================================================
# 7. 217heidai AdBlock
#
# MRS + SRS
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
            path.relative_to(
                ROOT
            )
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
# 10. 检查全部文件名小写
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
        "Invalid rule file extension."
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
        "CNIP files are incomplete."
    )


print(
    "OK: All CNIP files exist."
)


# ============================================================
# 13. 检查所有目录非空
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
            f"Empty directory: "
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
