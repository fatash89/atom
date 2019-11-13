# SDK Graphics Support
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

There are two options for rendering graphics from within an Element: by VNC (compatible with any host machine hardware but slow) and by GPU (fast, but less portable).

### Portable Graphics Support (no hardware acceleration)

`atom` ships with an OpenGL-enabled VNC, NoVNC, that by default renders to port `6080`. This is implemented largely based off of [docker-opengl](https://github.com/thewtex/docker-opengl), which is also included as a submodule in this repo. In order to launch the screen server and view it:

1. If you're using the `launch.sh` template then you'll notice you can just set the `GRAPHICS` environment variable. If you're not using this template, the server can be launched with the command:
```
/usr/bin/supervisord -c /etc/supervisor/supervisord.conf
```
2. Remap the port `6080` to be exposed on your system. This can be done in the `docker-compose` or by passing the `-p` flag when using `docker run`.
3. Visit `localhost:$port` in your browser, where `$port` corresponds to the port you mapped `6080` to using docker.

### Hardware-accelerated Graphics Support

If you would like to use graphics hardware (currently only Nvidia hardware is supported) then there are a few extra steps to get set up.

1. Install the appropriate NVIDIA driver and on your host machine.
2. Install the [Nvidia Container Toolkit](https://github.com/NVIDIA/nvidia-docker) by following their instructions.
3. Install `nvidia-container-runtime`: `sudo apt-get install nvidia-container-runtime`
4. Rather than using `elementaryrobotics/atom` in your `Dockerfile` you will need to use one of the graphics-enabled Atom base images (listed under "OpenGL and Cuda support" [here](https://github.com/elementary-robotics/atom)).
5. Modify `/etc/docker/daemon.json` to use NVIDIA as the default runtime by adding the line `"default-runtime": "nvidia",` as in the example to the right.
6. Run `sudo systemctl restart docker.service`
7. Execute `xhost +si:localuser:root` in order to give containers permission to use your display (on a Linux system).
Note that you'll need to execute this command again _after every reboot_, so you may want to configure your system to execute this automatically at boot.
9. Build and start your containers using the `docker-compose` command as usual, adding any dependencies that require GPU-accelerated graphics to your `Dockerfile`!
