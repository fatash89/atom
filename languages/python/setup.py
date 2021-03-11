import setuptools

# Used to upload package to PyPI
# TODO: discuss what we should put in install_requires
setuptools.setup(
    name="elementary-atom",
    packages=["atom"],
    version="2.5.1",
    include_package_data=True,
    keywords="elementary robotics atom redis rts",
    url="https://github.com/elementary-robotics/atom",
    author="Elementary Robotics",
    author_email="dan@elementaryrobotics.com",
    license="Apache License",
    install_requires=[
        "msgpack==0.6.2",
        "numpy==1.18.3",
        "redis==3.5.3",
        "redistimeseries==1.4.3",
    ],
    classifiers=[
        "Intended Audience :: Developers",
        "Programming Language :: Python",
    ],
)
