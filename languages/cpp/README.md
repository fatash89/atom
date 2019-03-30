# C++ Atom API

## Overview

TODO

## Debugging with Valgrind

First, make and run the tests
```
make test
```

Then, remove the old valgrind logs and run valgrind. The log report
will list any errors and memory allocations that aren't freed. As of this
writing everything checks out for the unit tests run which cover basic
functionality with all of the APIs.

```
rm valgrind.log

G_SLICE=always-malloc G_DEBUG=gc-friendly  valgrind -v --tool=memcheck --leak-check=full --num-callers=40 --log-file=valgrind.log --error-exitcode=1 test/build/test_atom_cpp
```
