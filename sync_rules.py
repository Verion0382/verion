import io
import shutil
import time
import zipfile
import requests

from pathlib import Path


# ============================================================
# 基础配置
# ============================================================

ROOT = Path("rules")

MAX_RETRIES = 8

HEADERS = {
    "User-Agent": "verion-rules-sync",
    "Accept": "application/vnd.github+json",
    "X-GitHub-Api-Version": "2022-11-28",
}

session = requests.Session()

session.headers.update(
    HEADERS
)


# ============================================================
# 基础目录工具
# ============================================================

def clean_dir(path: Path):

    if path.exists():

        shutil.rmtree(
            path
        )

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
# GitHub API 请求
#
# 自动处理：
# 429
# 403 Rate Limit
# 网络错误
# ============================================================

def github_get(
    url,
    params=None,
    timeout=120
):

    for attempt in range(
        1,
        MAX_RETRIES + 1
    ):

        try:

            response = session.get(
                url,
                params=params,
                timeout=timeout
            )

            # ------------------------------------------------
            # 429
            # ------------------------------------------------

            if response.status_code == 429:

                retry_after = (
                    response.headers.get(
                        "Retry-After"
                    )
                )

                if retry_after:

                    wait = int(
                        retry_after
                    )

                else:

                    wait = min(
                        10 * attempt,
                        120
                    )

                print(
                    f"GitHub API 429 "
                    f"rate limit."
                )

                print(
                    f"Waiting {wait}s..."
                )

                time.sleep(
                    wait
                )

                continue

            # ------------------------------------------------
            # 403 Rate Limit
            # ------------------------------------------------

            if response.status_code == 403:

                remaining = (
                    response.headers.get(
                        "X-RateLimit-Remaining"
                    )
                )

                if remaining == "0":

                    reset = (
                        response.headers.get(
                            "X-RateLimit-Reset"
                        )
                    )

                    if reset:

                        wait = max(
                            int(reset)
                            - int(time.time())
                            + 5,
                            5
                        )

                    else:

                        wait = min(
                            10 * attempt,
                            120
                        )

                    print(
                        "GitHub API rate limit."
                    )

                    print(
                        f"Waiting {wait}s..."
                    )

                    time.sleep(
                        wait
                    )

                    continue

            response.raise_for_status()

            return response

        except requests.RequestException as error:

            if attempt >= MAX_RETRIES:

                raise

            wait = min(
                5 * attempt,
                60
            )

            print(
                f"Request failed: {error}"
            )

            print(
                f"Retrying in {wait}s..."
            )

            time.sleep(
                wait
            )

    raise RuntimeError(
        f"GitHub request failed: {url}"
    )


# ============================================================
# GitHub Contents API
#
# 自动分页
# ============================================================

def github_contents(
    owner,
    repo,
    path="",
    branch="main"
):

    url = (
        f"https://api.github.com/repos/"
        f"{owner}/{repo}/contents/"
        f"{path}"
    )

    all_items = []

    page = 1

    while True:

        params = {
            "ref": branch,
            "per_page": 100,
            "page": page,
        }

        response = github_get(
            url,
            params=params
        )

        data = response.json()

        if not isinstance(
            data,
            list
        ):

            return [
                data
            ]

        all_items.extend(
            data
        )

        if len(data) < 100:

            break

        page += 1

    return all_items


# ============================================================
# 递归扫描 GitHub 目录
# ============================================================

def github_tree_files(
    owner,
    repo,
    path,
    branch="main"
):

    result = []

    items = github_contents(
        owner,
        repo,
        path,
        branch
    )

    for item in items:

        item_type = item.get(
            "type"
        )

        item_path = item.get(
            "path",
            ""
        )

        # ----------------------------------------------------
        # 文件
        # ----------------------------------------------------

        if item_type == "file":

            result.append(
                item
            )

        # ----------------------------------------------------
        # 子目录
        # ----------------------------------------------------

        elif item_type == "dir":

            print(
                f"SCAN: {item_path}"
            )

            result.extend(

                github_tree_files(

                    owner,
                    repo,
                    item_path,
                    branch

                )

            )

    return result


# ============================================================
# 下载 GitHub 文件
# ============================================================

def download_github_file(
    item,
    output
):

    url = item.get(
        "download_url"
    )

    if not url:

        raise RuntimeError(
            f"No download_url: "
            f"{item.get('path')}"
        )

    print(
        f"DOWNLOAD: "
        f"{item['path']}"
        f" -> "
        f"{output.name}"
    )

    response = session.get(
        url,
        timeout=300
    )

    response.raise_for_status()

    ensure_dir(
        output.parent
    )

    output.write_bytes(
        response.content
    )


