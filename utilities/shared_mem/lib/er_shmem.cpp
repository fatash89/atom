#include <cstdint>
#include <iostream>

//boost
#include <boost/interprocess/managed_shared_memory.hpp>

//local
#include "er_shmem.h"

namespace boost_ipc = boost::interprocess;

static std::unique_ptr<boost_ipc::managed_shared_memory> ptr_shmem(nullptr);

int er_shmem_create(const char* name, int64_t size)
{
    if (ptr_shmem != nullptr) {
        return -1;
    }
    ptr_shmem = std::unique_ptr<boost_ipc::managed_shared_memory>(new boost_ipc::managed_shared_memory(boost_ipc::create_only,name,size));
    return 0;
}

int er_shmem_open(const char* name)
{
    if (ptr_shmem != nullptr) {
        return -1;
    }
	ptr_shmem = std::unique_ptr<boost_ipc::managed_shared_memory>(new boost_ipc::managed_shared_memory(boost_ipc::open_only,name));
    return 0;
}

int64_t er_shmem_alloc(int size)
{
    if (ptr_shmem != nullptr) {
        boost_ipc::managed_shared_memory::size_type free_memory = ptr_shmem->get_free_memory();
        void * shptr = ptr_shmem->allocate(1024/*bytes to allocate*/);
    
        //Check invariant
        if(free_memory <= ptr_shmem->get_free_memory())
            return -1;

        boost_ipc::managed_shared_memory::handle_t handle = ptr_shmem->get_handle_from_address(shptr);
        return handle;
    }
    return -1;
}

int er_shmem_init(int64_t handle, void* data, int data_size)
{
    if (ptr_shmem != nullptr) {
        boost_ipc::managed_shared_memory::handle_t tmp_handle = handle;
        void* dst = ptr_shmem->get_address_from_handle(tmp_handle);
        if (dst) {
            memcpy(dst,data,data_size); 
            return 0;
        }
    }
    return -1;
}

void* er_shmem_get(int64_t handle)
{
    if (ptr_shmem != nullptr) {
        boost_ipc::managed_shared_memory::handle_t tmp_handle = handle;
        return ptr_shmem->get_address_from_handle(handle);
    }
    return nullptr;
}

int er_shmem_delete(int64_t handle)
{
    if (ptr_shmem != nullptr) {
        boost_ipc::managed_shared_memory::handle_t tmp_handle = handle;
        void* addr = ptr_shmem->get_address_from_handle(handle);
        if (addr != nullptr) {
            ptr_shmem->deallocate(addr);
            return 0;
        }
    }
    return -1;
}

int er_shmem_destroy(char* name)
{
    ptr_shmem.reset(nullptr);
    if (boost_ipc::shared_memory_object::remove(name))
        return 0;
    return -1;
}

