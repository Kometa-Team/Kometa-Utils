import argparse, os, platform, re, requests, uuid
from dotenv import load_dotenv
from functools import cached_property
from pathlib import Path
from .exceptions import Failed

def parse_choice(env_str, default, arg_bool=False, arg_int=False):
    env_value = os.environ.get(env_str)
    if env_value is None:
        return default
    elif arg_bool:
        return parse_bool(env_value, default)
    elif arg_int:
        try:
            return int(env_value)
        except ValueError:
            return default
    else:
        return str(env_value)

def parse_bool(value, default=None):
    if value is True or value is False:
        return value
    elif value.lower() in ["t", "true", "1", "y", "yes"]:
        return True
    elif value.lower() in ["f", "false", "0", "n", "no"]:
        return False
    else:
        return default

class Version:
    def __init__(self, original="Unknown", text="develop"):
        self.original = original
        self.text = text
        self.version = self.original.replace("develop", self.text)
        split_version = self.version.split(f"-{self.text}")
        self.master = split_version[0]
        self.patch = int(split_version[1]) if len(split_version) > 1 else 0
        sp = self.master.split(".")
        sep = (0, 0, 0) if self.original == "Unknown" or len(sp) < 3 else sp
        self.compare = (sep[0], sep[1], sep[2], self.patch)
        self._has_patch = None

    def same_master(self, other):
        return self.master == other.master

    def has_patch(self):
        return self.patch > 0

    def __str__(self):
        return self.version

    def __bool__(self):
        return self.original != "Unknown"

    def __eq__(self, other):
        return self.compare == other.compare

    def __ne__(self, other):
        return self.compare != other.compare

    def __lt__(self, other):
        return self.compare < other.compare

    def __le__(self, other):
        return self.compare <= other.compare

    def __gt__(self, other):
        return self.compare > other.compare

    def __ge__(self, other):
        return self.compare >= other.compare

