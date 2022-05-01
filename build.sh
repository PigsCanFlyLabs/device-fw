#!/bin/bash

source common.sh

#MICRO_PYTHON_VERSION=${MICRO_PYTHON_VERSION:-v1.18}
# Needed to use 4.4 -- see https://github.com/micropython/micropython/issues/8277
MICRO_PYTHON_VERSION=${MICRO_PYTHON_VERSION:-master}
ESP_IDF_VERSION="v4.4"
if [ ! -d "${build_dir}" ]; then
  mkdir "${build_dir}"
fi
pushd "${build_dir}"

if [ ! -d "${venv_dir}" ]; then
  virtualenv  "${venv_dir}" --python python3.9
fi

source ${venv_dir}/bin/activate
pip install -r ${SCRIPT_DIR}/requirements.txt

# Install the esp-idf dev tool chain if needed
# Note: can not be called from inside a venv
if ! command -v idf.py &> /dev/null; then
  if [ ! -d "esp-idf" ]; then
    git clone -b "${ESP_IDF_VERSION}" --recursive https://github.com/espressif/esp-idf.git &> clone_logs || (cat clone_logs; exit 1)
  fi
  pushd esp-idf
  if [ ! -d "~/.espressif" ]; then
    # ESP dev env can't be installed while inside a venv so deactivate / re-activate
    deactivate
    (./install.sh &> espidf_install) || (cat espidf_install; exit 1)
    source ${venv_dir}/bin/activate
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

git fetch || echo "No internet, not updating."
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
  make &> base || (cat base; exit 1)
  export PATH="${PATH}:$(pwd)"
fi
popd
# Make uasyncio available for testing on unix port
if [ ! -d ~/.micropython/lib/ ]; then
  mkdir -p ~/.micropython/lib
  cp -af ./extmod/* ~/.micropython/lib/
  micropython -m upip install unittest logging threading typing warnings base64 hmac
fi
# Run some smoke tests
pushd "${FW_DIR}"
flake8 --max-line-length 100 --ignore=Q000 --exclude=manifest.py
micropython -c "import unittest;unittest.main('smoke_test')"
popd
pushd "${MP_ROOT}/ports/esp32"
if [ ! -d "esp-idf" ]; then
  ln -s "${build_dir}/esp-idf" ./esp-idf
fi
cp -af "${PCF_BOARD_DIR}/esp/"* ./boards || echo "already copied"
make submodules &> submod
# make BOARD=GENERIC &> base
# make BOARD=${BOARD:-SPACEBEAVER_C3} FROZEN_MANIFEST="${SCRIPT_DIR}/fw/manifest.py" clean

#make clean USER_C_MODULES="${SCRIPT_DIR}/modules/micropython.cmake"
#make BOARD=${ESP_BOARD:-SPACEBEAVER_C3} FROZEN_MANIFEST="${SCRIPT_DIR}/fw/manifest.py" USER_C_MODULES="${SCRIPT_DIR}/modules/micropython.cmake"

pwd
popd
pushd "${MP_ROOT}/ports/nrf"
cp -af "${PCF_BOARD_DIR}/nrf/"* ./boards || echo "already copied"
if [ ! -d "drivers/bluetooth/s132_nrf52_"* ]; then
  ./drivers/bluetooth/download_ble_stack.sh
fi
if [ ! -d "arm-toolchain" ]; then
  mkdir arm-toolchain
  ARM_TOOLCHAIN_VERSION=${ARM_TOOLCHAIN_VERSION:-$(curl -s https://developer.arm.com/tools-and-software/open-source-software/developer-tools/gnu-toolchain/gnu-rm/downloads | grep -Po '<h3>Version \K.+(?= <span)')}
  curl -Lo gcc-arm-none-eabi.tar.bz2 "https://developer.arm.com/-/media/Files/downloads/gnu-rm/${ARM_TOOLCHAIN_VERSION}/gcc-arm-none-eabi-${ARM_TOOLCHAIN_VERSION}-x86_64-linux.tar.bz2"
  tar xf gcc-arm-none-eabi.tar.bz2 --strip-components=1 -C ./arm-toolchain
fi
PATH="$PATH:$(pwd)/arm-toolchain"
make clean USER_C_MODULES="${SCRIPT_DIR}/modules/micropython.cmake"
make submodules &> submod
# Include extmod for thing.
echo '
include("$(PORT_DIR)/modules/manifest.py")
freeze("$(MPY_DIR)/tools", ("upip.py", "upip_utarfile.py"))
freeze("$(MPY_DIR)/drivers/onewire")
freeze("$(MPY_DIR)/drivers/dht", "dht.py")
' > ./boards/manifest.py
make V=1 BOARD=${NRF_BOARD:-SPACEBEAVER_NRF} SD=s140 FROZEN_MANIFEST="${SCRIPT_DIR}/fw/manifest.py" USER_C_MODULES="${SCRIPT_DIR}/modules/micropython.cmake" MICROPY_VFS=1 MICROPY_VFS_FAT=1 MICROPY_PY_MACHINE_I2C=1 BLUETOOTH_SD=1
