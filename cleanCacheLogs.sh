#!/bin/bash

find . -name '__pycache__' -exec rm -rf {} +
echo "Pycache cleaned!"

find . -name '*.log' -exec rm -rf {} +
echo "log files cleaned!"
