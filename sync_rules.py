import gzip
import io
import shutil
import time
import zipfile
from pathlib import Path

import requests


# ============================================================
# CONFIG
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
# HTTP REQUEST
# ============================================================

def request(
    method,
    url,
    *,
    timeout=TIMEOUT,
    retries=6,
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
            if response.status_code in (403, 429):

                retry_after = response.headers.get(
                    "Retry-After"
                )

                try:
                    wait = int(retry_after)
                except (
                    TypeError,
                    ValueError
                ):
                    wait = min(
                        attempt * 10,
                        60
                    )

                print(
                    f"HTTP {response.status_code}, "
                    f"retry after {wait}s..."
                )

                time.sleep(wait)

                continue

            response.raise_for_status()

            return response

        except Exception as error:

            last_error = error

            print(
                f"Request failed "
                f"({attempt}/{retries}):"
            )

            print(
                f"{url}"
            )

            print(
                f"ERROR: {error}"
            )

            if attempt < retries:

                wait = min(
                    attempt * 5,
                    60
                )

                print(
                    f"Retry in {wait}s..."
                )

                time.sleep(wait)

    raise last_error


def download_bytes(
    url,
    timeout=TIMEOUT
):

    print(
        f"DOWNLOAD: {url}"
    )

    return request(
        "GET",
        url,
        timeout=timeout
    ).content


def download_file(
    url,
    output,
    timeout=TIMEOUT
):

    data = download_bytes(
        url,
        timeout
    )

    output.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    output.write_bytes(
        data
    )

    print(
        f"OK: {output} "
        f"({len(data)} bytes)"
    )


# ============================================================
# GITHUB ZIP
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
        url,
        timeout=600
    )

    if not data:

        raise RuntimeError(
            f"Empty ZIP: {url}"
        )

    try:

        return zipfile.ZipFile(
            io.BytesIO(data)
        )

    except zipfile.BadZipFile as error:

        raise RuntimeError(
            f"Invalid ZIP downloaded: {url}"
        ) from error


def zip_relative_path(
    filename
):

    parts = Path(
        filename
    ).parts

    if len(parts) <= 1:

        return Path()

    # GitHub ZIP 第一层通常是：
    #
    # repo-branch/
    #
    # 去掉第一层
    return Path(
        *parts[1:]
    )


# ============================================================
# CLEAN DIRECTORY
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
# MIHOMO FILE NAME
#
# YouTube_domain.mrs
#        ↓
# youtube.mrs
#
# YouTube_ipcidr.mrs
#        ↓
# youtubeip.mrs
#
# YouTube_classical.mrs
#        ↓
# SKIP
# ============================================================

def mihomo_output_name(
    filename
):

    stem = Path(
        filename
    ).stem

    lower = stem.lower()

    # 不同步 classical
    if lower.endswith(
        "_classical"
    ):

        return None

    # domain
    if lower.endswith(
        "_domain"
    ):

        name = lower[
            :-len("_domain")
        ]

        return (
            name +
            ".mrs"
        )

    # ipcidr
    if lower.endswith(
        "_ipcidr"
    ):

        name = lower[
            :-len("_ipcidr")
        ]

        return (
            name +
            "ip.mrs"
        )

    # 普通 MRS
    return (
        lower +
        ".mrs"
    )


