#!/usr/bin/env python3

import io
import shutil
import tempfile
import time
import zipfile

from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import requests


# ============================================================
# 基础配置
# ============================================================

ROOT = Path("rules")

MAX_WORKERS = 8

REQUEST_TIMEOUT = 180

ZIP_TIMEOUT = 600

RETRIES = 3


# ============================================================
# HTTP
# ============================================================

HEADERS = {
    "User-Agent": "Verion-Rules-Sync/3.0",
    "Accept": "*/*",
}

GITHUB_HEADERS = {
    "User-Agent": "Verion-Rules-Sync/3.0",
    "Accept": "application/vnd.github+json",
}


session = requests.Session()

session.headers.update(
    HEADERS
)


# ============================================================
# HTTP GET
# ============================================================

def http_get(
    url,
    *,
    timeout=REQUEST_TIMEOUT,
    github=False,
    retries=RETRIES,
):

    headers = (
        GITHUB_HEADERS
        if github
        else HEADERS
    )

    last_error = None

    for attempt in range(
        1,
        retries + 1,
    ):

        try:

            response = session.get(
                url,
                headers=headers,
                timeout=timeout,
            )

            # ------------------------------------------------
            # GitHub 限流
            # ------------------------------------------------

            if response.status_code in (
                403,
                429,
            ):

                retry_after = (
                    response.headers.get(
                        "Retry-After"
                    )
                )

                try:

                    wait = int(
                        retry_after
                    )

                except (
                    TypeError,
                    ValueError,
                ):

                    wait = min(
                        5 * attempt,
                        20,
                    )

                print(
                    f"HTTP {response.status_code} "
                    f"retry after {wait}s"
                )

                time.sleep(
                    wait
                )

                continue

            response.raise_for_status()

            return response

        except Exception as error:

            last_error = error

            print(
                f"DOWNLOAD ERROR "
                f"({attempt}/{retries})"
            )

            print(
                url
            )

            print(
                error
            )

            if attempt < retries:

                wait = min(
                    2 * attempt,
                    8,
                )

                time.sleep(
                    wait
                )

    raise RuntimeError(
        "Failed to download:\n"
        f"{url}\n"
        f"{last_error}"
    )


# ============================================================
# 下载文件
# ============================================================

def download_file(
    url,
    output,
    *,
    timeout=REQUEST_TIMEOUT,
):

    response = http_get(
        url,
        timeout=timeout,
    )

    data = response.content

    if len(data) < 100:

        raise RuntimeError(
            "Downloaded file is too small:\n"
            f"{url}\n"
            f"Size: {len(data)} bytes"
        )

    output.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    output.write_bytes(
        data
    )

    print(
        f"OK: {output} "
        f"({len(data)} bytes)"
    )


# ============================================================
# 下载 GitHub ZIP
# ============================================================

def download_github_zip(
    owner,
    repo,
    branch,
):

    url = (
        f"https://github.com/"
        f"{owner}/{repo}/"
        f"archive/refs/heads/"
        f"{branch}.zip"
    )

    print()
    print(
        "=" * 70
    )

    print(
        "DOWNLOAD GITHUB ZIP"
    )

    print(
        url
    )

    response = http_get(
        url,
        timeout=ZIP_TIMEOUT,
    )

    data = response.content

    if len(data) < 100:

        raise RuntimeError(
            f"GitHub ZIP is too small:\n"
            f"{url}"
        )

    try:

        archive = zipfile.ZipFile(
            io.BytesIO(data)
        )

    except zipfile.BadZipFile as error:

        raise RuntimeError(
            f"Invalid GitHub ZIP:\n"
            f"{url}"
        ) from error

    print(
        f"ZIP size: "
        f"{len(data) / 1024 / 1024:.2f} MB"
    )

    return archive


# ============================================================
# ZIP 路径
# ============================================================

def zip_relative_path(
    filename,
):

    parts = Path(
        filename
    ).parts

    if len(parts) <= 1:

        return Path()

    return Path(
        *parts[1:]
    )


