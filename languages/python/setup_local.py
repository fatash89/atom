import setuptools

# Used in Dockerfiles
setuptools.setup(
    name="atom",
    packages=["atom"],
    version="2.5.1",
    include_package_data=True,
)
