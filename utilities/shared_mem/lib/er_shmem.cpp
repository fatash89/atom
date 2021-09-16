#include <cstdint>
#include <iostream>

#include "er_shmem.h"

int er_shmem_create(const char* name)
{
    std::cout << __FUNCTION__ << ":" << __LINE__ << std::endl;
    return 0;
}

int er_shmem_open(const char* name)
{
    std::cout << __FUNCTION__ << ":" << __LINE__ << std::endl;
    return 0;
}

int64_t er_shmem_alloc(int size)
{
    std::cout << __FUNCTION__ << ":" << __LINE__ << std::endl;
    return 0;
}

int er_shmem_init(int64_t handle, void* data, int data_size)
{
    std::cout << __FUNCTION__ << ":" << __LINE__ << std::endl;
    return 0;
}

void* er_shmem_get(int64_t handle)
{
    std::cout << __FUNCTION__ << ":" << __LINE__ << std::endl;
    return nullptr;
}

void er_shmem_delete(int64_t handle)
{
    std::cout << __FUNCTION__ << ":" << __LINE__ << std::endl;
    return;
}
