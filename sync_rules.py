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

REQUEST_TIMEOUT = 180
ZIP_TIMEOUT = 600

MAX_WORKERS = 8
RETRIES = 3

HEADERS = {
    "User-Agent": "Verion-Rules-Sync/2.0",
    "Accept": "*/*",
}

GITHUB_HEADERS = {
    "User-Agent": "Verion-Rules-Sync/2.0",
    "Accept": "application/vnd.github+json",
}


# ============================================================
# Session
# ============================================================

session = requests.Session()
session.headers.update(HEADERS)


# ============================================================
# HTTP 请求
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

    for attempt in range(1, retries + 1):

        try:

            response = session.get(
                url,
                headers=headers,
                timeout=timeout,
            )

            # GitHub 限流
            if response.status_code in (
                403,
                429,
            ):

                retry_after = response.headers.get(
                    "Retry-After"
                )

                try:
                    wait = int(retry_after)
                except (
                    TypeError,
                    ValueError,
                ):
                    wait = min(
                        5 * attempt,
                        20,
                    )

                print(
                    f"HTTP {response.status_code}: "
                    f"retry in {wait}s"
                )

                time.sleep(wait)

                continue

            response.raise_for_status()

            return response

        except Exception as error:

            last_error = error

            print(
                f"DOWNLOAD ERROR "
                f"({attempt}/{retries})"
            )

            print(url)
            print(error)

            if attempt < retries:

                wait = min(
                    3 * attempt,
                    10,
                )

                time.sleep(wait)

    raise RuntimeError(
        f"Failed to download:\n{url}\n"
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
            f"Downloaded file is too small:\n"
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
    branch="main",
):

    url = (
        f"https://github.com/"
        f"{owner}/{repo}/"
        f"archive/refs/heads/"
        f"{branch}.zip"
    )

    print()
    print(
        f"DOWNLOAD ZIP:"
    )
    print(url)

    response = http_get(
        url,
        timeout=ZIP_TIMEOUT,
    )

    data = response.content

    if len(data) < 100:

        raise RuntimeError(
            f"GitHub ZIP is too small: "
            f"{len(data)} bytes"
        )

    try:

        archive = zipfile.ZipFile(
            io.BytesIO(data)
        )

    except zipfile.BadZipFile as error:

        raise RuntimeError(
            f"Invalid GitHub ZIP:\n{url}"
        ) from error

    print(
        f"ZIP downloaded: "
        f"{len(data) / 1024 / 1024:.2f} MB"
    )

    return archive


# ============================================================
# ZIP 相对路径
# ============================================================

def relative_zip_path(
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
# 清理目录
# ============================================================

def clean_directory(
    directory,
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
        exist_ok=True,
    )


# ============================================================
# 临时目录同步
# ============================================================

def replace_directory(
    temp_dir,
    target_dir,
):

    target_dir = Path(
        target_dir
    )

    if target_dir.exists():

        shutil.rmtree(
            target_dir
        )

    target_dir.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    shutil.move(
        str(temp_dir),
        str(target_dir),
    )


# ============================================================
# Mihomo 文件重命名
#
# YouTube_domain.mrs
#      ↓
# youtube.mrs
#
# YouTube_ipcidr.mrs
#      ↓
# youtubeip.mrs
#
# YouTube_classical.mrs
#      ↓
# 不同步
# ============================================================

def mihomo_name(
    filename,
):

    path = Path(
        filename
    )

    stem = path.stem.lower()

    # classical 不同步
    if stem.endswith(
        "_classical"
    ):

        return None

    # domain
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

    # ipcidr
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

    return (
        stem +
        ".mrs"
    )


# ============================================================
# 从 milangree ZIP 同时同步 Mihomo + SingBox
#
# 重要：
# 这里整个 milangree/rules ZIP 只下载一次。
# ============================================================

def sync_milangree(
    archive,
    staging_root,
):

    print()
    print("=" * 70)
    print("PROCESS MILANGREE")
    print("=" * 70)

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
    singbox_names = set()

    for info in archive.infolist():

        if info.is_dir():
            continue

        relative = relative_zip_path(
            info.filename
        )

        parts = relative.parts

        if len(parts) < 3:
            continue

        if parts[0].lower() != "rules":
            continue

        category = parts[1].lower()

        filename = parts[-1]

        # ====================================================
        # MIHOMO
        # ====================================================

        if category == "mihomo":

            if not filename.lower().endswith(
                ".mrs"
            ):
                continue

            new_name = mihomo_name(
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
                    f"File 1: "
                    f"{mihomo_names[new_name]}\n"
                    f"File 2: "
                    f"{relative}\n"
                    f"Target: "
                    f"{new_name}"

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
        # SINGBOX
        # ====================================================

        elif category == "singbox":

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
                    f"{relative}\n"
                    f"Target: {new_name}"

                )

            singbox_names.add(
                new_name
            )

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
            "in milangree repository."
        )

    if singbox_count == 0:

        raise RuntimeError(
            "No SingBox SRS files found "
            "in milangree repository."
        )

    print()
    print(
        f"Mihomo files : {mihomo_count}"
    )

    print(
        f"SingBox files: {singbox_count}"
    )


