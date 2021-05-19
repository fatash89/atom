#!/bin/bash
#
# Installs CUDA requirements based on platform

if [ "$(arch)" == "x86_64" ]; then
    pip3 install -r requirements-cuda.txt
elif [ "$(arch)" == "aarch64" ]; then
    pip3 install third-party/wheels/cupy-8.6.0-cp38-cp38-linux_aarch64.whl
    pip3 install third-party/wheels/torch-1.8.0a0+56b43f4-cp38-cp38-linux_aarch64.whl
    pip3 install third-party/wheels/torchvision-0.9.0a0+8fb5838-cp38-cp38-linux_aarch64.whl
else
    exit 1
fi
