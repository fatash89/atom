import sys
import cv2
import ershmem
import numpy

#img=cv2.imread('Linux_logo.jpg')
#type(img)
#<class 'numpy.ndarray'>
#img.shape
#(500, 421, 3)
#img.strides
#(1263, 3, 1)
#img.size
#631500

SH_MEM_SIZE = 16777216

if (__name__=='__main__'):
    if (len(sys.argv) == 3):
        img = cv2.imread(sys.argv[1],cv2.IMREAD_UNCHANGED)
#        cv2.imshow(sys.argv[1],img)
#        cv2.waitKey(0)
#        cv2.destroyAllWindows()

        ershmem.er_shmem_create(sys.argv[2],SH_MEM_SIZE)
        handle = ershmem.er_shmem_alloc(img.size)

        print(img.size)
        print(img.dtype)
        print(img.shape)
        print(img.strides)
        print(type(img))

        ershmem.er_shmem_init(handle,img,img.size);
        #cv2.imshow("new jpg",img)
        #cv2.waitKey(0)
        #cv2.destroyAllWindows()

        print("ShMem Handle =",handle)
        input("Hit any key to exit")

        ershmem.er_shmem_destroy(sys.argv[2])
    elif (len(sys.argv) == 4):
        ershmem.er_shmem_open(sys.argv[2])
        handle = int(sys.argv[3])

        shmem_img = ershmem.er_shmem_get(handle)

        shmem_img.dtype = numpy.uint8
        shmem_img.shape = (500,421,3)
        shmem_img.strides = (1263,3,1)

        print(shmem_img.size)
        print(shmem_img.shape)
        print(shmem_img.strides)
        print(type(shmem_img))

        #shmem_img = shmem_img.astype(numpy.uint8)

        cv2.imshow("new jpg",shmem_img)
        cv2.waitKey(0)
        cv2.destroyAllWindows()
        cv2.imwrite(sys.argv[1],shmem_img,[int(cv2.IMWRITE_JPEG_QUALITY), 100])

        ershmem.er_shmem_delete(handle)
    else:
        print("Wrong Number of Args")
