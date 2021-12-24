#!/bin/bash

source common.sh

MICRO_PYTHON_VERSION=${MICRO_PYTHON_VERSION:-v1.17}
ESP_IDF_VERSION="v4.3.2"
if [ ! -d "${build_dir}" ]; then
  mkdir "${build_dir}"
fi
pushd "${build_dir}"
if [ ! -d "${venv_dir}" ]; then
  virtualenv  "${venv_dir}"
fi

(dpkg -l |grep gcc-arm-none-eabi) || sudo apt-get install -y build-essential libreadline-dev libffi-dev git pkg-config gcc-arm-none-eabi libnewlib-arm-none-eabi


source "${venv_dir}/bin/activate"

# Install the esp-idf dev tool chain
if ! command -v idf.py &> /dev/null; then
  if [ ! -d "esp-idf" ]; then
    git clone -b "${ESP_IDF_VERSION}" --recursive https://github.com/espressif/esp-idf.git
  fi
  pushd esp-idf
  if [ ! -d "~/.espressif" ]; then
    ./install.sh
  fi
  source ./export.sh
  popd
fi


mkdir -p ./microPython/project
pushd ./microPython/project

if [ ! -d "micropython" ]; then
  git clone --recurse-submodules git@github.com:micropython/micropython.git
fi
pushd micropython

git fetch
git checkout 
git checkout "${MICRO_PYTHON_VERSION}"


if [ ! -f "${build_dir}/microPython/project/micropython/mpy-cross" ]; then
  pushd mpy-cross
  make
  cp mpy-cross "${venv_dir}/bin/"
  popd
fi
pushd ./ports/unix
if [ ! -f "micorpython" ]; then
  make submodules
  make
fi
popd
pushd ./ports/esp32
if [ ! -d "esp-idf" ]; then
  ln -s "${build_dir}/esp-idf" ./esp-idf
fi
make clean
make submodules
make BOARD=GENERIC
#make BOARD=GENERIC FROZEN_MPY_DIR="${SCRIPT_DIR}/fw"
popd