# ============================================================
# 临时目录
# ============================================================

def replace_directory(
    source,
    target,
):

    target = Path(
        target
    )

    if target.exists():

        shutil.rmtree(
            target
        )

    target.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    shutil.move(
        str(source),
        str(target),
    )


# ============================================================
# Mihomo 文件重命名
# ============================================================

def mihomo_filename(
    filename,
):

    path = Path(
        filename
    )

    stem = path.stem.lower()

    # --------------------------------------------------------
    # classical 不同步
    # --------------------------------------------------------

    if stem.endswith(
        "_classical"
    ):

        return None

    # --------------------------------------------------------
    # domain
    #
    # YouTube_domain.mrs
    #       ↓
    # youtube.mrs
    # --------------------------------------------------------

    if stem.endswith(
        "_domain"
    ):

        name = stem[
            :-len("_domain")
        ]

        return (
            name +
            ".mrs"
        )

    # --------------------------------------------------------
    # ipcidr
    #
    # YouTube_ipcidr.mrs
    #       ↓
    # youtubeip.mrs
    # --------------------------------------------------------

    if stem.endswith(
        "_ipcidr"
    ):

        name = stem[
            :-len("_ipcidr")
        ]

        return (
            name +
            "ip.mrs"
        )

    # --------------------------------------------------------
    # 普通 MRS
    # --------------------------------------------------------

    return (
        stem +
        ".mrs"
    )


# ============================================================
# 处理 milangree
#
# 一个 ZIP
# 同时处理 Mihomo + SingBox
# ============================================================

def sync_milangree(
    archive,
    staging_root,
):

    print()
    print(
        "=" * 70
    )

    print(
        "SYNC MILANGREE"
    )

    print(
        "=" * 70
    )

    mihomo_dir = (
        staging_root /
        "Mihomo"
    )

    singbox_dir = (
        staging_root /
        "SingBox"
    )

    mihomo_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    singbox_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    mihomo_count = 0
    singbox_count = 0

    mihomo_names = {}
    singbox_names = {}

    for info in archive.infolist():

        if info.is_dir():
            continue

        relative = zip_relative_path(
            info.filename
        )

        parts = [
            x.lower()
            for x in relative.parts
        ]

        if len(parts) < 3:
            continue

        if parts[0] != "rules":
            continue

        category = parts[1]

        filename = relative.name

        # ====================================================
        # Mihomo
        # ====================================================

        if category == "mihomo":

            if not filename.lower().endswith(
                ".mrs"
            ):
                continue

            new_name = mihomo_filename(
                filename
            )

            if new_name is None:

                print(
                    f"SKIP CLASSICAL: "
                    f"{relative}"
                )

                continue

            if new_name in mihomo_names:

                raise RuntimeError(
                    "Mihomo filename collision:\n"
                    f"{mihomo_names[new_name]}\n"
                    f"{relative}\n"
                    f"Target: {new_name}"
                )

            mihomo_names[
                new_name
            ] = str(relative)

            output = (
                mihomo_dir /
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
                        destination,
                    )

            print(
                f"MIHOMO: "
                f"{relative} -> "
                f"{new_name}"
            )

            mihomo_count += 1

        # ====================================================
        # SingBox
        # ====================================================

        elif category in (
            "singbox",
            "sing-box",
        ):

            if not filename.lower().endswith(
                ".srs"
            ):
                continue

            new_name = (
                filename.lower()
            )

            if new_name in singbox_names:

                raise RuntimeError(
                    "SingBox filename collision:\n"
                    f"{singbox_names[new_name]}\n"
                    f"{relative}\n"
                    f"Target: {new_name}"
                )

            singbox_names[
                new_name
            ] = str(relative)

            output = (
                singbox_dir /
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
                        destination,
                    )

            print(
                f"SINGBOX: "
                f"{relative} -> "
                f"{new_name}"
            )

            singbox_count += 1

    if mihomo_count == 0:

        raise RuntimeError(
            "No Mihomo MRS files found "
            "in milangree/rules."
        )

    if singbox_count == 0:

        raise RuntimeError(
            "No SingBox SRS files found "
            "in milangree/rules."
        )

    print()
    print(
        f"Mihomo : {mihomo_count}"
    )

    print(
        f"SingBox: {singbox_count}"
    )


