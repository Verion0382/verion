#!/usr/bin/env python3

import json
import shutil
import subprocess
import tempfile
import urllib.request
from pathlib import Path


# ============================================================
# 基础路径
# ============================================================

ROOT = Path(__file__).resolve().parent

RULES_DIR = ROOT / "rules"



# ============================================================
# 输出目录
# ============================================================

MILANGREE_MIHOMO = (
    RULES_DIR /
    "milangree" /
    "Mihomo"
)

MILANGREE_SINGBOX = (
    RULES_DIR /
    "milangree" /
    "SingBox"
)



DUSTINWIN_MIHOMO = (
    RULES_DIR /
    "DustinWin" /
    "Mihomo"
)

DUSTINWIN_SINGBOX = (
    RULES_DIR /
    "DustinWin" /
    "SingBox"
)



METACUBEX_MIHOMO_IPC = (
    RULES_DIR /
    "MetaCubeX" /
    "Mihomo" /
    "ipc"
)


METACUBEX_MIHOMO_DOM = (
    RULES_DIR /
    "MetaCubeX" /
    "Mihomo" /
    "dom"
)



METACUBEX_SINGBOX_IPC = (
    RULES_DIR /
    "MetaCubeX" /
    "SingBox" /
    "ipc"
)


METACUBEX_SINGBOX_DOM = (
    RULES_DIR /
    "MetaCubeX" /
    "SingBox" /
    "dom"
)



CNIP_DIR = RULES_DIR / "cnip"


ADBLOCK_DIR = RULES_DIR / "AdBlock"





# ============================================================
# 仓库
# ============================================================


MILANGREE_REPO = (
    "https://github.com/milangree/rules.git"
)


DUSTINWIN_REPO = (
    "https://github.com/DustinWin/"
    "ruleset_geodata.git"
)


METACUBEX_REPO = (
    "https://github.com/MetaCubeX/"
    "meta-rules-dat.git"
)


CNIP_REPO = (
    "https://github.com/X-Shelby/"
    "geoip.git"
)


ADBLOCK_REPO = (
    "https://github.com/217heidai/"
    "adblockfilters.git"
)



GITHUB_API = (
    "https://api.github.com"
)




# ============================================================
# 执行命令
# ============================================================


def run(cmd, cwd=None):

    print(
        "+",
        " ".join(
            str(x)
            for x in cmd
        )
    )


    subprocess.run(
        cmd,
        cwd=cwd,
        check=True
    )




# ============================================================
# clone
# ============================================================


def clone_repo(
    repo,
    branch=None
):

    temp = Path(
        tempfile.mkdtemp(
            prefix="rules-sync-"
        )
    )


    cmd = [
        "git",
        "clone",
        "--depth",
        "1",
    ]


    if branch:

        cmd.extend(
            [
                "--branch",
                branch
            ]
        )


    cmd.extend(
        [
            repo,
            str(temp)
        ]
    )


    run(cmd)


    return temp





# ============================================================
# GitHub API
# ============================================================


def github_api(url):

    req = urllib.request.Request(
        url,
        headers={
            "User-Agent":
            "rules-sync"
        }
    )


    with urllib.request.urlopen(
        req,
        timeout=60
    ) as r:

        return json.loads(
            r.read()
            .decode("utf-8")
        )





# ============================================================
# 下载
# ============================================================


def download(
    url,
    target
):

    print(
        "download:",
        url
    )


    req = urllib.request.Request(
        url,
        headers={
            "User-Agent":
            "rules-sync"
        }
    )


    with urllib.request.urlopen(
        req,
        timeout=120
    ) as r:

        data = r.read()



    target.parent.mkdir(
        parents=True,
        exist_ok=True
    )


    target.write_bytes(
        data
    )





# ============================================================
# 清理旧目录
# ============================================================


def clean_rules():

    if RULES_DIR.exists():

        print(
            "remove old rules"
        )

        shutil.rmtree(
            RULES_DIR
        )


    RULES_DIR.mkdir(
        parents=True
    )





# ============================================================
# 文件名规范化
# ============================================================


def normalize_filename(filename):

    path = Path(filename)

    stem = path.stem.lower()

    suffix = path.suffix.lower()



    if stem.endswith("_domain"):

        stem = stem[:-7]



    elif stem.endswith("_ipcidr"):

        stem = stem[:-7] + "_ip"



    return stem + suffix





# ============================================================
# classical 排除
# ============================================================


def is_classical(filename):
    """
    排除：

    xxx_classical
    xxx_classical_domain
    xxx_classical_ipcidr
    """

    stem = Path(
        filename
    ).stem.lower()



    return (
        "_classical" in stem
    )





# ============================================================
# 文件过滤
# ============================================================


def should_keep(filename):
    """
    文件过滤

    默认同步所有文件
    仅排除：
    .md
    *_classical*
    """

    lower = filename.lower()


    # 排除 Markdown

    if lower.endswith(".md"):
        return False



    # 排除 classical

    if is_classical(filename):
        return False



    # 其他全部保留

    return True





# ============================================================
# 复制文件
# ============================================================


