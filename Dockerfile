################################################################################
#
# Base image: Deps that change infrequently so that we don't have to
#  rebuild this part of the file often and can rely on the cache
#
################################################################################

#
# ALL ARGS TO BE USED IN **ANY** FROM MUST OCCUR BEFORE THE **FIRST** FROM
# https://docs.docker.com/engine/reference/builder/#understand-how-arg-and-from-interact
#
ARG STOCK_IMAGE=ubuntu:focal-20210416
ARG ATOM_BASE=atom-base
ARG DEBIAN_FRONTEND=noninteractive

FROM $STOCK_IMAGE as atom-base

# Which version of Python we should build/install
ARG PYTHON_VERSION=3.8.10

#
# System-level installs
#

RUN apt-get update \
 && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
      apt-utils \
      git \
      autoconf \
      libtool \
      cmake \
      build-essential \
      zlib1g-dev \
      libssl-dev \
      libbz2-dev \
      libffi-dev \
      liblzma-dev \
      libncursesw5-dev \
      libgdbm-dev \
      libsqlite3-dev \
      libc6-dev \
      tk-dev \
      wget \
      flex \
      bison \
      curl \
      pkg-config

# Set up the ability to run things with libraries in /usr/local/lib
ENV LD_LIBRARY_PATH=/usr/local/lib:${LD_LIBRARY_PATH}

# Install Python PYTHON_VERSION from source and set as the default Python version
RUN set +x; mkdir /tmp/python && \
  cd /tmp/python && \
  wget --no-check-certificate https://www.python.org/ftp/python/${PYTHON_VERSION}/Python-${PYTHON_VERSION}.tgz && \
  tar -xzvf Python-${PYTHON_VERSION}.tgz && \
  cd Python-${PYTHON_VERSION} && \
  ./configure --enable-optimizations --enable-shared && \
  make -j8 install && \
  ln -sf /usr/local/bin/python3.8 /usr/bin/python3 && \
  rm -rf /tmp/python

# Switch over to the venv
RUN python3 -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Install setuptools
RUN pip3 install --no-cache-dir --upgrade pip setuptools
RUN pip3 install wheel

#
# C/C++ deps
#

# Build third-party C dependencies
ADD ./languages/c/third-party /atom/languages/c/third-party
RUN cd /atom/languages/c/third-party && make

#
# Python deps
#

# Install custom third-party deps. We need to build
# some of these separately as opposed to installing
# from pip
#
# Install list:
#   1. Cython (needs to be x-compiled for aarch64)
#   2. OpenBLAS (needs to be x-compiled for aarch64/ARM CPU)
#   3. numpy (needs to be x-compiled for aarch64)
#   4. pyarrow (needs to be x-compiled for aarch64)
#   5. redis-py (needs support for memoryviews)

# Cython
ADD ./languages/python/third-party/cython /atom/languages/python/third-party/cython
WORKDIR /atom/languages/python/third-party/cython
RUN python3 setup.py build -j8 install

# OpenBLAS
ADD ./third-party/OpenBLAS /atom/third-party/OpenBLAS
ARG BLAS_TARGET_CPU=""
RUN cd /atom/third-party/OpenBLAS \
  && make TARGET=${BLAS_TARGET_CPU} -j8 \
  && make PREFIX=/usr/local install

# Numpy
ADD ./languages/python/third-party/numpy /atom/languages/python/third-party/numpy
ADD ./languages/python/third-party/numpy.site.cfg /atom/languages/python/third-party/numpy/site.cfg
WORKDIR /atom/languages/python/third-party/numpy
RUN python3 setup.py build -j8 install

# Pyarrow
ADD ./third-party/apache-arrow /atom/third-party/apache-arrow
WORKDIR /atom/third-party/apache-arrow/python
RUN mkdir -p /atom/third-party/apache-arrow/cpp/build \
  && cd /atom/third-party/apache-arrow/cpp/build \
  && cmake -DCMAKE_BUILD_TYPE=release \
           -DOPENSSL_ROOT_DIR=/usr/local/ssl \
           -DCMAKE_INSTALL_LIBDIR=lib \
           -DCMAKE_INSTALL_PREFIX=/usr/local \
           -DARROW_PARQUET=OFF \
           -DARROW_PYTHON=ON \
           -DARROW_PLASMA=ON \
           -DARROW_BUILD_TESTS=OFF \
           -DPYTHON_EXECUTABLE=/opt/venv/bin/python3 \
           .. \
  && make -j8 \
  && make install
