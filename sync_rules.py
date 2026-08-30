import gzip
import io
import shutil
import subprocess
import tempfile
import time
import zipfile
from pathlib import Path

import requests


# ============================================================
# 基础配置
# ============================================================

ROOT = Path("rules")

TIMEOUT = 300

HEADERS = {
    "User-Agent": "Verion-Rules-Sync/1.0",
    "Accept": "application/vnd.github+json",
}

session = requests.Session()
session.headers.update(HEADERS)


# ============================================================
# HTTP 请求
# ============================================================

def request(
    method,
    url,
    *,
    timeout=TIMEOUT,
    retries=5,
    **kwargs
):

    last_error = None

    for attempt in range(1, retries + 1):

        try:

            response = session.request(
                method,
                url,
                timeout=timeout,
                **kwargs
            )

            if response.status_code in (429, 403):

                retry_after = response.headers.get(
                    "Retry-After"
                )

                if retry_after:
                    try:
                        wait = int(retry_after)
                    except ValueError:
                        wait = attempt * 5
                else:
                    wait = attempt * 5

                print(
                    f"HTTP {response.status_code}, "
                    f"retry in {wait}s..."
                )

                time.sleep(wait)

                continue

            response.raise_for_status()

            return response

        except Exception as error:

            last_error = error

            print(
                f"Request failed "
                f"({attempt}/{retries}): "
                f"{url}"
            )

            print(
                f"ERROR: {error}"
            )

            if attempt < retries:

                time.sleep(
                    attempt * 3
                )

    raise last_error


def download_bytes(url):

    print(
        f"DOWNLOAD: {url}"
    )

    response = request(
        "GET",
        url
    )

    return response.content


def download_file(
    url,
    output
):

    data = download_bytes(
        url
    )

    output.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    output.write_bytes(
        data
    )

    print(
        f"OK: {output}"
    )


# ============================================================
# GitHub ZIP
# ============================================================

def github_zip(
    owner,
    repo,
    branch="main"
):

    url = (
        f"https://github.com/"
        f"{owner}/{repo}/"
        f"archive/refs/heads/"
        f"{branch}.zip"
    )

    print()
    print(
        f"DOWNLOAD ZIP: {url}"
    )

    data = download_bytes(
        url
    )

    return zipfile.ZipFile(
        io.BytesIO(data)
    )


def zip_relative_path(
    filename
):

    parts = Path(
        filename
    ).parts

    if len(parts) <= 1:
        return Path()

    return Path(
        *parts[1:]
    )


def safe_zip_path(
    filename
):

    path = Path(
        filename
    )

    if ".." in path.parts:

        raise RuntimeError(
            f"Unsafe ZIP path: {filename}"
        )

    return path


# ============================================================
# 清理目录
# ============================================================

def clean_dir(
    directory
):

    directory = Path(
        directory
    )

    if directory.exists():

        shutil.rmtree(
            directory
        )

    directory.mkdir(
        parents=True,
        exist_ok=True
    )


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
# 排除
# ============================================================

def mihomo_output_name(
    filename
):

    stem = Path(
        filename
    ).stem

    lower = stem.lower()

    if lower.endswith(
        "_classical"
    ):

        return None

    if lower.endswith(
        "_domain"
    ):

        base = lower[
            :-len("_domain")
        ]

        return (
            base +
            ".mrs"
        )

    if lower.endswith(
        "_ipcidr"
    ):

        base = lower[
            :-len("_ipcidr")
        ]

        return (
            base +
            "ip.mrs"
        )

    return (
        lower +
        ".mrs"
    )


# ============================================================
# Mihomo
# Milangree
# ============================================================

