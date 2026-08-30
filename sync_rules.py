import io
import shutil
import zipfile
import requests
import subprocess
import tempfile
from pathlib import Path


# ============================================================
# 基础配置
# ============================================================

ROOT = Path("rules")

HEADERS = {
    "User-Agent": "Verion-Rules-Sync",
}

session = requests.Session()
session.headers.update(HEADERS)

DOWNLOAD_TIMEOUT = 300


# ============================================================
# Mihomo Meta Converter
#
# 用于：
#
# threads.mrs
# facebook.mrs
# instagram.mrs
#
# 合并为：
#
# meta.mrs
#
# 注意：
# .mrs 是二进制格式，不能直接 cat。
# ============================================================

MIHOMO_CONVERTER_URL = (
    "https://github.com/MetaCubeX/mihomo/releases/latest/download/"
    "mihomo-linux-amd64-compatible"
)


# ============================================================
# 基础目录
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
# 普通下载
# ============================================================

def download_file(
    url,
    output
):

    print()
    print(f"DOWNLOAD: {url}")

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
        f"OK: {output}"
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
# ZIP 路径安全检查
# ============================================================

def safe_zip_path(name):

    path = Path(name)

    if ".." in path.parts:

        raise RuntimeError(
            f"Unsafe ZIP path: {name}"
        )

    return path


