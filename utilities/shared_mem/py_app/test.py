import sys
import ershmem

SH_MEM_SIZE=4096
SH_MEM_OBJ_SIZE=1024

if (__name__ == '__main__'):
    num_args = len(sys.argv)
    if (num_args == 2):
        ershmem.er_shmem_create(sys.argv[1],SH_MEM_SIZE)
        handle = ershmem.er_shmem_alloc(SH_MEM_OBJ_SIZE)

        print("ShMem Handle =",handle)

        msg = b'Hello from Python test app'
        ershmem.er_shmem_init(handle,msg,len(msg))

        input("Hit any key to exit")

        ershmem.er_shmem_destroy(sys.argv[1])
    elif (num_args == 3):
        ershmem.er_shmem_open(sys.argv[1])
        handle = int(sys.argv[2])

        msg = ershmem.er_shmem_get(handle)
        print("Read:",msg)
        ershmem.er_shmem_delete(handle)
    else:
        print("Wrong number of arguments")
    
