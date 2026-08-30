import io
import gzip
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

TIMEOUT = 300


# ============================================================
# 下载
# ============================================================

def download_bytes(url):

    print(f"DOWNLOAD: {url}")

    response = session.get(
        url,
        timeout=TIMEOUT
    )

    response.raise_for_status()

    return response.content


def download_file(url, output):

    data = download_bytes(url)

    output.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    output.write_bytes(data)

    print(f"OK: {output}")


# ============================================================
# 清空目录
# ============================================================

def clean_dir(path):

    if path.exists():

        shutil.rmtree(path)

    path.mkdir(
        parents=True,
        exist_ok=True
    )


# ============================================================
# ZIP
# ============================================================

def download_zip(url):

    data = download_bytes(url)

    return zipfile.ZipFile(
        io.BytesIO(data)
    )


def safe_path(name):

    path = Path(name)

    if ".." in path.parts:

        raise RuntimeError(
            f"Unsafe ZIP path: {name}"
        )

    return path


# ============================================================
# 获取 ZIP 文件
# ============================================================

def zip_files(
    archive,
    prefix=""
):

    prefix = prefix.strip("/")

    result = []

    for info in archive.infolist():

        if info.is_dir():

            continue

        path = safe_path(
            info.filename
        )

        parts = path.parts

        if len(parts) < 2:

            continue

        # 去掉 GitHub ZIP 最外层目录
        relative = Path(
            *parts[1:]
        )

        if prefix:

            try:

                relative_file = (
                    relative.relative_to(
                        prefix
                    )
                )

            except ValueError:

                continue

        else:

            relative_file = relative

        result.append(
            (
                info,
                relative_file
            )
        )

    return result


# ============================================================
# Mihomo 文件命名
# ============================================================

def rename_mihomo(filename):

    stem = Path(
        filename
    ).stem

    lower = stem.lower()

    if lower.endswith(
        "_domain"
    ):

        base = stem[
            :-len("_domain")
        ]

        return (
            base.lower() +
            ".mrs"
        )

    if lower.endswith(
        "_ipcidr"
    ):

        base = stem[
            :-len("_ipcidr")
        ]

        return (
            base.lower() +
            "ip.mrs"
        )

    return (
        stem.lower() +
        ".mrs"
    )


def is_classical(filename):

    return (
        Path(filename)
        .stem
        .lower()
        .endswith(
            "_classical"
        )
    )


# ============================================================
# 同步 Mihomo
# ============================================================

