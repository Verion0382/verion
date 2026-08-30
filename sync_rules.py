import io
import gzip
import shutil
import zipfile
import tempfile
import subprocess
from pathlib import Path

import requests


# ============================================================
# 基础配置
# ============================================================

ROOT = Path("rules")

HEADERS = {
    "User-Agent": "Verion-Rules-Sync/1.0",
    "Accept": "application/vnd.github+json",
}

TIMEOUT = 300

session = requests.Session()
session.headers.update(HEADERS)


# ============================================================
# 通用 HTTP
# ============================================================

def request(
    method,
    url,
    *,
    timeout=TIMEOUT,
    retries=4,
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

            # GitHub API 限流
            if response.status_code == 429:

                retry_after = response.headers.get(
                    "Retry-After",
                    "10"
                )

                print(
                    f"GitHub rate limit: "
                    f"waiting {retry_after}s..."
                )

                import time

                time.sleep(
                    int(retry_after)
                )

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

            if attempt < retries:

                import time

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

    path = Path(
        filename
    )

    parts = path.parts

    if len(parts) <= 1:

        return Path()

    # 去掉 GitHub ZIP 最外层目录
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
# Mihomo
# Milangree
#
# rules/mihomo/
#
# 每个服务一个子目录
#
# 只保存 MRS
# ============================================================

def mihomo_output_name(
    filename
):

    stem = Path(
        filename
    ).stem

    lower = stem.lower()

    # 不应该调用到 classical
    if lower.endswith(
        "_classical"
    ):

        return None

    # xxx_domain.mrs
    #
    # -> xxx.mrs

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

    # xxx_ipcidr.mrs
    #
    # -> xxxip.mrs

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

            # 必须位于 rules/mihomo/
            if len(parts) < 3:

                continue

            if parts[0].lower() != "rules":

                continue

            if parts[1].lower() != "mihomo":

                continue

            filename = parts[-1]

            # 只同步 MRS
            if not filename.lower().endswith(
                ".mrs"
            ):

                continue

            # 排除 classical
            if (
                "_classical."
                in filename.lower()
            ):

                print(
                    f"SKIP CLASSICAL: "
                    f"{relative}"
                )

                continue

            new_name = mihomo_output_name(
                filename
            )

            if not new_name:

                continue

            # 防止两个源文件重命名冲突
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

        print()
        print(
            f"Mihomo MRS files: {count}"
        )

    finally:

        archive.close()


# ============================================================
# 读取 Milangree YAML
#
# 不使用 PyYAML
# 因为这里的 YAML 结构非常简单：
#
# payload:
#   - +.example.com
#   - +.example.org
#
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

        if line.startswith(
            "#"
        ):

            continue

        if line == "payload:":

            inside_payload = True

            continue

        if not inside_payload:

            continue

        if line.startswith(
            "-"
        ):

            value = line[1:].strip()

            # 去掉 YAML 引号
            if (
                len(value) >= 2
                and
                value[0] == value[-1]
                and
                value[0] in (
                    "'",
                    '"'
                )
            ):

                value = value[1:-1]

            if value:

                rules.append(
                    value
                )

    return rules


# ============================================================
# 找到三个 Meta 源
#
# 实际结构：
#
# rules/mihomo/Facebook/
#     Facebook_domain.yaml
#
# rules/mihomo/Instagram/
#     Instagram_domain.yaml
#
# rules/mihomo/Threads/
#     Threads_domain.yaml
#
# ============================================================

META_SOURCES = {

    "threads": (
        "threads",
        "Threads_domain.yaml"
    ),

    "facebook": (
        "facebook",
        "Facebook_domain.yaml"
    ),

    "instagram": (
        "instagram",
        "Instagram_domain.yaml"
    ),

}


def find_meta_yaml_sources(
    archive
):

    found = {}

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

        if len(parts) < 4:

            continue

        if parts[0].lower() != "rules":

            continue

        if parts[1].lower() != "mihomo":

            continue

        filename = parts[-1]

        lower_filename = (
            filename.lower()
        )

        if not lower_filename.endswith(
            ".yaml"
        ):

            continue

        for service, (
            directory,
            wanted
        ) in META_SOURCES.items():

            if (
                filename.lower()
                ==
                wanted.lower()
            ):

                found[
                    service
                ] = (
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
# 不再使用：
#
# mihomo-linux-amd64-compatible
#
# 使用 GitHub Release API
# 自动找到当前版本：
#
# linux-amd64-v1
#
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

    for asset in assets:

        name = asset.get(
            "name",
            ""
        )

        lower = name.lower()

        # 优先 v1
        if (
            "linux-amd64-v1"
            in lower
            and
            "go" not in lower
        ):

            candidates.append(
                asset
            )

    # 如果没有 v1，再寻找 compatible
    if not candidates:

        for asset in assets:

            name = asset.get(
                "name",
                ""
            )

            lower = name.lower()

            if (
                "linux-amd64-compatible"
                in lower
            ):

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
        ]

        raise RuntimeError(

            "Cannot find Mihomo Linux AMD64 "
            "converter.\n\n"
            "Available assets:\n"
            +
            "\n".join(
                available
            )

        )

    asset = candidates[0]

    url = asset[
        "browser_download_url"
    ]

    print(
        f"Asset: {asset['name']}"
    )

    data = download_bytes(
        url
    )

    # Release 可能是 gzip
    if data[:2] == b"\x1f\x8b":

        data = gzip.decompress(
            data
        )

    output.write_bytes(
        data
    )

    output.chmod(
        0o755
    )

    # 测试二进制
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

            "Downloaded Mihomo binary "
            "cannot execute.\n"
            f"STDOUT:\n{result.stdout}\n"
            f"STDERR:\n{result.stderr}"

        )

    print(
        result.stdout
    )


