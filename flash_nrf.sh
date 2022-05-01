#!/bin/bash

source common.sh

source "${venv_dir}/bin/activate"
pushd "${build_dir}/microPython/project/micropython/ports/nrf"

if ! command -v openocd; then
  sudo apt-get install openocd
fi

pip install pyOCD nrfutil>6.0.0 intelhex adafruit-nrfutil

if ! command -v nrfjprog; then
  wget https://www.nordicsemi.com/-/media/Software-and-other-downloads/Desktop-software/nRF-command-line-tools/sw/Versions-10-x-x/10-15-3/nrf-command-line-tools_10.15.3_amd64.deb
  sudo dpkg --install nrf-command-line-tools_10.15.3_amd64.deb
  echo "Go to https://www.segger.com/downloads/jlink/JLink_Linux_V764c_x86_64.deb and install it then press key."
  read -n 1 k <&1
fi

PORT=${PORT:-${1:-/dev/ttyACM0}}
BOARD=${NRF_BOARD:-${BOARD:-${2:-"SPACEBEAVER_NRF"}}}
export Q="adafruit-"

# See https://forum.micropython.org/viewtopic.php?f=12&t=7783
make V=1 BOARD=${NRF_BOARD:-SPACEBEAVER_NRF} NRFUTIL_PORT=${PORT} SD=s140 sd
