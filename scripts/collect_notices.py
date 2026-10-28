"""Preserve wheel license notices in the onedir Windows distribution."""

import importlib.metadata
import shutil
import sys
from pathlib import Path

output = Path("dist/Deskpad/licenses")
output.mkdir(parents=True, exist_ok=True)
for distribution in importlib.metadata.distributions():
    name = distribution.metadata.get("Name", "unknown")
    for file in distribution.files or []:
        if any(word in file.name.lower() for word in ("license", "copying", "notice")):
            source = Path(distribution.locate_file(file))
            if source.is_file():
                directory = output / name / str(file.parent).replace("..", "_")
                directory.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, directory / file.name)
python_license = Path(sys.base_prefix) / "LICENSE.txt"
if python_license.exists():
    shutil.copy2(python_license, output / "Python-LICENSE.txt")

# Preserve the scanner's browser-bundled dependency license too.
shutil.copytree("web/public/licenses", output / "web", dirs_exist_ok=True)
