# SDK CUDA Support
```
{
    "default-runtime": "nvidia",
    "runtimes": {
        "nvidia": {
            "path": "/usr/bin/nvidia-container-runtime",
            "runtimeArgs": []
        }
    }
}
```
If your element requires CUDA support for tasks like deep learning, there are a few extra steps to get set up.

1. Install the appropriate NVIDIA driver and CUDA on your host machine.
2. Install [nvidia-docker2](https://github.com/NVIDIA/nvidia-docker) by following their instructions.
3. Rather than using `elementaryrobotics/atom` in your `Dockerfile` you will need to use `elementaryrobotics/atom-CUDA-<CUDA_VERSION>`, where `<CUDA_VERSION>` matches the version of CUDA on your host machine.
4. Modify `/etc/docker/daemon.json` to use NVIDIA as the default runtime by adding the line `"default-runtime": "nvidia",` as in the example.
5. Run `sudo systemctl restart docker.service`
6. Build and start your containers using the `docker-compose` command as usual. To verify that everything is running, you can start a shell in your element and run `nvidia-smi`, which should show some output.
7. Now you can add any dependencies that rely on CUDA to your `Dockerfile`!