def sync_mihomo():

    print()
    print("=" * 70)
    print("MIHOMO")
    print("=" * 70)

    target = (
        ROOT /
        "Mihomo"
    )

    clean_dir(
        target
    )

    url = (
        "https://github.com/"
        "milangree/rules/"
        "archive/refs/heads/main.zip"
    )

    archive = download_zip(
        url
    )

    try:

        files = zip_files(
            archive,
            "rules/mihomo"
        )

        used = {}

        count = 0

        for info, relative in files:

            name = relative.name

            if not name.lower().endswith(
                ".mrs"
            ):

                continue

            if is_classical(name):

                print(
                    f"SKIP CLASSICAL: "
                    f"{relative}"
                )

                continue

            new_name = rename_mihomo(
                name
            )

            if new_name in used:

                raise RuntimeError(
                    "\n"
                    "Mihomo filename collision:\n"
                    f"{new_name}\n\n"
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

                with open(
                    output,
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
            f"Mihomo files: {count}"
        )

    finally:

        archive.close()


# ============================================================
# 查找 Milangree 原始规则
#
# 用于 Meta 合并
# ============================================================

def find_meta_sources(archive):

    wanted = {

        "threads",
        "facebook",
        "instagram",

    }

    found = {}

    for info, relative in zip_files(
        archive,
        "rules/mihomo"
    ):

        filename = relative.name

        stem = Path(
            filename
        ).stem.lower()

        # 排除 classical
        if stem.endswith(
            "_classical"
        ):

            continue

        # domain
        if stem.endswith(
            "_domain"
        ):

            service = stem[
                :-len("_domain")
            ]

            if service in wanted:

                found[
                    service
                ] = (
                    info,
                    relative
                )

    missing = (
        wanted -
        set(found)
    )

    if missing:

        raise RuntimeError(

            "Cannot find original "
            "domain rule sources:\n"
            +
            "\n".join(
                sorted(missing)
            )

        )

    return found


# ============================================================
# 下载当前 Mihomo
#
# 不再使用错误的：
#
# mihomo-linux-amd64-compatible
#
# 通过 GitHub Release API 找到当前
# linux-amd64-v1 的 gzip 包。
#
# 官方目前使用 v1/v2/v3 标识 AMD64
# ============================================================

def download_mihomo_binary(
    output
):

    print()
    print(
        "=" * 70
    )

    print(
        "DOWNLOAD MIHOMO CONVERTER"
    )

    print(
        "=" * 70
    )

    api = (
        "https://api.github.com/repos/"
        "MetaCubeX/mihomo/releases/latest"
    )

    response = session.get(
        api,
        timeout=120
    )

    response.raise_for_status()

    release = response.json()

    tag = release.get(
        "tag_name",
        ""
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

        if (
            "linux-amd64-v1"
            in lower
            and
            lower.endswith(
                ".gz"
            )
        ):

            candidates.append(
                asset
            )

    if not candidates:

        # 某些版本可能没有 v1
        # 尝试 linux-amd64
        for asset in assets:

            name = asset.get(
                "name",
                ""
            )

            lower = name.lower()

            if (
                "linux-amd64"
                in lower
                and
                "v2"
                not in lower
                and
                "v3"
                not in lower
                and
                lower.endswith(
                    ".gz"
                )
            ):

                candidates.append(
                    asset
                )

    if not candidates:

        names = [
            x.get(
                "name",
                ""
            )
            for x in assets
        ]

        raise RuntimeError(

            "Cannot find compatible "
            "Mihomo Linux AMD64 asset.\n\n"
            "Available assets:\n"
            +
            "\n".join(names)

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

    try:

        binary = gzip.decompress(
            data
        )

    except gzip.BadGzipFile:

        raise RuntimeError(
            "Mihomo asset is not gzip."
        )

    output.write_bytes(
        binary
    )

    output.chmod(
        0o755
    )

    print(
        f"Mihomo binary: {output}"
    )


# ============================================================
# 合并 Threads + Facebook + Instagram
#
# 目标：
#
# meta.mrs
#
# 注意：
#
# 不直接合并已有 MRS 二进制。
#
# 从 ZIP 中寻找原始 domain 规则，
# 合并后重新编译。
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

    archive = download_zip(
        "https://github.com/"
        "milangree/rules/"
        "archive/refs/heads/main.zip"
    )

    try:

        sources = find_meta_sources(
            archive
        )

        with tempfile.TemporaryDirectory() as tmp:

            tmp = Path(tmp)

            source_text = (
                tmp /
                "meta.txt"
            )

            rules = set()

            # ------------------------------------------------
            # 提取三个原始 domain 文件
            # ------------------------------------------------

            for service in [
                "threads",
                "facebook",
                "instagram",
            ]:

                info, relative = (
                    sources[service]
                )

                print(
                    f"READ: {relative}"
                )

                raw = archive.read(
                    info
                )

                text = raw.decode(
                    "utf-8",
                    errors="ignore"
                )

                for line in text.splitlines():

                    line = line.strip()

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
                    "Meta source rules are empty."
                )

            # ------------------------------------------------
            # 排序
            # ------------------------------------------------

            rules = sorted(
                rules,
                key=lambda x: x.lower()
            )

            source_text.write_text(
                "\n".join(rules) +
                "\n",
                encoding="utf-8"
            )

            print(
                f"META RULE COUNT: "
                f"{len(rules)}"
            )

            # ------------------------------------------------
            # Mihomo
            # ------------------------------------------------

            mihomo = (
                tmp /
                "mihomo"
            )

            download_mihomo_binary(
                mihomo
            )

            # ------------------------------------------------
            # 编译
            #
            # 官方格式：
            #
            # mihomo convert-ruleset
            # domain
            # text
            # input.txt
            # output.mrs
            # ------------------------------------------------

            output = (
                mihomo_dir /
                "meta.mrs"
            )

            command = [

                str(mihomo),

                "convert-ruleset",

                "domain",

                "text",

                str(source_text),

                str(output),

            ]

            print()
            print(
                "COMPILE META.MRS"
            )

            print(
                " ".join(command)
            )

            result = subprocess.run(

                command,

                stdout=subprocess.PIPE,

                stderr=subprocess.PIPE,

                text=True,

                timeout=180

            )

            if result.stdout:

                print(
                    result.stdout
                )

            if result.stderr:

                print(
                    result.stderr
                )

            if (
                result.returncode != 0
                or
                not output.exists()
                or
                output.stat().st_size == 0
            ):

                raise RuntimeError(

                    "Failed to compile "
                    "meta.mrs.\n"
                    f"Return code: "
                    f"{result.returncode}\n"
                    f"STDOUT:\n"
                    f"{result.stdout}\n"
                    f"STDERR:\n"
                    f"{result.stderr}"

                )

            # ------------------------------------------------
            # 删除原三个文件
            # ------------------------------------------------

            for filename in [

                "threads.mrs",
                "facebook.mrs",
                "instagram.mrs",

            ]:

                path = (
                    mihomo_dir /
                    filename
                )

                if path.exists():

                    path.unlink()

            print()
            print(
                "META.MRS CREATED:"
            )

            print(
                output
            )

            print(
                f"SIZE: "
                f"{output.stat().st_size} bytes"
            )

    finally:

        archive.close()


# ============================================================
# SingBox
# ============================================================

def sync_singbox():

    print()
    print("=" * 70)
    print("SINGBOX")
    print("=" * 70)

    target = (
        ROOT /
        "SingBox"
    )

    clean_dir(
        target
    )

    archive = download_zip(
        "https://github.com/"
        "milangree/rules/"
        "archive/refs/heads/main.zip"
    )

    try:

        count = 0

        used = set()

        for info, relative in zip_files(
            archive,
            "rules/singbox"
        ):

            name = relative.name

            if not name.lower().endswith(
                ".srs"
            ):

                continue

            new_name = (
                name.lower()
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

                with open(
                    output,
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
                "No SingBox SRS found."
            )

        print(
            f"SingBox files: {count}"
        )

    finally:

        archive.close()


# ============================================================
# DustinWin Mihomo
# ============================================================

def sync_dustinwin_mihomo():

    print()
    print("=" * 70)
    print("DUSTINWIN MIHOMO")
    print("=" * 70)

    target = (
        ROOT /
        "DustinWin"
    )

    clean_dir(
        target
    )

    archive = download_zip(
        "https://github.com/"
        "DustinWin/ruleset_geodata/"
        "archive/refs/heads/"
        "mihomo-ruleset.zip"
    )

    try:

        count = 0

        used = set()

        for info, relative in zip_files(
            archive
        ):

            name = relative.name

            if not name.lower().endswith(
                ".mrs"
            ):

                continue

            new_name = (
                name.lower()
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

                with open(
                    output,
                    "wb"
                ) as destination:

                    shutil.copyfileobj(
                        source,
                        destination
                    )

            count += 1

        if count == 0:

            raise RuntimeError(
                "No DustinWin MRS found."
            )

        print(
            f"DustinWin MRS: {count}"
        )

    finally:

        archive.close()


# ============================================================
# DustinWin SingBox
# ============================================================

def sync_dustinwin_singbox():

    print()
    print("=" * 70)
    print("DUSTINWIN SINGBOX")
    print("=" * 70)

    target = (
        ROOT /
        "DustinWin"
    )

    ensure = target.mkdir(
        parents=True,
        exist_ok=True
    )

    api = (
        "https://api.github.com/repos/"
        "DustinWin/ruleset_geodata/"
        "releases/tags/"
        "sing-box-ruleset-compatible"
    )

    response = session.get(
        api,
        timeout=120
    )

    response.raise_for_status()

    assets = response.json().get(
        "assets",
        []
    )

    count = 0

    existing = {

        x.name

        for x in target.iterdir()

        if x.is_file()

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
                f"DustinWin SRS collision: "
                f"{new_name}"
            )

        download_file(

            asset[
                "browser_download_url"
            ],

            target /
            new_name

        )

        existing.add(
            new_name
        )

        count += 1

    if count == 0:

        raise RuntimeError(
            "No DustinWin SRS found."
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
    print("GEOIP")
    print("=" * 70)

    target = (
        ROOT /
        "geoip"
    )

    clean_dir(
        target
    )

    archive = download_zip(
        "https://github.com/"
        "MetaCubeX/meta-rules-dat/"
        "archive/refs/heads/meta.zip"
    )

    try:

        count = 0

        for info, relative in zip_files(
            archive,
            "geo/geoip"
        ):

            name = relative.name

            if not name.lower().endswith(
                ".mrs"
            ):

                continue

            new_name = (
                name.lower()
            )

            output = (
                target /
                new_name
            )

            with archive.open(
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

        if count == 0:

            raise RuntimeError(
                "No GeoIP MRS found."
            )

        print(
            f"GeoIP MRS: {count}"
        )

    finally:

        archive.close()


# ============================================================
# CNIP
# ============================================================

def sync_cnip():

    print()
    print("=" * 70)
    print("CNIP")
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

            base +
            filename,

            target /
            filename.lower()

        )


# ============================================================
# AdBlock
# ============================================================

def sync_adblock():

    print()
    print("=" * 70)
    print("ADBLOCK")
    print("=" * 70)

    target = (
        ROOT /
        "AdBlock"
    )

    clean_dir(
        target
    )

    archive = download_zip(
        "https://github.com/"
        "217heidai/adblockfilters/"
        "archive/refs/heads/main.zip"
    )

    try:

        count = 0

        used = set()

        for info, relative in zip_files(
            archive
        ):

            name = relative.name

            if not name.lower().endswith(
                (
                    ".mrs",
                    ".srs"
                )
            ):

                continue

            new_name = (
                name.lower()
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

                with open(
                    output,
                    "wb"
                ) as destination:

                    shutil.copyfileobj(
                        source,
                        destination
                    )

            count += 1

        if count == 0:

            raise RuntimeError(
                "No AdBlock MRS/SRS found."
            )

        print(
            f"AdBlock files: {count}"
        )

    finally:

        archive.close()


# ============================================================
# 检查目录
# ============================================================

def check_directories():

    expected = {

        "Mihomo",
        "SingBox",
        "DustinWin",
        "geoip",
        "cnip",
        "AdBlock",

    }

    actual = {

        p.name

        for p in ROOT.iterdir()

        if p.is_dir()

    }

    if actual != expected:

        raise RuntimeError(

            "Directory structure error.\n"
            f"Expected: {sorted(expected)}\n"
            f"Actual: {sorted(actual)}"

        )

    for directory in ROOT.iterdir():

        for path in directory.iterdir():

            if path.is_dir():

                raise RuntimeError(

                    f"Subdirectory detected: "
                    f"{path}"

                )


# ============================================================
# 小写检查
# ============================================================

def check_lowercase():

    for path in ROOT.rglob("*"):

        if not path.is_file():

            continue

        if path.name != path.name.lower():

            raise RuntimeError(

                f"Filename is not lowercase: "
                f"{path}"

            )


# ============================================================
# 扩展名检查
# ============================================================

def check_extensions():

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

                    f"Invalid extension: "
                    f"{path}"

                )


# ============================================================
# Meta 检查
# ============================================================

def check_meta():

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

    if meta.stat().st_size == 0:

        raise RuntimeError(
            "meta.mrs is empty."
        )

    for filename in [

        "threads.mrs",
        "facebook.mrs",
        "instagram.mrs",

    ]:

        if (
            directory /
            filename
        ).exists():

            raise RuntimeError(

                f"Old Meta file still exists: "
                f"{filename}"

            )


# ============================================================
# CNIP 检查
# ============================================================

def check_cnip():

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

        p.name

        for p in directory.iterdir()

        if p.is_file()

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


# ============================================================
# 统计
# ============================================================

def statistics():

    print()
    print("=" * 70)
    print("FINAL STATISTICS")
    print("=" * 70)

    total = 0

    for name in [

        "Mihomo",
        "SingBox",
        "DustinWin",
        "geoip",
        "cnip",
        "AdBlock",

    ]:

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
            f"{name:15}"
            f"MRS={mrs:4} "
            f"SRS={srs:4}"
        )

    print()
    print(
        f"TOTAL: {total}"
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

    # 1
    sync_mihomo()

    # 2
    merge_meta_rules()

    # 3
    sync_singbox()

    # 4
    sync_dustinwin_mihomo()

    # 5
    sync_dustinwin_singbox()

    # 6
    sync_geoip()

    # 7
    sync_cnip()

    # 8
    sync_adblock()

    # --------------------------------------------------------
    # 检查
    # --------------------------------------------------------

    check_directories()

    check_lowercase()

    check_extensions()

    check_meta()

    check_cnip()

    # --------------------------------------------------------
    # 统计
    # --------------------------------------------------------

    statistics()

    print()
    print("=" * 70)
    print("SYNC COMPLETE")
    print("=" * 70)


if __name__ == "__main__":

    main()
