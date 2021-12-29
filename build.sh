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
    git clone -b "${ESP_IDF_VERSION}" --recursive https://github.com/espressif/esp-idf.git &> clone_logs || (cat clone_logs; exit 1)
  fi
  pushd esp-idf
  if [ ! -d "~/.espressif" ]; then
    (./install.sh &> espidf_install) || (cat espidf_install; exit 1)
  fi
  source ./export.sh
  popd
fi

mkdir -p ./microPython/project
pushd ./microPython/project

pwd
if [ ! -d "micropython" ]; then
  git clone --recurse-submodules https://github.com/micropython/micropython.git &> clone_logs || (cat clone_logs; exit 1)
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
  make submodules &> submod
  make &> base
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
pushd "${FW_DIR}"
flake8 --max-line-length 100
micropython -c "import unittest;unittest.main('smoke_test')"
popd
pushd "${MP_ROOT}/ports/esp32"
if [ ! -d "esp-idf" ]; then
  ln -s "${build_dir}/esp-idf" ./esp-idf
fi
make submodules &> submod
make BOARD=GENERIC &> base
make BOARD=GENERIC FROZEN_MPY_DIR="${SCRIPT_DIR}/fw/*.py"
pwd
popd

