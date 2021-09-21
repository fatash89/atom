#ifndef __ER_SHMEM_H__
#define __ER_SHMEM_H__

#ifdef ER_C_LINKAGE
#ifdef __cplusplus
extern "C" {
#endif
#endif /*ER_C_LINKAGE*/

extern int er_shmem_create(const char* name, int64_t size);
extern int er_shmem_open(const char* name);
extern int64_t er_shmem_alloc(int size);
extern int er_shmem_init(int64_t handle, char* data, int data_size);
extern char* er_shmem_get(int64_t handle);
extern int er_shmem_delete(int64_t handle);
extern int er_shmem_destroy(char* name);

#ifdef ER_C_LINKAGE
#ifdef __cplusplus
}
#endif
#endif /*ER_C_LINKAGE*/

#endif
