
# Camera Element Tutorial

Estimated Time: **5 minutes**

The goal of this tutorial is to create a camera element that could read and write the realsense camera streams.

## **Run the RealSense Demo**

> <button class="copy-button" onclick='copyText(this, "docker-compose up -d")'>Copy</button> Launch the demo

```shell_session
docker-compose up -d
```

To run the demo: please install real sense SDK, docker and docker-compose. Download the folder <a href="real-sense-demo.zip" download>real sense demo</a>. Open the terminal and run the command in the right.   Please find the explanation of the code for the demo below:

## Declare Images for realsense element

```yaml
version: "3.2"

services:

  nucleus:
    image: elementaryrobotics/nucleus
    volumes:
      - type: volume
        source: shared
        target: /shared
        volume:
          nocopy: true

  stream-viewer:
    image: elementaryrobotics/element-stream-viewer
    volumes:
      - type: volume
        source: shared
        target: /shared
        volume:
          nocopy: true
      - "/tmp/.X11-unix:/tmp/.X11-unix:rw"
    environment:
      - "DISPLAY"
      - "QT_X11_NO_MITSHM=1"
    depends_on:
      - "nucleus"

  realsense:
    image: elementaryrobotics/element-realsense
    volumes:
      - type: volume
        source: shared
        target: /shared
        volume:
          nocopy: true
    depends_on:
      - "nucleus"
    privileged: true

 demo:
    container_name: demo
    build:
        context: .
        dockerfile: Dockerfile
    volumes:
      - type: volume
        source: shared
        target: /shared
        volume:
          nocopy: true
      - ".:/demo"
    depends_on:
      - "nucleus"
    command: "launch.sh"

volumes:
  shared:
    driver_opts:
      type: tmpfs
      device: tmpfs
```

In docker-compose.yml, we specify the containers and include the respective docker images that needs to be pulled for our demo. We have built various images for respective purposes.

* The first container we create is "nucleus" that pulls the docker image of "elementaryrobotics/nucleus" which is core of our system and helps to communicate elements with one another.

* The second container we create is "stream viewer" that pulls the docker image of "elementaryrobotics/stream-viwer" which includes the GUI to view the video streams that are currently being published in Atom OS.

* The third container we create is "realsense" that pulls the docker image of "elementaryrobotics/realsense" which includes all drivers and requirements necessary to run the realsense camera.

* The fourth and last container is "demo". Instead of directly pulling the pre-baked image unlike in the previous tutoiral, we use a dockerfile to build our image by providing the details in that file. As you could see in the dockerfile we pull the image that we require "elementaryrobotics/atom" and include the commands to install the demo requirements. We create the container that is specific to the demo, you could modify this based on the requirements of your app. Please make sure that you specifiy the volume is shared in the attributes of the container. We use ".:/demo" in volumes section. It means copy all the files from current directory(".") to demo folder ("/demo")inside the docker container. It is also suggested to mention the depenedancy of the nucleus in the docker-compose file to ensure the execution of the elements in the right order. The "command" in the docker-compose file specifies the default command the container should run, as soon as it loads up.

## Configure the Video

> <button class="copy-button" onclick='copyText(this, "element = Element(\"camera\")\r\nfourcc = cv2.VideoWriter_fourcc(*\"MJPG\")\r\nout = cv2.VideoWriter(\"output.avi\",fourcc, 20.0, (640,480))")'>Copy</button> Set the specifics

```python
element = Element("camera")
fourcc = cv2.VideoWriter_fourcc(*"MJPG")
out = cv2.VideoWriter("output.avi",fourcc, 20.0, (640,480))
```

In run_demo.py, we first create an element named camera. Then we call a video writer function specifying the encoder that we would like to use. In the third line, we mention the name of the file in which our video stream would be saved and the dimensions of that video.

## Read and Write Stream

> <button class="copy-button" onclick='copyText(this, "entries = element.entry_read_n(\"realsense\",\"color\",1)\r\nraw_image_data = entries[0][\"data\"]\r\nnp_array = np.fromstring(raw_image_data, np.uint8)\r\nnp_image = cv2.imdecode(numpy_array, cv2.IMREAD_COLOR)\r\nout.write(np_image)")'>Copy</button> Read and write the stream.

```python
entries = element.entry_read_n("realsense","color",1)
raw_image_data = entries[0]["data"]
np_array = np.fromstring(raw_image_data, np.uint8)
np_image = cv2.imdecode(numpy_array, cv2.IMREAD_COLOR)
out.write(np_image)
```

The final step is to read and write the video stream. We first declare the specific stream we would like to read, in our case it is the 'color'. We select the raw data that we get and store it in the raw_image_data and then we convert it into a numpy array. We further decode the numpy array into an opencv image. After the processing of the image is done, we write the frame from stream to the video file.

## Stop the RealSense Demo

> <button class="copy-button" onclick='copyText(this, "docker-compose down -t 1 -v")'>Copy</button> Launch the demo

```shell_session
docker-compose down -t 1 -v
```

To stop the demo please run the command on your right
