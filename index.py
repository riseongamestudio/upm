"""Builds this repo's static UPM registry from the releases of the repos that publish packages.

Each source repo publishes a package version as a GitHub release asset named "<package name>-<version>.tgz". This
repo holds no package: the registry folder holds one packument per package, pointing at those assets, and the search
files Unity's Package Manager reads. A version already in the registry is never read again, so an asset replaced
after its version went up changes nothing.

    python index.py <registry folder>      # needs GH_TOKEN, as the workflow sets it
"""
import base64, datetime, hashlib, io, json, os, re, sys, tarfile, urllib.error, urllib.request

SITE = "https://upm.riseongamestudio.com"

# The repos whose releases make the registry. A repo left out here is never published.
SOURCES = [
    # Third-party packages, mirrored as their makers publish them.
    "riseongamestudio/FirebaseMirror",
    "riseongamestudio/AppsFlyerMirror",
    # RiseOn's packages, each released by its repo's Release workflow when a tag is pushed.
    "riseongamestudio/AdImpression",
    "riseongamestudio/Ads",
    "riseongamestudio/Analytics",
    "riseongamestudio/Consent",
    "riseongamestudio/Firebase",
    "riseongamestudio/IAP",
    "riseongamestudio/NativeAdMob",
    "riseongamestudio/Outline2D",
    "riseongamestudio/Propositions",
    "riseongamestudio/Serializables",
    "riseongamestudio/Transitions",
    "riseongamestudio/Utils",
    "riseongamestudio/Vibration",
    "riseongamestudio/Wipe2D",
]

# "<package name>-<version>.tgz", the version being numbers and an optional pre-release suffix such as "-preview.1".
ASSET = re.compile(r"^(?P<name>[a-z0-9._-]+?)-(?P<version>\d+\.\d+\.\d+(-[0-9A-Za-z.-]+)?)\.tgz$")


def fetch(url, api=False):
    headers = {"User-Agent": "riseon-upm-index"}
    if api:
        headers["Authorization"] = "Bearer " + os.environ["GH_TOKEN"]
        headers["Accept"] = "application/vnd.github+json"
    with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=600) as response:
        return response.read()


def version_order(text):
    """Releases above their pre-releases; pre-releases of one release by their suffix."""
    core, _, suffix = text.partition("-")
    return tuple(int(part) for part in core.split(".")), suffix == "", suffix


def assets(repo):
    page = 1
    while True:
        releases = json.loads(fetch(f"https://api.github.com/repos/{repo}/releases?per_page=100&page={page}", api=True))
        if not releases:
            return
        for release in releases:
            if release["draft"]:
                continue
            for asset in release["assets"]:
                match = ASSET.match(asset["name"])
                if match:
                    yield match["name"], match["version"], asset
        page += 1


def read_manifest(data):
    with tarfile.open(fileobj=io.BytesIO(data)) as tar:
        return json.load(io.TextIOWrapper(tar.extractfile("package/package.json"), encoding="utf-8-sig"))


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
    skipped_path = os.path.join(site, "-", "skipped")
    skipped = json.load(open(skipped_path, encoding="utf-8")) if os.path.exists(skipped_path) else {}

    added = []
    for repo in SOURCES:
        for name, version, asset in assets(repo):
            if version in documents.get(name, {}).get("versions", {}) or str(asset["id"]) in skipped:
                continue
            url = asset["browser_download_url"]
            data = fetch(url)
            manifest = read_manifest(data)
            if (manifest.get("name"), manifest.get("version")) != (name, version):
                # Read again only when the asset is replaced, which gives it a new id.
                print(f"{url}: its package.json is {manifest.get('name')}@{manifest.get('version')}, not indexed")
                skipped[str(asset["id"])] = url
                continue

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
            added.append(f"{name}@{version}")
            print("indexed", added[-1], flush=True)

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