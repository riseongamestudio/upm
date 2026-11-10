"""Mirrors third-party Unity packages into this repo's static UPM registry.

Every package version is uploaded once, as its maker published it, to the GitHub release named after its source and
version; the registry folder holds one packument per package and the search files Unity's Package Manager reads.
A version already in the registry is never uploaded again.

    python mirror.py <registry folder>      # needs GH_TOKEN and GITHUB_REPOSITORY, as the workflow sets them
"""
import base64, datetime, hashlib, io, json, os, subprocess, sys, tarfile, tempfile, urllib.error, urllib.request

REPO = os.environ["GITHUB_REPOSITORY"]

# Firebase: every package Google publishes for Unity, from 13.17.0 on, taken from Google's own UPM tarballs.
FIREBASE_PACKAGES = [
    "app", "analytics", "app-check", "auth", "crashlytics", "database", "firebaseai", "firestore", "functions",
    "installations", "messaging", "remote-config", "storage",
]
FIREBASE_FROM = (13, 17, 0)
FIREBASE_TARBALL = "https://dl.google.com/games/registry/unity/com.google.firebase.{0}/com.google.firebase.{0}-{1}.tgz"

# AppsFlyer publishes its UPM package only as the head of its upm branch, rewritten at each release, so each new
# version there is mirrored; older versions are kept from the commits RiseOn projects had locked.
APPSFLYER_REPO = "AppsFlyerSDK/appsflyer-unity-plugin"
APPSFLYER_REFS = [
    "refs/heads/upm",
    "d26fcb5d8c7d0f6598764dc687154e967b167761",  # 6.17.900
    "313c87fbf49d6f2863f54315cc00300032372774",  # 7.0.2
]


def fetch(url, token=False):
    headers = {"User-Agent": "riseon-upm-mirror"}
    if token:
        headers["Authorization"] = "Bearer " + os.environ["GH_TOKEN"]
    with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=600) as response:
        return response.read()


def parse_version(text):
    return tuple(int(part) for part in text.split("."))


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


def firebase_tarballs(published):
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


def appsflyer_tarballs(published):
    for ref in APPSFLYER_REFS:
        raw = f"https://raw.githubusercontent.com/{APPSFLYER_REPO}/{ref.removeprefix('refs/heads/')}/package.json"
        manifest = json.loads(fetch(raw))
        if manifest["version"] in published.get(manifest["name"], ()):
            continue

        # The archive keeps the package under "<repo>-<ref>/"; an npm tarball keeps it under "package/".
        archive = fetch(f"https://codeload.github.com/{APPSFLYER_REPO}/tar.gz/{ref}")
        out = io.BytesIO()
        with tarfile.open(fileobj=io.BytesIO(archive)) as source, tarfile.open(fileobj=out, mode="w:gz") as target:
            for member in source.getmembers():
                parts = member.name.split("/", 1)
                if len(parts) < 2 or not parts[1] or member.type in (tarfile.XGLTYPE, tarfile.XHDTYPE):
                    continue
                content = source.extractfile(member) if member.isfile() else None
                member.name = "package/" + parts[1]
                target.addfile(member, content)
        yield "appsflyer-" + manifest["version"], out.getvalue()


def read_manifest(data):
    with tarfile.open(fileobj=io.BytesIO(data)) as tar:
        return json.load(io.TextIOWrapper(tar.extractfile("package/package.json"), encoding="utf-8-sig"))


def gh(*args, check=True):
    return subprocess.run(["gh", *args, "-R", REPO], check=check, capture_output=True, text=True)


def upload(tag, file_name, data):
    if gh("release", "view", tag, check=False).returncode != 0:
        gh("release", "create", tag, "--title", tag, "--notes", "Package tarballs mirrored into the RiseOn UPM registry.")
    with tempfile.TemporaryDirectory() as folder:
        path = os.path.join(folder, file_name)
        with open(path, "wb") as file:
            file.write(data)
        gh("release", "upload", tag, path)
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

    added = []
    for source in (firebase_tarballs, appsflyer_tarballs):
        for tag, data in source(published):
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
            doc["dist-tags"] = {"latest": max(doc["versions"], key=parse_version)}
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

    with open(os.environ.get("GITHUB_OUTPUT", os.devnull), "a") as output:
        output.write(f"added={len(added)}\n")


if __name__ == "__main__":
    main(sys.argv[1])
