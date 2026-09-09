#!/usr/bin/env bash
# Build script for joulectrl fixed_compute kernel
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "${SCRIPT_DIR}"

CC="${CC:-gcc}"
CFLAGS="${CFLAGS:--O3 -Wall -Wextra -pthread}"
TARGET="fixed_compute"

echo "Compiling ${TARGET} with ${CC} (${CFLAGS})..."
${CC} ${CFLAGS} -o "${TARGET}" fixed_compute.c

echo "Build complete: ${SCRIPT_DIR}/${TARGET}"
"${SCRIPT_DIR}/${TARGET}" -w 1 -c 16 -i 1000 -q > /dev/null
echo "Smoke test passed."
