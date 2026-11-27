"""Fills this repo's static UPM registry: RiseOn's own packages, built from their git tags, and mirrors of third-party
Unity packages.

Every package version is uploaded once, as its maker published it, to a GitHub release of this repo; the registry
folder holds one packument per package and the search files Unity's Package Manager reads. A version already in the
registry is never uploaded again, so a tag moved after its package went up changes nothing.

    python mirror.py <registry folder>      # needs GH_TOKEN and GITHUB_REPOSITORY, as the workflow sets them
"""
import base64, datetime, hashlib, io, json, os, re, subprocess, sys, tarfile, tempfile, urllib.error, urllib.request

REPO = os.environ["GITHUB_REPOSITORY"]
SITE = "https://upm.riseongamestudio.com"

# Firebase: every package Google publishes for Unity, from 13.17.0 on, taken from Google's own UPM tarballs.
FIREBASE_PACKAGES = [
    "app", "analytics", "app-check", "auth", "crashlytics", "database", "firebaseai", "firestore", "functions",
    "installations", "messaging", "remote-config", "storage",
]
FIREBASE_FROM = (13, 17, 0)
FIREBASE_TARBALL = "https://dl.google.com/games/registry/unity/com.google.firebase.{0}/com.google.firebase.{0}-{1}.tgz"

# AppsFlyer publishes its UPM package only as the head of its upm branch, rewritten at each release, so each new
# version there is mirrored as it appears.
APPSFLYER_REPO = "AppsFlyerSDK/appsflyer-unity-plugin"
APPSFLYER_BRANCH = "upm"


# RiseOn's packages. A repo holding one package at its root tags "v<version>"; a repo holding several keeps each in
# its own folder and tags "<package name>/<version>". A repo or package left out here is never published.
RISEON_REPOS = {
    "riseongamestudio/AdImpression": {"com.riseon.adimpression": ""},
    "riseongamestudio/Ads": {
        "com.riseon.ads": "Core",
        "com.riseon.ads.admob": "AdMob",
        "com.riseon.ads.admob.native": "AdMob.Native",
        "com.riseon.ads.levelplay": "LevelPlay",
        "com.riseon.ads.max": "Max",
    },
    "riseongamestudio/Analytics": {
        "com.riseon.analytics": "Core",
        "com.riseon.analytics.appsflyer": "AppsFlyer",
        "com.riseon.analytics.firebase": "Firebase",
    },
    "riseongamestudio/Consent": {"com.riseon.consent": ""},
    "riseongamestudio/Firebase": {
        "com.riseon.firebase": "Core",
        "com.riseon.firebase.remoteconfig": "RemoteConfig",
    },
    "riseongamestudio/IAP": {"com.riseon.iap": ""},
    "riseongamestudio/NativeAdMob": {"com.riseon.nativeadmob": ""},
    "riseongamestudio/Outline2D": {"com.riseon.outline2d": ""},
    "riseongamestudio/Propositions": {"com.riseon.propositions": ""},
    "riseongamestudio/Serializables": {"com.riseon.serializables": ""},
    "riseongamestudio/Transitions": {"com.riseon.transitions": ""},
    "riseongamestudio/Vibration": {"com.riseon.vibration": ""},
    "riseongamestudio/Wipe2D": {"com.riseon.wipe2d": ""},
    "riseongamestudio/Utils": {
        "com.riseon.utils": "Core",
        "com.riseon.utils.litmotion": "LitMotion",
        "com.riseon.utils.network": "Network",
        "com.riseon.utils.renderers": "Renderers",
        "com.riseon.utils.ui": "UI",
    },
}


def fetch(url, token=False):
    headers = {"User-Agent": "riseon-upm-mirror"}
    if token:
        headers["Authorization"] = "Bearer " + os.environ["GH_TOKEN"]
    with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=600) as response:
        return response.read()


# A version UPM reads: numbers, then an optional pre-release suffix such as "-preview.1".
VERSION = re.compile(r"^\d+\.\d+\.\d+(-[0-9A-Za-z.-]+)?$")