def sync_mihomo():

    print()
    print("=" * 70)
    print("SYNC MIHOMO")
    print("=" * 70)

    target = (
        ROOT /
        "Mihomo"
    )

    clean_dir(
        target
    )

    archive = github_zip(
        "milangree",
        "rules",
        "main"
    )

    try:

        used = {}

        count = 0

        for info in archive.infolist():

            if info.is_dir():
                continue

            safe_zip_path(
                info.filename
            )

            relative = zip_relative_path(
                info.filename
            )

            parts = relative.parts

            if len(parts) < 3:
                continue

            if parts[0].lower() != "rules":
                continue

            if parts[1].lower() != "mihomo":
                continue

            filename = parts[-1]

            if not filename.lower().endswith(
                ".mrs"
            ):
                continue

            if "_classical." in filename.lower():

                print(
                    f"SKIP CLASSICAL: {relative}"
                )

                continue

            new_name = mihomo_output_name(
                filename
            )

            if not new_name:
                continue

            if new_name in used:

                raise RuntimeError(

                    "Mihomo filename collision:\n"
                    f"Target: {new_name}\n"
                    f"Source 1: {used[new_name]}\n"
                    f"Source 2: {relative}"

                )

            used[new_name] = str(
                relative
            )

            output = (
                target /
                new_name
            )

            with archive.open(
                info
            ) as source:

                with output.open(
                    "wb"
                ) as destination:

                    shutil.copyfileobj(
                        source,
                        destination
                    )

            print(
                f"{relative} -> {new_name}"
            )

            count += 1

        if count == 0:

            raise RuntimeError(
                "No Mihomo MRS files found."
            )

        print(
            f"Mihomo MRS files: {count}"
        )

    finally:

        archive.close()


# ============================================================
# 解析简单 payload YAML
# ============================================================

def parse_payload_yaml(
    text
):

    rules = []

    inside_payload = False

    for raw_line in text.splitlines():

        line = raw_line.strip()

        if not line:
            continue

        if line.startswith("#"):
            continue

        if line == "payload:":

            inside_payload = True

            continue

        if not inside_payload:
            continue

        if line.startswith("-"):

            value = line[1:].strip()

            if (
                len(value) >= 2
                and value[0] == value[-1]
                and value[0] in ("'", '"')
            ):

                value = value[1:-1]

            if value:

                rules.append(
                    value
                )

    return rules


# ============================================================
# Meta 源
# ============================================================

META_SOURCES = {

    "threads": "Threads_domain.yaml",

    "facebook": "Facebook_domain.yaml",

    "instagram": "Instagram_domain.yaml",

}


def find_meta_yaml_sources(
    archive
):

    found = {}

    wanted = {
        x.lower(): x
        for x in META_SOURCES.values()
    }

    for info in archive.infolist():

        if info.is_dir():
            continue

        relative = zip_relative_path(
            info.filename
        )

        parts = relative.parts

        if len(parts) < 4:
            continue

        if parts[0].lower() != "rules":
            continue

        if parts[1].lower() != "mihomo":
            continue

        filename = parts[-1]

        lower = filename.lower()

        if lower not in wanted:
            continue

        service = None

        if lower == "threads_domain.yaml":
            service = "threads"

        elif lower == "facebook_domain.yaml":
            service = "facebook"

        elif lower == "instagram_domain.yaml":
            service = "instagram"

        if service:

            found[service] = (
                info,
                relative
            )

    missing = (
        set(META_SOURCES)
        -
        set(found)
    )

    if missing:

        raise RuntimeError(

            "Missing Meta YAML sources:\n"
            +
            "\n".join(
                sorted(missing)
            )

        )

    return found


# ============================================================
# 下载 Mihomo Converter
#
# 关键修复：
#
# 不允许：
#   .deb
#   .rpm
#   .zip
#
# 优先：
#   mihomo-linux-amd64-v1-*.gz
#
# 官方 Release 同时提供多种架构/编译方式，
# v1 是 AMD64 v1 指令集版本。
# ============================================================

