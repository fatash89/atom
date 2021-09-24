#include <cstdint>
#include "pybind11/pybind11.h"
#include "pybind11/numpy.h"

#include <stdio.h>

#include "er_shmem.h"

namespace py = pybind11;

PYBIND11_MODULE(ershmem,m) {
    m.doc() = "shared memory module";
    m.def("er_shmem_create",&er_shmem_create,"create shared memory");
    m.def("er_shmem_open",&er_shmem_open,"open shared memory");
    m.def("er_shmem_alloc",&er_shmem_alloc,"allocate shared memory");
    m.def("er_shmem_init",
            [](int64_t handle, py::array_t<char> in, int size) {
                er_shmem_init(handle,in.data(),size);
            },
            "init allocated shared memory");
    m.def("er_shmem_get",
            [](int64_t handle) {
                unsigned char* start = er_shmem_get(handle);
                uint64_t size = er_shmem_get_size(handle);
                return py::array_t<char>({size},{1},(const char*)start);
                },"get shared memory pointer");
    m.def("er_shmem_get_size",&er_shmem_get_size,"get chunk size");
    m.def("er_shmem_delete",&er_shmem_delete,"free shared memory");
    m.def("er_shmem_destroy",&er_shmem_destroy,"delete shared memory");
}
