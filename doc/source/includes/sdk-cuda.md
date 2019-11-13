# SDK CUDA Support

If your element requires CUDA support for tasks like deep learning, follow the instructions in "SDK Graphics Support" with these modifications:

1. Install both the NVIDIA driver and CUDA on your host machine.  Nvidia provides detailed [instructions](https://docs.nvidia.com/cuda/cuda-installation-guide-linux/index.html).
2. Use one of the provided CUDA-enabled Atom base images, taking care that the image CUDA version matches the CUDA version on your host machine.
3. (optional) To verify that everything is running, you can start a shell in your element and run `nvidia-smi`, which should show some output.
