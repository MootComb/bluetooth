#!/usr/bin/env bash

pkg update && pkg upgrade
pkg install -y python git
pkg install -y python-pip
pip install -y flask flask-cors pydbus
python backand.py
