################################################################################
#
# Base image. Contains all third-party dependencies and all source
#
################################################################################

ARG BASE_IMAGE=debian:buster-slim
FROM $BASE_IMAGE as atom-base

ARG DEBIAN_FRONTEND=noninteractive

#
# System-level installs
#

RUN apt-get update -y \
 && apt-get install -y --no-install-recommends \
      apt-utils \
      git \
      autoconf \
      libtool \
      cmake \
      build-essential \
      python3-minimal \
      python3-pip \
      python3-venv \
      python3-dev \
      flex \
      bison \
      curl \
      pkg-config \
 && pip3 install --no-cache-dir --upgrade pip setuptools

#
# C client
#

# Build third-party C dependencies
ADD ./languages/c/third-party /atom/languages/c/third-party
RUN cd /atom/languages/c/third-party && make

# Build the C library
ADD ./languages/c /atom/languages/c
RUN cd /atom/languages/c \
 && make clean && make -j16 && make install

#
# C++ client
#

# Build and install the c++ library
ADD ./languages/cpp /atom/languages/cpp
RUN cd /atom/languages/cpp \
 && make clean && make -j16 && make install

#
# Python client
#

# Create and activate python virtualenv
RUN python3 -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

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
RUN python3 setup.py build -j16 install

# OpenBLAS
ADD ./third-party/OpenBLAS /atom/third-party/OpenBLAS
RUN cd /atom/third-party/OpenBLAS \
  && make -j16 \
  && make PREFIX=/usr/local install

# Numpy
ADD ./languages/python/third-party/numpy /atom/languages/python/third-party/numpy
ADD ./languages/python/third-party/numpy.site.cfg /atom/languages/python/third-party/numpy/site.cfg
WORKDIR /atom/languages/python/third-party/numpy
RUN python3 setup.py build -j16 install

# Pyarrow
ADD ./third-party/apache-arrow /atom/third-party/apache-arrow
WORKDIR /atom/third-party/apache-arrow/python
RUN mkdir -p /atom/third-party/apache-arrow/cpp/build \
  && cd /atom/third-party/apache-arrow/cpp/build \
  && cmake -DCMAKE_BUILD_TYPE=release \
           -DOPENSSL_ROOT_DIR=/usr/local/ssl \
           -DCMAKE_INSTALL_LIBDIR=lib \
           -DCMAKE_INSTALL_PREFIX=/usr/local \
           -DARROW_PARQUET=ON \
           -DARROW_PYTHON=ON \
           -DARROW_PLASMA=ON \
           -DARROW_BUILD_TESTS=OFF \
           -DPYTHON_EXECUTABLE=/opt/venv/bin/python3 \
           .. \
  && make -j16 \
  && make install
RUN cd /atom/third-party/apache-arrow/python \
  && SETUPTOOLS_SCM_PRETEND_VERSION="apache-arrow-0.14.1" python3 setup.py build_ext -j 16 --build-type=release --with-parquet install

# Redis-py
ADD ./languages/python/third-party/redis-py /atom/languages/python/third-party/redis-py
RUN cd /atom/languages/python/third-party/redis-py \
 && python3 setup.py install

# Build and install the python library
# Add and install requirements first to use DLC
ADD ./languages/python/requirements.txt /atom/languages/python/requirements.txt
RUN pip3 install --no-cache-dir -r /atom/languages/python/requirements.txt
ADD ./lua-scripts /atom/lua-scripts
ADD ./languages/python /atom/languages/python
RUN cd /atom/languages/python \
 && python3 setup.py install

#
# Command-line utility
#

ADD ./utilities/atom-cli/requirements.txt /atom/utilities/atom-cli/requirements.txt
RUN pip3 install --no-cache-dir -r /atom/utilities/atom-cli/requirements.txt
ADD ./utilities/atom-cli /atom/utilities/atom-cli
RUN cp /atom/utilities/atom-cli/atom-cli.py /usr/local/bin/atom-cli \
 && chmod +x /usr/local/bin/atom-cli

#
# Redis itself. Need this in the atom image s.t. we have redis-cli in all of
# the atom containers for inspecting redis. We will also use this to copy
# the redis-server into the Nucleus
#

# Build redis
ADD ./third-party/redis /atom/third-party/redis
RUN cd /atom/third-party/redis && make -j16 && make PREFIX=/usr/local install

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

FROM $BASE_IMAGE as atom

# Cache buster env var - change date to invalidate subsequent caching
# See the atom README "Atom Dockerfile" section for more information
ENV LAST_UPDATED 2019-03-06

# Install python
RUN apt-get update -y \
 && apt-get install -y --no-install-recommends apt-utils \
                                               python3-minimal \
                                               python3-pip

# Copy contents of python virtualenv and activate
COPY --from=atom-base /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Copy C builds
COPY --from=atom-base /usr/local/lib /usr/local/lib
COPY --from=atom-base /usr/local/include /usr/local/include

# Copy atom-cli
COPY --from=atom-base /usr/local/bin/atom-cli /usr/local/bin/atom-cli

# Copy redis-cli
COPY --from=atom-base /usr/local/bin/redis-cli /usr/local/bin/redis-cli

# Add .circleci for docs build
ADD ./.circleci /atom/.circleci

# Change working directory back to atom location
WORKDIR /atom

################################################################################
#
# Nucleus image. Copies out only binary of redis-server
#
################################################################################

FROM atom as nucleus

# Add in redis-server
COPY --from=atom-base /usr/local/bin/redis-server /usr/local/bin/redis-server

ADD ./launch_nucleus.sh /nucleus/launch.sh
ADD ./redis.conf /nucleus/redis.conf
WORKDIR /nucleus
RUN chmod +x launch.sh
CMD ["./launch.sh"]

################################################################################
#
# Test image. Based off of production, adds in test dependencies
#
################################################################################

FROM atom as test

ARG DEBIAN_FRONTEND=noninteractive

#
# Install test dependencies
#

# Cache buster env var - change date to invalidate subsequent caching
# See the atom README "Atom Dockerfile" section for more information
ENV LAST_UPDATED 2019-03-12

# Install googletest
RUN apt-get update \
 && apt-get install -y --no-install-recommends libgtest-dev cmake build-essential \
 && cd /usr/src/gtest \
 && cmake CMakeLists.txt && make -j16 && cp *.a /usr/lib

# Install valgrind
RUN apt-get install -y --no-install-recommends valgrind

# Install pytest
RUN pip3 install --no-cache-dir pytest

# Copy source code
COPY ./languages/c/ /atom/languages/c
COPY ./languages/cpp/ /atom/languages/cpp
COPY ./languages/python/tests /atom/languages/python/tests

################################################################################
#
# Graphics image. Based off of production, adds in support for various
#     graphics packages and VNC.
#
################################################################################

FROM atom as graphics

ARG DEBIAN_FRONTEND=noninteractive

# Add in noVNC to /opt/noVNC
ADD third-party/noVNC /opt/noVNC

# Install graphics
# Note: supervisor-stdout must be installed with pip2 and not pip3
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
      git \
      sudo \
      python-pip \
 && rm -f /usr/share/applications/x11vnc.desktop \
# VNC
 && cd /opt/noVNC \
 && ln -s vnc_auto.html index.html \
 && pip2 install --no-cache-dir setuptools \
 && pip2 install --no-cache-dir supervisor-stdout \
 && apt-get -y remove python-pip git \
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

# Need to run app with python2 instead of python3
RUN var='#!/usr/bin/env python2' \
 && sed -i "1s@.*@${var}@" /usr/bin/graphical-app-launcher.py

ENV DISPLAY :0