# ============================================================
# META
#
# Facebook -> meta.mrs
#
# 不再合并：
# threads
# instagram
# ============================================================

def sync_meta(
    staging_root,
):

    print()
    print("=" * 70)
    print("SYNC META")
    print("=" * 70)

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

    print(
        f"DOWNLOAD: {url}"
    )

    response = http_get(
        url,
        timeout=120,
    )

    data = response.content

    if len(data) < 100:

        raise RuntimeError(
            "Facebook rule is too small."
        )

    output.write_bytes(
        data
    )

    print(
        f"Facebook -> meta.mrs "
        f"({len(data)} bytes)"
    )

    # 确保旧文件不会出现
    for filename in (
        "facebook.mrs",
        "threads.mrs",
        "instagram.mrs",
    ):

        old_file = (
            directory /
            filename
        )

        if old_file.exists():

            old_file.unlink()

            print(
                f"REMOVE: {filename}"
            )


# ============================================================
# DustinWin
#
# MRS:
# https://github.com/DustinWin/ruleset_geodata
# branch: mihomo-ruleset
#
# SRS:
# release:
# sing-box-ruleset-compatible
# ============================================================

def sync_dustinwin(
    staging_root,
):

    print()
    print("=" * 70)
    print("SYNC DUSTINWIN")
    print("=" * 70)

    directory = (
        staging_root /
        "DustinWin"
    )

    directory.mkdir(
        parents=True,
        exist_ok=True,
    )

    # --------------------------------------------------------
    # MRS
    # --------------------------------------------------------

    archive = download_github_zip(
        "DustinWin",
        "ruleset_geodata",
        "mihomo-ruleset",
    )

    mrs_count = 0

    try:

        for info in archive.infolist():

            if info.is_dir():
                continue

            relative = relative_zip_path(
                info.filename
            )

            filename = relative.name

            if not filename.lower().endswith(
                ".mrs"
            ):
                continue

            output = (
                directory /
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
                        destination,
                    )

            print(
                f"DUSTINWIN MRS: "
                f"{filename.lower()}"
            )

            mrs_count += 1

    finally:

        archive.close()

    # --------------------------------------------------------
    # SRS
    # --------------------------------------------------------

    api = (
        "https://api.github.com/"
        "repos/DustinWin/ruleset_geodata/"
        "releases/tags/"
        "sing-box-ruleset-compatible"
    )

    release = http_get(
        api,
        timeout=120,
        github=True,
    ).json()

    srs_count = 0

    for asset in release.get(
        "assets",
        [],
    ):

        name = asset.get(
            "name",
            "",
        )

        if not name.lower().endswith(
            ".srs"
        ):
            continue

        output = (
            directory /
            name.lower()
        )

        download_file(
            asset[
                "browser_download_url"
            ],
            output,
            timeout=180,
        )

        srs_count += 1

    if mrs_count == 0:

        raise RuntimeError(
            "No DustinWin MRS files found."
        )

    if srs_count == 0:

        raise RuntimeError(
            "No DustinWin SRS files found."
        )

    print()
    print(
        f"DustinWin MRS: {mrs_count}"
    )

    print(
        f"DustinWin SRS: {srs_count}"
    )


