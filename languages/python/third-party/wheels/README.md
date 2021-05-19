# Pre-built Python third-party wheels

We need to pre-build some Python third-party wheels, primarily for packages that will run on the Jetson and leverage the CUDA resources on the system. This is because we need to be in a container running with the nvcr runtime in order to compile against the CUDA headers.

## General Steps

1. Build the atom-cv-base target from the main Dockerfile
2. Run the docker container from (1) using `--runtime nvidia`
3. Clone the repo that you want to build a wheel for
4. Build the wheel, typically with `python3 setup.py bdist_wheel`
5. Copy the wheel out of the container and check it in

## Specific Steps

### Cupy 8.6.0

Clone the source
```
git clone --recursive --branch v8.6.0 http://github.com/cupy/cupy
cd cupy
```

Set the environment variables below to fan the job out across cores
```
export CUPY_NUM_NVCC_THREADS=6
export CUPY_NUM_BUILD_JOBS=6
python3 setup.py bdist_wheel
```

### Pytorch 1.8.1

Docs [here](https://forums.developer.nvidia.com/t/pytorch-for-jetson-version-1-8-0-now-available/72048)


Clone the source
```
git clone --recursive --branch v1.8.1 http://github.com/pytorch/pytorch
cd pytorch
```

Apply [this patch](https://gist.github.com/dusty-nv/ce51796085178e1f38e3c6a1663a93a1#file-pytorch-1-8-jetpack-4-4-1-patch)
```
curl https://gist.githubusercontent.com/dusty-nv/ce51796085178e1f38e3c6a1663a93a1/raw/b1fb148f0ce8e28d9e6df577c9fd794892002e80/pytorch-1.8-jetpack-4.4.1.patch -o patch.txt
git apply patch.txt
```

Set build variables
```
export USE_NCCL=0
export USE_DISTRIBUTED=0
export USE_QNNPACK=0
export USE_PYTORCH_QNNPACK=0
export TORCH_CUDA_ARCH_LIST="5.3;6.2;7.2"
export PYTORCH_BUILD_VERSION=1.8.1
export PYTORCH_BUILD_NUMBER=1
```

Install pre-requirements
```
pip3 install -r requirements.txt
pip3 install scikit-build
pip3 install ninja
```

Finally, build the wheel
```
python3 setup.py bdist_wheel
```

### Torchvision v0.9.1

Pytorch must be installed first. Then, clone the source:

```
git clone --recursive --branch v0.9.1 http://github.com/pytorch/vision
cd vision
```

```
python setup.py bdist_wheel
```
