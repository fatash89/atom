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

There are two options for rendering graphics from within an Element: by VNC (compatible with any host machine hardware but slow) and by X11 window (Linux only, fast when used with hardware acceleration).

### Portable VNC-based Graphics Support (no hardware acceleration)

`atom` ships with an OpenGL-enabled VNC, NoVNC, that by default renders to port `6080`. This is implemented largely based off of [docker-opengl](https://github.com/thewtex/docker-opengl), which is also included as a submodule in this repo. In order to launch the screen server and view it:

1. If you're using the `launch.sh` template then you'll notice you can just set the `GRAPHICS` environment variable. If you're not using this template, the server can be launched with the command:
```
/usr/bin/supervisord -c /etc/supervisor/supervisord.conf
```
2. Remap the port `6080` to be exposed on your system. This can be done in the `docker-compose` or by passing the `-p` flag when using `docker run`.
3. Visit `localhost:$port` in your browser, where `$port` corresponds to the port you mapped `6080` to using docker.

<aside class="notice">
Elements that support VNC-based rendering should support toggling graphics via the `GRAPHICS` environmental variable.  Setting `GRAPHICS=1` for an element in the docker-compose file should enable VNC-based graphics.
</aside>

### X11-based graphics support (optional hardware acceleration)

If you would like to display graphics in an X11 window on a Linux system you must do the following before launching the element with docker-compose:

1. Give containers permission to use your display by executing `xhost +si:localuser:root`.
Note that you'll need to execute this command again _after every reboot_, so you may want to configure your system to execute this automatically at boot.
2. Add this entry to the docker-compose file under `volumes`: "/tmp/.X11-unix:/tmp/.X11-unix:rw"
3. Add these entries to the docker-compose file under `environment`: `"DISPLAY"` and `"QT_X11_NO_MITSHM=1"`
4. Build and start your containers using the `docker-compose` command as usual.

For better performance you can render to an X11 window _using a graphics card_ (currently only Nvidia hardware is supported).
In addition to the steps above, perform the following to make use of a graphics card for rendering in an X11 window:

1. Install the appropriate NVIDIA driver and on your host machine.
2. Install the [Nvidia Container Toolkit](https://github.com/NVIDIA/nvidia-docker) by following their instructions.
3. Install `nvidia-container-runtime`: `sudo apt-get install nvidia-container-runtime`
4. Rather than using `elementaryrobotics/atom` in your `Dockerfile` you will need to use one of the graphics-enabled Atom base images (listed under "OpenGL and Cuda support" [here](https://github.com/elementary-robotics/atom)).
5. Modify `/etc/docker/daemon.json` to use NVIDIA as the default runtime by adding the line `"default-runtime": "nvidia",` as in the example to the right.
6. Run `sudo systemctl restart docker.service`
7. Build and start your containers using the `docker-compose` command as usual, adding any dependencies that require GPU-accelerated graphics to your `Dockerfile`!

<aside class="notice">
Do not mix the configuration for VNC-based rendering with the X11-based rendering in the docker-compose file.
For example, do not set both `GRAPHICS=1` and `DISPLAY` environment variables.
This will likely break the element's graphics.
</aside>
