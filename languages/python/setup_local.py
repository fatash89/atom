import setuptools

# Used in Dockerfiles
setuptools.setup(
    name="atom",
    packages=["atom"],
    version="2.7.1",
    include_package_data=True,
)
