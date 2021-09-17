#include <stdint.h>
#include <string.h>
#include <stdlib.h>
#include <stdio.h>

#include <er_shmem.h>

#define SHMEM_SIZE 4096
#define BUFF_SIZE 1024

int main(int argc, char* argv[])
{
    int64_t handle;
    const char* buff = "Hello From C test app";
    if (argc == 2) {
        er_shmem_create(argv[1],SHMEM_SIZE);

        handle = er_shmem_alloc(BUFF_SIZE);
        printf("handle = %ld\n",handle);
        er_shmem_init(handle,(void*)buff,strlen(buff)+1);

        printf("Hit any key to exit");
        getchar();

        er_shmem_destroy(argv[1]);
    } else if (argc == 3){
        er_shmem_open(argv[1]);
        handle = atol(argv[2]);
        char* tmp = (char*)er_shmem_get(handle);

        printf("read: %s\n",tmp);

        er_shmem_delete(handle);
    } else
        printf("Wrong number of arguments");
    return 0;
}
