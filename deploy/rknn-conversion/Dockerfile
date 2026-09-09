FROM python:3.12-slim-bookworm@sha256:782412e85d0f0984994c290652577d4018aff08145c85b262bb63dc0c7522254

# Offline model conversion only. This image is never deployed to an edge Runtime.
RUN sed -i 's|http://deb.debian.org|https://deb.debian.org|g' /etc/apt/sources.list.d/debian.sources \
    && apt-get -o Acquire::Retries=3 update \
    && apt-get -o Acquire::Retries=3 install -y --no-install-recommends libglib2.0-0 libgl1 libgomp1 \
    && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir \
    rknn-toolkit2==2.3.2 numpy==1.26.4 onnx==1.16.1 onnxruntime==1.19.2 \
    torch==2.2.0 opencv-python==4.10.0.84 protobuf==4.25.4 'setuptools<81'
ENV OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2
WORKDIR /work