# ============================================================
# Meta
#
# Facebook -> meta.mrs
# Threads / Instagram 不同步
# ============================================================

def sync_meta(
    staging_root,
):

    print()
    print(
        "=" * 70
    )

    print(
        "SYNC META"
    )

    print(
        "=" * 70
    )

    directory = (
        staging_root /
        "Mihomo"
    )

    directory.mkdir(
        parents=True,
        exist_ok=True,
    )

    url = (
        "https://cdn.jsdelivr.net/gh/"
        "Verion0382/verion@main/"
        "rules/Mihomo/facebook.mrs"
    )

    output = (
        directory /
        "meta.mrs"
    )

    response = http_get(
        url,
        timeout=180,
    )

    data = response.content

    if len(data) < 100:

        raise RuntimeError(
            "Facebook MRS is too small."
        )

    output.write_bytes(
        data
    )

    print(
        "facebook.mrs -> meta.mrs"
    )

    # --------------------------------------------------------
    # 删除旧 Meta 文件
    # --------------------------------------------------------

    for old_name in (
        "facebook.mrs",
        "threads.mrs",
        "instagram.mrs",
    ):

        old_file = (
            directory /
            old_name
        )

        if old_file.exists():

            old_file.unlink()

            print(
                f"REMOVE: "
                f"{old_name}"
            )


# ============================================================
# GitHub Release Assets
# ============================================================

def github_release_assets(
    owner,
    repo,
    tag,
):

    api_url = (
        f"https://api.github.com/"
        f"repos/{owner}/{repo}/"
        f"releases/tags/{tag}"
    )

    print()
    print(
        "GET RELEASE:"
    )

    print(
        api_url
    )

    response = http_get(
        api_url,
        timeout=120,
        github=True,
    )

    data = response.json()

    assets = data.get(
        "assets",
        []
    )

    if not assets:

        raise RuntimeError(
            "Release has no assets:\n"
            f"{owner}/{repo}:{tag}"
        )

    result = {}

    for asset in assets:

        name = asset.get(
            "name",
            ""
        )

        url = asset.get(
            "browser_download_url"
        )

        if not name or not url:
            continue

        result[
            name.lower()
        ] = url

    return result


# ============================================================
# DustinWin
#
# mihomo-ruleset
# sing-box-ruleset-compatible
# ============================================================

def sync_dustinwin(
    staging_root,
):

    print()
    print(
        "=" * 70
    )

    print(
        "SYNC DUSTINWIN"
    )

    print(
        "=" * 70
    )

    directory = (
        staging_root /
        "DustinWin"
    )

    directory.mkdir(
        parents=True,
        exist_ok=True,
    )

    jobs = []

    # --------------------------------------------------------
    # Mihomo MRS
    # --------------------------------------------------------

    mrs_assets = github_release_assets(
        "DustinWin",
        "ruleset_geodata",
        "mihomo-ruleset",
    )

    for name, url in mrs_assets.items():

        if not name.endswith(
            ".mrs"
        ):
            continue

        jobs.append(
            (
                url,
                directory /
                name,
            )
        )

    # --------------------------------------------------------
    # SingBox SRS
    # --------------------------------------------------------

    srs_assets = github_release_assets(
        "DustinWin",
        "ruleset_geodata",
        "sing-box-ruleset-compatible",
    )

    for name, url in srs_assets.items():

        if not name.endswith(
            ".srs"
        ):
            continue

        jobs.append(
            (
                url,
                directory /
                name,
            )
        )

    if not jobs:

        raise RuntimeError(
            "No DustinWin MRS/SRS assets found."
        )

    success = 0

    # --------------------------------------------------------
    # 并发
    # --------------------------------------------------------

    with ThreadPoolExecutor(
        max_workers=MAX_WORKERS
    ) as executor:

        futures = {

            executor.submit(
                download_file,
                url,
                output,
                timeout=180,
            ): output

            for url, output in jobs

        }

        for future in as_completed(
            futures
        ):

            output = futures[
                future
            ]

            try:

                future.result()

                success += 1

            except Exception as error:

                print()
                print(
                    f"DUSTINWIN FAILED:"
                )

                print(
                    output
                )

                print(
                    error
                )

    if success != len(jobs):

        raise RuntimeError(
            "DustinWin download incomplete:\n"
            f"Expected: {len(jobs)}\n"
            f"Downloaded: {success}"
        )

    print()
    print(
        f"DustinWin files: "
        f"{success}"
    )


