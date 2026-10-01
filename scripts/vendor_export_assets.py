"""Refresh pinned, local browser PDF dependencies without npm or a build step."""

import base64
import hashlib
import io
import json
from pathlib import Path
import shutil
import tarfile
from urllib.request import urlopen

import matplotlib


def main():
    target = Path(__file__).resolve().parents[1] / "frontend" / "vendor"
    target.mkdir(exist_ok=True)
    manifest = {}
    for name, version, filename in (
        ("jspdf", "4.2.1", "jspdf.umd.min.js"),
        ("svg2pdf.js", "2.8.1", "svg2pdf.umd.min.js"),
    ):
        with urlopen(f"https://registry.npmjs.org/{name}/{version}", timeout=30) as response:
            metadata = json.load(response)
        with urlopen(metadata["dist"]["tarball"], timeout=30) as response:
            archive = response.read()
        algorithm, expected = metadata["dist"]["integrity"].split("-", 1)
        actual = base64.b64encode(hashlib.new(algorithm, archive).digest()).decode()
        if actual != expected:
            raise ValueError(f"Integrity mismatch for {name}")
        # Read named members only; never extract arbitrary archive paths.
        with tarfile.open(fileobj=io.BytesIO(archive), mode="r:gz") as package:
            data = package.extractfile(f"package/dist/{filename}").read()
            license_names = [m.name for m in package if m.name.lower() in ("package/license", "package/license.txt", "package/license.md")]
            if not license_names:
                raise ValueError(f"Missing license for {name}")
            (target / filename).write_bytes(data)
            (target / f"{name}.LICENSE.txt").write_bytes(package.extractfile(license_names[0]).read())
        manifest[name] = {
            "version": version, "source": metadata["dist"]["tarball"],
            "archive_integrity": metadata["dist"]["integrity"],
            "file": filename, "sha256": hashlib.sha256(data).hexdigest(),
        }
        print(f"Vendored {name} {version}: {len(data)} bytes")
    fonts = Path(matplotlib.get_data_path()) / "fonts" / "ttf"
    for name in ("DejaVuSans.ttf", "DejaVuSans-Bold.ttf", "LICENSE_DEJAVU"):
        shutil.copyfile(fonts / name, target / name)
        manifest[name] = {"source": f"Matplotlib {matplotlib.__version__} / DejaVu fonts", "sha256": hashlib.sha256((target / name).read_bytes()).hexdigest()}
    (target / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
