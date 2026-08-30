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
    "User-Agent": "verion-rules-sync",
}

session = requests.Session()
session.headers.update(HEADERS)

DOWNLOAD_TIMEOUT = 300


# ============================================================
# 基础目录操作
# ============================================================

def clean_dir(path: Path):

    if path.exists():
        shutil.rmtree(path)

    path.mkdir(
        parents=True,
        exist_ok=True
    )


def ensure_dir(path: Path):

    path.mkdir(
        parents=True,
        exist_ok=True
    )


# ============================================================
# 下载 ZIP
# ============================================================

def download_zip(url):

    print()
    print("=" * 70)
    print("DOWNLOAD ZIP")
    print(url)
    print("=" * 70)

    response = session.get(
        url,
        timeout=DOWNLOAD_TIMEOUT
    )

    response.raise_for_status()

    print(
        f"ZIP SIZE: "
        f"{len(response.content) / 1024 / 1024:.2f} MB"
    )

    return zipfile.ZipFile(
        io.BytesIO(
            response.content
        )
    )


# ============================================================
# 安全 ZIP 路径
# ============================================================

def safe_zip_path(name):

    path = Path(name)

    # 防止 ../ 路径穿越
    if ".." in path.parts:

        raise RuntimeError(
            f"Unsafe ZIP path: {name}"
        )

    return path


# ============================================================
# 从 ZIP 中提取指定目录的所有文件
#
# 这里使用 ZIP 本地扫描：
#
# 不依赖 GitHub Contents API
# 不受 GitHub API 429 影响
# 自动递归所有子目录
# ============================================================

def get_zip_files(
    zip_file,
    source_prefix
):

    source_prefix = (
        source_prefix
        .strip("/")
    )

    result = []

    for info in zip_file.infolist():

        if info.is_dir():

            continue

        path = safe_zip_path(
            info.filename
        )

        parts = path.parts

        if len(parts) < 2:

            continue

        # GitHub ZIP 第一层通常为：
        #
        # repository-branch/
        #
        relative = Path(
            *parts[1:]
        )

        prefix = Path(
            source_prefix
        )

        try:

            file_relative = (
                relative
                .relative_to(
                    prefix
                )
            )

        except ValueError:

            continue

        result.append(
            (
                info,
                file_relative
            )
        )

    return result


# ============================================================
# ZIP 中的文件名
# ============================================================

def get_filename(
    relative_path
):

    return Path(
        relative_path
    ).name


# ============================================================
# 通用 ZIP 规则同步
#
# 只保存文件
# 不保存子目录
# ============================================================