# ============================================================
# ZIP 下载
# ============================================================

def download_zip(url):

    print()
    print(
        f"DOWNLOAD ZIP:"
    )

    print(
        url
    )

    response = session.get(
        url,
        timeout=300
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
# ZIP 提取规则
#
# 不保留子目录
# 文件名小写
# ============================================================

def extract_rules(
    zip_file,
    target_dir,
    source_prefix=None,
    extensions=None,
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

    count = 0

    used_names = {}

    for info in zip_file.infolist():

        if info.is_dir():

            continue

        original_path = Path(
            info.filename
        )

        # ----------------------------------------------------
        # 去掉 ZIP 第一层
        # ----------------------------------------------------

        if len(
            original_path.parts
        ) < 2:

            continue

        relative_path = Path(
            *original_path.parts[1:]
        )

        # ----------------------------------------------------
        # 源目录过滤
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
        # 扩展名
        # ----------------------------------------------------

        suffix = (
            relative_path.suffix
            .lower()
        )

        if extensions:

            if suffix not in extensions:

                continue

        # ----------------------------------------------------
        # 文件名小写
        # ----------------------------------------------------

        filename = (
            relative_path.name
            .lower()
        )

        # ----------------------------------------------------
        # 重名检测
        # ----------------------------------------------------

        if filename in used_names:

            raise RuntimeError(

                "Filename collision:\n"
                f"  {used_names[filename]}\n"
                f"  {relative_path}\n"
                f"  -> {filename}"

            )

        used_names[
            filename
        ] = str(
            relative_path
        )

        output = (
            target_dir /
            filename
        )

        print(
            f"  {relative_path}"
            f" -> {filename}"
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

    return count


# ============================================================
# 通用 ZIP 同步
# ============================================================

def sync_repository(
    url,
    target_dir,
    source_prefix=None,
    extensions=None,
    clean=True
):

    zip_file = download_zip(
        url
    )

    try:

        count = extract_rules(

            zip_file=zip_file,

            target_dir=target_dir,

            source_prefix=source_prefix,

            extensions=extensions,

            clean=clean

        )

    finally:

        zip_file.close()

    print()
    print(
        f"SYNC DONE: "
        f"{target_dir}"
    )

    print(
        f"FILES: {count}"
    )

    if count == 0:

        raise RuntimeError(
            f"No files found for "
            f"{target_dir}"
        )

    return count


# ============================================================
# Release API
# ============================================================

def get_release_assets(
    owner,
    repo,
    tag
):

    url = (
        f"https://api.github.com/repos/"
        f"{owner}/{repo}/releases/tags/{tag}"
    )

    response = github_get(
        url
    )

    data = response.json()

    return data.get(
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
        owner,
        repo,
        tag
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

    print()
    print(
        f"Release: "
        f"{owner}/{repo}"
    )

    print(
        f"Tag: {tag}"
    )

    print(
        f"{extension} files: "
        f"{len(selected)}"
    )

    if not selected:

        raise RuntimeError(
            f"No {extension} assets found."
        )

    count = 0

    used_names = set()

    for asset in selected:

        filename = (
            asset["name"]
            .lower()
        )

        if filename in used_names:

            raise RuntimeError(
                f"Duplicate asset: "
                f"{filename}"
            )

        used_names.add(
            filename
        )

        output = (
            target_dir /
            filename
        )

        download_file(

            asset[
                "browser_download_url"
            ],

            output

        )

        count += 1

    return count


# ============================================================
# 普通文件下载
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
        timeout=300
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
# 1. Milangree Mihomo
#
# 来源：
#
# https://github.com/milangree/rules/tree/main/rules/mihomo
#
# 只取 .mrs
#
# 命名：
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
#
# 不保留子目录
# ============================================================

def sync_milangree_mihomo():

    print()
    print("=" * 70)
    print("1. MILANGREE MIHOMO")
    print("=" * 70)

    target_dir = (
        ROOT /
        "Mihomo"
    )

    clean_dir(
        target_dir
    )

    files = github_tree_files(

        owner="milangree",

        repo="rules",

        path="rules/mihomo",

        branch="main"

    )

    print()
    print(
        f"Total files found: "
        f"{len(files)}"
    )

    selected = []

    for item in files:

        filename = item.get(
            "name",
            ""
        )

        # ----------------------------------------------------
        # 只取 MRS
        # ----------------------------------------------------

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

        # ----------------------------------------------------
        # 排除 classical
        # ----------------------------------------------------

        if stem_lower.endswith(
            "_classical"
        ):

            print(
                f"SKIP: "
                f"{item['path']}"
            )

            continue

        selected.append(
            item
        )

    print()
    print(
        f"Mihomo .mrs found: "
        f"{len(selected)}"
    )

    if not selected:

        raise RuntimeError(
            "No Mihomo .mrs files found."
        )

    used_names = {}

    count = 0

    for item in selected:

        original_name = item[
            "name"
        ]

        stem = Path(
            original_name
        ).stem

        stem_lower = (
            stem.lower()
        )

        # ----------------------------------------------------
        # _domain
        #
        # YouTube_domain.mrs
        # ->
        # youtube.mrs
        # ----------------------------------------------------

        if stem_lower.endswith(
            "_domain"
        ):

            base = stem[
                :-len("_domain")
            ]

            new_name = (
                base +
                ".mrs"
            )

        # ----------------------------------------------------
        # _ipcidr
        #
        # YouTube_ipcidr.mrs
        # ->
        # youtubeip.mrs
        # ----------------------------------------------------

        elif stem_lower.endswith(
            "_ipcidr"
        ):

            base = stem[
                :-len("_ipcidr")
            ]

            new_name = (
                base +
                "ip.mrs"
            )

        # ----------------------------------------------------
        # 其他 MRS
        # ----------------------------------------------------

        else:

            new_name = (
                stem +
                ".mrs"
            )

        # ----------------------------------------------------
        # 全部小写
        # ----------------------------------------------------

        new_name = (
            new_name.lower()
        )

        # ----------------------------------------------------
        # 检查重名
        # ----------------------------------------------------

        if new_name in used_names:

            raise RuntimeError(

                "Mihomo filename collision:\n"
                f"  {used_names[new_name]}\n"
                f"  {item['path']}\n"
                f"  -> {new_name}"

            )

        used_names[
            new_name
        ] = item[
            "path"
        ]

        output = (
            target_dir /
            new_name
        )

        print(
            f"  {item['path']}"
            f" -> {new_name}"
        )

        download_github_file(
            item,
            output
        )

        count += 1

    print()
    print(
        f"Mihomo completed: "
        f"{count} files"
    )

    return count


# ============================================================
# 开始同步
# ============================================================

ROOT.mkdir(
    parents=True,
    exist_ok=True
)


# ============================================================
# 1. Mihomo
# ============================================================

sync_milangree_mihomo()


# ============================================================
# 2. SingBox
#
# Milangree
# rules/singbox
#
# 只取 .srs
# ============================================================

print()
print("=" * 70)
print("2. MILANGREE SINGBOX")
print("=" * 70)

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
# mihomo-ruleset
#
# 只取 .mrs
# ============================================================

print()
print("=" * 70)
print("3. DUSTINWIN MIHOMO")
print("=" * 70)

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
# 只取 .srs
#
# clean=False
#
# 保留上一步的 .mrs
# ============================================================

print()
print("=" * 70)
print("4. DUSTINWIN SINGBOX")
print("=" * 70)

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
# 5. GeoIP
#
# MetaCubeX
#
# 只取 .mrs
# ============================================================

print()
print("=" * 70)
print("5. GEOIP")
print("=" * 70)

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
# 6. CNIP
#
# X-Shelby
#
# MRS + SRS
# ============================================================

print()
print("=" * 70)
print("6. CNIP")
print("=" * 70)

cnip_dir = (
    ROOT /
    "cnip"
)

clean_dir(
    cnip_dir
)

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

for filename in CNIP_FILES:

    download_file(

        X_SHELBY_RELEASE +
        filename,

        cnip_dir /
        filename.lower()

    )


# ============================================================
# 7. AdBlock
#
# 217heidai
#
# MRS + SRS
# ============================================================

print()
print("=" * 70)
print("7. ADBLOCK")
print("=" * 70)

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
# 8. 清理子目录
# ============================================================

print()
print("=" * 70)
print("8. REMOVE SUBDIRECTORIES")
print("=" * 70)

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
# 9. 检查顶层目录
# ============================================================

print()
print("=" * 70)
print("9. DIRECTORY CHECK")
print("=" * 70)

ALLOWED_DIRECTORIES = {

    "Mihomo",
    "SingBox",
    "DustinWin",
    "geoip",
    "cnip",
    "AdBlock",

}

actual_directories = {

    path.name

    for path in ROOT.iterdir()

    if path.is_dir()

}

unexpected = (
    actual_directories
    - ALLOWED_DIRECTORIES
)

missing = (
    ALLOWED_DIRECTORIES
    - actual_directories
)


if unexpected:

    raise RuntimeError(
        "Unexpected directories:\n"
        +
        "\n".join(
            sorted(unexpected)
        )
    )


if missing:

    raise RuntimeError(
        "Missing directories:\n"
        +
        "\n".join(
            sorted(missing)
        )
    )


# ============================================================
# 10. 检查不能存在子目录
# ============================================================

print(
    "Checking subdirectories..."
)

for directory in ROOT.iterdir():

    if not directory.is_dir():

        continue

    for path in directory.rglob("*"):

        if path.is_dir():

            raise RuntimeError(
                f"Subdirectory detected: "
                f"{path}"
            )


print(
    "OK: No subdirectories."
)


# ============================================================
# 11. 检查文件名
#
# 全部小写
# ============================================================

print()
print("=" * 70)
print("11. FILENAME CHECK")
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
# 12. 检查扩展名
# ============================================================

print()
print("=" * 70)
print("12. EXTENSION CHECK")
print("=" * 70)

for path in ROOT.rglob("*"):

    if not path.is_file():

        continue

    suffix = (
        path.suffix
        .lower()
    )

    directory = (
        path.parent.name
    )

    if directory == "Mihomo":

        allowed = {
            ".mrs"
        }

    elif directory == "SingBox":

        allowed = {
            ".srs"
        }

    elif directory == "DustinWin":

        allowed = {
            ".mrs",
            ".srs"
        }

    elif directory == "geoip":

        allowed = {
            ".mrs"
        }

    elif directory == "cnip":

        allowed = {
            ".mrs",
            ".srs"
        }

    elif directory == "AdBlock":

        allowed = {
            ".mrs",
            ".srs"
        }

    else:

        raise RuntimeError(
            f"Unknown directory: "
            f"{directory}"
        )

    if suffix not in allowed:

        raise RuntimeError(
            f"Invalid extension: "
            f"{path}"
        )


print(
    "OK: Extensions valid."
)


# ============================================================
# 13. 检查 Mihomo classical
#
# 确保没有 *_classical.mrs
# ============================================================

print()
print("=" * 70)
print("13. MIHOMO CLASSICAL CHECK")
print("=" * 70)

classical_files = []

mihomo_dir = (
    ROOT /
    "Mihomo"
)

for path in mihomo_dir.iterdir():

    if not path.is_file():

        continue

    if path.name.lower().endswith(
        "_classical.mrs"
    ):

        classical_files.append(
            str(path)
        )


if classical_files:

    raise RuntimeError(

        "Classical files detected:\n"
        +
        "\n".join(
            classical_files
        )

    )


print(
    "OK: No classical files."
)


# ============================================================
# 14. 检查 Mihomo 命名
#
# 例如：
#
# youtube.mrs
# youtubeip.mrs
#
# 不允许：
#
# youtube_domain.mrs
# youtube_ipcidr.mrs
# youtube_classical.mrs
# ============================================================

print()
print("=" * 70)
print("14. MIHOMO NAMING CHECK")
print("=" * 70)

for path in mihomo_dir.iterdir():

    if not path.is_file():

        continue

    name = path.name.lower()

    if name.endswith(
        "_domain.mrs"
    ):

        raise RuntimeError(
            f"Unconverted domain file: "
            f"{path}"
        )

    if name.endswith(
        "_ipcidr.mrs"
    ):

        raise RuntimeError(
            f"Unconverted ipcidr file: "
            f"{path}"
        )


print(
    "OK: Mihomo naming valid."
)


# ============================================================
# 15. CNIP 检查
# ============================================================

print()
print("=" * 70)
print("15. CNIP CHECK")
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

actual_cnip = {

    path.name

    for path in cnip_dir.iterdir()

    if path.is_file()

}

missing_cnip = (
    required_cnip
    - actual_cnip
)


if missing_cnip:

    raise RuntimeError(

        "Missing CNIP files:\n"
        +
        "\n".join(
            sorted(missing_cnip)
        )

    )


print(
    "OK: CNIP complete."
)


# ============================================================
# 16. 最终统计
# ============================================================

print()
print("=" * 70)
print("16. FINAL STATISTICS")
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

    mrs_count = 0
    srs_count = 0

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
    "=" * 70
)

print(
    "ALL RULES SYNC FINISHED"
)

print(
    "=" * 70
)