def download_mihomo_converter(
    output
):

    print()
    print("=" * 70)
    print("DOWNLOAD MIHOMO CONVERTER")
    print("=" * 70)

    api = (
        "https://api.github.com/"
        "repos/MetaCubeX/mihomo/"
        "releases/latest"
    )

    response = request(
        "GET",
        api,
        timeout=120
    )

    release = response.json()

    tag = release.get(
        "tag_name"
    )

    print(
        f"Mihomo release: {tag}"
    )

    assets = release.get(
        "assets",
        []
    )

    candidates = []

    # ========================================================
    # 第一优先级
    #
    # linux-amd64-v1-xxx.gz
    # ========================================================

    for asset in assets:

        name = asset.get(
            "name",
            ""
        )

        lower = name.lower()

        if not lower.startswith(
            "mihomo-linux-amd64-v1"
        ):
            continue

        if not lower.endswith(
            ".gz"
        ):
            continue

        if any(
            lower.endswith(ext)
            for ext in (
                ".deb",
                ".rpm",
                ".zip",
                ".tar.gz",
                ".sha256",
                ".sig",
            )
        ):
            continue

        candidates.append(
            asset
        )

    # ========================================================
    # 第二优先级
    #
    # linux-amd64-v1 无压缩二进制
    # ========================================================

    if not candidates:

        for asset in assets:

            name = asset.get(
                "name",
                ""
            )

            lower = name.lower()

            if not lower.startswith(
                "mihomo-linux-amd64-v1"
            ):
                continue

            if lower.endswith(
                (
                    ".deb",
                    ".rpm",
                    ".zip",
                    ".tar.gz",
                    ".gz",
                    ".sha256",
                    ".sig",
                )
            ):
                continue

            candidates.append(
                asset
            )

    # ========================================================
    # 第三优先级
    #
    # linux-amd64-compatible
    # ========================================================

    if not candidates:

        for asset in assets:

            name = asset.get(
                "name",
                ""
            )

            lower = name.lower()

            if not lower.startswith(
                "mihomo-linux-amd64-compatible"
            ):
                continue

            if not lower.endswith(
                ".gz"
            ):
                continue

            candidates.append(
                asset
            )

    if not candidates:

        available = [
            x.get(
                "name",
                ""
            )
            for x in assets
            if "linux-amd64"
            in x.get(
                "name",
                ""
            ).lower()
        ]

        raise RuntimeError(

            "Cannot find usable Mihomo "
            "Linux AMD64 binary.\n\n"
            "Available linux-amd64 assets:\n"
            +
            "\n".join(
                available
            )

        )

    # ========================================================
    # 优先选择最标准的 v1 gz
    # ========================================================

    candidates.sort(
        key=lambda asset: (
            0
            if asset["name"].lower().endswith(".gz")
            else 1
        )
    )

    asset = candidates[0]

    name = asset[
        "name"
    ]

    url = asset[
        "browser_download_url"
    ]

    print(
        f"Asset: {name}"
    )

    data = download_bytes(
        url
    )

    # ========================================================
    # GZIP
    # ========================================================

    if name.lower().endswith(
        ".gz"
    ):

        print(
            "Extracting gzip..."
        )

        try:

            data = gzip.decompress(
                data
            )

        except Exception as error:

            raise RuntimeError(

                "Failed to decompress "
                f"{name}: {error}"

            )

    # ========================================================
    # 写入
    # ========================================================

    output.write_bytes(
        data
    )

    output.chmod(
        0o755
    )

    size = (
        output.stat()
        .st_size
    )

    print(
        f"Mihomo binary size: "
        f"{size} bytes"
    )

    # ========================================================
    # ELF 验证
    # ========================================================

    magic = output.read_bytes()[:4]

    if magic != b"\x7fELF":

        raise RuntimeError(

            "Downloaded Mihomo file is not "
            "a valid Linux ELF binary.\n"
            f"Asset: {name}\n"
            f"Magic: {magic!r}"

        )

    print(
        "OK: Valid Linux ELF binary."
    )

    # ========================================================
    # version
    # ========================================================

    result = subprocess.run(

        [
            str(output),
            "version"
        ],

        stdout=subprocess.PIPE,

        stderr=subprocess.PIPE,

        text=True,

        timeout=30

    )

    if result.returncode != 0:

        raise RuntimeError(

            "Mihomo binary failed to execute.\n"
            f"Return code: "
            f"{result.returncode}\n"
            f"STDOUT:\n"
            f"{result.stdout}\n"
            f"STDERR:\n"
            f"{result.stderr}"

        )

    print(
        result.stdout
    )


# ============================================================
# 合并 Meta
#
# Threads
# Facebook
# Instagram
#
# YAML
#   ↓
# 去重
#   ↓
# meta.txt
#   ↓
# Mihomo
#   ↓
# meta.mrs
# ============================================================

