#!/usr/bin/env bash
set -euo pipefail

# This intentionally destructive helper is pinned to the empty USB device
# inspected on 2026-10-24. Every identifying property is checked again before
# mkfs is allowed to run so a changed device name cannot target the NVMe disk.
expected_uuid="34EE-9793"
expected_label="backup"
expected_filesystem="exfat"
expected_size="62024286208"
mount_target="/mnt/gm-backup"

if (( EUID != 0 )); then
  printf 'Run this guarded formatter as root: sudo %s\n' "$0" >&2
  exit 1
fi

device=$(blkid -U "$expected_uuid" 2>/dev/null || true)
if [[ -z "$device" || ! -b "$device" ]]; then
  printf 'Refusing to continue: USB UUID %s is not present.\n' "$expected_uuid" >&2
  exit 1
fi

device_type=$(lsblk -dnro TYPE "$device")
device_size=$(lsblk -bnro SIZE "$device")
device_filesystem=$(lsblk -dnro FSTYPE "$device")
device_label=$(lsblk -dnro LABEL "$device")
parent_name=$(lsblk -dnro PKNAME "$device")
parent_transport=""
if [[ -n "$parent_name" ]]; then
  parent_transport=$(lsblk -dnro TRAN "/dev/$parent_name")
fi

if [[ "$device_type" != "part" \
   || "$device_size" != "$expected_size" \
   || "$device_filesystem" != "$expected_filesystem" \
   || "$device_label" != "$expected_label" \
   || "$parent_transport" != "usb" ]]; then
  printf 'Refusing to format: the inspected USB identity no longer matches.\n' >&2
  printf 'Observed: device=%s type=%s size=%s fs=%s label=%s parent=%s transport=%s\n' \
    "$device" "$device_type" "$device_size" "$device_filesystem" \
    "$device_label" "$parent_name" "$parent_transport" >&2
  exit 1
fi

if findmnt --source "$device" >/dev/null 2>&1 \
   || lsblk -nrpo MOUNTPOINT "$device" | grep -q '[^[:space:]]'; then
  printf 'Refusing to format: %s is mounted.\n' "$device" >&2
  exit 1
fi

root_source=$(findmnt -nro SOURCE /)
if [[ "$root_source" == "$device" || "$root_source" == "/dev/$parent_name" ]]; then
  printf 'Refusing to format: selected device is associated with the root filesystem.\n' >&2
  exit 1
fi

printf 'Formatting verified empty USB partition %s (%s bytes) as ext4...\n' \
  "$device" "$device_size"
mkfs.ext4 -F -m 0 -L gm-backup "$device"
udevadm settle

new_uuid=$(blkid -s UUID -o value "$device")
if [[ -z "$new_uuid" ]]; then
  printf 'Formatting completed but the new filesystem UUID could not be read.\n' >&2
  exit 1
fi

install -d -o root -g gm -m 2770 "$mount_target"

fstab_backup="/etc/fstab.gm-media-server.$(date -u +%Y%m%dT%H%M%SZ).bak"
cp --preserve=all /etc/fstab "$fstab_backup"

fstab_temporary=$(mktemp --tmpdir gm-media-fstab.XXXXXX)
cleanup() {
  rm -f -- "$fstab_temporary"
}
trap cleanup EXIT

awk -v target="$mount_target" '$2 != target { print }' /etc/fstab >"$fstab_temporary"
printf 'UUID=%s %s ext4 defaults,nofail,x-systemd.device-timeout=10s 0 2\n' \
  "$new_uuid" "$mount_target" >>"$fstab_temporary"
install -o root -g root -m 0644 "$fstab_temporary" /etc/fstab

systemctl daemon-reload
mount "$mount_target"
chown root:gm "$mount_target"
chmod 2770 "$mount_target"

marker_temporary=$(mktemp --tmpdir gm-backup-marker.XXXXXX)
printf 'GM Media Server backup device\nUUID=%s\nPrepared=%s\n' \
  "$new_uuid" "$(date -u +%Y-%m-%dT%H:%M:%SZ)" >"$marker_temporary"
install -o root -g gm -m 0640 "$marker_temporary" "$mount_target/.gm-backup-device"
rm -f -- "$marker_temporary"

findmnt --target "$mount_target" --output TARGET,SOURCE,FSTYPE,OPTIONS,SIZE,AVAIL
printf '\nPrepared %s successfully.\n' "$mount_target"
printf 'New filesystem UUID: %s\n' "$new_uuid"
printf 'Previous /etc/fstab saved as: %s\n' "$fstab_backup"