# ============================================================
# GeoIP
#
# MetaCubeX/meta-rules-dat
#
# 直接下载 meta 分支 ZIP
#
# 自动读取：
#
# geo/geoip/*.mrs
#
# 不再猜文件名
# ============================================================

def sync_geoip(
    staging_root,
):

    print()
    print(
        "=" * 70
    )

    print(
        "SYNC GEOIP"
    )

    print(
        "=" * 70
    )

    directory = (
        staging_root /
        "geoip"
    )

    directory.mkdir(
        parents=True,
        exist_ok=True,
    )

    archive = download_github_zip(
        "MetaCubeX",
        "meta-rules-dat",
        "meta",
    )

    files = {}

    try:

        for info in archive.infolist():

            if info.is_dir():
                continue

            relative = zip_relative_path(
                info.filename
            )

            parts = [
                x.lower()
                for x in relative.parts
            ]

            if len(parts) < 3:
                continue

            # geo/geoip/*.mrs
            if parts[0] != "geo":
                continue

            if parts[1] != "geoip":
                continue

            filename = relative.name

            if not filename.lower().endswith(
                ".mrs"
            ):
                continue

            new_name = (
                filename.lower()
            )

            if new_name in files:

                raise RuntimeError(
                    "GeoIP filename collision:\n"
                    f"{files[new_name]}\n"
                    f"{relative}"
                )

            files[
                new_name
            ] = info

        if not files:

            raise RuntimeError(
                "No GeoIP MRS files found in "
                "MetaCubeX/meta-rules-dat "
                "meta branch."
            )

        print()
        print(
            f"FOUND GEOIP: "
            f"{len(files)}"
        )

        for name in sorted(
            files
        ):

            print(
                f"  {name}"
            )

        # ----------------------------------------------------
        # 直接从 ZIP 解压
        # ----------------------------------------------------

        for name in sorted(
            files
        ):

            info = files[
                name
            ]

            output = (
                directory /
                name
            )

            with archive.open(
                info
            ) as source:

                with output.open(
                    "wb"
                ) as destination:

                    shutil.copyfileobj(
                        source,
                        destination,
                    )

            print(
                f"GEOIP: "
                f"{name}"
            )

    finally:

        archive.close()

    print()
    print(
        f"GeoIP files: "
        f"{len(files)}"
    )


# ============================================================
# CNIP
#
# X-Shelby/geoip
#
# latest release
#
# 自动获取所有 MRS + SRS
# ============================================================

