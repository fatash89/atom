import setuptools
from atom import __version__

setuptools.setup(
    name="atom",
    packages=["atom"],
    version=__version__,
    include_package_data=True,
)