# ============================================================
# MIHOMO
#
# Source:
#
# https://github.com/milangree/rules/tree/main/rules/mihomo
#
# 只同步 MRS
# 不同步 classical
# 文件名全部小写
# 不保留子目录
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

            relative = zip_relative_path(
                info.filename
            )

            parts = relative.parts

            if len(parts) < 3:
                continue

            # rules/mihomo
            if parts[0].lower() != "rules":
                continue

            if parts[1].lower() != "mihomo":
                continue

            filename = parts[-1]

            # 只要 MRS
            if not filename.lower().endswith(
                ".mrs"
            ):
                continue

            # 不要 classical
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

            # 文件名冲突检查
            if new_name in used:

                raise RuntimeError(

                    "Mihomo filename collision:\n"
                    f"Existing: {used[new_name]}\n"
                    f"New:      {relative}\n"
                    f"Target:   {new_name}"

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
# META
#
# 只同步 Facebook
#
# facebook.mrs
#      ↓
# meta.mrs
#
# 不同步：
#
# threads.mrs
# instagram.mrs
#
# 不需要 Mihomo converter
# ============================================================

def sync_meta():

    print()
    print("=" * 70)
    print("SYNC META")
    print("=" * 70)

    target = (
        ROOT /
        "Mihomo"
    )

    target.mkdir(
        parents=True,
        exist_ok=True
    )

    url = (
        "https://cdn.jsdelivr.net/gh/"
        "Verion0382/verion@main/"
        "rules/Mihomo/facebook.mrs"
    )

    output = (
        target /
        "meta.mrs"
    )

    print(
        f"DOWNLOAD: {url}"
    )

    response = request(
        "GET",
        url,
        timeout=120
    )

    data = response.content

    if len(data) < 100:

        raise RuntimeError(

            "Facebook MRS is too small:\n"
            f"URL: {url}\n"
            f"Size: {len(data)} bytes"

        )

    output.write_bytes(
        data
    )

    print(
        "Facebook rule -> meta.mrs"
    )

    print(
        f"Size: {len(data)} bytes"
    )

    # 删除旧的三个独立 Meta 文件
    old_files = [

        "facebook.mrs",
        "threads.mrs",
        "instagram.mrs",

    ]

    for filename in old_files:

        old_file = (
            target /
            filename
        )

        if old_file.exists():

            old_file.unlink()

            print(
                f"REMOVE: {filename}"
            )

    # 最终检查
    if not output.exists():

        raise RuntimeError(
            "meta.mrs was not created."
        )

    final_size = (
        output.stat()
        .st_size
    )

    if final_size < 100:

        raise RuntimeError(

            f"meta.mrs is too small: "
            f"{final_size} bytes"

        )

    print()
    print(
        "META SYNC COMPLETE"
    )

    print(
        f"Output: {output}"
    )

    print(
        f"Size: {final_size} bytes"
    )

    print(
        "Source: Facebook"
    )


# ============================================================
# SINGBOX
#
# Source:
#
# milangree/rules/rules/singbox
#
# 只同步 SRS
# 文件名全部小写
# 不保留子目录
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

            print(
                f"{relative} -> {new_name}"
            )

            count += 1

        if count == 0:

            raise RuntimeError(
                "No SingBox SRS files found."
            )

        print(
            f"SingBox SRS files: {count}"
        )

    finally:

        archive.close()


# ============================================================
# DUSTINWIN MRS
#
# Source:
#
# DustinWin/ruleset_geodata
# branch: mihomo-ruleset
#
# 只 MRS
# ============================================================

def sync_dustinwin_mrs():

    print()
    print("=" * 70)
    print("SYNC DUSTINWIN MRS")
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

        used = set()

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

            if new_name in used:

                raise RuntimeError(

                    "DustinWin MRS collision: "
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

            print(
                f"{relative} -> {new_name}"
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
# DUSTINWIN SRS
#
# Release:
#
# sing-box-ruleset-compatible
# ============================================================

def sync_dustinwin_srs():

    print()
    print("=" * 70)
    print("SYNC DUSTINWIN SRS")
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

    release = request(
        "GET",
        api,
        timeout=120
    ).json()

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
            "No DustinWin SRS found."
        )

    print(
        f"DustinWin SRS: {count}"
    )


# ============================================================
# GEOIP
#
# MetaCubeX/meta-rules-dat
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

    # 直接使用 GitHub raw / jsdelivr
    # 避免 API 大量请求
    #
    # GeoIP 常用 MRS
    files = [

        "geoip/cn.mrs",
        "geoip/private.mrs",
        "geoip/google.mrs",
        "geoip/telegram.mrs",

    ]

    base = (
        "https://cdn.jsdelivr.net/gh/"
        "MetaCubeX/meta-rules-dat@meta/"
    )

    count = 0

    for filename in files:

        name = Path(
            filename
        ).name.lower()

        url = (
            base +
            filename
        )

        try:

            output = (
                target /
                name
            )

            download_file(
                url,
                output,
                timeout=120
            )

            count += 1

        except Exception as error:

            print(
                f"SKIP GEOIP: "
                f"{filename}"
            )

            print(
                f"Reason: {error}"
            )

    if count == 0:

        raise RuntimeError(
            "No GeoIP MRS files found."
        )

    print(
        f"GeoIP MRS: {count}"
    )


# ============================================================
# CNIP
#
# X-Shelby/geoip
#
# latest
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

        output = (
            target /
            filename.lower()
        )

        download_file(
            base +
            filename,
            output,
            timeout=180
        )

    print(
        f"CNIP files: {len(files)}"
    )


# ============================================================
# ADBLOCK
#
# 217heidai
#
# 同步 MRS + SRS
# ============================================================

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
        "217heidai",
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

                    f"AdBlock collision: "
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

            print(
                f"{relative} -> {new_name}"
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
# CHECK DIRECTORIES
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

    # 不允许子目录
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
# LOWERCASE CHECK
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
# EXTENSION CHECK
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

    for name, allowed in (
        ALLOWED_EXTENSIONS.items()
    ):

        directory = (
            ROOT /
            name
        )

        if not directory.exists():

            raise RuntimeError(
                f"Directory missing: {directory}"
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
# META CHECK
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
        f"meta.mrs: {size} bytes"
    )

    if size < 100:

        raise RuntimeError(
            "meta.mrs is too small."
        )

    # 不允许这些旧文件存在
    forbidden = [

        "facebook.mrs",
        "threads.mrs",
        "instagram.mrs",

    ]

    for filename in forbidden:

        path = (
            directory /
            filename
        )

        if path.exists():

            raise RuntimeError(

                f"Old Meta file exists: "
                f"{filename}"

            )

    print(
        "OK: Facebook -> meta.mrs"
    )


# ============================================================
# CNIP CHECK
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
# FILE SIZE CHECK
# ============================================================

def check_files():

    print()
    print("=" * 70)
    print("CHECK FILES")
    print("=" * 70)

    total = 0

    for path in ROOT.rglob("*"):

        if not path.is_file():
            continue

        size = (
            path.stat()
            .st_size
        )

        if size < 100:

            raise RuntimeError(

                f"File too small: "
                f"{path} "
                f"({size} bytes)"

            )

        total += 1

    print(
        f"OK: {total} files checked."
    )


# ============================================================
# STATISTICS
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

    print(
        "Update source:"
    )

    print(
        "Mihomo   : milangree/rules"
    )

    print(
        "Meta     : Facebook -> meta.mrs"
    )

    print(
        "SingBox  : milangree/rules"
    )

    print(
        "DustinWin: MRS + SRS"
    )

    print(
        "GeoIP    : MetaCubeX"
    )

    print(
        "CNIP     : X-Shelby"
    )

    print(
        "AdBlock  : 217heidai"
    )

    ROOT.mkdir(
        parents=True,
        exist_ok=True
    )

    # ========================================================
    # MIHOMO
    # ========================================================

    sync_mihomo()

    # ========================================================
    # META
    #
    # Facebook -> meta.mrs
    # ========================================================

    sync_meta()

    # ========================================================
    # SINGBOX
    # ========================================================

    sync_singbox()

    # ========================================================
    # DUSTINWIN
    # ========================================================

    sync_dustinwin_mrs()

    sync_dustinwin_srs()

    # ========================================================
    # GEOIP
    # ========================================================

    sync_geoip()

    # ========================================================
    # CNIP
    # ========================================================

    sync_cnip()

    # ========================================================
    # ADBLOCK
    # ========================================================

    sync_adblock()

    # ========================================================
    # CHECK
    # ========================================================

    check_directories()

    check_lowercase()

    check_extensions()

    check_meta()

    check_cnip()

    check_files()

    # ========================================================
    # STATISTICS
    # ========================================================

    statistics()

    print()
    print("=" * 70)
    print("SYNC COMPLETE")
    print("=" * 70)


if __name__ == "__main__":

    main()
