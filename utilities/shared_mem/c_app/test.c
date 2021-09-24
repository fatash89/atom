#include <stdint.h>
#include <string.h>
#include <stdlib.h>
#include <stdio.h>

#include "er_shmem.h"

#define SHMEM_SIZE 4096

int main(int argc, char* argv[])
{
    int64_t handle;
    const unsigned char buff[] = {11,22,33,44};
    if (argc == 2) {
        er_shmem_create(argv[1],SHMEM_SIZE);

        handle = er_shmem_alloc(sizeof(buff));
        printf("handle = %ld\n",handle);
        er_shmem_init(handle,(const char*)buff,sizeof(buff));

        printf("Hit any key to exit");
        getchar();

        er_shmem_destroy(argv[1]);
    } else if (argc == 3){
        er_shmem_open(argv[1]);
        handle = atol(argv[2]);
        unsigned char* tmp = er_shmem_get(handle);
        int64_t size = er_shmem_get_size(handle);

        printf("Read: ");
        for (int i=0;i<size;i++) {
            printf("%d ",tmp[i]);
        }
        printf("\n");

        er_shmem_delete(handle);
    } else
        printf("Wrong number of arguments");
    return 0;
}