def parse_version(text):
    return tuple(int(part) for part in text.split("."))


def version_order(text):
    """Releases above their pre-releases; pre-releases of one release by their suffix."""
    core, _, suffix = text.partition("-")
    return parse_version(core), suffix == "", suffix


def firebase_versions():
    versions, page = [], 1
    while True:
        url = f"https://api.github.com/repos/firebase/firebase-unity-sdk/releases?per_page=100&page={page}"
        releases = json.loads(fetch(url, token=True))
        if not releases:
            return sorted(versions, key=parse_version)
        for release in releases:
            version = release["tag_name"].lstrip("v")
            if release["draft"] or release["prerelease"] or not version.replace(".", "").isdigit():
                continue
            if parse_version(version) >= FIREBASE_FROM:
                versions.append(version)
        page += 1


def firebase_tarballs(published, skipped):
    for version in firebase_versions():
        for package in FIREBASE_PACKAGES:
            name = "com.google.firebase." + package
            if version in published.get(name, ()):
                continue
            try:
                data = fetch(FIREBASE_TARBALL.format(package, version))
            except urllib.error.HTTPError as error:
                if error.code != 404:
                    raise
                print(f"{name}@{version}: Google publishes no tarball for it")
                continue
            yield "firebase-" + version, data


def repo_tags(repo):
    tags, page = {}, 1
    while True:
        batch = json.loads(fetch(f"https://api.github.com/repos/{repo}/tags?per_page=100&page={page}", token=True))
        if not batch:
            return tags
        tags.update((tag["name"], tag["commit"]["sha"]) for tag in batch)
        page += 1


def riseon_tarballs(published, skipped):
    for repo, packages in RISEON_REPOS.items():
        for tag, commit in repo_tags(repo).items():
            if len(packages) == 1:
                if not tag.startswith("v"):
                    continue
                (name, folder), = packages.items()
                version = tag[1:]
            else:
                name, _, version = tag.partition("/")
                if name not in packages:
                    continue
                folder = packages[name]
            # A tag skipped once is read again only when it moves to another commit.
            if version in published.get(name, ()) or skipped.get(f"{repo} {tag}") == commit:
                continue

            data = repack(fetch(f"https://codeload.github.com/{repo}/tar.gz/refs/tags/{tag}"), folder)
            manifest = read_manifest(data)
            if (manifest["name"], manifest["version"]) != (name, version) or not VERSION.match(version):
                print(f"{repo} {tag}: its package.json is {manifest['name']}@{manifest['version']}, not published")
                skipped[f"{repo} {tag}"] = commit
                continue
            yield name, data


def repack(archive, folder=""):
    """A GitHub archive keeps the repo under "<repo>-<ref>/"; an npm tarball keeps the package under "package/"."""
    prefix = folder.strip("/") + "/" if folder else ""
    out = io.BytesIO()
    with tarfile.open(fileobj=io.BytesIO(archive)) as source, tarfile.open(fileobj=out, mode="w:gz") as target:
        for member in source.getmembers():
            parts = member.name.split("/", 1)
            if len(parts) < 2 or not parts[1].startswith(prefix) or member.type in (tarfile.XGLTYPE, tarfile.XHDTYPE):
                continue
            path = parts[1][len(prefix):]
            if not path:
                continue
            content = source.extractfile(member) if member.isfile() else None
            member.name = "package/" + path
            target.addfile(member, content)
    return out.getvalue()


def appsflyer_tarballs(published, skipped):
    manifest = json.loads(fetch(f"https://raw.githubusercontent.com/{APPSFLYER_REPO}/{APPSFLYER_BRANCH}/package.json"))
    if manifest["version"] in published.get(manifest["name"], ()):
        return

    yield "appsflyer-" + manifest["version"], repack(fetch(f"https://codeload.github.com/{APPSFLYER_REPO}/tar.gz/refs/heads/{APPSFLYER_BRANCH}"))