# ============================================================
# Meta 合并
#
# 三个 domain YAML
#       ↓
# 提取 payload
#       ↓
# 去重
#       ↓
# meta.txt
#       ↓
# Mihomo convert-ruleset
#       ↓
# meta.mrs
# ============================================================

def merge_meta_rules():

    print()
    print("=" * 70)
    print("MERGE THREADS + FACEBOOK + INSTAGRAM")
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

        for service in [
            "threads",
            "facebook",
            "instagram",
        ]:

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
                "utf-8",
                errors="strict"
            )

            rules = parse_payload_yaml(
                text
            )

            # 去除空值
            rules = [
                x.strip()
                for x in rules
                if x.strip()
            ]

            # 当前服务去重
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

                    f"{service} source is empty: "
                    f"{relative}"

                )

            all_rules.update(
                unique_rules
            )

        # ====================================================
        # 合并结果检查
        # ====================================================

        total_source = sum(
            statistics.values()
        )

        unique_count = len(
            all_rules
        )

        print()
        print(
            "------------------------------------------"
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
            "------------------------------------------"
        )

        if unique_count <= 1:

            raise RuntimeError(

                "META MERGE FAILED: "
                "only one unique rule was found."

            )

        # ====================================================
        # 写入临时 text
        # ====================================================

        with tempfile.TemporaryDirectory() as tmp:

            tmp = Path(
                tmp
            )

            source = (
                tmp /
                "meta.txt"
            )

            # 排序保证每次构建结果稳定
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

            print()
            print(
                f"Meta source written: "
                f"{source}"
            )

            # =================================================
            # Mihomo
            # =================================================

            converter = (
                tmp /
                "mihomo"
            )

            download_mihomo_converter(
                converter
            )

            # =================================================
            # 输出临时文件
            # =================================================

            temp_output = (
                tmp /
                "meta.mrs"
            )

            command = [

                str(converter),

                "convert-ruleset",

                "domain",

                "text",

                str(source),

                str(temp_output),

            ]

            print()
            print(
                "CONVERT:"
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

            if not temp_output.exists():

                raise RuntimeError(
                    "meta.mrs was not generated."
                )

            size = (
                temp_output.stat()
                .st_size
            )

            if size < 100:

                raise RuntimeError(

                    "meta.mrs is suspiciously small: "
                    f"{size} bytes"

                )

            # =================================================
            # 替换正式文件
            # =================================================

            final_output = (
                target /
                "meta.mrs"
            )

            shutil.copy2(
                temp_output,
                final_output
            )

            print()
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

            # =================================================
            # 删除三个独立文件
            # =================================================

            for filename in [

                "threads.mrs",
                "facebook.mrs",
                "instagram.mrs",

            ]:

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
#
# 分支：
# mihomo-ruleset
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
#
# MetaCubeX meta-rules-dat
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

    # 官方 geoip MRS
    #
    # 使用 GitHub 仓库 ZIP
    # 避免 GitHub Contents API 429

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

            parts = relative.parts

            if len(parts) < 3:

                continue

            if parts[0].lower() != "geo":

                continue

            if parts[1].lower() != "geoip":

                continue

            filename = parts[-1]

            if not filename.lower().endswith(
                ".mrs"
            ):

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

    required = [

        "cn.mrs",
        "cn_v4.mrs",
        "cn_v6.mrs",
        "cnip_all.mrs",

        "cn.srs",
        "cn_v4.srs",
        "cn_v6.srs",
        "cnip_all.srs",

    ]

    for filename in required:

        download_file(

            base +
            filename,

            target /
            filename.lower()

        )

    print(
        f"CNIP files: "
        f"{len(required)}"
    )


# ============================================================
# AdBlock
#
# 这里保留 MRS + SRS
#
# 如果你的 AdBlock 来源仓库不同，
# 只需要修改下面三个常量。
# ============================================================

ADBLOCK_OWNER = "217heidai"

ADBLOCK_REPO = "adblockfilters"

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
# 检查目录
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

    if not ROOT.exists():

        raise RuntimeError(
            "rules directory missing."
        )

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

    # 不允许 rules/ 下出现额外目录
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

    # 每个目录都不能再有子目录
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
# 检查文件名全部小写
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
        "OK: All filenames are lowercase."
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

            suffix = (
                path.suffix.lower()
            )

            if suffix not in allowed:

                raise RuntimeError(

                    f"Invalid extension: "
                    f"{path}"

                )

    print(
        "OK: Extensions are valid."
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
            "meta.mrs is too small."
        )

    # 不能继续存在三个独立规则
    for filename in [

        "threads.mrs",
        "facebook.mrs",
        "instagram.mrs",

    ]:

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
        "OK: CNIP MRS + SRS"
    )