def sync_zip_rules(
    url,
    target_dir,
    source_prefix,
    extensions,
    clean=True,
    rename_func=None,
    skip_func=None
):

    if clean:

        clean_dir(
            target_dir
        )

    else:

        ensure_dir(
            target_dir
        )

    zip_file = download_zip(
        url
    )

    try:

        files = get_zip_files(

            zip_file,

            source_prefix

        )

        print()
        print(
            f"SOURCE DIRECTORY: "
            f"{source_prefix}"
        )

        print(
            f"FILES FOUND: "
            f"{len(files)}"
        )

        count = 0
        skipped = 0

        used_names = {}

        for info, relative_path in files:

            original_name = (
                get_filename(
                    relative_path
                )
            )

            suffix = (
                Path(
                    original_name
                ).suffix
                .lower()
            )

            # ------------------------------------------------
            # 扩展名过滤
            # ------------------------------------------------

            if suffix not in extensions:

                continue

            # ------------------------------------------------
            # 自定义跳过
            # ------------------------------------------------

            if skip_func:

                if skip_func(
                    original_name,
                    relative_path
                ):

                    print(
                        f"SKIP: "
                        f"{relative_path}"
                    )

                    skipped += 1

                    continue

            # ------------------------------------------------
            # 重命名
            # ------------------------------------------------

            if rename_func:

                new_name = rename_func(
                    original_name
                )

            else:

                new_name = (
                    original_name
                )

            # ------------------------------------------------
            # 全部小写
            # ------------------------------------------------

            new_name = (
                new_name.lower()
            )

            # ------------------------------------------------
            # 确保扩展名正确
            # ------------------------------------------------

            if not new_name.endswith(
                tuple(extensions)
            ):

                raise RuntimeError(

                    "Invalid renamed "
                    f"filename:\n"
                    f"Source: {relative_path}\n"
                    f"Target: {new_name}"

                )

            # ------------------------------------------------
            # 重名保护
            #
            # 绝不覆盖文件
            # ------------------------------------------------

            if new_name in used_names:

                old_path = (
                    used_names[
                        new_name
                    ]
                )

                raise RuntimeError(

                    "FILENAME COLLISION\n"
                    "\n"
                    f"Target filename:\n"
                    f"  {new_name}\n"
                    "\n"
                    f"Source 1:\n"
                    f"  {old_path}\n"
                    "\n"
                    f"Source 2:\n"
                    f"  {relative_path}\n"
                    "\n"
                    "Synchronization stopped "
                    "to prevent rule loss."

                )

            used_names[
                new_name
            ] = str(
                relative_path
            )

            output = (
                target_dir /
                new_name
            )

            # ------------------------------------------------
            # 写入文件
            # ------------------------------------------------

            print(
                f"  {relative_path}"
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

        print()
        print(
            f"DOWNLOADED: {count}"
        )

        print(
            f"SKIPPED: {skipped}"
        )

        if count == 0:

            raise RuntimeError(

                "No valid rule files "
                f"found in {source_prefix}"

            )

        return count

    finally:

        zip_file.close()


# ============================================================
# Mihomo 文件重命名
#
# YouTube_domain.mrs
#       ↓
# youtube.mrs
#
# YouTube_ipcidr.mrs
#       ↓
# youtubeip.mrs
#
# YouTube_classical.mrs
#       ↓
# 跳过
# ============================================================

def rename_mihomo(
    filename
):

    stem = Path(
        filename
    ).stem

    stem_lower = (
        stem.lower()
    )

    # --------------------------------------------------------
    # domain
    # --------------------------------------------------------

    if stem_lower.endswith(
        "_domain"
    ):

        base = stem[
            :-len("_domain")
        ]

        return (
            base +
            ".mrs"
        )

    # --------------------------------------------------------
    # ipcidr
    # --------------------------------------------------------

    if stem_lower.endswith(
        "_ipcidr"
    ):

        base = stem[
            :-len("_ipcidr")
        ]

        return (
            base +
            "ip.mrs"
        )

    # --------------------------------------------------------
    # 其他
    # --------------------------------------------------------

    return (
        stem +
        ".mrs"
    )


# ============================================================
# Mihomo 跳过 classical
# ============================================================

def skip_mihomo(
    filename,
    relative_path
):

    stem = Path(
        filename
    ).stem

    return (
        stem.lower()
        .endswith(
            "_classical"
        )
    )


# ============================================================
# 1. Mihomo
#
# 来源：
#
# https://github.com/milangree/rules/tree/main/rules/mihomo
#
# ZIP：
#
# https://github.com/milangree/rules/archive/refs/heads/main.zip
# ============================================================

def sync_mihomo():

    print()
    print("=" * 70)
    print("1. MIHOMO")
    print("=" * 70)

    return sync_zip_rules(

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

        clean=True,

        rename_func=rename_mihomo,

        skip_func=skip_mihomo

    )


# ============================================================
# 2. SingBox
#
# Milangree
#
# 只保留 .srs
# ============================================================

def sync_singbox():

    print()
    print("=" * 70)
    print("2. SINGBOX")
    print("=" * 70)

    return sync_zip_rules(

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
# ZIP：
#
# mihomo-ruleset
#
# 只保留 .mrs
# ============================================================

def sync_dustinwin_mihomo():

    print()
    print("=" * 70)
    print("3. DUSTINWIN MIHOMO")
    print("=" * 70)

    return sync_zip_rules(

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

        source_prefix="",

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
# 只同步 .srs
# ============================================================

def github_release_assets(
    owner,
    repo,
    tag
):

    url = (
        f"https://api.github.com/repos/"
        f"{owner}/{repo}/releases/tags/{tag}"
    )

    response = session.get(
        url,
        timeout=120
    )

    response.raise_for_status()

    data = response.json()

    return data.get(
        "assets",
        []
    )


def sync_dustinwin_singbox():

    print()
    print("=" * 70)
    print("4. DUSTINWIN SINGBOX")
    print("=" * 70)

    target_dir = (
        ROOT /
        "DustinWin"
    )

    ensure_dir(
        target_dir
    )

    assets = github_release_assets(

        "DustinWin",

        "ruleset_geodata",

        "sing-box-ruleset-compatible"

    )

    count = 0

    used_names = {

        path.name

        for path
        in target_dir.iterdir()

        if path.is_file()

    }

    for asset in assets:

        original_name = asset.get(
            "name",
            ""
        )

        if not original_name.lower().endswith(
            ".srs"
        ):

            continue

        new_name = (
            original_name
            .lower()
        )

        if new_name in used_names:

            raise RuntimeError(

                "DustinWin filename collision:\n"
                f"{new_name}"

            )

        used_names.add(
            new_name
        )

        output = (
            target_dir /
            new_name
        )

        print(
            f"  {original_name}"
            f" -> {new_name}"
        )

        download_file(

            asset[
                "browser_download_url"
            ],

            output

        )

        count += 1

    if count == 0:

        raise RuntimeError(
            "No DustinWin .srs files found."
        )

    print(
        f"DustinWin SRS: {count}"
    )

    return count


# ============================================================
# 5. GeoIP
#
# MetaCubeX
#
# 只保留 .mrs
# ============================================================

def sync_geoip():

    print()
    print("=" * 70)
    print("5. GEOIP")
    print("=" * 70)

    return sync_zip_rules(

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
# 6. CNIP
#
# X-Shelby
#
# MRS + SRS
#
# 固定文件：
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
# ============================================================

def sync_cnip():

    print()
    print("=" * 70)
    print("6. CNIP")
    print("=" * 70)

    target_dir = (
        ROOT /
        "cnip"
    )

    clean_dir(
        target_dir
    )

    base_url = (
        "https://github.com/"
        "X-Shelby/geoip/"
        "releases/download/latest/"
    )

    files = [

        "cn.mrs",
        "cn_v4.mrs",
        "cn_v6.mrs",
        "cnip_all.mrs",

        "cn.srs",
        "cn_v4.srs",
        "cn_v6.srs",
        "cnip_all.srs",

    ]

    for filename in files:

        download_file(

            base_url +
            filename,

            target_dir /
            filename.lower()

        )

    return len(files)


# ============================================================
# 7. AdBlock
#
# MRS + SRS
# ============================================================

def sync_adblock():

    print()
    print("=" * 70)
    print("7. ADBLOCK")
    print("=" * 70)

    return sync_zip_rules(

        url=(
            "https://github.com/"
            "217heidai/adblockfilters/"
            "archive/refs/heads/main.zip"
        ),

        target_dir=(
            ROOT /
            "AdBlock"
        ),

        source_prefix="",

        extensions={
            ".mrs",
            ".srs"
        },

        clean=True

    )


# ============================================================
# 普通下载
# ============================================================

def download_file(
    url,
    output
):

    print(
        f"DOWNLOAD: {url}"
    )

    response = session.get(
        url,
        timeout=DOWNLOAD_TIMEOUT
    )

    response.raise_for_status()

    ensure_dir(
        output.parent
    )

    output.write_bytes(
        response.content
    )

    print(
        f"OK: {output.name}"
    )


# ============================================================
# 检查目录
# ============================================================

def check_directories():

    print()
    print("=" * 70)
    print("CHECK DIRECTORIES")
    print("=" * 70)

    allowed = {

        "Mihomo",
        "SingBox",
        "DustinWin",
        "geoip",
        "cnip",
        "AdBlock",

    }

    if not ROOT.exists():

        raise RuntimeError(
            "rules directory does not exist."
        )

    actual = {

        path.name

        for path
        in ROOT.iterdir()

        if path.is_dir()

    }

    if actual != allowed:

        raise RuntimeError(

            "Directory structure mismatch.\n"
            f"Expected: {sorted(allowed)}\n"
            f"Actual: {sorted(actual)}"

        )

    for directory in ROOT.iterdir():

        for path in directory.iterdir():

            if path.is_dir():

                raise RuntimeError(

                    "SUBDIRECTORY DETECTED:\n"
                    f"{path}"

                )

    print(
        "OK: No subdirectories."
    )


# ============================================================
# 检查小写文件名
# ============================================================

def check_lowercase():

    print()
    print("=" * 70)
    print("CHECK LOWERCASE")
    print("=" * 70)

    for path in ROOT.rglob("*"):

        if not path.is_file():

            continue

        if path.name != path.name.lower():

            raise RuntimeError(

                "Filename is not lowercase:\n"
                f"{path}"

            )

    print(
        "OK: All filenames lowercase."
    )


# ============================================================
# 检查扩展名
# ============================================================

def check_extensions():

    print()
    print("=" * 70)
    print("CHECK EXTENSIONS")
    print("=" * 70)

    allowed = {

        "Mihomo": {
            ".mrs"
        },

        "SingBox": {
            ".srs"
        },

        "DustinWin": {
            ".mrs",
            ".srs"
        },

        "geoip": {
            ".mrs"
        },

        "cnip": {
            ".mrs",
            ".srs"
        },

        "AdBlock": {
            ".mrs",
            ".srs"
        },

    }

    for directory_name, extensions in allowed.items():

        directory = (
            ROOT /
            directory_name
        )

        for path in directory.iterdir():

            if not path.is_file():

                continue

            if path.suffix.lower() not in extensions:

                raise RuntimeError(

                    "Invalid extension:\n"
                    f"{path}"

                )

    print(
        "OK: All extensions valid."
    )


# ============================================================
# 检查 CNIP
# ============================================================

def check_cnip():

    print()
    print("=" * 70)
    print("CHECK CNIP")
    print("=" * 70)

    required = {

        "cn.mrs",
        "cn_v4.mrs",
        "cn_v6.mrs",
        "cnip_all.mrs",

        "cn.srs",
        "cn_v4.srs",
        "cn_v6.srs",
        "cnip_all.srs",

    }

    directory = (
        ROOT /
        "cnip"
    )

    actual = {

        path.name

        for path
        in directory.iterdir()

        if path.is_file()

    }

    missing = (
        required -
        actual
    )

    if missing:

        raise RuntimeError(

            "Missing CNIP files:\n"
            +
            "\n".join(
                sorted(missing)
            )

        )

    print(
        "OK: CNIP MRS/SRS complete."
    )


# ============================================================
# 检查 Mihomo 命名
#
# 确保不存在：
#
# *_domain.mrs
# *_ipcidr.mrs
# *_classical.mrs
# ============================================================

def check_mihomo_names():

    print()
    print("=" * 70)
    print("CHECK MIHOMO NAMES")
    print("=" * 70)

    directory = (
        ROOT /
        "Mihomo"
    )

    for path in directory.iterdir():

        if not path.is_file():

            continue

        stem = path.stem.lower()

        if stem.endswith(
            "_domain"
        ):

            raise RuntimeError(

                "Mihomo domain filename "
                "was not renamed:\n"
                f"{path}"

            )

        if stem.endswith(
            "_ipcidr"
        ):

            raise RuntimeError(

                "Mihomo ipcidr filename "
                "was not renamed:\n"
                f"{path}"

            )

        if stem.endswith(
            "_classical"
        ):

            raise RuntimeError(

                "Classical file was not "
                "excluded:\n"
                f"{path}"

            )

    print(
        "OK: Mihomo naming valid."
    )


# ============================================================
# 最终统计
# ============================================================

def statistics():

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
        "AdBlock",

    ]:

        directory = (
            ROOT /
            directory_name
        )

        mrs = 0
        srs = 0

        for path in directory.iterdir():

            if not path.is_file():

                continue

            suffix = (
                path.suffix
                .lower()
            )

            if suffix == ".mrs":

                mrs += 1

            elif suffix == ".srs":

                srs += 1

        total += (
            mrs +
            srs
        )

        print(
            f"{directory_name:15}"
            f"MRS={mrs:4} "
            f"SRS={srs:4}"
        )

    print()
    print(
        f"TOTAL FILES: {total}"
    )


# ============================================================
# 主程序
# ============================================================

def main():

    print()
    print("=" * 70)
    print("START RULE SYNC")
    print("=" * 70)

    # --------------------------------------------------------
    # 创建 rules
    # --------------------------------------------------------

    ROOT.mkdir(
        parents=True,
        exist_ok=True
    )

    # --------------------------------------------------------
    # 同步
    # --------------------------------------------------------

    sync_mihomo()

    sync_singbox()

    sync_dustinwin_mihomo()

    sync_dustinwin_singbox()

    sync_geoip()

    sync_cnip()

    sync_adblock()

    # --------------------------------------------------------
    # 检查
    # --------------------------------------------------------

    check_directories()

    check_lowercase()

    check_extensions()

    check_cnip()

    check_mihomo_names()

    statistics()

    print()
    print("=" * 70)
    print("ALL RULES SYNC FINISHED")
    print("=" * 70)


# ============================================================
# Entry
# ============================================================

if __name__ == "__main__":

    main()
