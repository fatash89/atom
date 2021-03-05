import setuptools

import version

try:
    from atom import __version__
except Exception:
    __version__ = version.main()


setuptools.setup(
    name="atom",
    packages=["atom"],
    version=__version__,
    include_package_data=True,
)
