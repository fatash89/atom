#include <cstdlib>
#include <cstdint>
#include <iostream>
#include <cstring>

#include "er_shmem.h"

#define SHMEM_SIZE 4096
#define BUFF_SIZE 1024

int main(int argc, char* argv[])
{
    int64_t handle;
    const char* buff = "Hello From C++ test app";
    if (argc == 2) {
        er_shmem_create(argv[1],SHMEM_SIZE);

        handle = er_shmem_alloc(BUFF_SIZE);
        std::cout << "handle = " << handle << std::endl;
        er_shmem_init(handle,(char*)buff,strlen(buff)+1);

        std::cout << "Hit any key to exit" << std::endl;
        std::cin.get();

        er_shmem_destroy(argv[1]);
    } else if (argc == 3){
        er_shmem_open(argv[1]);
        handle = atol(argv[2]);
        char* tmp = (char*)er_shmem_get(handle);

        std::cout << "read: " << tmp << std::endl;

        er_shmem_delete(handle);
    } else
        std::cout << "Wrong number of arguments" << std::endl;
    return 0;
}
