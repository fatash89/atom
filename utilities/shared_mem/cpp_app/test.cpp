#include <cstdlib>
#include <cstdint>
#include <iostream>
#include <cstring>

#include "er_shmem.h"

#define SHMEM_SIZE 4096

int main(int argc, char* argv[])
{
    int64_t handle;
    const unsigned char buff[] = {11,22,33,44};
    if (argc == 2) {
        er_shmem_create(argv[1],SHMEM_SIZE);

        handle = er_shmem_alloc(sizeof(buff));
        std::cout << "handle = " << handle << std::endl;
        er_shmem_init(handle,(char*)buff,sizeof(buff));

        std::cout << "Hit any key to exit" << std::endl;
        std::cin.get();

        er_shmem_destroy(argv[1]);
    } else if (argc == 3){
        er_shmem_open(argv[1]);
        handle = atol(argv[2]);
        unsigned char* tmp = (unsigned char*)er_shmem_get(handle);
        int64_t size = er_shmem_get_size(handle);

        std::cout << "read: ";
        for (int i=0;i<size;i++)
             std::cout << (unsigned int)tmp[i] << " ";
        std::cout << std::endl;

        er_shmem_delete(handle);
    } else
        std::cout << "Wrong number of arguments" << std::endl;
    return 0;
}
