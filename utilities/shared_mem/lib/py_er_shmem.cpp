#include <cstdint>
#include "pybind11/pybind11.h"

#include "er_shmem.h"

namespace py = pybind11;

PYBIND11_MODULE(ershmem,m) {
    m.doc() = "shared memory module";
    m.def("er_shmem_create",&er_shmem_create,"create shared memory");
    m.def("er_shmem_open",&er_shmem_open,"open shared memory");
    m.def("er_shmem_alloc",&er_shmem_alloc,"allocate shared memory");
    m.def("er_shmem_init",&er_shmem_init,"init allocated shared memory");
    m.def("er_shmem_get",&er_shmem_get,"get shared memory pointer");
    m.def("er_shmem_delete",&er_shmem_delete,"free shared memory");
    m.def("er_shmem_destroy",&er_shmem_destroy,"delete shared memory");
}
