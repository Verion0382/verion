#!/usr/bin/env python3

import concurrent.futures
import json
import os
import shutil
import tempfile
import time
from pathlib import Path
from urllib.parse import quote

import requests


# ============================================================
# 基础配置
# ============================================================

ROOT = Path(__file__).resolve().parent
RULES_DIR = ROOT / "rules"

MAX_WORKERS = 12
REQUEST_TIMEOUT = 120
DOWNLOAD_TIMEOUT = 180
RETRIES = 3

SESSION = requests.Session()

SESSION.headers.update(
    {
        "User-Agent": "verion-rules-sync/1.0",
        "Accept": "application/vnd.github+json",
    }
)


# ============================================================
# 目录
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
    "Mihomo": {".mrs"},
    "SingBox": {".srs"},
    "DustinWin": {".mrs", ".srs"},
    "geoip": {".mrs"},
    "cnip": {".mrs", ".srs"},
    "AdBlock": {".mrs", ".srs"},
}


# ============================================================
# HTTP
# ============================================================

def http_get(
    url,
    *,
    timeout=REQUEST_TIMEOUT,
    github=False,
):

    last_error = None

    for attempt in range(
        1,
        RETRIES + 1,
    ):

        try:

            response = SESSION.get(
                url,
                timeout=timeout,
            )

            if (
                response.status_code
                == 429
            ):

                retry_after = (
                    response.headers.get(
                        "Retry-After",
                        "5",
                    )
                )

                try:
                    sleep_time = int(
                        retry_after
                    )
                except ValueError:
                    sleep_time = 5

                print(
                    f"HTTP 429: "
                    f"sleep {sleep_time}s"
                )

                time.sleep(
                    min(
                        sleep_time,
                        30,
                    )
                )

                continue

            response.raise_for_status()

            return response

        except Exception as error:

            last_error = error

            print(
                f"DOWNLOAD ERROR "
                f"({attempt}/{RETRIES})"
            )

            print(
                url
            )

            print(
                error
            )

            if attempt < RETRIES:

                time.sleep(
                    2 * attempt
                )

    raise last_error


# ============================================================
# 文件下载
# ============================================================

