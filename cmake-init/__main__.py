# cmake-init - The missing CMake project initializer
# Copyright (C) 2021  friendlyanon
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.

# Website: https://github.com/friendlyanon/cmake-init

"""\
Opinionated CMake project initializer to generate CMake projects that are
FetchContent ready, separate consumer and developer targets, provide install
rules with proper relocatable CMake packages and use modern CMake (3.14+)
"""

import argparse
import contextlib
import io
import os
import re
import subprocess
import sys
import zipfile

from distutils.version import LooseVersion

__version__ = "0.12.1"

zip = zipfile.ZipFile(os.path.dirname(__file__), "r")

is_windows = os.name == "nt"


def not_empty(value):
    return len(value) != 0


def prompt(msg, default, mapper=None, predicate=not_empty, header=None, no_prompt=False):
    if header is not None:
        print(header)
    while True:
        # noinspection PyBroadException
        try:
            print(msg.format(default), end=": ")
            value = ("" if no_prompt else input()) or default
            if mapper is not None:
                value = mapper(value)
            if predicate(value):
                print()
                return value
        except Exception:
            pass
        if no_prompt:
            raise ValueError()
        print("Invalid value, try again")


def is_valid_name(name):
    special = ["test", "lib"]  # special case for this script only
    return name not in special \
        and re.match("^[a-zA-Z][0-9a-zA-Z-_]+$", name) is not None \
        and re.match("[-_]{2,}", name) is None


def is_semver(version):
    return re.match(r"^\d+(\.\d+){0,3}", version) is not None


def get_substitutes(cli_args, name):
    no_prompt = cli_args.flags_used
    if no_prompt and not is_valid_name(name):
        print(f"'{name}' is not a valid name", file=sys.stderr)
        exit(1)

    def ask(*args, **kwargs):
        return prompt(*args, **kwargs, no_prompt=no_prompt)

    d = {
        "name": ask(
            "Project name ({})",
            name,
            predicate=is_valid_name,
            header="Use only characters matching the [0-9a-zA-Z-_] pattern"
        ),
        "version": ask(
            "Project version ({})",
            "0.1.0",
            predicate=is_semver,
            header="""\
Use Semantic Versioning, because CMake naturally supports that. Visit
https://semver.org/ for more information."""
        ),
        "description": ask(*(["Short description"] * 2)),
        "homepage": ask("Homepage URL ({})", "https://example.com/"),
        "type_id": ask(
            "Target type ([E]xecutable or [s]tatic/shared or [h]eader-only)",
            cli_args.type_id or "e",
            mapper=lambda v: v[0:1].lower(),
            predicate=lambda v: v in ["s", "h", "e"],
            header="""\
Type of the target this project provides. A static/shared library will be set
up to hide every symbol by default (as it should) and use an export header to
explicitly mark symbols for export/import, but only when built as a shared
library."""
        ),
        "std": ask(
            "C++ standard (11/14/17/20)",
            cli_args.std or "17",
            predicate=lambda v: v in ["11", "14", "17", "20"],
            header="C++ standard to use. Defaults to 17.",
        ),
        "use_clang_tidy": ask(
            "Add clang-tidy to local dev preset ([Y]es/[n]o)",
            cli_args.use_clang_tidy or "y",
            mapper=lambda v: v[0:1].lower(),
            predicate=lambda v: v in ["y", "n"],
            header="This will require you to download clang-tidy locally.",
        ) == "y",
        "use_cppcheck": ask(
            "Add cppcheck to local dev preset ([Y]es/[n]o)",
            cli_args.use_cppcheck or "y",
            mapper=lambda v: v[0:1].lower(),
            predicate=lambda v: v in ["y", "n"],
            header="This will require you to download cppcheck locally.",
        ) == "y",
        "examples": False,
        "os": "win64" if is_windows else "unix",
    }
    d["uc_name"] = d["name"].upper().replace("-", "_")
    if d["type_id"] != "e":
        d["examples"] = "n" == ask(
            "Exclude examples ([Y]es/[n]o)",
            cli_args.examples or "y",
            mapper=lambda v: v[0:1].lower(),
            predicate=lambda v: v in ["y", "n"],
        )
    return d


def mkdir(path):
    os.makedirs(path, exist_ok=True)