# ============================================================
# GEOIP
#
# MetaCubeX/meta-rules-dat
#
# 使用 jsDelivr，避免大量 GitHub API 请求。
# ============================================================

def sync_geoip(
    staging_root,
):

    print()
    print("=" * 70)
    print("SYNC GEOIP")
    print("=" * 70)

    directory = (
        staging_root /
        "geoip"
    )

    directory.mkdir(
        parents=True,
        exist_ok=True,
    )

    files = [

        "cn.mrs",
        "private.mrs",
        "google.mrs",
        "telegram.mrs",

    ]

    base = (
        "https://cdn.jsdelivr.net/gh/"
        "MetaCubeX/meta-rules-dat@meta/"
        "geoip/"
    )

    jobs = []

    for filename in files:

        jobs.append(
            (
                base + filename,
                directory / filename,
            )
        )

    success = 0

    with ThreadPoolExecutor(
        max_workers=MAX_WORKERS
    ) as executor:

        futures = {

            executor.submit(
                download_file,
                url,
                output,
                timeout=120,
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

                print(
                    f"GEOIP FAILED: "
                    f"{output}"
                )

                print(error)

    if success == 0:

        raise RuntimeError(
            "No GeoIP files downloaded."
        )

    print(
        f"GeoIP files: {success}"
    )


# ============================================================
# CNIP
#
# X-Shelby/geoip
# release: latest
#
# MRS + SRS
# ============================================================

def sync_cnip(
    staging_root,
):

    print()
    print("=" * 70)
    print("SYNC CNIP")
    print("=" * 70)

    directory = (
        staging_root /
        "cnip"
    )

    directory.mkdir(
        parents=True,
        exist_ok=True,
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

    jobs = []

    for filename in files:

        jobs.append(
            (
                base + filename,
                directory / filename,
            )
        )

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

                print(
                    f"CNIP FAILED: "
                    f"{output}"
                )

                print(error)

    if success != len(files):

        raise RuntimeError(

            "CNIP download incomplete:\n"
            f"Expected: {len(files)}\n"
            f"Downloaded: {success}"

        )

    print(
        f"CNIP files: {success}"
    )


# ============================================================
# ADBLOCK
#
# 217heidai/rules
#
# 只取 MRS + SRS
# 不保留子目录
# ============================================================

def sync_adblock(
    staging_root,
):

    print()
    print("=" * 70)
    print("SYNC ADBLOCK")
    print("=" * 70)

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
        "main",
    )

    count = 0
    names = set()

    try:

        for info in archive.infolist():

            if info.is_dir():
                continue

            relative = relative_zip_path(
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

            if new_name in names:

                raise RuntimeError(

                    "AdBlock filename collision:\n"
                    f"{relative}\n"
                    f"Target: {new_name}"

                )

            names.add(
                new_name
            )

            output = (
                directory /
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
                f"ADBLOCK: "
                f"{relative} -> "
                f"{new_name}"
            )

            count += 1

    finally:

        archive.close()

    if count == 0:

        raise RuntimeError(
            "No AdBlock MRS/SRS files found."
        )

    print(
        f"AdBlock files: {count}"
    )


# ============================================================
# 最终检查
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


def validate(
    root,
):

    print()
    print("=" * 70)
    print("VALIDATE")
    print("=" * 70)

    root = Path(
        root
    )

    # --------------------------------------------------------
    # 目录
    # --------------------------------------------------------

    actual_dirs = {

        x.name

        for x in root.iterdir()

        if x.is_dir()

    }

    missing = (
        EXPECTED_DIRS -
        actual_dirs
    )

    if missing:

        raise RuntimeError(
            "Missing directories:\n"
            +
            "\n".join(
                sorted(missing)
            )
        )

    # --------------------------------------------------------
    # 不允许额外目录
    # --------------------------------------------------------

    extra = (
        actual_dirs -
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

    # --------------------------------------------------------
    # 文件检查
    # --------------------------------------------------------

    total = 0

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

        files = list(
            directory.iterdir()
        )

        if not files:

            raise RuntimeError(
                f"Empty directory: "
                f"{directory}"
            )

        for path in files:

            # 不允许子目录
            if path.is_dir():

                raise RuntimeError(

                    "Subdirectory detected:\n"
                    f"{path}"

                )

            # 全部小写
            if path.name != path.name.lower():

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
            "Mihomo/meta.mrs missing."
        )

    for filename in (
        "facebook.mrs",
        "threads.mrs",
        "instagram.mrs",
    ):

        old = (
            root /
            "Mihomo" /
            filename
        )

        if old.exists():

            raise RuntimeError(
                f"Old Meta file exists: {old}"
            )

    # --------------------------------------------------------
    # CNIP
    # --------------------------------------------------------

    cnip = (
        root /
        "cnip"
    )

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

    actual_cnip = {

        x.name

        for x in cnip.iterdir()

        if x.is_file()

    }

    missing_cnip = (
        required_cnip -
        actual_cnip
    )

    if missing_cnip:

        raise RuntimeError(

            "Missing CNIP files:\n"
            +
            "\n".join(
                sorted(missing_cnip)
            )

        )

    # --------------------------------------------------------
    # Classical 检查
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

    print(
        f"OK: {total} rule files"
    )

    print(
        "OK: No subdirectories"
    )

    print(
        "OK: All filenames lowercase"
    )

    print(
        "OK: Extensions valid"
    )

    print(
        "OK: Meta = Facebook"
    )

    print(
        "OK: CNIP MRS + SRS"
    )


# ============================================================
# 统计
# ============================================================

def statistics(
    root,
):

    print()
    print("=" * 70)
    print("FINAL STATISTICS")
    print("=" * 70)

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
            f"{directory_name:<12} "
            f"MRS={mrs:<4} "
            f"SRS={srs:<4} "
            f"TOTAL={count}"
        )

    print()
    print(
        f"TOTAL: {total}"
    )


# ============================================================
# MAIN
# ============================================================

def main():

    print()
    print("=" * 70)
    print("VERION RULE SYNC")
    print("=" * 70)

    start_time = time.time()

    # --------------------------------------------------------
    # 临时工作目录
    # --------------------------------------------------------

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
        # 1. milangree
        #
        # 只下载一次 ZIP
        # 同时处理 Mihomo + SingBox
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
        #
        # Facebook -> meta.mrs
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
        # 7. 验证临时目录
        # ====================================================

        validate(
            staging_root
        )

        statistics(
            staging_root
        )

        # ====================================================
        # 8. 同步成功后一次性替换 rules
        # ====================================================

        print()
        print("=" * 70)
        print("INSTALL RULES")
        print("=" * 70)

        if ROOT.exists():

            shutil.rmtree(
                ROOT
            )

        shutil.move(
            str(staging_root),
            str(ROOT),
        )

    # ========================================================
    # 最终再次检查
    # ========================================================

    validate(
        ROOT
    )

    statistics(
        ROOT
    )

    elapsed = (
        time.time() -
        start_time
    )

    print()
    print("=" * 70)
    print("SYNC COMPLETE")
    print("=" * 70)

    print(
        f"Elapsed: {elapsed:.1f}s"
    )


# ============================================================
# ENTRY
# ============================================================

if __name__ == "__main__":

    main()
