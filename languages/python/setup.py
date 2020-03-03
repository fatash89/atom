import setuptools
import version


setuptools.setup(
    name="atom",
    packages=["atom"],
    version=version.main(),
    include_package_data=True,
)
