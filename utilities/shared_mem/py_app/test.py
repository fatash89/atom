import sys
import numpy
import ershmem

SH_MEM_SIZE=4096
SH_MEM_OBJ_SIZE=1024

if (__name__ == '__main__'):
    num_args = len(sys.argv)
    if (num_args == 2):
        test = numpy.array([11,22,33,44],dtype=numpy.uint8)

        ershmem.er_shmem_create(sys.argv[1],SH_MEM_SIZE)
        handle = ershmem.er_shmem_alloc(test.size)

        print("ShMem Handle =",handle)

        ershmem.er_shmem_init(handle,test,test.size)

        input("Hit any key to exit")

        ershmem.er_shmem_destroy(sys.argv[1])
    elif (num_args == 3):
        ershmem.er_shmem_open(sys.argv[1])
        handle = int(sys.argv[2])

        test = ershmem.er_shmem_get(handle)
        print("Read:")
        print(test)
        print("Type:",type(test))
        ershmem.er_shmem_delete(handle)
    else:
        print("Wrong number of arguments")
    
