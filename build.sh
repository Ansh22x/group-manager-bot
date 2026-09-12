#!/usr/bin/env bash
export CARGO_HOME=/tmp/cargo
export RUSTUP_HOME=/tmp/rustup

curl -L https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-linux64-gpl.tar.xz -o ffmpeg.tar.xz
tar -xf ffmpeg.tar.xz

cp ffmpeg-master-latest-linux64-gpl/bin/ffmpeg .
cp ffmpeg-master-latest-linux64-gpl/bin/ffprobe .

pip install --upgrade pip setuptools wheel
pip install -r requirements.txt

