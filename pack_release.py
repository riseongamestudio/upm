"""Publishes one RiseOn package version as a GitHub release of its own repo, for the registry to index.

A repo holding one package at its root tags "v<version>"; a repo holding several keeps each in its own folder and tags
"<package name>/<version>". The release takes the tag's name and holds one asset, "<package name>-<version>.tgz", the
package's folder at that tag as an npm tarball. A release already holding its asset is left as it is, so a version
goes up once.

    python pack_release.py <tag>      # in the pack repo's checkout; needs GH_TOKEN and GITHUB_REPOSITORY
"""
import io, json, os, re, subprocess, sys, tarfile, tempfile

# A version UPM reads: numbers, then an optional pre-release suffix such as "-preview.1".
VERSION = re.compile(r"^\d+\.\d+\.\d+(-[0-9A-Za-z.-]+)?$")


def git(*args):
    return subprocess.run(["git", *args], check=True, capture_output=True).stdout


def gh(*args, check=True):
    return subprocess.run(["gh", *args, "-R", os.environ["GITHUB_REPOSITORY"]], check=check, capture_output=True, text=True)


def manifest_at(tag, path):
    return json.loads(git("show", f"{tag}:{path}").decode("utf-8-sig"))


def package_folder(tag):
    """The folder of the package the tag names, and its name and version."""
    if tag.startswith("v"):
        return "", manifest_at(tag, "package.json"), tag[1:]
    name, _, version = tag.partition("/")
    for path in git("ls-tree", "-r", "--name-only", tag).decode().splitlines():
        if path.count("/") == 1 and path.endswith("/package.json") and manifest_at(tag, path).get("name") == name:
            return path.split("/")[0], manifest_at(tag, path), version
    sys.exit(f"{tag}: no folder holds package.json of {name}")


def tarball(tag, folder):
    """The folder at the tag, as git exports it, under "package/"."""
    prefix = folder + "/" if folder else ""
    out = io.BytesIO()
    with tarfile.open(fileobj=io.BytesIO(git("archive", "--format=tar", tag, *([folder] if folder else []))), mode="r:") as source, \
            tarfile.open(fileobj=out, mode="w:gz") as target:
        for member in source.getmembers():
            if member.type in (tarfile.XGLTYPE, tarfile.XHDTYPE) or not member.name.startswith(prefix):
                continue
            path = member.name[len(prefix):].strip("/")
            if not path:
                continue
            content = source.extractfile(member) if member.isfile() else None
            member.name = "package/" + path
            target.addfile(member, content)
    return out.getvalue()


def main(tag):
    folder, manifest, version = package_folder(tag)
    name = manifest["name"]
    if manifest.get("version") != version or not VERSION.match(version):
        sys.exit(f"{tag}: its package.json is {name}@{manifest.get('version')}, not published")

    asset = f"{name}-{version}.tgz"
    view = gh("release", "view", tag, "--json", "assets", check=False)
    if view.returncode == 0 and any(each["name"] == asset for each in json.loads(view.stdout)["assets"]):
        print(f"{asset} is published already")
        return

    with tempfile.TemporaryDirectory() as temp:
        path = os.path.join(temp, asset)
        with open(path, "wb") as file:
            file.write(tarball(tag, folder))
        if view.returncode != 0:
            gh("release", "create", tag, path, "--verify-tag", "--title", f"{name} {version}",
               "--notes", "The package as the RiseOn UPM registry serves it.")
        else:
            gh("release", "upload", tag, path)
    print("published", asset)


if __name__ == "__main__":
    main(sys.argv[1])