class KometaArgs:
    def __init__(self, repo_name, base_dir, options, config_folder="config", use_nightly=True, running_nightly=False):
        self.repo = repo_name
        self.base_dir = Path(base_dir)
        self.options = options
        self.use_nightly = use_nightly
        self.running_nightly = running_nightly
        self.original_choices = {}
        self.choices = {}
        parser = argparse.ArgumentParser()
        if not isinstance(options, list):
            raise ValueError("options must be a list")
        for o in self.options:
            for atr in ["type", "arg", "env", "key", "help", "default"]:
                if atr not in o:
                    raise AttributeError(f"{o} attribute must be in every option")
            if o["type"] == "int":
                parser.add_argument(f"-{o['arg']}", f"--{o['key']}", dest=o["key"], help=o["help"], type=int, default=o["default"])
            elif o["type"] == "bool":
                parser.add_argument(f"-{o['arg']}", f"--{o['key']}", dest=o["key"], help=o["help"], action="store_true", default=o["default"])
            else:
                parser.add_argument(f"-{o['arg']}", f"--{o['key']}", dest=o["key"], help=o["help"])
        args_parsed = parser.parse_args()
        load_dotenv(self.base_dir / config_folder / ".env" if config_folder else self.base_dir / ".env")

        for o in self.options:
            value = parse_choice(o["env"], getattr(args_parsed, o["key"]), arg_int=o["type"] == "int", arg_bool=o["type"] == "bool")
            self.original_choices[o["key"]] = value
            self.choices[o["key"]] = value

    def __getitem__(self, key):
        if key in self.choices:
            return self.choices[key]
        raise KeyError(key)

    def __setitem__(self, key, value):
        self.choices[key] = value

    def __contains__(self, key):
        return key in self.choices

    def _github_request(self, path, repo=None, params=None):
        response = requests.get(f"https://api.github.com/repos/{repo or self.repo}/{path}", params=params)
        if response.status_code >= 400:
            raise Failed(f"({response.status_code} [{response.reason}]) {response.json()}")
        return response.json()

    def git_release_notes(self, repo=None):
        return self._github_request("releases/latest", repo=repo)["body"]

    def git_commits(self, repo=None):
        master_sha = self._github_request("commits/master", repo=repo)["sha"]
        commits = []
        for commit in self._github_request("commits", repo=repo, params={"sha": "nightly" if self.is_nightly else "develop"}):
            if commit["sha"] == master_sha:
                break
            message = commit["commit"]["message"]
            match = re.match("^\\[(\\d)\\]", message)
            if match and int(match.group(1)) <= self.local_version.patch:
                break
            commits.append(message)
        return "\n".join(commits)

    def git_tags(self, repo=None):
        return [r["ref"][11:] for r in self._github_request("git/refs/tags", repo=repo)]

    @cached_property
    def update_notes(self):
        if self.update_version and self.local_version:
            if not self.update_version.same_master(self.local_version):
                return self.git_release_notes()
            elif self.local_version.patch and self.local_version < self.update_version:
                return self.git_commits()
        return None

    @cached_property
    def uuid(self):
        uuid_file = self.base_dir / "config" / "UUID"
        if uuid_file.exists():
            with uuid_file.open() as handle:
                for line in handle.readlines():
                    line = line.strip()
                    if len(line) > 0:
                        return str(line)
        _uuid = str(uuid.uuid4())
        with uuid_file.open(mode="w") as handle:
            handle.write(_uuid)
        return _uuid

    @cached_property
    def system_version(self):
        if self.is_docker:
            return "(Docker)"
        elif self.is_linuxserver:
            return "(Linuxserver)"
        else:
            return f"(Python {platform.python_version()}){f' (Git: {self.local_branch})' if self.local_branch else ''}"

    @cached_property
    def is_docker(self):
        return parse_choice("KOMETA_DOCKER", False, arg_bool=True)

    @cached_property
    def is_linuxserver(self):
        return parse_choice("KOMETA_LINUXSERVER", False, arg_bool=True)

    @cached_property
    def local_version(self):
        ver = Version()
        with (self.base_dir / "VERSION").open() as handle:
            for line in handle.readlines():
                line = line.strip()
                if len(line) > 0:
                    ver = Version(line)
        return ver

    @cached_property
    def nightly_version(self):
        return self.online_version("nightly")

    @cached_property
    def develop_version(self):
        return self.online_version("develop")

    @cached_property
    def master_version(self):
        return self.online_version("master")

    def online_version(self, level):
        try:
            response = requests.get(f"https://raw.githubusercontent.com/{self.repo}/{level}/VERSION")
            if response.status_code < 400:
                return Version(response.content.decode().strip(), text=level)
        except requests.exceptions.ConnectionError:
            pass
        return Version()

    @cached_property
    def version(self):
        match self.branch:
            case "nightly":
                return self.nightly_version
            case "develop":
                return self.develop_version
            case _:
                return self.master_version

    @cached_property
    def update_version(self):
        return self.version if self.version and self.local_version < self.version else None

    @cached_property
    def local_branch(self):
        try:
            from git import Repo
            return Repo(path=".").head.ref.name # noqa
        except Exception:
            return None

    @cached_property
    def env_branch(self):
        return parse_choice("BRANCH_NAME", "master")

    @cached_property
    def branch(self):
        if self.running_nightly:
            return "nightly"
        elif self.local_branch:
            return self.local_branch
        elif self.env_branch in ["nightly", "develop"]:
            return self.env_branch
        elif self.local_version.has_patch():
            return "develop" if not self.use_nightly or self.local_version <= self.develop_version else "nightly"
        else:
            return "master"

    @cached_property
    def is_nightly(self):
        return self.branch == "nightly"

    @cached_property
    def is_develop(self):
        return self.branch == "develop"

    @cached_property
    def is_master(self):
        return self.branch == "master"