def download_file(
    url,
    output,
    *,
    timeout=DOWNLOAD_TIMEOUT,
):

    response = http_get(
        url,
        timeout=timeout,
    )

    data = response.content

    # --------------------------------------------------------
    # 只禁止 0 字节文件
    #
    # 不再限制 100 bytes
    # --------------------------------------------------------

    if len(data) <= 0:

        raise RuntimeError(
            "Downloaded file is empty:\n"
            f"{url}"
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
# GitHub API
# ============================================================

def github_api(
    url,
):

    response = http_get(
        url,
        timeout=REQUEST_TIMEOUT,
        github=True,
    )

    return response.json()


# ============================================================
# GitHub Repository
# ============================================================

def github_repo(
    owner,
    repo,
):

    url = (
        f"https://api.github.com/"
        f"repos/{owner}/{repo}"
    )

    data = github_api(
        url
    )

    branch = data.get(
        "default_branch"
    )

    if not branch:

        raise RuntimeError(
            f"Unable to determine "
            f"default branch: "
            f"{owner}/{repo}"
        )

    return branch


# ============================================================
# GitHub Tree
# ============================================================

def github_tree(
    owner,
    repo,
    branch,
):

    encoded_branch = quote(
        branch,
        safe="",
    )

    url = (
        f"https://api.github.com/"
        f"repos/{owner}/{repo}/"
        f"git/trees/{encoded_branch}"
        f"?recursive=1"
    )

    data = github_api(
        url
    )

    if data.get(
        "truncated",
        False,
    ):

        raise RuntimeError(
            f"GitHub tree is truncated: "
            f"{owner}/{repo}"
        )

    return data.get(
        "tree",
        [],
    )


# ============================================================
# GitHub Contents
# ============================================================

def github_contents(
    owner,
    repo,
    path,
    branch,
):

    encoded_path = "/".join(
        quote(
            part,
            safe="",
        )
        for part in path.split("/")
    )

    encoded_branch = quote(
        branch,
        safe="",
    )

    url = (
        f"https://api.github.com/"
        f"repos/{owner}/{repo}/"
        f"contents/{encoded_path}"
        f"?ref={encoded_branch}"
    )

    return github_api(
        url
    )


# ============================================================
# 并发下载
# ============================================================

def download_jobs(
    jobs,
):

    if not jobs:

        return

    success = 0
    errors = []

    with concurrent.futures.ThreadPoolExecutor(
        max_workers=MAX_WORKERS
    ) as executor:

        future_map = {
            executor.submit(
                download_file,
                url,
                output,
            ): output
            for url, output in jobs
        }

        for future in concurrent.futures.as_completed(
            future_map
        ):

            output = future_map[
                future
            ]

            try:

                future.result()

                success += 1

            except Exception as error:

                errors.append(
                    (
                        output,
                        error,
                    )
                )

    if errors:

        print()
        print(
            "FAILED FILES:"
        )

        for output, error in errors:

            print(
                output
            )

            print(
                error
            )

        raise RuntimeError(
            f"{len(errors)} "
            f"files failed."
        )

    print(
        f"Downloaded: {success}"
    )


# ============================================================
# 规范文件名
# ============================================================

def normalize_name(
    filename,
):

    name = filename.lower()

    rename_map = {
        "youtube_domain.mrs":
            "youtube.mrs",

        "youtube_ipcidr.mrs":
            "youtubeip.mrs",
    }

    name = rename_map.get(
        name,
        name,
    )

    return name


# ============================================================
# Mihomo
# ============================================================

def sync_mihomo(
    staging_root,
):

    print()
    print("=" * 70)
    print("SYNC MIHOMO")
    print("=" * 70)

    target = (
        staging_root /
        "Mihomo"
    )

    target.mkdir(
        parents=True,
        exist_ok=True,
    )

    owner = "milangree"
    repo = "rules"
    source = "rules/mihomo"

    branch = github_repo(
        owner,
        repo,
    )

    print(
        f"BRANCH: {branch}"
    )

    tree = github_tree(
        owner,
        repo,
        branch,
    )

    jobs = []
    names = set()

    prefix = (
        source.rstrip("/") +
        "/"
    )

    for item in tree:

        if item.get(
            "type"
        ) != "blob":

            continue

        path = item.get(
            "path",
            ""
        )

        if not path.startswith(
            prefix
        ):

            continue

        filename = Path(
            path
        ).name

        lower = filename.lower()

        if not lower.endswith(
            ".mrs"
        ):

            continue

        # ----------------------------------------------------
        # 不同步 classical
        # ----------------------------------------------------

        if "_classical" in lower:

            continue

        new_name = normalize_name(
            filename
        )

        # ----------------------------------------------------
        # 只保存最终文件
        # ----------------------------------------------------

        if new_name in names:

            raise RuntimeError(
                "Mihomo filename collision:\n"
                f"{new_name}\n"
                f"{path}"
            )

        names.add(
            new_name
        )

        raw_url = (
            "https://raw.githubusercontent.com/"
            f"{owner}/{repo}/"
            f"{branch}/"
            f"{path}"
        )

        output = (
            target /
            new_name
        )

        jobs.append(
            (
                raw_url,
                output,
            )
        )

    if not jobs:

        raise RuntimeError(
            "No Mihomo .mrs files found."
        )

    jobs.sort(
        key=lambda x: x[1].name
    )

    print(
        f"FOUND MIHOMO: "
        f"{len(jobs)}"
    )

    for _, output in jobs:

        print(
            f"  {output.name}"
        )

    download_jobs(
        jobs
    )

    print(
        "Mihomo sync completed."
    )


# ============================================================
# SingBox
# ============================================================

def sync_singbox(
    staging_root,
):

    print()
    print("=" * 70)
    print("SYNC SINGBOX")
    print("=" * 70)

    target = (
        staging_root /
        "SingBox"
    )

    target.mkdir(
        parents=True,
        exist_ok=True,
    )

    owner = "milangree"
    repo = "rules"
    source = "rules/singbox"

    branch = github_repo(
        owner,
        repo,
    )

    tree = github_tree(
        owner,
        repo,
        branch,
    )

    prefix = (
        source.rstrip("/") +
        "/"
    )

    jobs = []
    names = set()

    for item in tree:

        if item.get(
            "type"
        ) != "blob":

            continue

        path = item.get(
            "path",
            ""
        )

        if not path.startswith(
            prefix
        ):

            continue

        filename = Path(
            path
        ).name

        lower = filename.lower()

        if not lower.endswith(
            ".srs"
        ):

            continue

        new_name = lower

        if new_name in names:

            raise RuntimeError(
                "SingBox filename collision:\n"
                f"{new_name}\n"
                f"{path}"
            )

        names.add(
            new_name
        )

        raw_url = (
            "https://raw.githubusercontent.com/"
            f"{owner}/{repo}/"
            f"{branch}/"
            f"{path}"
        )

        output = (
            target /
            new_name
        )

        jobs.append(
            (
                raw_url,
                output,
            )
        )

    if not jobs:

        raise RuntimeError(
            "No SingBox .srs files found."
        )

    jobs.sort(
        key=lambda x: x[1].name
    )

    print(
        f"FOUND SINGBOX: "
        f"{len(jobs)}"
    )

    download_jobs(
        jobs
    )

    print(
        "SingBox sync completed."
    )


# ============================================================
# DustinWin
# ============================================================

def sync_dustinwin(
    staging_root,
):

    print()
    print("=" * 70)
    print("SYNC DUSTINWIN")
    print("=" * 70)

    target = (
        staging_root /
        "DustinWin"
    )

    target.mkdir(
        parents=True,
        exist_ok=True,
    )

    api_url = (
        "https://api.github.com/"
        "repos/DustinWin/"
        "ruleset_geodata/"
        "releases/tags/"
        "sing-box-ruleset-compatible"
    )

    print(
        "GET RELEASE:"
    )

    print(
        api_url
    )

    data = github_api(
        api_url
    )

    assets = data.get(
        "assets",
        []
    )

    jobs = []

    for asset in assets:

        name = asset.get(
            "name",
            ""
        )

        lower = name.lower()

        if not lower.endswith(
            (
                ".mrs",
                ".srs",
            )
        ):

            continue

        url = asset.get(
            "browser_download_url"
        )

        if not url:

            continue

        output = (
            target /
            lower
        )

        jobs.append(
            (
                url,
                output,
            )
        )

    if not jobs:

        raise RuntimeError(
            "No MRS/SRS assets found "
            "in DustinWin release."
        )

    jobs.sort(
        key=lambda x: x[1].name
    )

    print(
        f"FOUND DUSTINWIN: "
        f"{len(jobs)}"
    )

    download_jobs(
        jobs
    )

    print(
        "DustinWin sync completed."
    )


# ============================================================
# GeoIP
# ============================================================

def sync_geoip(
    staging_root,
):

    print()
    print("=" * 70)
    print("SYNC GEOIP")
    print("=" * 70)

    target = (
        staging_root /
        "geoip"
    )

    target.mkdir(
        parents=True,
        exist_ok=True,
    )

    owner = "MetaCubeX"
    repo = "meta-rules-dat"
    branch = "meta"
    source = "geoip"

    tree = github_tree(
        owner,
        repo,
        branch,
    )

    prefix = (
        source.rstrip("/") +
        "/"
    )

    jobs = []

    for item in tree:

        if item.get(
            "type"
        ) != "blob":

            continue

        path = item.get(
            "path",
            ""
        )

        if not path.startswith(
            prefix
        ):

            continue

        filename = Path(
            path
        ).name

        lower = filename.lower()

        if not lower.endswith(
            ".mrs"
        ):

            continue

        output = (
            target /
            lower
        )

        raw_url = (
            "https://raw.githubusercontent.com/"
            f"{owner}/{repo}/"
            f"{branch}/"
            f"{path}"
        )

        jobs.append(
            (
                raw_url,
                output,
            )
        )

    if not jobs:

        raise RuntimeError(
            "No GeoIP .mrs files found."
        )

    jobs.sort(
        key=lambda x: x[1].name
    )

    print(
        f"GeoIP files: "
        f"{len(jobs)}"
    )

    download_jobs(
        jobs
    )

    print(
        "GeoIP sync completed."
    )


# ============================================================
# CNIP
# ============================================================

def sync_cnip(
    staging_root,
):

    print()
    print("=" * 70)
    print("SYNC CNIP")
    print("=" * 70)

    target = (
        staging_root /
        "cnip"
    )

    target.mkdir(
        parents=True,
        exist_ok=True,
    )

    api_url = (
        "https://api.github.com/"
        "repos/X-Shelby/geoip/"
        "releases/tags/latest"
    )

    print(
        "GET RELEASE:"
    )

    print(
        api_url
    )

    data = github_api(
        api_url
    )

    assets = data.get(
        "assets",
        []
    )

    jobs = []

    for asset in assets:

        name = asset.get(
            "name",
            ""
        )

        lower = name.lower()

        if not lower.endswith(
            (
                ".mrs",
                ".srs",
            )
        ):

            continue

        url = asset.get(
            "browser_download_url"
        )

        if not url:

            continue

        output = (
            target /
            lower
        )

        jobs.append(
            (
                url,
                output,
            )
        )

    if not jobs:

        raise RuntimeError(
            "No MRS/SRS files found "
            "in X-Shelby latest release."
        )

    # --------------------------------------------------------
    # 去重
    # --------------------------------------------------------

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

    print(
        f"FOUND CNIP: "
        f"{len(jobs)}"
    )

    for _, output in jobs:

        print(
            f"  {output.name}"
        )

    download_jobs(
        jobs
    )

    print(
        f"CNIP files: "
        f"{len(jobs)}"
    )

    print(
        "CNIP sync completed."
    )


# ============================================================
# AdBlock
# ============================================================

def sync_adblock(
    staging_root,
):

    print()
    print("=" * 70)
    print("SYNC ADBLOCK")
    print("=" * 70)

    target = (
        staging_root /
        "AdBlock"
    )

    target.mkdir(
        parents=True,
        exist_ok=True,
    )

    owner = "217heidai"
    repo = "adblockfilters"
    source = "rules"

    branch = github_repo(
        owner,
        repo,
    )

    api_url = (
        "https://api.github.com/"
        f"repos/{owner}/{repo}/"
        f"contents/{source}"
        f"?ref={quote(branch, safe='')}"
    )

    print(
        "GET ADBLOCK DIRECTORY:"
    )

    print(
        api_url
    )

    items = github_api(
        api_url
    )

    if not isinstance(
        items,
        list,
    ):

        raise RuntimeError(
            "Invalid GitHub Contents response."
        )

    jobs = []
    names = set()

    for item in items:

        if item.get(
            "type"
        ) != "file":

            continue

        filename = item.get(
            "name",
            ""
        )

        lower = filename.lower()

        if not lower.endswith(
            (
                ".mrs",
                ".srs",
            )
        ):

            continue

        url = item.get(
            "download_url"
        )

        if not url:

            continue

        if lower in names:

            raise RuntimeError(
                "AdBlock filename collision:\n"
                f"{lower}"
            )

        names.add(
            lower
        )

        output = (
            target /
            lower
        )

        jobs.append(
            (
                url,
                output,
            )
        )

    if not jobs:

        raise RuntimeError(
            "No .mrs/.srs files found in "
            "217heidai/adblockfilters/rules."
        )

    jobs.sort(
        key=lambda x: x[1].name
    )

    print(
        f"FOUND ADBLOCK: "
        f"{len(jobs)}"
    )

    for _, output in jobs:

        print(
            f"  {output.name}"
        )

    download_jobs(
        jobs
    )

    print(
        f"AdBlock files: "
        f"{len(jobs)}"
    )

    print(
        "AdBlock sync completed."
    )


# ============================================================
# 清理
# ============================================================

def clean_rules():

    RULES_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    for directory_name in (
        EXPECTED_DIRS
    ):

        directory = (
            RULES_DIR /
            directory_name
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
# 删除 classical
# ============================================================

def remove_classical(
    root,
):

    for path in root.rglob(
        "*"
    ):

        if not path.is_file():

            continue

        if (
            "_classical"
            in path.name.lower()
        ):

            print(
                f"REMOVE CLASSICAL: "
                f"{path}"
            )

            path.unlink()


# ============================================================
# 验证
# ============================================================

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

    if not root.exists():

        raise RuntimeError(
            "Rules directory does not exist."
        )

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

        for path in directory.iterdir():

            if path.is_dir():

                raise RuntimeError(
                    "Subdirectory detected:\n"
                    f"{path}"
                )

            if path.name != (
                path.name.lower()
            ):

                raise RuntimeError(
                    "Filename is not lowercase:\n"
                    f"{path}"
                )

            if path.suffix.lower() not in allowed:

                raise RuntimeError(
                    "Invalid extension:\n"
                    f"{path}"
                )

            size = (
                path.stat()
                .st_size
            )

            # ------------------------------------------------
            # 只禁止 0 字节
            # ------------------------------------------------

            if size <= 0:

                raise RuntimeError(
                    "Empty rule file:\n"
                    f"{path}"
                )

            total += 1

    # --------------------------------------------------------
    # Classical
    # --------------------------------------------------------

    classical = []

    for path in root.rglob(
        "*"
    ):

        if not path.is_file():

            continue

        if (
            "_classical"
            in path.name.lower()
        ):

            classical.append(
                path
            )

    if classical:

        raise RuntimeError(
            "Classical rules detected:\n"
            +
            "\n".join(
                str(x)
                for x in classical
            )
        )

    # --------------------------------------------------------
    # Meta 合并文件必须不存在
    # --------------------------------------------------------

    meta = (
        root /
        "Mihomo" /
        "meta.mrs"
    )

    if meta.exists():

        raise RuntimeError(
            "meta.mrs exists. "
            "Mihomo rules must NOT be merged."
        )

    # --------------------------------------------------------
    # Facebook / Instagram / Threads
    # --------------------------------------------------------

    for name in (
        "facebook.mrs",
        "instagram.mrs",
        "threads.mrs",
    ):

        path = (
            root /
            "Mihomo" /
            name
        )

        if path.exists():

            print(
                f"OK: {name} "
                "(independent rule)"
            )

    # --------------------------------------------------------
    # YouTube
    # --------------------------------------------------------

    for name in (
        "youtube.mrs",
        "youtubeip.mrs",
    ):

        path = (
            root /
            "Mihomo" /
            name
        )

        if path.exists():

            print(
                f"OK: {name}"
            )

    print()
    print(
        "VALIDATION OK"
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
        "No Mihomo converter."
    )

    print(
        "No rule merging."
    )


# ============================================================
# 主程序
# ============================================================

def main():

    print()
    print("=" * 70)
    print("VERION RULES SYNC")
    print("=" * 70)

    temp_root = Path(
        tempfile.mkdtemp(
            prefix="verion-rules-"
        )
    )

    staging_root = (
        temp_root /
        "rules"
    )

    try:

        staging_root.mkdir(
            parents=True,
            exist_ok=True,
        )

        # ----------------------------------------------------
        # 依次同步
        # ----------------------------------------------------

        sync_mihomo(
            staging_root
        )

        sync_singbox(
            staging_root
        )

        sync_dustinwin(
            staging_root
        )

        sync_geoip(
            staging_root
        )

        sync_cnip(
            staging_root
        )

        sync_adblock(
            staging_root
        )

        # ----------------------------------------------------
        # 清理 classical
        # ----------------------------------------------------

        remove_classical(
            staging_root
        )

        # ----------------------------------------------------
        # 最终验证
        # ----------------------------------------------------

        validate(
            staging_root
        )

        # ----------------------------------------------------
        # 替换正式目录
        # ----------------------------------------------------

        if RULES_DIR.exists():

            shutil.rmtree(
                RULES_DIR
            )

        shutil.copytree(
            staging_root,
            RULES_DIR
        )

        print()
        print("=" * 70)
        print("SYNC COMPLETED")
        print("=" * 70)

    finally:

        shutil.rmtree(
            temp_root,
            ignore_errors=True,
        )


if __name__ == "__main__":

    main()
