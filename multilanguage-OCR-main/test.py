import paddle

print("CUDA available:", paddle.is_compiled_with_cuda())
print("cuDNN version:", paddle.version.cudnn())
print("GPU count:", paddle.device.cuda.device_count())
print("GPU name:", paddle.device.cuda.get_device_name(0))