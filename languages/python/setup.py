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
    install_requires=[
        "msgpack==0.6.2",
        "redis@git+https://github.com/andymccurdy/redis-py.git#2c9f41f46991f94f0626598600d1023d4e12f0bc",
        "redistimeseries@git+https://github.com/RedisTimeSeries/redistimeseries-py.git#b451b43c564076acfe8de62eb001277876631a9a",  # noqa: E501
    ],
    version=__version__,
    include_package_data=True,
)
