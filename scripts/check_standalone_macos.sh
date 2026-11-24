#!/bin/bash
# Mount the delivered DMG and test its copied app with only loopback access.
set -euo pipefail

package=${1:?Provide the OSII Standalone disk image}
repository=$(cd "$(dirname "$0")/.." && pwd)
node=$(command -v node)
test_root=$(mktemp -d -t osii-mac-test)
mountpoint="$test_root/mounted"
app="$test_root/OSII Standalone.app"
cleanup() {
    if /sbin/mount | /usr/bin/grep -Fq " on $mountpoint "; then
        /usr/bin/hdiutil detach "$mountpoint" >/dev/null
    fi
    rm -rf "$test_root"
}
trap cleanup EXIT

/usr/bin/hdiutil attach -readonly -nobrowse -mountpoint "$mountpoint" "$package"
/usr/bin/ditto "$mountpoint/OSII Standalone.app" "$app"
/usr/bin/hdiutil detach "$mountpoint"
/usr/bin/codesign --verify --deep --strict "$app"

network_profile='(version 1) (allow default) (deny network-outbound) (allow network-outbound (remote ip "localhost:*"))'
/usr/bin/curl -fsS --max-time 15 https://github.com/robots.txt >/dev/null
export PATH=/usr/bin:/bin:/usr/sbin:/sbin
export OSII_DESKTOP_EXECUTABLE="$app/Contents/MacOS/OSII Standalone"
/usr/bin/sandbox-exec -p "$network_profile" "$app/Contents/Resources/runtime/osii-runtime" self-test
OSII_SMOKE_DIRECTORY="$test_root/Normal launch" "$node" "$repository/osii-desktop/tests/smoke.cjs"
export OSII_SMOKE_DIRECTORY="$test_root/Offline launch"
export OSII_SMOKE_BLOCK_EXTERNAL=1 OSII_SMOKE_MAC_NETWORK_SANDBOX=1
/usr/bin/sandbox-exec -p "$network_profile" "$node" "$repository/osii-desktop/tests/smoke.cjs"
