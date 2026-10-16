# SPDX-FileCopyrightText: 2026 BidWeave contributors
# SPDX-License-Identifier: Apache-2.0
"""Consumer-visible inventory boundaries; no external services or fixture JARs."""

import hashlib
import importlib.util
import io
from pathlib import Path
import sys
import unittest
import zipfile

spec = importlib.util.spec_from_file_location(
    "bidweave_dependency_sbom", Path(__file__).with_name("dependency-sbom.py")
)
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)


class ShadedJarInventory(unittest.TestCase):
    def test_shaded_components_keep_identity_and_do_not_inherit_container_hash(self):
        jar = io.BytesIO()
        with zipfile.ZipFile(jar, "w") as nested:
            for group, artifact, version, licenses in (
                ("a.library", "helper", "2.0", ["MIT"]),
                ("z.vendor", "bundle", "1.0", ["MIT", "Apache-2.0"]),
            ):
                directory = f"META-INF/maven/{group}/{artifact}"
                nested.writestr(
                    directory + "/pom.properties",
                    f"groupId={group}\nartifactId={artifact}\nversion={version}\n",
                )
                license_xml = "".join(
                    f"<license><name>{name}</name></license>" for name in licenses
                )
                nested.writestr(
                    directory + "/pom.xml",
                    f"<project><licenses>{license_xml}</licenses></project>",
                )
        archive = io.BytesIO()
        with zipfile.ZipFile(archive, "w") as outer:
            outer.writestr("BOOT-INF/lib/bundle-1.0.jar", jar.getvalue())
        packages = {
            item["name"]: item for item in module.parse_workflow_jar(archive.getvalue())
        }
        self.assertEqual(set(packages), {"z.vendor:bundle", "a.library:helper"})
        self.assertEqual(packages["z.vendor:bundle"]["versionInfo"], "1.0")
        self.assertEqual(packages["a.library:helper"]["versionInfo"], "2.0")
        self.assertEqual(
            packages["z.vendor:bundle"]["checksums"],
            [
                {
                    "algorithm": "SHA256",
                    "checksumValue": hashlib.sha256(jar.getvalue()).hexdigest(),
                }
            ],
        )
        self.assertNotIn("checksums", packages["a.library:helper"])
        self.assertEqual(packages["a.library:helper"]["licenseDeclared"], "MIT")
        # A POM list does not say whether two licenses are alternatives or cumulative.
        self.assertEqual(packages["z.vendor:bundle"]["licenseDeclared"], "NOASSERTION")


if __name__ == "__main__":
    unittest.main()
