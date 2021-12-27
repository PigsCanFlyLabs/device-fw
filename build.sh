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

# Install the esp-idf dev tool chain if needed
# Note: can not be called from inside a venv
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

# Activate the venv now that we have the esp dev env
source "${venv_dir}/bin/activate"

mkdir -p ./microPython/project
pushd ./microPython/project

pwd
if [ ! -d "micropython" ]; then
  git clone --recurse-submodules https://github.com/micropython/micropython.git
fi
pushd micropython
MP_ROOT=$(pwd)

git fetch
git checkout 
git checkout "${MICRO_PYTHON_VERSION}"


if [ ! -f "${build_dir}/microPython/project/micropython/mpy-cross/mpy-cross" ]; then
  pushd mpy-cross
  make
  cp mpy-cross "${venv_dir}/bin/"
  popd
fi
pushd ./ports/unix
if [ ! -f "micorpython" ]; then
  make submodules
  make
  export PATH="${PATH}:$(pwd)"
fi
popd
# Make uasyncio available for testing on unix port
if [ ! -d "~/.micropython/lib/" ]; then
  mkdir -p ~/.micropython/lib
  cp -af ./extmod/* ~/.micropython/lib/
  micropython -m upip install unittest
fi
# Run some smoke tests
popd
pushd fw
micropython -c "import unittest;unittest.main('smoke_test')"
popd
pushd "${MP_ROOT}/ports/esp32"
if [ ! -d "esp-idf" ]; then
  ln -s "${build_dir}/esp-idf" ./esp-idf
fi
make submodules
make BOARD=GENERIC
make BOARD=GENERIC FROZEN_MPY_DIR="${SCRIPT_DIR}/fw/*.py"
popd

