# VNC

The `graphics` variants of Atom come with a built-in VNC that allow the user to view graphical outputs in the browser. This is particularly nice for users who are running on mac/windows or are running headless as it allows the graphics to be written once for linux and either rendered natively or through the VNC depending on the situation at hand. All that changes is how you launch your atom element.

The original inspiration for the VNC inside of docker is credited to the [`docker-opengl`](https://github.com/thewtex/docker-opengl) project (Apache 2.0 license, included in this directory). In order to work with the Atom build system and minimized Docker containers we are no longer submoduling the original code and maintaining any links to `docker-opengl` though it is important to note that a decent amount of the source in this directory is from that project.

Most of the VNC is implemented through `noVNC` which is included [as a third-party dependency](../../third-party/noVNC).
