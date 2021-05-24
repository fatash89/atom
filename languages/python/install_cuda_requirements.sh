#!/bin/bash
#
# Installs CUDA requirements based on platform

WHEEL_DIR=/atom/languages/python/third-party/wheels

if [ "$(arch)" == "x86_64" ]; then
    pip3 install -r requirements-cuda.txt
elif [ "$(arch)" == "aarch64" ]; then
    pip3 install ${WHEEL_DIR}/cupy-8.6.0-cp38-cp38-linux_aarch64.whl
    pip3 install ${WHEEL_DIR}/torch-1.8.0a0+56b43f4-cp38-cp38-linux_aarch64.whl
    pip3 install ${WHEEL_DIR}/torchvision-0.9.0a0+8fb5838-cp38-cp38-linux_aarch64.whl
else
    exit 1
fi
