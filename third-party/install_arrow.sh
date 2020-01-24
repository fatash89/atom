# Script to build and install arrow on alpine

# build Cody's fork of redis-py
git clone https://github.com/Cody-G/redis-py.git
cd redis-py
python3 setup.py install

export ARROW_BUILD_TYPE=release
export ARROW_HOME=/usr/local \
       PARQUET_HOME=/usr/local
export PYTHON_EXECUTABLE=/usr/bin/python3

# install requirements
if [[ `which apt` ]]; then
  export DEBIAN_FRONTEND="noninteractive"
  apt-get update
  apt-get install -y python3-dev \
                     libjemalloc-dev libboost-dev \
                     build-essential \
                     libboost-filesystem-dev \
                     libboost-regex-dev \
                     libboost-system-dev \
                     flex \
                     bison

elif [[ `which apk` ]]; then
  apk add python3-dev \
          bash \
          autoconf \
          flex \
          bison \
          curl \
          build-base \
          boost-dev \
          zlib-dev \
          libressl-dev
fi

pip3 install --no-cache-dir six pytest numpy cython

# build and install
mkdir -p /atom/third-party/apache-arrow/cpp/build \
  && cd /atom/third-party/apache-arrow/cpp/build \
  && cmake -DCMAKE_BUILD_TYPE=$ARROW_BUILD_TYPE \
           -DOPENSSL_ROOT_DIR=/usr/local/ssl \
           -DCMAKE_INSTALL_LIBDIR=lib \
           -DCMAKE_INSTALL_PREFIX=$ARROW_HOME \
           -DARROW_PARQUET=ON \
           -DARROW_PYTHON=ON \
           -DARROW_PLASMA=ON \
           -DARROW_BUILD_TESTS=OFF \
           -DPYTHON_EXECUTABLE=$PYTHON_EXECUTABLE \
           .. \
  && make -j$(nproc) \
  && make install \
  && cd /atom/third-party/apache-arrow/python \
  && python3 setup.py build_ext --build-type=$ARROW_BUILD_TYPE --with-parquet \
  && python3 setup.py install
