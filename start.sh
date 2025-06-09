#!/usr/bin/env bash

pkg update && pkg upgrade
pkg install python git
pkg install python-pip
pip install flask flask-cors pydbus
python backand.py