def sync_cnip(
    staging_root,
):

    print()
    print(
        "=" * 70
    )

    print(
        "SYNC CNIP"
    )

    print(
        "=" * 70
    )

    directory = (
        staging_root /
        "cnip"
    )

    directory.mkdir(
        parents=True,
        exist_ok=True,
    )

    # ========================================================
    # X-Shelby / geoip
    #
    # 直接读取 latest Release 实际存在的 Assets
    #
    # 不固定要求：
    # cn.mrs
    # cn_v4.mrs
    # cn_v6.mrs
    # cnip_all.mrs
    #
    # Release 有什么就同步什么
    # ========================================================

    assets = github_release_assets(
        "X-Shelby",
        "geoip",
        "latest",
    )

    jobs = []

    for name, url in assets.items():

        name = name.lower()

        if not name.endswith(
            (
                ".mrs",
                ".srs",
            )
        ):
            continue

        output = (
            directory /
            name
        )

        jobs.append(
            (
                url,
                output,
            )
        )

    # ========================================================
    # 没有找到文件
    # ========================================================

    if not jobs:

        raise RuntimeError(
            "No MRS/SRS files found in "
            "X-Shelby/geoip latest release."
        )

    # ========================================================
    # 去重
    # ========================================================

    unique = {}

    for url, output in jobs:

        unique[
            output.name
        ] = (
            url,
            output,
        )

    jobs = list(
        unique.values()
    )

    jobs.sort(
        key=lambda x: x[1].name
    )

    print()
    print(
        f"FOUND CNIP: "
        f"{len(jobs)}"
    )

    for _, output in jobs:

        print(
            f"  {output.name}"
        )

    # ========================================================
    # 并发下载
    # ========================================================

    success = 0

    with ThreadPoolExecutor(
        max_workers=MAX_WORKERS
    ) as executor:

        futures = {

            executor.submit(
                download_file,
                url,
                output,
                timeout=180,
            ): output

            for url, output in jobs

        }

        for future in as_completed(
            futures
        ):

            output = futures[
                future
            ]

            try:

                future.result()

                success += 1

            except Exception as error:

                print()
                print(
                    "CNIP FAILED:"
                )

                print(
                    output
                )

                print(
                    error
                )

                # ------------------------------------------------
                # CNIP 单文件失败时记录，但最后统一判断
                # ------------------------------------------------

    # ========================================================
    # 最终检查
    # ========================================================

    missing = []

    for _, output in jobs:

        if not output.exists():

            missing.append(
                output.name
            )

    if missing:

        raise RuntimeError(

            "CNIP download incomplete:\n"
            f"Expected: {len(jobs)}\n"
            f"Downloaded: {success}\n"
            "Missing:\n"
            +
            "\n".join(
                sorted(
                    missing
                )
            )

        )

    # ========================================================
    # 完成
    # ========================================================

    print()

    print(
        f"CNIP files: {success}"
    )

    print(
        "CNIP sync completed."
    )


# ============================================================
# AdBlock
#
# 217heidai/rules
#
# 自动提取所有 MRS + SRS
# ============================================================

def sync_adblock(
    staging_root,
):

    print()
    print(
        "=" * 70
    )

    print(
        "SYNC ADBLOCK"
    )

    print(
        "=" * 70
    )

    directory = (
        staging_root /
        "AdBlock"
    )

    directory.mkdir(
        parents=True,
        exist_ok=True,
    )

    archive = download_github_zip(
        "217heidai",
        "rules",
    )

    files = {}

    try:

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
                    ".srs",
                )
            ):

                continue

            new_name = (
                filename.lower()
            )

            if new_name in files:

                raise RuntimeError(
                    "AdBlock filename collision:\n"
                    f"{files[new_name]}\n"
                    f"{relative}"
                )

            files[
                new_name
            ] = info

        if not files:

            raise RuntimeError(
                "No AdBlock MRS/SRS files found."
            )

        print()
        print(
            f"FOUND ADBLOCK: "
            f"{len(files)}"
        )

        for name in sorted(
            files
        ):

            info = files[
                name
            ]

            output = (
                directory /
                name
            )

            with archive.open(
                info
            ) as source:

                with output.open(
                    "wb"
                ) as destination:

                    shutil.copyfileobj(
                        source,
                        destination,
                    )

            print(
                f"ADBLOCK: "
                f"{name}"
            )

    finally:

        archive.close()

    print()
    print(
        f"AdBlock files: "
        f"{len(files)}"
    )


# ============================================================
# 最终目录
# ============================================================

EXPECTED_DIRS = {
    "Mihomo",
    "SingBox",
    "DustinWin",
    "geoip",
    "cnip",
    "AdBlock",
}


