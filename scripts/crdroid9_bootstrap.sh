#!/usr/bin/env bash
set -euo pipefail
cd /home/circleci/m6-runtime
test "$(sha256sum /home/circleci/m6-private/inputs.tar.gz | cut -d' ' -f1)" = 5b28402383ac9255fb2809b094fa8c837a18ae53db2efd2cca98dc0d367594e8
git lfs version || { sudo apt-get update; sudo apt-get install -y git-lfs; }
docker build -t androidforge/build-env:android-9 recipes/crdroid9
python3 scripts/crdroid9_prepare.py /home/circleci/m6-private/inputs.tar.gz 5b28402383ac9255fb2809b094fa8c837a18ae53db2efd2cca98dc0d367594e8
sudo python3 scripts/crdroid9_launch.py "${1:-600}"