def write_file(path, d, overwrite, zip_path):
    if not overwrite and os.path.exists(path):
        return

    def replacer(match):
        query = match.group(1)
        if query == "type":
            mapping = {"exe": "e", "shared": "s", "header": "h"}
            if mapping[match.group(2)] == d["type_id"]:
                return match.group(3)
        elif query == "if" and d[match.group(2)] is True:
            return match.group(3)
        return ""

    regex = re.compile("{(type|if) ([^}]+)}(.+?){end}", re.DOTALL)
    contents = regex.sub(replacer, zip_path.read_text())
    with open(path, "w", newline="\n") as f:
        f.write(contents % d)


def write_dir(path, d, overwrite, zip_path):
    for entry in zip_path.iterdir():
        name = entry.name.replace("__name__", d["name"])
        next_path = os.path.join(path, name)
        if entry.is_file():
            write_file(next_path, d, overwrite, entry)
        elif name != "example" or d["examples"]:
            mkdir(next_path)
            write_dir(next_path, d, overwrite, entry)


def git_init(cwd):
    branch = ""
    git_version_out = \
        subprocess.run("git --version", shell=True, capture_output=True)
    git_version_str = str(git_version_out.stdout[12:], sys.stdout.encoding)
    git_version = LooseVersion(git_version_str.rstrip())
    if LooseVersion("2.28.0") <= git_version:
        branch = " -b master"
    subprocess.run(f"git init{branch}", shell=True, check=True, cwd=cwd)
    print("""
The project is ready to be used with git. If you are using GitHub, you may
push the project with the following commands from the project directory:

    git add .
    git commit -m "Initial commit"
    git remote add origin https://github.com/<your-account>/<repository>.git
    git push -u origin master
""")


def print_tips(d):
    config = " --config Release" if is_windows else ""
    test_cfg = " -C Release" if is_windows else ""
    cpus = os.cpu_count()
    print(f"""\
To get you started with the project in developer mode, you may configure,
build, install and test with the following commands from the project directory,
in that order:

    cmake --preset=dev
    cmake --build build/dev{config} -j {cpus}
    cmake --install build/dev{config} --prefix prefix
    ctest --test-dir build/dev{test_cfg} -j {cpus} --output-on-failure
""")
    extra = ["    docs - build the documentation using Doxygen and m.css"]
    if d["examples"]:
        extra.append("""\
    run_examples - runs all the examples created by the add_example command""")
    if d["type_id"] == "e":
        extra.append("""\
    run_exe - runs the executable built by the project""")
    print("""\
There are some convenience targets that you can run manually:
""")
    for msg in extra:
        print(msg)
    print(f"""
These targets are only available in developer mode, because they are generally
not useful for consumers. You can run these targets with the following command:

    cmake --build build/dev{config} -t <target>
""")


def create(args):
    """Create a CMake project according to the provided information
    """
    path = args.path
    if not args.overwrite \
            and os.path.exists(path) \
            and os.path.isdir(path) \
            and len(os.listdir(path)) != 0:
        print(
            f"Error - directory exists and is not empty:\n{path}",
            file=sys.stderr,
        )
        exit(1)
    if args.flags_used:
        with contextlib.redirect_stdout(io.StringIO()):
            d = get_substitutes(args, os.path.basename(path))
    else:
        d = get_substitutes(args, os.path.basename(path))
    mkdir(path)
    mapping = {"s": "shared/", "e": "executable/", "h": "header/"}
    zip_paths = ["templates/" + mapping[d["type_id"]], "templates/common/"]
    if args.overwrite:
        zip_paths.reverse()
    for zip_path in zip_paths:
        write_dir(path, d, args.overwrite, zipfile.Path(zip, zip_path))
    git_init(path)
    print_tips(d)
    print("""\
Now make sure you have at least CMake 3.19 installed for local development, to
make use of all the nice Quality-of-Life improvements in newer releases:
https://cmake.org/download/

For more tips, like integration with package managers, please see the Wiki:
http://github.com/friendlyanon/cmake-init/wiki

You are all set. Have fun programming and create something awesome!""")


