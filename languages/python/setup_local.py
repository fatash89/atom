import setuptools

# Used in Dockerfiles
setuptools.setup(
    name="atom",
    packages=["atom"],
    version="2.7.0",
    include_package_data=True,
)