ARG PYARROW_EXTRA_CMAKE_ARGS=""
RUN cd /atom/third-party/apache-arrow/python \
  && ARROW_HOME=/usr/local SETUPTOOLS_SCM_PRETEND_VERSION="0.17.0" python3 setup.py build_ext -j 8 --build-type=release --extra-cmake-args=${PYARROW_EXTRA_CMAKE_ARGS} install

#
# Redis itself
#

# Build redis
ADD ./third-party/redis /atom/third-party/redis
RUN cd /atom/third-party/redis && make -j8 && make PREFIX=/usr/local install

#
# Redis time series module.
#
RUN apt-get install -y ca-certificates
ADD ./third-party/RedisTimeSeries /atom/third-party/RedisTimeSeries
WORKDIR /atom/third-party/RedisTimeSeries

# Need to make a separate virtualenv for the build since it installs
# a bunch of python cruft we don't need in our production env. Make the
# env, use it for the build, and then re-source the original
# environment.
RUN python3 -m venv env && \
  . env/bin/activate && \
  python3 system-setup.py && \
  make build MK.pyver=3 && \
  . /opt/venv/bin/activate && \
  rm -rf env

#
# Finish up
#

# Change working directory back to atom location
WORKDIR /atom

################################################################################
#
# Base image: atom + CV tools
#
################################################################################

FROM atom-base as atom-base-cv-build

# Install pre-requisites
RUN apt-get update && DEBIAN_FRONTEND=noninteractive apt-get install -y \
    zlib1g-dev \
    libjpeg-turbo8-dev \
    libpng-dev \
    libtiff-dev \
    libopenexr-dev \
    libavcodec-dev \
    libavformat-dev \
    libswscale-dev \
    libwebp-dev

# Install openCV + python3 bindings
ENV CFLAGS="-I /usr/local/include -I /usr/local/include/python3.8 -L /usr/local/lib ${CFLAGS}"
ENV CXXFLAGS="-I /usr/local/include -I /usr/local/include/python3.8 -L /usr/local/lib ${CXXFLAGS}"
COPY ./third-party/opencv /atom/third-party/opencv
WORKDIR /atom/third-party/opencv
RUN mkdir -p build && cd build && \
    cmake \
    --verbose \
    -DCMAKE_BUILD_TYPE=Release \
    -DCMAKE_INSTALL_PREFIX=/usr/local \
    -DPYTHON3_EXECUTABLE=/opt/venv/bin/python3 \
    -DPYTHON_INCLUDE_DIR=/usr/include/python3.8 \
    -DPYTHON_INCLUDE_DIR2=/usr/include/$(arch)-linux-gnu/python3.8 \
    -DPYTHON_LIBRARY=/usr/lib/$(arch)-linux-gnu/libpython3.8.so \
    -DPYTHON3_NUMPY_INCLUDE_DIRS=/opt/venv/lib/python3.8/site-packages/numpy-1.20.3-py3.8-linux-$(arch).egg/numpy/core/include \
    -DOPENCV_PYTHON3_INSTALL_PATH=/opt/venv/lib/python3.8/site-packages \
    ../ && \
    make -j8 && \
    make install

# Install Pillow (PIL) as that's also used frequently with opencv
COPY ./languages/python/third-party/Pillow /atom/languages/python/third-party/Pillow
WORKDIR /atom/languages/python/third-party/Pillow
RUN MAX_CONCURRENCY=8 python3 setup.py install

RUN ldd /usr/local/lib/libopencv* | grep "=> /" | awk '{print $3}' | sort -u > /tmp/required_libs.txt

#
# Determine libraries we'll ship with in production so we can see what's
#   missing
#
FROM $STOCK_IMAGE as no-deps

