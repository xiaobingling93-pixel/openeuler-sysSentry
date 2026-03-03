#!/bin/sh
echo "----------build begin------------"
echo "---------------------------------"

BUILD_DIR=build

if [ "$1" = "clean" ]; then
    if [ -d "$BUILD_DIR" ]; then
        echo "----------clean begin------------"
        cd "$BUILD_DIR" && make clean
        echo "----------clean end--------------"
    else
        echo "Build directory does not exist. Nothing to clean."
    fi
    exit 0
fi

[ ! -d $BUILD_DIR ] && mkdir -p $BUILD_DIR
cd $BUILD_DIR

cmake ..
make || exit "$?"

echo "------- build end -----------"
echo "-----------------------------"
exit 0