def merge_meta_rules():

    print()
    print("=" * 70)
    print("MERGE META RULES")
    print("=" * 70)

    target = (
        ROOT /
        "Mihomo"
    )

    archive = github_zip(
        "milangree",
        "rules",
        "main"
    )

    try:

        sources = find_meta_yaml_sources(
            archive
        )

        all_rules = set()

        statistics = {}

        for service in (
            "threads",
            "facebook",
            "instagram",
        ):

            info, relative = (
                sources[service]
            )

            print()
            print(
                f"READ: {relative}"
            )

            raw = archive.read(
                info
            )

            text = raw.decode(
                "utf-8"
            )

            rules = parse_payload_yaml(
                text
            )

            rules = [
                x.strip()
                for x in rules
                if x.strip()
            ]

            unique_rules = set(
                rules
            )

            statistics[
                service
            ] = len(
                unique_rules
            )

            print(
                f"{service.title()} rules: "
                f"{len(unique_rules)}"
            )

            if not unique_rules:

                raise RuntimeError(

                    f"{service} rules are empty:\n"
                    f"{relative}"

                )

            all_rules.update(
                unique_rules
            )

        total_source = sum(
            statistics.values()
        )

        unique_count = len(
            all_rules
        )

        print()
        print(
            "=" * 70
        )

        print(
            f"Threads rules:    "
            f"{statistics['threads']}"
        )

        print(
            f"Facebook rules:   "
            f"{statistics['facebook']}"
        )

        print(
            f"Instagram rules:  "
            f"{statistics['instagram']}"
        )

        print(
            f"Source total:     "
            f"{total_source}"
        )

        print(
            f"Unique rules:     "
            f"{unique_count}"
        )

        print(
            "=" * 70
        )

        if unique_count <= 1:

            raise RuntimeError(

                "Meta merge failed: "
                "only one unique rule."

            )

        # ====================================================
        # 临时目录
        # ====================================================

        with tempfile.TemporaryDirectory() as temp_dir:

            temp_dir = Path(
                temp_dir
            )

            source = (
                temp_dir /
                "meta.txt"
            )

            ordered = sorted(
                all_rules,
                key=lambda x: x.lower()
            )

            source.write_text(
                "\n".join(
                    ordered
                )
                +
                "\n",
                encoding="utf-8"
            )

            print(
                f"Meta source written: "
                f"{source}"
            )

            # =================================================
            # Mihomo
            # =================================================

            converter = (
                temp_dir /
                "mihomo"
            )

            download_mihomo_converter(
                converter
            )

            # =================================================
            # 转换
            # =================================================

            output = (
                temp_dir /
                "meta.mrs"
            )

            command = [

                str(converter),

                "convert-ruleset",

                "domain",

                "text",

                str(source),

                str(output),

            ]

            print()
            print(
                "CONVERT COMMAND:"
            )

            print(
                " ".join(
                    command
                )
            )

            result = subprocess.run(

                command,

                stdout=subprocess.PIPE,

                stderr=subprocess.PIPE,

                text=True,

                timeout=300

            )

            if result.stdout:

                print(
                    result.stdout
                )

            if result.stderr:

                print(
                    result.stderr
                )

            if result.returncode != 0:

                raise RuntimeError(

                    "Mihomo convert-ruleset failed.\n"
                    f"Return code: "
                    f"{result.returncode}\n"
                    f"STDOUT:\n"
                    f"{result.stdout}\n"
                    f"STDERR:\n"
                    f"{result.stderr}"

                )

            if not output.exists():

                raise RuntimeError(
                    "meta.mrs was not generated."
                )

            size = (
                output.stat()
                .st_size
            )

            if size < 100:

                raise RuntimeError(

                    "Generated meta.mrs is "
                    f"suspiciously small: {size} bytes"

                )

            final_output = (
                target /
                "meta.mrs"
            )

            shutil.copy2(
                output,
                final_output
            )

            print()
            print(
                "=" * 70
            )

            print(
                "META.MRS CREATED"
            )

            print(
                f"Rules: {unique_count}"
            )

            print(
                f"Size: "
                f"{size} bytes"
            )

            print(
                "=" * 70
            )

            # =================================================
            # 删除三个独立规则文件
            # =================================================

            for filename in (
                "threads.mrs",
                "facebook.mrs",
                "instagram.mrs",
            ):

                path = (
                    target /
                    filename
                )

                if path.exists():

                    path.unlink()

                    print(
                        f"REMOVE: {path}"
                    )

    finally:

        archive.close()