def get_subfolder(filename):

    # 去掉扩展名
    name = Path(filename).stem.lower()


    # xxx_ip.mrs → xxx
    if name.endswith("_ip"):
        name = name[:-3]


    return name


def copy_rule(
    source,
    destination,
    create_folder=False
):

    if not source.is_file():
        return



    # 排除 .git

    if ".git" in source.parts:
        return



    # 排除声明文件

    if not should_keep(
        source.name
    ):
        return



        # 文件名规范化

    new_name = normalize_filename(
        source.name
    )


    # 自动创建分类文件夹

    if create_folder:

        folder_name = get_subfolder(
            new_name
        )

        target_dir = (
            destination /
            folder_name
        )

    else:

        target_dir = destination


    target_dir.mkdir(
        parents=True,
        exist_ok=True
    )


    target = (
        target_dir /
        new_name
    )


    shutil.copy2(
        source,
        target
    )


    print(
        source.name,
        "->",
        target.relative_to(ROOT)
    )
# ============================================================
# milangree
# ============================================================


def sync_milangree():

    print("\n")
    print("=" * 60)
    print("MILANGREE")
    print("=" * 60)


    repo = clone_repo(
        MILANGREE_REPO,
        branch="main"
    )


    # ========================================================
    # Mihomo
    #
    # rules/mihomo
    #
    # 只同步:
    # .mrs
    # .yaml
    # ========================================================


    print(
        "\n[milangree Mihomo]"
    )


    mihomo_source = (
        repo /
        "rules" /
        "mihomo"
    )


    for file in mihomo_source.rglob("*"):


        if not file.is_file():

            continue


        if file.suffix.lower() not in (
            ".mrs",
            ".yaml",
        ):

            continue


        copy_rule(
            file,
            MILANGREE_MIHOMO,
            create_folder=True
        )



    # ========================================================
    # SingBox
    #
    # rules/singbox
    #
    # 只同步:
    # .srs
    # .json
    # ========================================================


    print(
        "\n[milangree SingBox]"
    )


    singbox_source = (
        repo /
        "rules" /
        "singbox"
    )


    for file in singbox_source.rglob("*"):


        if not file.is_file():

            continue


        if file.suffix.lower() not in (
            ".srs",
            ".json",
        ):

            continue


        copy_rule(
            file,
            MILANGREE_SINGBOX,
            create_folder=True
        )





# ============================================================
# DustinWin
# ============================================================


def sync_dustinwin():

    print("\n")
    print("=" * 60)
    print("DUSTINWIN")
    print("=" * 60)



    # -------------------------
    # Mihomo
    # -------------------------

    print(
        "\n[DustinWin Mihomo]"
    )


    mihomo_repo = clone_repo(
        DUSTINWIN_REPO,
        branch="mihomo-ruleset"
    )


    for file in mihomo_repo.rglob("*"):


        copy_rule(
            file,
            DUSTINWIN_MIHOMO
        )





    # -------------------------
    # SingBox release
    # -------------------------

    print(
        "\n[DustinWin SingBox]"
    )


    release_url = (
        GITHUB_API
        +
        "/repos/DustinWin/"
        "ruleset_geodata/"
        "releases/tags/"
        "sing-box-ruleset"
    )


    release = github_api(
        release_url
    )


    assets = release.get(
        "assets",
        []
    )


    if not assets:

        raise RuntimeError(
            "DustinWin sing-box-ruleset "
            "没有找到release文件"
        )



    for asset in assets:


        name = asset.get(
            "name",
            ""
        )


        if not should_keep(
            name
        ):

            continue



        url = asset.get(
            "browser_download_url"
        )


        if not url:

            continue



        target = (
            DUSTINWIN_SINGBOX
            /
            normalize_filename(
                name
            )
        )


        download(
            url,
            target
        )





# ============================================================
# MetaCubeX
# ============================================================


def sync_metacubex():


    print("\n")
    print("=" * 60)
    print("METACUBEX")
    print("=" * 60)



    # ========================================================
    # Mihomo
    # branch meta
    #
    # geo/
    # ├── geoip
    # └── geosite
    # ========================================================


    print(
        "\n[MetaCubeX Mihomo]"
    )


    repo = clone_repo(
        METACUBEX_REPO,
        branch="meta"
    )


    geo = repo / "geo"



    # geoip -> ipc

    geoip = (
        geo /
        "geoip"
    )


    if geoip.exists():


        for file in geoip.rglob("*"):


            copy_rule(
                file,
                METACUBEX_MIHOMO_IPC,
                create_folder=True
            )



    # geosite -> dom

    geosite = (
        geo /
        "geosite"
    )


    if geosite.exists():


        for file in geosite.rglob("*"):


            copy_rule(
                file,
                METACUBEX_MIHOMO_DOM,
                create_folder=True
            )







    # ========================================================
    # SingBox
    # branch sing
    #
    # geo/
    # ├── geoip
    # └── geosite
    # ========================================================


    print(
        "\n[MetaCubeX SingBox]"
    )



    repo = clone_repo(
        METACUBEX_REPO,
        branch="sing"
    )



    geo = repo / "geo"



    # geoip -> ipc

    geoip = (
        geo /
        "geoip"
    )


    if geoip.exists():


        for file in geoip.rglob("*"):


            copy_rule(
                file,
                METACUBEX_SINGBOX_IPC,
                create_folder=True
            )




    # geosite -> dom

    geosite = (
        geo /
        "geosite"
    )


    if geosite.exists():


        for file in geosite.rglob("*"):


            copy_rule(
                file,
                METACUBEX_SINGBOX_DOM,
                create_folder=True
            )
    # ============================================================
