#!/usr/bin/env bash
set -euo pipefail
cd /home/circleci/m6-runtime
test "$(sha256sum /home/circleci/m6-private/inputs.tar.gz | cut -d' ' -f1)" = bc8bc975c0f89e461c63b2bb9b33abb746371be4618cea53931d77030e6129ca
git lfs version || { sudo apt-get update; sudo apt-get install -y git-lfs; }
docker build -t androidforge/build-env:android-9 recipes/crdroid9
python3 scripts/crdroid9_prepare.py /home/circleci/m6-private/inputs.tar.gz bc8bc975c0f89e461c63b2bb9b33abb746371be4618cea53931d77030e6129ca
sudo python3 scripts/crdroid9_launch.py "${1:-600}"
