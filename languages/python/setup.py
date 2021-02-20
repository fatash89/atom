import setuptools
import version

try:
    from atom import __version__
except Exception:
    __version__ = version.main()


setuptools.setup(
    name="atom",
    packages=["atom"],
    description="Python bindings for the Elementary Robotics Atom SDK",
    url="https://github.com/elementary-robotics/atom",
    author="Elementary Robotics",
    install_requires=["msgpack==0.6.2"],
    version=__version__,
    include_package_data=True,
)
