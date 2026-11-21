#!/bin/sh
# Builds the desktop simulator of the Nod firmware. Needs g++ and git.
set -e
cd "$(dirname "$0")"
mkdir -p lib
[ -d lib/Adafruit-GFX-Library ] || git clone -q --depth 1 https://github.com/adafruit/Adafruit-GFX-Library lib/Adafruit-GFX-Library
[ -d lib/ArduinoJson ] || git clone -q --depth 1 https://github.com/bblanchon/ArduinoJson lib/ArduinoJson
FLAGS="-std=c++17 -O1 -Wall -Wno-unused-function -DARDUINO=100 -DNOD_MIRROR=0 \
 -DARDUINOJSON_ENABLE_ARDUINO_STRING=0 -DARDUINOJSON_ENABLE_ARDUINO_STREAM=0 \
 -DARDUINOJSON_ENABLE_ARDUINO_PRINT=0 -DARDUINOJSON_ENABLE_PROGMEM=0 \
 -Imock -Ilib/Adafruit-GFX-Library/src -Ilib/ArduinoJson/src"
g++ $FLAGS -c lib/Adafruit-GFX-Library/src/Adafruit_GFX.cpp -o gfx.o
g++ $FLAGS harness.cpp gfx.o -o nod_sim
echo built nod_sim