# ============================================================
# SingBox
# ============================================================

def sync_singbox():

    print()
    print("=" * 70)
    print("SYNC SINGBOX")
    print("=" * 70)

    target = (
        ROOT /
        "SingBox"
    )

    clean_dir(
        target
    )

    archive = github_zip(
        "milangree",
        "rules",
        "main"
    )

    try:

        used = set()

        count = 0

        for info in archive.infolist():

            if info.is_dir():
                continue

            relative = zip_relative_path(
                info.filename
            )

            parts = relative.parts

            if len(parts) < 3:
                continue

            if parts[0].lower() != "rules":
                continue

            if parts[1].lower() != "singbox":
                continue

            filename = parts[-1]

            if not filename.lower().endswith(
                ".srs"
            ):
                continue

            new_name = (
                filename.lower()
            )

            if new_name in used:

                raise RuntimeError(

                    f"SingBox filename collision: "
                    f"{new_name}"

                )

            used.add(
                new_name
            )

            output = (
                target /
                new_name
            )

            with archive.open(
                info
            ) as source:

                with output.open(
                    "wb"
                ) as destination:

                    shutil.copyfileobj(
                        source,
                        destination
                    )

            count += 1

        if count == 0:

            raise RuntimeError(
                "No SingBox SRS files found."
            )

        print(
            f"SingBox SRS: {count}"
        )

    finally:

        archive.close()


# ============================================================
# DustinWin Mihomo
# ============================================================

def sync_dustinwin_mihomo():

    print()
    print("=" * 70)
    print("SYNC DUSTINWIN MIHOMO")
    print("=" * 70)

    target = (
        ROOT /
        "DustinWin"
    )

    clean_dir(
        target
    )

    archive = github_zip(
        "DustinWin",
        "ruleset_geodata",
        "mihomo-ruleset"
    )

    try:

        count = 0

        used = set()

        for info in archive.infolist():

            if info.is_dir():
                continue

            relative = zip_relative_path(
                info.filename
            )

            filename = relative.name

            if not filename.lower().endswith(
                ".mrs"
            ):
                continue

            new_name = (
                filename.lower()
            )

            if new_name in used:

                raise RuntimeError(

                    f"DustinWin MRS collision: "
                    f"{new_name}"

                )

            used.add(
                new_name
            )

            output = (
                target /
                new_name
            )

            with archive.open(
                info
            ) as source:

                with output.open(
                    "wb"
                ) as destination:

                    shutil.copyfileobj(
                        source,
                        destination
                    )

            count += 1

        if count == 0:

            raise RuntimeError(
                "No DustinWin MRS files found."
            )

        print(
            f"DustinWin MRS: {count}"
        )

    finally:

        archive.close()


# ============================================================
# DustinWin SingBox
#
# Release:
# sing-box-ruleset-compatible
# ============================================================

def sync_dustinwin_singbox():

    print()
    print("=" * 70)
    print("SYNC DUSTINWIN SINGBOX")
    print("=" * 70)

    target = (
        ROOT /
        "DustinWin"
    )

    target.mkdir(
        parents=True,
        exist_ok=True
    )

    api = (
        "https://api.github.com/"
        "repos/DustinWin/ruleset_geodata/"
        "releases/tags/"
        "sing-box-ruleset-compatible"
    )

    response = request(
        "GET",
        api,
        timeout=120
    )

    release = response.json()

    assets = release.get(
        "assets",
        []
    )

    count = 0

    for asset in assets:

        name = asset.get(
            "name",
            ""
        )

        if not name.lower().endswith(
            ".srs"
        ):
            continue

        output = (
            target /
            name.lower()
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
            "No DustinWin SRS files found."
        )

    print(
        f"DustinWin SRS: {count}"
    )