# ============================================================
# 规则统计
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
                path.suffix.lower()
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
            f"{directory_name:12} "
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
    print("VERION RULE SYNC")
    print("=" * 70)

    ROOT.mkdir(
        parents=True,
        exist_ok=True
    )

    # --------------------------------------------------------
    # 1. Mihomo
    # --------------------------------------------------------

    sync_mihomo()

    # --------------------------------------------------------
    # 2. Meta 合并
    #
    # 必须在 Mihomo 同步之后执行
    # --------------------------------------------------------

    merge_meta_rules()

    # --------------------------------------------------------
    # 3. SingBox
    # --------------------------------------------------------

    sync_singbox()

    # --------------------------------------------------------
    # 4. DustinWin Mihomo
    # --------------------------------------------------------

    sync_dustinwin_mihomo()

    # --------------------------------------------------------
    # 5. DustinWin SingBox
    # --------------------------------------------------------

    sync_dustinwin_singbox()

    # --------------------------------------------------------
    # 6. GeoIP
    # --------------------------------------------------------

    sync_geoip()

    # --------------------------------------------------------
    # 7. CNIP
    # --------------------------------------------------------

    sync_cnip()

    # --------------------------------------------------------
    # 8. AdBlock
    # --------------------------------------------------------

    sync_adblock()

    # ========================================================
    # 最终检查
    # ========================================================

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