ALLOWED_EXTENSIONS = {

    "Mihomo": {
        ".mrs",
    },

    "SingBox": {
        ".srs",
    },

    "DustinWin": {
        ".mrs",
        ".srs",
    },

    "geoip": {
        ".mrs",
    },

    "cnip": {
        ".mrs",
        ".srs",
    },

    "AdBlock": {
        ".mrs",
        ".srs",
    },

}


# ============================================================
# 最终验证
# ============================================================

def validate(
    root,
):

    print()
    print(
        "=" * 70
    )

    print(
        "VALIDATE"
    )

    print(
        "=" * 70
    )

    root = Path(
        root
    )

    if not root.exists():

        raise RuntimeError(
            "Rules directory does not exist."
        )

    # --------------------------------------------------------
    # 目录
    # --------------------------------------------------------

    actual_dirs = {

        item.name

        for item in root.iterdir()

        if item.is_dir()

    }

    missing_dirs = (
        EXPECTED_DIRS -
        actual_dirs
    )

    if missing_dirs:

        raise RuntimeError(
            "Missing directories:\n"
            +
            "\n".join(
                sorted(
                    missing_dirs
                )
            )
        )

    extra_dirs = (
        actual_dirs -
        EXPECTED_DIRS
    )

    if extra_dirs:

        raise RuntimeError(
            "Unexpected directories:\n"
            +
            "\n".join(
                sorted(
                    extra_dirs
                )
            )
        )

    total = 0

    # --------------------------------------------------------
    # 每个目录
    # --------------------------------------------------------

    for directory_name in sorted(
        EXPECTED_DIRS
    ):

        directory = (
            root /
            directory_name
        )

        allowed = (
            ALLOWED_EXTENSIONS[
                directory_name
            ]
        )

        items = list(
            directory.iterdir()
        )

        if not items:

            raise RuntimeError(
                f"Empty directory:\n"
                f"{directory}"
            )

        for path in items:

            # 不允许子目录
            if path.is_dir():

                raise RuntimeError(
                    "Subdirectory detected:\n"
                    f"{path}"
                )

            # 小写
            if path.name != (
                path.name.lower()
            ):

                raise RuntimeError(
                    "Filename is not lowercase:\n"
                    f"{path}"
                )

            # 扩展名
            if path.suffix.lower() not in allowed:

                raise RuntimeError(
                    "Invalid extension:\n"
                    f"{path}"
                )

            # 文件大小
            size = (
                path.stat()
                .st_size
            )

            if size < 100:

                raise RuntimeError(
                    "File too small:\n"
                    f"{path}\n"
                    f"{size} bytes"
                )

            total += 1

    # --------------------------------------------------------
    # Meta
    # --------------------------------------------------------

    meta = (
        root /
        "Mihomo" /
        "meta.mrs"
    )

    if not meta.exists():

        raise RuntimeError(
            "Mihomo/meta.mrs is missing."
        )

    for old_name in (
        "facebook.mrs",
        "threads.mrs",
        "instagram.mrs",
    ):

        old_file = (
            root /
            "Mihomo" /
            old_name
        )

        if old_file.exists():

            raise RuntimeError(
                f"Old Meta file exists:\n"
                f"{old_file}"
            )

    # --------------------------------------------------------
    # Classical
    # --------------------------------------------------------

    for path in (
        root /
        "Mihomo"
    ).iterdir():

        if (
            path.is_file()
            and
            "_classical"
            in path.name.lower()
        ):

            raise RuntimeError(
                "Classical rule detected:\n"
                f"{path}"
            )

    # --------------------------------------------------------
    # YouTube 重命名检查
    # --------------------------------------------------------

    youtube_domain = (
        root /
        "Mihomo" /
        "youtube.mrs"
    )

    youtube_ip = (
        root /
        "Mihomo" /
        "youtubeip.mrs"
    )

    if youtube_domain.exists():

        print(
            "OK: youtube.mrs"
        )

    if youtube_ip.exists():

        print(
            "OK: youtubeip.mrs"
        )

    # --------------------------------------------------------
    # CNIP
    # --------------------------------------------------------

    cnip_dir = (
        root /
        "cnip"
    )

    if missing_cnip:

        print()
        print(
            "WARNING: Some expected CNIP "
            "files are not present:"
        )

        for filename in missing_cnip:

            print(
                f"  {filename}"
            )

        print(
            "This is allowed because "
            "the source release may change."
        )

    # --------------------------------------------------------
    # 完成
    # --------------------------------------------------------

    print()
    print(
        f"VALIDATION OK"
    )

    print(
        f"Total files: {total}"
    )

    print(
        "No subdirectories."
    )

    print(
        "All filenames lowercase."
    )

    print(
        "Mihomo converter not used."
    )

    print(
        "Meta = Facebook."
    )


