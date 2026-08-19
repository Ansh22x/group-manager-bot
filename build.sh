#!/usr/bin/env bash

curl -L https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-linux64-gpl.tar.xz -o ffmpeg.tar.xz
tar -xf ffmpeg.tar.xz

cp ffmpeg-master-latest-linux64-gpl/bin/ffmpeg .
cp ffmpeg-master-latest-linux64-gpl/bin/ffprobe .

pip install -r requirements.txt
