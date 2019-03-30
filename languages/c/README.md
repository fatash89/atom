# C atom library

## Overview

The C atom library implements the atom spec. More documentation
should be added here.

## Building

### Third-party Dependencies

The C atom library has a single third-party dependency, `hiredis`,
which is included as a submodule in this repo. To build this, run:
```
git submodule update --init --recursive
cd third-party/hiredis && make && make install
```

### `libatom.so`

The C atom library builds to a shared library named `libatom.so`. To build
this library, simply run:
```
make
```
This will create a `build` output directory with a `lib` and `inc` folder which
contain the library and the headers, respectively.

To install the library, simply run
```
make install
```
This will install the library to `/usr/local/`.