def vcpkg(d):
    """Generate a vcpkg port in the ports folder, to make writing custom ports
    easier for dependencies on GitHub that are not present among the vcpkg
    provided ports
    """
    path = os.path.join("ports", d["name"])
    if os.path.isdir(path):
        print(f"""'{d["name"]}' already exists""", file=sys.stderr)
        exit(1)
    mkdir(path)
    write_dir(path, d, False, zipfile.Path(zip, "templates/vcpkg/"))
    vcpkg_root = "%VCPKG_ROOT:\=/%" if is_windows else "$VCPKG_ROOT"
    pwd = "%cd:\=/%" if is_windows else "$PWD"
    print(f"""\
The port has been generated in:

    {os.path.realpath(path)}

Please navigate there and edit the placeholders that are surrounded with
<angle brackets> and follow the instructions in the comments. After that's
done, make sure you add the port to your vcpkg manifest for easy integration.
When configuring your project, you must pass some extra variables:

    cmake --preset=dev
    -D "CMAKE_TOOLCHAIN_FILE={vcpkg_root}/scripts/buildsystems/vcpkg.cmake"
    -D "VCPKG_OVERLAY_PORTS={pwd}/ports"

Make sure you always keep up-to-date with vcpkg documentation:
https://github.com/microsoft/vcpkg

See the following example for how integration with vcpkg should look like:
https://github.com/friendlyanon/cmake-init-vcpkg-example""")


def vcpkg_mode():
    if not os.path.isdir(".git") or not os.path.isfile("CMakeLists.txt"):
        print("Working directory is not a CMake project", file=sys.stderr)
        exit(1)
    p = argparse.ArgumentParser(
        prog="cmake-init",
        description=vcpkg.__doc__,
        add_help=False,
    )
    p.add_argument("--vcpkg", dest="name", metavar="<name>", required=True)
    p.set_defaults(type_id="")
    type_g = p.add_mutually_exclusive_group()
    for flag in "sh":
        type_g.add_argument(
            f"-{flag}",
            dest="type_id",
            action="store_const",
            const=flag,
        )
    args = p.parse_args()
    if args.type_id == "":
        args.type_id = prompt(
            "Library type ([S]tatic/shared or [h]eader-only)",
            "s",
            mapper=lambda v: v[0:1].lower(),
            predicate=lambda v: v in "sh",
        )
    vcpkg(args.__dict__)


def get_or(array, index, default):
    try:
        return array[index]
    except IndexError:
        return default


def main():
    # I guess this is similar to how cmake switches modes on the first flag in
    # the CLI, like cmake --build and cmake --install, but how to include that
    # in argparse's help output?
    if get_or(sys.argv, 1, "") == "--vcpkg":
        vcpkg_mode()
        return
    p = argparse.ArgumentParser(
        prog="cmake-init",
        description=__doc__,
        add_help=False,
    )
    p.add_argument(
        "--help",
        action="help",
        help="show this help message and exit",
    )
    p.add_argument("--version", action="version", version=__version__)
    p.set_defaults(overwrite=False, dummy=False)
    p.add_argument(
        "--vcpkg",
        dest="dummy",
        type=lambda _: True,
        metavar="<name>",
        help="\
pass as the first flag to make a vcpkg port of <name> with type -s or -h",
    )
    p.add_argument(
        "path",
        type=os.path.realpath,
        help="path to generate to, the name is also derived from this",
    )
    create_flags = \
        ["type_id", "std", "use_clang_tidy", "use_cppcheck", "examples"]
    p.set_defaults(**{k: "" for k in create_flags})
    type_g = p.add_mutually_exclusive_group()
    mapping = {
        "s": "omit prompts, generate a static/shared library (default)",
        "e": "omit prompts, generate an executable",
        "h": "omit prompts, generate a header-only library",
    }
    for flag, help in mapping.items():
        type_g.add_argument(
            f"-{flag}",
            dest="type_id",
            action="store_const",
            const=flag,
            help=help,
        )
    p.add_argument(
        "--std",
        choices=["11", "14", "17", "20"],
        help="set the C++ standard to use (default: 17)",
    )
    p.add_argument(
        "--no-clang-tidy",
        action="store_const",
        dest="use_clang_tidy",
        const="n",
        help="omit the clang-tidy preset from the dev preset",
    )
    p.add_argument(
        "--no-cppcheck",
        action="store_const",
        dest="use_cppcheck",
        const="n",
        help="omit the cppcheck preset from the dev preset",
    )
    p.add_argument(
        "--overwrite",
        action="store_true",
        help="omit checks for existing files and non-empty project root",
    )
    p.add_argument(
        "--examples",
        action="store_const",
        const="n",
        help="generate examples for a library",
    )
    args = p.parse_args()
    if args.dummy:
        p.print_help()
        exit()
    flags_used = any(getattr(args, k) != "" for k in create_flags)
    setattr(args, "flags_used", flags_used)
    create(args)


try:
    # open a dummy fd to keep the zip from being closed
    with zip.open("__main__.py") as dummy_fp:
        main()
except KeyboardInterrupt:
    pass