RUN ls /lib/$(arch)-linux-gnu/*.so* > /tmp/existing_libs.txt && \
    ls /usr/lib/$(arch)-linux-gnu/*.so* >> /tmp/existing_libs.txt

#
# Copy missing libraries from production into /usr/local/lib
#
FROM atom-base-cv-build as atom-base-cv-deps

COPY --from=no-deps /tmp/existing_libs.txt /tmp/existing_libs.txt

# Diff the libs to see what we should copy over. If nothing to copy over,
#  just exit out
RUN diff --new-line-format="" --unchanged-line-format="" /tmp/required_libs.txt /tmp/existing_libs.txt | grep -v /usr/local/lib > /tmp/libs_to_copy.txt && xargs -a /tmp/libs_to_copy.txt cp -L -t /usr/local/lib || exit 0


#
# Clean up and only ship the following folders:
#   1. /usr/local/lib
#   2. /usr/local/include
#   3. /opt/venv
#
FROM atom-base as atom-base-cv

COPY --from=atom-base-cv-deps /usr/local/lib /usr/local/lib
COPY --from=atom-base-cv-deps /usr/local/include /usr/local/include
COPY --from=atom-base-cv-deps /opt/venv /opt/venv

################################################################################
#
# Base image: atom + CV tools + VNC
#
################################################################################
FROM atom-base-cv as atom-base-vnc

ARG DEBIAN_FRONTEND=noninteractive

# Install dependencies
RUN apt-get install -y --no-install-recommends \
      libgl1-mesa-dri \
      menu \
      net-tools \
      openbox \
      supervisor \
      tint2 \
      x11-xserver-utils \
      x11vnc \
      xinit \
      xserver-xorg-video-dummy \
      xserver-xorg-input-void \
      websockify \
      sudo \
 && rm -f /usr/share/applications/x11vnc.desktop

# Add in noVNC to /opt/noVNC
ADD third-party/noVNC /opt/noVNC

RUN cd /opt/noVNC \
 && ln -s vnc_auto.html index.html \
 && pip3 install --no-cache-dir setuptools \
 && pip3 install --no-cache-dir supervisor-stdout \
 && apt-get -y autoremove \
 && apt-get -y clean \
 && rm -rf /var/lib/apt/lists/*

# noVNC (http server) is on 6080, and the VNC server is on 5900
EXPOSE 6080 5900
COPY third-party/docker-opengl/etc/skel/.xinitrc /etc/skel/.xinitrc

RUN useradd -m -s /bin/bash user
USER user
RUN cp /etc/skel/.xinitrc /home/user/
USER root
RUN echo "user ALL=(ALL) NOPASSWD:ALL" > /etc/sudoers.d/user

COPY third-party/docker-opengl/etc /etc
COPY third-party/docker-opengl/usr /usr

ENV DISPLAY :0

################################################################################
#
# Base image: atom + CV tools + CUDA tools
#
################################################################################
FROM atom-base-cv as atom-base-cuda

WORKDIR /atom/languages/python
ADD ./languages/python/requirements-cuda.txt .
ADD ./languages/python/install_cuda_requirements.sh .
ADD ./languages/python/third-party/wheels ./third-party/wheels
RUN ./install_cuda_requirements.sh

################################################################################
#
# Atom: Built atop any of the bases
#
################################################################################

FROM ${ATOM_BASE} as atom-source

#
# C client
#

# Build the C library
ADD ./languages/c /atom/languages/c
RUN cd /atom/languages/c \
   && make clean && make -j8 && make install

#
# C++ client
#

# Build and install the c++ library
ADD ./languages/cpp /atom/languages/cpp
RUN cd /atom/languages/cpp \
   && make clean && make -j8 && make install

#
# Python client
#

# Build and install the python library
# Add and install requirements first to use DLC
ADD ./languages/python/requirements.txt /atom/languages/python/requirements.txt
RUN pip3 install --no-cache-dir -r /atom/languages/python/requirements.txt
ADD ./lua-scripts /atom/lua-scripts
ADD ./languages/python /atom/languages/python
RUN cd /atom/languages/python \
   && python3 setup_local.py install

#
# Command-line utility
#

ADD ./utilities/atom-cli/requirements.txt /atom/utilities/atom-cli/requirements.txt
RUN pip3 install --no-cache-dir -r /atom/utilities/atom-cli/requirements.txt
ADD ./utilities/atom-cli /atom/utilities/atom-cli
RUN cp /atom/utilities/atom-cli/atom-cli.py /usr/local/bin/atom-cli \
   && chmod +x /usr/local/bin/atom-cli


#
# Requirements for metrics/monitoring
#
ADD metrics/monitoring /usr/local/bin/monitoring
RUN pip3 install -r /usr/local/bin/monitoring/requirements.txt

#
# Finish up
#

# Change working directory back to atom location
WORKDIR /atom

################################################################################
#
# Production atom image. Strips out source. Only includes libraries, headers
#     and Python venv.
#
################################################################################

FROM $STOCK_IMAGE as atom

# Configuration environment variables
ENV ATOM_NUCLEUS_HOST ""
ENV ATOM_METRICS_HOST ""
ENV ATOM_NUCLEUS_PORT "6379"
ENV ATOM_METRICS_PORT "6380"
ENV ATOM_NUCLEUS_SOCKET "/shared/redis.sock"
ENV ATOM_METRICS_SOCKET "/shared/metrics.sock"
ENV ATOM_LOG_DIR "/var/log/atom/"
ENV ATOM_LOG_FILE_SIZE 2000
ENV PYTHONUNBUFFERED=TRUE

# Install python
RUN apt-get update -y \
   && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends apt-utils \
   curl \
   libatomic1

# Copy contents of python virtualenv and activate
COPY --from=atom-source /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Copy /usr/local
COPY --from=atom-source /usr/local/lib /usr/local/lib
COPY --from=atom-source /usr/local/include /usr/local/include
COPY --from=atom-source /usr/local/bin /usr/local/bin
ENV LD_LIBRARY_PATH=/usr/local/lib:${LD_LIBRARY_PATH}

# Set Python3.8 as the default if it's not already
RUN ln -sf /usr/local/bin/python3.8 /usr/bin/python3

# Set the Redis CLI binary
ENV REDIS_CLI_BIN /usr/local/bin/redis-cli

# Add .circleci for docs build
ADD ./.circleci /atom/.circleci

# Change working directory back to atom location
WORKDIR /atom

# Add in the wait_for_nucleus.sh script
ADD utilities/wait_for_nucleus.sh /usr/local/bin/wait_for_nucleus.sh

# Make the log directory so that it exists in the Docker container
RUN mkdir -p ${ATOM_LOG_DIR}

# Run the wait_for_nucleus script by default
CMD [ "/usr/local/bin/wait_for_nucleus.sh", "echo 'No startup command -- exiting!'" ]

################################################################################
#
# Nucleus image. Copies out only binary of redis-server
#
################################################################################

FROM atom as nucleus

# Set some environment variables
ENV NUCLEUS_METRICS_MONITOR TRUE

# Add in monitoring
COPY --from=atom-source /usr/local/bin/monitoring /usr/local/bin/monitoring

# Add in redis-server
COPY --from=atom-source /usr/local/bin/redis-server /usr/local/bin/redis-server
# Add in redis-time-series
COPY --from=atom-source /atom/third-party/RedisTimeSeries/bin/redistimeseries.so /etc/redis/redistimeseries.so

# Add in supervisor and config files
RUN DEBIAN_FRONTEND=noninteractive apt-get install -y supervisor
ADD ./config/nucleus/supervisor /etc/supervisor
ADD ./config/nucleus/redis /etc/redis
RUN mkdir /metrics

# Add in launch script
ADD config/nucleus/launch.sh launch.sh

CMD [ "/bin/bash", "launch.sh" ]

################################################################################
#
# Test image for atom release. Based off of production, adds in test dependencies
#
################################################################################

FROM atom as test

#
# Install test dependencies
#

# Install dependencies
RUN apt-get update \
   && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
   libgtest-dev \
   cmake \
   build-essential \
   python3-pip

# Build and install googletest
RUN cd /usr/src/gtest \
   && cmake CMakeLists.txt \
   && make -j8 \
   && set -x \
   && { cp lib/*.a /usr/lib || cp *.a /usr/lib; } \
   && set +x

# Install valgrind
RUN DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends valgrind

# Install pytest
ADD ./languages/python/requirements-test.txt .
RUN pip3 install --no-cache-dir -r requirements-test.txt

# Install pyright
RUN apt install -y curl
RUN if ! lsb_release; then apt-get install -y lsb-release && sed -i 's/python3/python3.6/g' /usr/bin/lsb_release; fi
RUN curl -sL https://deb.nodesource.com/setup_12.x | bash -
RUN apt install -y nodejs && npm install -g pyright
# Copy in pyright config for running pyright on atom source code
ADD ./languages/python/pyrightconfig-ci.json /atom/languages/python/pyrightconfig-ci.json

# Copy source code
COPY ./languages/c/ /atom/languages/c
COPY ./languages/cpp/ /atom/languages/cpp
COPY ./languages/python/tests /atom/languages/python/tests
COPY ./languages/python/atom /atom/languages/python/atom
