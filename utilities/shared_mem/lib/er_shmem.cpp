#include <cstdint>
#include <iostream>

//local
#include "er_shmem.h"

//boost
#include <boost/interprocess/managed_shared_memory.hpp>

#ifdef USE_CPP_VECTORS
#include <boost/interprocess/containers/vector.hpp>
#include <boost/interprocess/allocators/allocator.hpp>
#endif


namespace boost_ipc = boost::interprocess;

#ifdef USE_CPP_VECTORS
typedef boost_ipc::allocator<uint8_t,boost_ipc::managed_shared_memory::segment_manager> ErShMemAllocator;
typedef boost_ipc::vector<uint8_t,ErShMemAllocator> ErShMemVector;
#endif

static std::unique_ptr<boost_ipc::managed_shared_memory> ptr_shmem(nullptr);

#ifdef USE_CPP_VECTORS
static std::unique_ptr<ErShMemAllocator> ptr_alloc(nullptr);
#endif

int er_shmem_create(const char* name, int64_t size)
{
    if (ptr_shmem != nullptr) {
        return -1;
    }
    //create shared memory
    ptr_shmem = std::unique_ptr<boost_ipc::managed_shared_memory>(new boost_ipc::managed_shared_memory(boost_ipc::create_only,name,size));
#ifdef USE_CPP_VECTORS
    //create shared memory allocator
    ptr_alloc = std::unique_ptr<ErShMemAllocator>(new ErShMemAllocator(ptr_shmem->get_segment_manager()));
#endif
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

int64_t er_shmem_alloc(int64_t size)
{
    if (ptr_shmem != nullptr) {
#ifdef USE_CPP_VECTORS
        ErShMemVector* shptr = ptr_shmem->construct<ErShMemVector>(boost_ipc::anonymous_instance)(size,*ptr_alloc);
#else
        //allocate first sizeof(int64_t) bytes to store the size of the chunk
        void * shptr = ptr_shmem->allocate(size+sizeof(int64_t));
        *(uint64_t*)shptr = size;
#endif
        boost_ipc::managed_shared_memory::handle_t handle = ptr_shmem->get_handle_from_address(shptr);
        return handle;
    }
    return -1;
}

int er_shmem_init(int64_t handle, const char* data, int data_size)
{
    if (ptr_shmem != nullptr) {
        boost_ipc::managed_shared_memory::handle_t tmp_handle = handle;
#ifdef USE_CPP_VECTORS
        ErShMemVector* dst_vector = (ErShMemVector*)ptr_shmem->get_address_from_handle(tmp_handle);
        void* dst = (void*)dst_vector->data();
        if (dst) {
            memcpy(dst,data,data_size); 
            return 0;
        }
#else
        void* dst = ptr_shmem->get_address_from_handle(tmp_handle);
        if (dst) {
            memcpy((unsigned char*)dst+sizeof(uint64_t),data,data_size); 
            return 0;
        }
#endif
    }
    return -1;
}

int64_t er_shmem_get_size(int64_t handle)
{
    if (ptr_shmem != nullptr) {
#ifdef USE_CPP_VECTORS
        ErShMemVector* dst_vector = static_cast<ErShMemVector*>(ptr_shmem->get_address_from_handle(handle));
        return dst_vector->size();
#else
        void* start = ptr_shmem->get_address_from_handle(handle);
        return *((uint64_t*)start);
#endif
    }
    return -1;
}

unsigned char* er_shmem_get(int64_t handle)
{
    if (ptr_shmem != nullptr) {
#ifdef USE_CPP_VECTORS
        ErShMemVector* dst_vector = static_cast<ErShMemVector*>(ptr_shmem->get_address_from_handle(handle));
        return dst_vector->data();
#else
        return static_cast<unsigned char*>(ptr_shmem->get_address_from_handle(handle))+sizeof(int64_t);
#endif
    }
    return nullptr;
}

int er_shmem_delete(int64_t handle)
{
    if (ptr_shmem != nullptr) {
        boost_ipc::managed_shared_memory::handle_t tmp_handle = handle;
#ifdef USE_CPP_VECTORS
        ErShMemVector* dst_vector = static_cast<ErShMemVector*>(ptr_shmem->get_address_from_handle(tmp_handle));
        ptr_shmem->destroy_ptr(dst_vector);
#else
        void* addr = ptr_shmem->get_address_from_handle(tmp_handle);
        if (addr != nullptr) {
            ptr_shmem->deallocate(addr);
            return 0;
        }
#endif
    }
    return -1;
}

int er_shmem_destroy(const char* name)
{
    ptr_shmem.reset(nullptr);
    if (boost_ipc::shared_memory_object::remove(name))
        return 0;
    return -1;
}