# ============================================================
# GeoIP
# ============================================================

def sync_geoip():

    print()
    print("=" * 70)
    print("SYNC GEOIP")
    print("=" * 70)

    target = (
        ROOT /
        "geoip"
    )

    clean_dir(
        target
    )

    # MetaCubeX geo 数据仓库
    #
    # 通过 ZIP 避免 GitHub Contents API 429
    archive = github_zip(
        "MetaCubeX",
        "meta-rules-dat",
        "meta"
    )

    try:

        count = 0

        for info in archive.infolist():

            if info.is_dir():
                continue

            relative = zip_relative_path(
                info.filename
            )

            filename = relative.name

            if not filename.lower().endswith(
                ".mrs"
            ):
                continue

            if "geoip" not in str(
                relative
            ).lower():

                continue

            output = (
                target /
                filename.lower()
            )

            with archive.open(
                info
            ) as source:

                with output.open(
                    "wb"
                ) as destination:

                    shutil.copyfileobj(
                        source,
                        destination
                    )

            count += 1

        if count == 0:

            raise RuntimeError(
                "No GeoIP MRS files found."
            )

        print(
            f"GeoIP MRS: {count}"
        )

    finally:

        archive.close()


# ============================================================
# CNIP
#
# X-Shelby
#
# MRS + SRS
# ============================================================

def sync_cnip():

    print()
    print("=" * 70)
    print("SYNC CNIP")
    print("=" * 70)

    target = (
        ROOT /
        "cnip"
    )

    clean_dir(
        target
    )

    base = (
        "https://github.com/"
        "X-Shelby/geoip/"
        "releases/download/latest/"
    )

    files = (

        "cn.mrs",
        "cn_v4.mrs",
        "cn_v6.mrs",
        "cnip_all.mrs",

        "cn.srs",
        "cn_v4.srs",
        "cn_v6.srs",
        "cnip_all.srs",

    )

    for filename in files:

        download_file(

            base +
            filename,

            target /
            filename.lower()

        )

    print(
        f"CNIP files: {len(files)}"
    )


# ============================================================
# AdBlock
#
# 这里使用 217heidai/rules
#
# 如果你的实际 AdBlock 仓库不同，
# 只修改这三个变量即可。
# ============================================================

ADBLOCK_OWNER = "217heidai"

ADBLOCK_REPO = "rules"

ADBLOCK_BRANCH = "main"


def sync_adblock():

    print()
    print("=" * 70)
    print("SYNC ADBLOCK")
    print("=" * 70)

    target = (
        ROOT /
        "AdBlock"
    )

    clean_dir(
        target
    )

    archive = github_zip(
        ADBLOCK_OWNER,
        ADBLOCK_REPO,
        ADBLOCK_BRANCH
    )

    try:

        count = 0

        used = set()

        for info in archive.infolist():

            if info.is_dir():
                continue

            relative = zip_relative_path(
                info.filename
            )

            filename = relative.name

            if not filename.lower().endswith(
                (
                    ".mrs",
                    ".srs"
                )
            ):
                continue

            new_name = (
                filename.lower()
            )

            if new_name in used:

                raise RuntimeError(

                    f"AdBlock filename collision: "
                    f"{new_name}"

                )

            used.add(
                new_name
            )

            output = (
                target /
                new_name
            )

            with archive.open(
                info
            ) as source:

                with output.open(
                    "wb"
                ) as destination:

                    shutil.copyfileobj(
                        source,
                        destination
                    )

            count += 1

        if count == 0:

            raise RuntimeError(
                "No AdBlock MRS/SRS files found."
            )

        print(
            f"AdBlock files: {count}"
        )

    finally:

        archive.close()


# ============================================================
# 目录检查
# ============================================================

EXPECTED_DIRS = {

    "Mihomo",
    "SingBox",
    "DustinWin",
    "geoip",
    "cnip",
    "AdBlock",

}


