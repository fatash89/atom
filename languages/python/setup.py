import setuptools

# Used to upload package to PyPI
setuptools.setup(
    name="elementary-atom",
    packages=["atom"],
    version="2.5.2",
    include_package_data=True,
    keywords="elementary robotics atom redis rts",
    url="https://github.com/elementary-robotics/atom",
    author="Elementary Robotics",
    author_email="dan@elementaryrobotics.com",
    license="Apache License",
    install_requires=[
        "Cython==0.29.16",
        "hiredis==1.1.0",
        "msgpack==0.6.2",
        "numpy==1.18.3",
        "prompt-toolkit==2.0.7",
        "psutil==5.8.0",
        "pyarrow==0.17.0",
        "pyfiglet==0.7.6",
        "redis==3.5.3",
        "redistimeseries==1.4.3",
        "rmtest==0.7.0",
        "six==1.15.0",
        "wcwidth==0.2.5",
        "typing_extensions==3.7.4.3",
    ],
    classifiers=[
        "Intended Audience :: Developers",
        "Programming Language :: Python",
    ],
)
