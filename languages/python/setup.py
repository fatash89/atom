import setuptools
import subprocess
from pathlib import Path

VERSION_SCRIPT = Path(__file__).parent / "version.py"
subprocess.call(["python3", "version.py"])

from atom import __version__

setuptools.setup(
    name="atom",
    packages=["atom"],
    version=__version__,
    include_package_data=True,
)
