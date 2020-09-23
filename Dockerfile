################################################################################
#
# Build in the source
#
################################################################################

ARG BASE_IMAGE=elementaryrobotics/atom:base
ARG PRODUCTION_IMAGE=debian:buster-slim
FROM $BASE_IMAGE as atom-source

ARG DEBIAN_FRONTEND=noninteractive

#
# Redis itself
#

# Build redis
ADD ./third-party/redis /atom/third-party/redis
RUN cd /atom/third-party/redis && make -j8 && make PREFIX=/usr/local install

#
# Redis time series module. Should eventually make its way
#   into the base, but for now can live in here
#
ADD ./third-party/RedisTimeSeries /atom/third-party/RedisTimeSeries
WORKDIR /atom/third-party/RedisTimeSeries
RUN ./deps/readies/bin/getpy2
RUN ./system-setup.py
RUN make build

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
ADD third-party/redistimeseries-py /atom/third-party/redistimeseries-py
RUN cd /atom/third-party/redistimeseries-py && python3 setup.py install

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
# Requirements for metrics/monitoring
#

RUN apt-get -y install python3-dev
RUN pip3 install wheel
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

FROM $PRODUCTION_IMAGE as atom

# Configuration environment variables
ENV ATOM_NUCLEUS_HOST ""
ENV ATOM_METRICS_HOST ""
ENV ATOM_NUCLEUS_PORT "6379"
ENV ATOM_METRICS_PORT "6380"
ENV ATOM_NUCLEUS_SOCKET "/shared/redis.sock"
ENV ATOM_METRICS_SOCKET "/shared/metrics.sock"
ENV ATOM_LOG_DIR "/var/log/atom/"
ENV ATOM_LOG_FILE_SIZE 2000

# Install python
RUN apt-get update -y \
 && apt-get install -y --no-install-recommends apt-utils \
                                               python3-minimal \
                                               python3-pip \
                                               libatomic1


# Copy contents of python virtualenv and activate
COPY --from=atom-source /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
ENV PYTHONUNBUFFERED=TRUE

# Copy C builds
COPY --from=atom-source /usr/local/lib /usr/local/lib
COPY --from=atom-source /usr/local/include /usr/local/include
ENV LD_LIBRARY_PATH=/usr/local/lib:${LD_LIBRARY_PATH}

# Copy atom-cli
COPY --from=atom-source /usr/local/bin/atom-cli /usr/local/bin/atom-cli

# Copy redis-cli
COPY --from=atom-source /usr/local/bin/redis-cli /usr/local/bin/redis-cli
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
RUN apt-get install -y supervisor
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

ARG DEBIAN_FRONTEND=noninteractive

#
# Install test dependencies
#

# Install googletest
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
    libgtest-dev \
    cmake \
    build-essential \
    python3-pip \
 && cd /usr/src/gtest \
 && cmake CMakeLists.txt \
 && make -j8 \
 && cp *.a /usr/lib

# Install valgrind
RUN apt-get install -y --no-install-recommends valgrind

# Install pytest
RUN pip3 install --no-cache-dir pytest

# Copy source code
COPY ./languages/c/ /atom/languages/c
COPY ./languages/cpp/ /atom/languages/cpp
COPY ./languages/python/tests /atom/languages/python/tests