# cnip
#
# X-Shelby/geoip
# Release latest
# ============================================================


def sync_cnip():

    print("\n")
    print("=" * 60)
    print("CNIP")
    print("=" * 60)



    release_url = (
        GITHUB_API
        +
        "/repos/X-Shelby/"
        "geoip/releases/latest"
    )


    release = github_api(
        release_url
    )


    assets = release.get(
        "assets",
        []
    )



    if not assets:

        raise RuntimeError(
            "X-Shelby geoip "
            "latest release 无文件"
        )



    for asset in assets:


        name = asset.get(
            "name",
            ""
        )


        # 过滤格式

        if not should_keep(
            name
        ):

            continue



        url = asset.get(
            "browser_download_url"
        )


        if not url:

            continue



        target = (
            CNIP_DIR
            /
            normalize_filename(
                name
            )
        )



        download(
            url,
            target
        )


        print(
            name,
            "->",
            target.relative_to(ROOT)
        )







# ============================================================
# AdBlock
# ============================================================


def sync_adblock():

    print("\n")
    print("=" * 60)
    print("ADBLOCK")
    print("=" * 60)



    repo = clone_repo(
        ADBLOCK_REPO,
        branch="main"
    )


    source = (
        repo /
        "rules"
    )


    if not source.exists():

        raise RuntimeError(
            "AdBlock rules目录不存在"
        )



    for file in source.rglob("*"):


        copy_rule(
            file,
            ADBLOCK_DIR
        )







# ============================================================
# 验证目录
# ============================================================


def validate():


    print("\n")
    print("=" * 60)
    print("VALIDATE")
    print("=" * 60)



    dirs = [

        MILANGREE_MIHOMO,
        MILANGREE_SINGBOX,

        DUSTINWIN_MIHOMO,
        DUSTINWIN_SINGBOX,

        METACUBEX_MIHOMO_IPC,
        METACUBEX_MIHOMO_DOM,

        METACUBEX_SINGBOX_IPC,
        METACUBEX_SINGBOX_DOM,

        CNIP_DIR,

        ADBLOCK_DIR,
    ]



    errors = []



    for directory in dirs:


        if not directory.exists():

            errors.append(
                f"Missing directory: {directory}"
            )

            continue



        files = list(
            directory.rglob("*")
        )


        if not any(
            f.is_file()
            for f in files
        ):

            errors.append(
                f"Empty directory: {directory}"
            )



        for file in files:


            if not file.is_file():

                continue



            name = file.name.lower()



            # md

            if name.endswith(
                ".md"
            ):

                errors.append(
                    f"Markdown file: {file}"
                )



            # classical

            if is_classical(
                file.name
            ):

                errors.append(
                    f"Classical file: {file}"
                )



            # 文件名大小写

            if file.name != name:

                errors.append(
                    f"Uppercase filename: {file}"
                )




    if errors:


        print(
            "\nValidation FAILED"
        )


        for e in errors:

            print(
                "ERROR:",
                e
            )


        raise RuntimeError(
            "validation failed"
        )



    print(
        "Validation PASSED"
    )








# ============================================================
# 统计
# ============================================================


def statistics():


    print("\n")
    print("=" * 60)
    print("STATISTICS")
    print("=" * 60)



    dirs = [

        MILANGREE_MIHOMO,
        MILANGREE_SINGBOX,

        DUSTINWIN_MIHOMO,
        DUSTINWIN_SINGBOX,

        METACUBEX_MIHOMO_IPC,
        METACUBEX_MIHOMO_DOM,

        METACUBEX_SINGBOX_IPC,
        METACUBEX_SINGBOX_DOM,

        CNIP_DIR,

        ADBLOCK_DIR,
    ]



    total = 0



    for directory in dirs:


        count = sum(

            1

            for f in directory.rglob("*")

            if f.is_file()

        )


        total += count


        print(
            directory.relative_to(ROOT),
            ":",
            count
        )



    print(
        "Total:",
        total
    )








# ============================================================
# MAIN
# ============================================================


def main():


    print(
        "=" * 60
    )

    print(
        "RULES SYNC START"
    )

    print(
        "=" * 60
    )



    # 清理旧目录

    clean_rules()



    # 同步

    sync_milangree()


    sync_dustinwin()


    sync_metacubex()


    sync_cnip()


    sync_adblock()



    # 验证

    validate()



    # 统计

    statistics()



    print(
        "\nSYNC COMPLETED"
    )






if __name__ == "__main__":

    main()