# ============================================================
# 获取 ZIP 内指定目录的所有文件
#
# 完全本地扫描 ZIP
# 不使用 GitHub Contents API
# 避免 429
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

    prefix = Path(
        source_prefix
    )

    for info in zip_file.infolist():

        if info.is_dir():

            continue

        path = safe_zip_path(
            info.filename
        )

        parts = path.parts

        if len(parts) < 2:

            continue

        # GitHub ZIP 第一层目录
        relative = Path(
            *parts[1:]
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
# 通用 ZIP 规则同步
#
# 不保留子目录
# 自动递归
# 自动去重检查
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
            f"SOURCE: {source_prefix}"
        )

        print(
            f"FILES FOUND: {len(files)}"
        )

        count = 0
        skipped = 0

        used_names = {}

        for info, relative_path in files:

            original_name = (
                relative_path.name
            )

            suffix = (
                Path(
                    original_name
                ).suffix
                .lower()
            )

            if suffix not in extensions:

                continue

            # ------------------------------------------------
            # 跳过
            # ------------------------------------------------

            if skip_func:

                if skip_func(
                    original_name,
                    relative_path
                ):

                    print(
                        f"SKIP: {relative_path}"
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

                new_name = original_name

            # ------------------------------------------------
            # 全部小写
            # ------------------------------------------------

            new_name = (
                new_name.lower()
            )

            # ------------------------------------------------
            # 重名保护
            # ------------------------------------------------

            if new_name in used_names:

                raise RuntimeError(

                    "FILENAME COLLISION\n"
                    "\n"
                    f"Target:\n"
                    f"  {new_name}\n"
                    "\n"
                    f"Source 1:\n"
                    f"  {used_names[new_name]}\n"
                    "\n"
                    f"Source 2:\n"
                    f"  {relative_path}\n"

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
                f"No valid files found: "
                f"{source_prefix}"
            )

        return count

    finally:

        zip_file.close()


# ============================================================
# Mihomo 命名
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

    return (
        stem +
        ".mrs"
    )


# ============================================================
# Mihomo 排除 classical
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
# Mihomo
#
# Milangree
#
# rules/mihomo
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
# 合并 Meta
#
# threads.mrs
# facebook.mrs
# instagram.mrs
#
# ↓
#
# meta.mrs
# ============================================================

def merge_meta_rules():

    print()
    print("=" * 70)
    print("MERGE META")
    print("=" * 70)

    mihomo_dir = (
        ROOT /
        "Mihomo"
    )

    source_files = [

        mihomo_dir /
        "threads.mrs",

        mihomo_dir /
        "facebook.mrs",

        mihomo_dir /
        "instagram.mrs",

    ]

    missing = [

        path.name

        for path
        in source_files

        if not path.exists()

    ]

    if missing:

        raise RuntimeError(

            "Cannot merge Meta.\n"
            "Missing files:\n"
            +
            "\n".join(
                missing
            )

        )

    # --------------------------------------------------------
    # 这里不能直接拼接 .mrs
    #
    # 需要使用 Mihomo 的规则集转换能力。
    #
    # 先准备临时目录
    # --------------------------------------------------------

    with tempfile.TemporaryDirectory() as tmp:

        tmp_path = Path(tmp)

        combined = (
            tmp_path /
            "meta.txt"
        )

        # ----------------------------------------------------
        # 尝试使用 mihomo convert-ruleset
        # ----------------------------------------------------

        mihomo = (
            tmp_path /
            "mihomo"
        )

        try:

            download_file(
                MIHOMO_CONVERTER_URL,
                mihomo
            )

            mihomo.chmod(
                0o755
            )

        except Exception as error:

            raise RuntimeError(

                "Failed to download "
                "Mihomo converter:\n"
                f"{error}"

            )

        # ----------------------------------------------------
        # 将三个 .mrs 转为文本
        # ----------------------------------------------------

        converted_files = []

        for source in source_files:

            output = (
                tmp_path /
                f"{source.stem}.txt"
            )

            print(
                f"CONVERT: "
                f"{source.name}"
            )

            commands = [

                [
                    str(mihomo),
                    "convert-ruleset",
                    "mrs",
                    "domain",
                    str(source),
                    str(output),
                ],

                [
                    str(mihomo),
                    "convert-ruleset",
                    "mrs",
                    "classical",
                    str(source),
                    str(output),
                ],

            ]

            converted = False

            for command in commands:

                try:

                    result = subprocess.run(

                        command,

                        stdout=subprocess.PIPE,

                        stderr=subprocess.PIPE,

                        text=True,

                        timeout=120

                    )

                    if (
                        result.returncode == 0
                        and output.exists()
                    ):

                        converted = True

                        break

                except Exception:

                    pass

            if not converted:

                raise RuntimeError(

                    "Failed to convert:\n"
                    f"{source.name}\n\n"
                    "The current Mihomo release "
                    "may have changed its "
                    "convert-ruleset interface."

                )

            converted_files.append(
                output
            )

        # ----------------------------------------------------
        # 合并 + 去重
        # ----------------------------------------------------

        rules = set()

        for file in converted_files:

            with open(
                file,
                "r",
                encoding="utf-8",
                errors="ignore"
            ) as f:

                for line in f:

                    line = (
                        line.strip()
                    )

                    if not line:

                        continue

                    if line.startswith(
                        "#"
                    ):

                        continue

                    rules.add(
                        line
                    )

        if not rules:

            raise RuntimeError(
                "Meta rule set is empty."
            )

        sorted_rules = sorted(
            rules,
            key=lambda x: x.lower()
        )

        with open(
            combined,
            "w",
            encoding="utf-8"
        ) as f:

            f.write(
                "\n".join(
                    sorted_rules
                )
            )

            f.write(
                "\n"
            )

        # ----------------------------------------------------
        # 编译成 meta.mrs
        # ----------------------------------------------------

        meta_output = (
            mihomo_dir /
            "meta.mrs"
        )

        print()
        print(
            f"RULES AFTER DEDUP: "
            f"{len(sorted_rules)}"
        )

        print(
            "COMPILE: meta.mrs"
        )

        compile_commands = [

            [
                str(mihomo),
                "convert-ruleset",
                "text",
                "domain",
                str(combined),
                str(meta_output),
            ],

            [
                str(mihomo),
                "convert-ruleset",
                "text",
                "classical",
                str(combined),
                str(meta_output),
            ],

        ]

        compiled = False

        for command in compile_commands:

            try:

                result = subprocess.run(

                    command,

                    stdout=subprocess.PIPE,

                    stderr=subprocess.PIPE,

                    text=True,

                    timeout=120

                )

                if (
                    result.returncode == 0
                    and meta_output.exists()
                    and meta_output.stat().st_size > 0
                ):

                    compiled = True

                    break

            except Exception:

                pass

        if not compiled:

            raise RuntimeError(
                "Failed to compile meta.mrs."
            )

    # --------------------------------------------------------
    # 删除原文件
    # --------------------------------------------------------

    for source in source_files:

        if source.exists():

            source.unlink()

    print()
    print(
        "META MERGE COMPLETE"
    )

    print(
        f"OUTPUT: {meta_output}"
    )

    print(
        f"SIZE: "
        f"{meta_output.stat().st_size} bytes"
    )


# ============================================================
# SingBox
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
# DustinWin Mihomo
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
# DustinWin Release
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

    return response.json().get(
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

    existing = {

        path.name

        for path
        in target_dir.iterdir()

        if path.is_file()

    }

    for asset in assets:

        name = asset.get(
            "name",
            ""
        )

        if not name.lower().endswith(
            ".srs"
        ):

            continue

        new_name = (
            name.lower()
        )

        if new_name in existing:

            raise RuntimeError(

                "DustinWin filename collision:\n"
                f"{new_name}"

            )

        output = (
            target_dir /
            new_name
        )

        download_file(

            asset[
                "browser_download_url"
            ],

            output

        )

        existing.add(
            new_name
        )

        count += 1

    if count == 0:

        raise RuntimeError(
            "No DustinWin SRS files found."
        )

    print(
        f"DustinWin SRS: {count}"
    )

    return count


# ============================================================
# GeoIP
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
# CNIP
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
# AdBlock
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
# 小写检查
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
# 扩展名检查
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
        "OK: Extensions valid."
    )


# ============================================================
# 检查 Mihomo
# ============================================================

def check_mihomo():

    print()
    print("=" * 70)
    print("CHECK MIHOMO")
    print("=" * 70)

    directory = (
        ROOT /
        "Mihomo"
    )

    # Meta 必须存在

    if not (
        directory /
        "meta.mrs"
    ).exists():

        raise RuntimeError(
            "meta.mrs does not exist."
        )

    # 三个源文件不能存在

    forbidden = [

        "threads.mrs",
        "facebook.mrs",
        "instagram.mrs",

    ]

    for filename in forbidden:

        if (
            directory /
            filename
        ).exists():

            raise RuntimeError(

                "Source Meta rule still exists:\n"
                f"{filename}"

            )

    # classical 不允许存在

    for path in directory.iterdir():

        if (
            path.is_file()
            and
            path.stem.lower().endswith(
                "_classical"
            )
        ):

            raise RuntimeError(

                "Classical rule detected:\n"
                f"{path}"

            )

    print(
        "OK: Mihomo Meta rule valid."
    )


# ============================================================
# CNIP 检查
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
        "OK: CNIP complete."
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

    ROOT.mkdir(
        parents=True,
        exist_ok=True
    )

    # --------------------------------------------------------
    # Mihomo
    # --------------------------------------------------------

    sync_mihomo()

    # --------------------------------------------------------
    # Meta 合并
    # --------------------------------------------------------

    merge_meta_rules()

    # --------------------------------------------------------
    # SingBox
    # --------------------------------------------------------

    sync_singbox()

    # --------------------------------------------------------
    # DustinWin
    # --------------------------------------------------------

    sync_dustinwin_mihomo()

    sync_dustinwin_singbox()

    # --------------------------------------------------------
    # GeoIP
    # --------------------------------------------------------

    sync_geoip()

    # --------------------------------------------------------
    # CNIP
    # --------------------------------------------------------

    sync_cnip()

    # --------------------------------------------------------
    # AdBlock
    # --------------------------------------------------------

    sync_adblock()

    # --------------------------------------------------------
    # 检查
    # --------------------------------------------------------

    check_directories()

    check_lowercase()

    check_extensions()

    check_mihomo()

    check_cnip()

    # --------------------------------------------------------
    # 统计
    # --------------------------------------------------------

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
