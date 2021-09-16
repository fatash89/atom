#ifndef __ER_SHMEM_H__
#define __ER_SHMEM_H__

#ifdef __cplusplus
extern "C" {
#endif

int er_shmem_create(const char* name);
int er_shmem_open(const char* name);
int64_t er_shmem_alloc(int size);
int er_shmem_init(int64_t handle, void* data, int data_size);
void* er_shmem_get(int64_t handle);
void er_shmem_delete(int64_t handle);

#ifdef __cplusplus
}
#endif
#endif