def check_directories():

    print()
    print("=" * 70)
    print("CHECK DIRECTORIES")
    print("=" * 70)

    actual = {

        x.name

        for x in ROOT.iterdir()

        if x.is_dir()

    }

    missing = (
        EXPECTED_DIRS -
        actual
    )

    if missing:

        raise RuntimeError(

            "Missing directories:\n"
            +
            "\n".join(
                sorted(missing)
            )

        )

    extra = (
        actual -
        EXPECTED_DIRS
    )

    if extra:

        raise RuntimeError(

            "Unexpected directories:\n"
            +
            "\n".join(
                sorted(extra)
            )

        )

    for directory in ROOT.iterdir():

        if not directory.is_dir():
            continue

        subdirs = [
            x
            for x in directory.iterdir()
            if x.is_dir()
        ]

        if subdirs:

            raise RuntimeError(

                "Subdirectories detected:\n"
                +
                "\n".join(
                    str(x)
                    for x in subdirs
                )

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

                f"Filename is not lowercase: "
                f"{path}"

            )

    print(
        "OK: All filenames lowercase."
    )


# ============================================================
# 扩展名检查
# ============================================================

ALLOWED_EXTENSIONS = {

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


def check_extensions():

    print()
    print("=" * 70)
    print("CHECK EXTENSIONS")
    print("=" * 70)

    for directory_name, allowed in (
        ALLOWED_EXTENSIONS.items()
    ):

        directory = (
            ROOT /
            directory_name
        )

        for path in directory.iterdir():

            if not path.is_file():
                continue

            if path.suffix.lower() not in allowed:

                raise RuntimeError(

                    f"Invalid extension: "
                    f"{path}"

                )

    print(
        "OK: Extensions valid."
    )


# ============================================================
# Meta 检查
# ============================================================

def check_meta():

    print()
    print("=" * 70)
    print("CHECK META")
    print("=" * 70)

    directory = (
        ROOT /
        "Mihomo"
    )

    meta = (
        directory /
        "meta.mrs"
    )

    if not meta.exists():

        raise RuntimeError(
            "meta.mrs missing."
        )

    size = (
        meta.stat()
        .st_size
    )

    print(
        f"meta.mrs size: "
        f"{size} bytes"
    )

    if size < 100:

        raise RuntimeError(
            "meta.mrs is suspiciously small."
        )

    for filename in (
        "threads.mrs",
        "facebook.mrs",
        "instagram.mrs",
    ):

        path = (
            directory /
            filename
        )

        if path.exists():

            raise RuntimeError(

                f"Old Meta file still exists: "
                f"{filename}"

            )

    print(
        "OK: meta.mrs"
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

        x.name

        for x in directory.iterdir()

        if x.is_file()

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
        "OK: CNIP MRS + SRS."
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

    for name in (
        "Mihomo",
        "SingBox",
        "DustinWin",
        "geoip",
        "cnip",
        "AdBlock",
    ):

        directory = (
            ROOT /
            name
        )

        mrs = 0
        srs = 0

        for path in directory.iterdir():

            if not path.is_file():
                continue

            if path.suffix.lower() == ".mrs":
                mrs += 1

            elif path.suffix.lower() == ".srs":
                srs += 1

        total += (
            mrs +
            srs
        )

        print(
            f"{name:12} "
            f"MRS={mrs:4} "
            f"SRS={srs:4}"
        )

    print()
    print(
        f"TOTAL FILES: {total}"
    )


# ============================================================
# MAIN
# ============================================================

def main():

    print()
    print("=" * 70)
    print("VERION RULE SYNC")
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
    # Meta
    # --------------------------------------------------------

    merge_meta_rules()

    # --------------------------------------------------------
    # SingBox
    # --------------------------------------------------------

    sync_singbox()

    # --------------------------------------------------------
    # DustinWin MRS
    # --------------------------------------------------------

    sync_dustinwin_mihomo()

    # --------------------------------------------------------
    # DustinWin SRS
    # --------------------------------------------------------

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
    # 最终检查
    # --------------------------------------------------------

    check_directories()

    check_lowercase()

    check_extensions()

    check_meta()

    check_cnip()

    statistics()

    print()
    print("=" * 70)
    print("SYNC COMPLETE")
    print("=" * 70)


if __name__ == "__main__":

    main()