# ============================================================
# 统计
# ============================================================

def statistics(
    root,
):

    print()
    print(
        "=" * 70
    )

    print(
        "FINAL STATISTICS"
    )

    print(
        "=" * 70
    )

    total = 0

    for directory_name in sorted(
        EXPECTED_DIRS
    ):

        directory = (
            root /
            directory_name
        )

        mrs = 0
        srs = 0

        for path in directory.iterdir():

            if not path.is_file():
                continue

            if path.suffix == ".mrs":

                mrs += 1

            elif path.suffix == ".srs":

                srs += 1

        count = (
            mrs +
            srs
        )

        total += count

        print(
            f"{directory_name:<12}"
            f"MRS={mrs:<4}"
            f"SRS={srs:<4}"
            f"TOTAL={count}"
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
    print(
        "=" * 70
    )

    print(
        "VERION RULE SYNC"
    )

    print(
        "=" * 70
    )

    start_time = time.time()

    # ========================================================
    # 临时目录
    # ========================================================

    with tempfile.TemporaryDirectory(
        prefix="verion-rules-"
    ) as temp:

        staging_root = (
            Path(temp) /
            "rules"
        )

        staging_root.mkdir(
            parents=True,
            exist_ok=True,
        )

        # ====================================================
        # 1. Milangree
        #
        # ZIP 只下载一次
        # ====================================================

        archive = download_github_zip(
            "milangree",
            "rules",
            "main",
        )

        try:

            sync_milangree(
                archive,
                staging_root,
            )

        finally:

            archive.close()

        # ====================================================
        # 2. Meta
        # ====================================================

        sync_meta(
            staging_root
        )

        # ====================================================
        # 3. DustinWin
        # ====================================================

        sync_dustinwin(
            staging_root
        )

        # ====================================================
        # 4. GeoIP
        # ====================================================

        sync_geoip(
            staging_root
        )

        # ====================================================
        # 5. CNIP
        # ====================================================

        sync_cnip(
            staging_root
        )

        # ====================================================
        # 6. AdBlock
        # ====================================================

        sync_adblock(
            staging_root
        )

        # ====================================================
        # 7. 临时目录验证
        # ====================================================

        validate(
            staging_root
        )

        statistics(
            staging_root
        )

        # ====================================================
        # 8. 替换正式 rules
        #
        # 只有全部成功才执行
        # ====================================================

        print()
        print(
            "=" * 70
        )

        print(
            "INSTALL RULES"
        )

        print(
            "=" * 70
        )

        if ROOT.exists():

            shutil.rmtree(
                ROOT
            )

        shutil.move(
            str(staging_root),
            str(ROOT),
        )

    # ========================================================
    # 最终验证
    # ========================================================

    validate(
        ROOT
    )

    statistics(
        ROOT
    )

    elapsed = (
        time.time()
        -
        start_time
    )

    print()
    print(
        "=" * 70
    )

    print(
        "SYNC COMPLETE"
    )

    print(
        "=" * 70
    )

    print(
        f"Elapsed: {elapsed:.1f}s"
    )


# ============================================================
# ENTRY
# ============================================================

if __name__ == "__main__":

    main()