def read_manifest(data):
    with tarfile.open(fileobj=io.BytesIO(data)) as tar:
        return json.load(io.TextIOWrapper(tar.extractfile("package/package.json"), encoding="utf-8-sig"))


def gh(*args, check=True):
    return subprocess.run(["gh", *args, "-R", REPO], check=check, capture_output=True, text=True)


def upload(tag, file_name, data):
    if gh("release", "view", tag, check=False).returncode != 0:
        gh("release", "create", tag, "--title", tag, "--notes", "Package tarballs of the RiseOn UPM registry.")
    with tempfile.TemporaryDirectory() as folder:
        path = os.path.join(folder, file_name)
        with open(path, "wb") as file:
            file.write(data)
        # A run that failed after this upload left the file without its packument; the next run uploads it again.
        gh("release", "upload", tag, path, "--clobber")
    return f"https://github.com/{REPO}/releases/download/{tag}/{file_name}"


def write_json(path, value):
    with open(path, "w", encoding="utf-8") as file:
        json.dump(value, file, indent=1, ensure_ascii=False)


def main(site):
    documents = {}
    for file in os.listdir(site):
        path = os.path.join(site, file)
        if os.path.isfile(path) and not file.startswith(".") and file != "README.md":
            with open(path, encoding="utf-8") as stream:
                documents[file] = json.load(stream)
    published = {name: set(doc["versions"]) for name, doc in documents.items()}
    skipped_path = os.path.join(site, "-", "skipped")
    skipped = json.load(open(skipped_path, encoding="utf-8")) if os.path.exists(skipped_path) else {}

    added = []
    for source in (riseon_tarballs, firebase_tarballs, appsflyer_tarballs):
        for tag, data in source(published, skipped):
            manifest = read_manifest(data)
            name, version = manifest["name"], manifest["version"]
            url = upload(tag, f"{name}-{version}.tgz", data)
            now = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")
            doc = documents.setdefault(name, {"name": name, "versions": {}, "time": {}})
            doc["versions"][version] = dict(manifest, dist={
                "tarball": url,
                "shasum": hashlib.sha1(data).hexdigest(),
                "integrity": "sha512-" + base64.b64encode(hashlib.sha512(data).digest()).decode(),
            })
            doc["time"][version] = doc["time"]["modified"] = now
            releases = [each for each in doc["versions"] if "-" not in each] or list(doc["versions"])
            doc["dist-tags"] = {"latest": max(releases, key=version_order)}
            write_json(os.path.join(site, name), doc)
            published.setdefault(name, set()).add(version)
            added.append(f"{name}@{version}")
            print("mirrored", added[-1], flush=True)

    # Unity lists a registry's packages through its search endpoint; one static file answers every query.
    latest = []
    for name in sorted(documents):
        doc = documents[name]
        version = doc["dist-tags"]["latest"]
        latest.append({"name": name, "version": version, "date": doc["time"][version],
                       "description": doc["versions"][version].get("description", "")})
    os.makedirs(os.path.join(site, "-", "v1"), exist_ok=True)
    write_json(os.path.join(site, "-", "v1", "search"), {"objects": [{"package": p} for p in latest], "total": len(latest)})
    write_json(os.path.join(site, "-", "all"), {"_updated": 0, **{p["name"]: p for p in latest}})
    write_json(skipped_path, skipped)

    # Deploys whenever the site differs from what Pages serves, so a deploy that failed is made again on the next run.
    with open(os.path.join(site, "-", "all"), "rb") as built:
        try:
            stale = fetch(SITE + "/-/all") != built.read()
        except urllib.error.URLError:
            stale = True

    with open(os.environ.get("GITHUB_OUTPUT", os.devnull), "a") as output:
        output.write(f"added={len(added)}\n")
        output.write(f"deploy={'1' if added or stale else '0'}\n")


if __name__ == "__main__":
    main(sys.argv[1])
