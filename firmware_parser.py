from __future__ import annotations

from pathlib import Path


EXPECTED_START_ADDRESS = 0x00000000
FLASH_START_ADDRESS = 0x00000000
FLASH_END_ADDRESS = 0x0007FFFF


class FirmwareValidationError(ValueError):
    """Raised when a firmware file is not safe to program."""


def parse_intel_hex(path: Path) -> list[tuple[int, int]]:
    ranges: list[tuple[int, int]] = []
    base_address = 0
    lines = path.read_text(encoding="ascii").lstrip("\ufeff").splitlines()

    for line_number, line in enumerate(lines, 1):
        line = line.strip()
        if not line:
            continue
        if not line.startswith(":"):
            raise FirmwareValidationError(f"\u7b2c {line_number} \u884c\u4e0d\u662f\u6709\u6548\u7684 Intel HEX \u8bb0\u5f55\u3002")
        try:
            record = bytes.fromhex(line[1:])
        except ValueError as exc:
            raise FirmwareValidationError(f"\u7b2c {line_number} \u884c\u5305\u542b\u65e0\u6548\u5341\u516d\u8fdb\u5236\u6570\u636e\u3002") from exc
        if len(record) < 5 or len(record) != record[0] + 5:
            raise FirmwareValidationError(f"\u7b2c {line_number} \u884c\u957f\u5ea6\u9519\u8bef\u3002")
        if sum(record) & 0xFF:
            raise FirmwareValidationError(f"\u7b2c {line_number} \u884c\u6821\u9a8c\u548c\u9519\u8bef\u3002")

        data_length = record[0]
        address = base_address + (record[1] << 8) + record[2]
        record_type = record[3]
        if record_type == 0x00 and data_length:
            ranges.append((address, address + data_length - 1))
        elif record_type == 0x02 and data_length == 2:
            base_address = ((record[4] << 8) | record[5]) << 4
        elif record_type == 0x04 and data_length == 2:
            base_address = ((record[4] << 8) | record[5]) << 16

    return ranges


def parse_s_record(path: Path) -> list[tuple[int, int]]:
    ranges: list[tuple[int, int]] = []
    address_lengths = {"1": 2, "2": 3, "3": 4}
    lines = path.read_text(encoding="ascii").lstrip("\ufeff").splitlines()

    for line_number, line in enumerate(lines, 1):
        line = line.strip()
        if not line:
            continue
        if len(line) < 4 or line[0].upper() != "S":
            raise FirmwareValidationError(f"\u7b2c {line_number} \u884c\u4e0d\u662f\u6709\u6548\u7684 S-Record\u3002")
        record_type = line[1].upper()
        try:
            count = int(line[2:4], 16)
            payload = bytes.fromhex(line[4:])
        except ValueError as exc:
            raise FirmwareValidationError(f"\u7b2c {line_number} \u884c\u5305\u542b\u65e0\u6548\u5341\u516d\u8fdb\u5236\u6570\u636e\u3002") from exc
        if len(payload) != count:
            raise FirmwareValidationError(f"\u7b2c {line_number} \u884c\u957f\u5ea6\u9519\u8bef\u3002")
        if (count + sum(payload)) & 0xFF != 0xFF:
            raise FirmwareValidationError(f"\u7b2c {line_number} \u884c\u6821\u9a8c\u548c\u9519\u8bef\u3002")

        address_length = address_lengths.get(record_type)
        if address_length is None:
            continue
        address = int.from_bytes(payload[:address_length], "big")
        data_length = count - address_length - 1
        if data_length > 0:
            ranges.append((address, address + data_length - 1))

    return ranges


def merge_ranges(ranges: list[tuple[int, int]]) -> list[tuple[int, int]]:
    merged: list[list[int]] = []
    for start, end in sorted(ranges):
        if not merged or start > merged[-1][1] + 1:
            merged.append([start, end])
        else:
            merged[-1][1] = max(merged[-1][1], end)
    return [(start, end) for start, end in merged]


def firmware_ranges(path: Path) -> list[tuple[int, int]]:
    suffix = path.suffix.lower()
    if suffix == ".hex":
        ranges = parse_intel_hex(path)
    elif suffix in {".s19", ".srec", ".mot"}:
        ranges = parse_s_record(path)
    elif suffix == ".bin":
        raise FirmwareValidationError("BIN \u6587\u4ef6\u4e0d\u5305\u542b\u5730\u5740\u4fe1\u606f\uff0c\u65e0\u6cd5\u5224\u65ad\u56fa\u4ef6\u8d77\u59cb\u5730\u5740\u3002")
    else:
        raise FirmwareValidationError("\u53ea\u652f\u6301 HEX\u3001S19\u3001SREC \u6216 MOT \u56fa\u4ef6\u6587\u4ef6\u3002")

    ranges = merge_ranges(ranges)
    if not ranges:
        raise FirmwareValidationError("\u56fa\u4ef6\u6587\u4ef6\u4e2d\u6ca1\u6709\u53ef\u70e7\u5f55\u7684\u6570\u636e\u8bb0\u5f55\u3002")
    return ranges


def validate_firmware(path: Path) -> tuple[int, int]:
    ranges = firmware_ranges(path)
    start_address = ranges[0][0]
    end_address = ranges[-1][1]
    if start_address != EXPECTED_START_ADDRESS:
        raise FirmwareValidationError(
            f"\u56fa\u4ef6\u8d77\u59cb\u5730\u5740\u4e3a 0x{start_address:08X}\uff0c"
            f"\u8981\u6c42\u5fc5\u987b\u4e3a 0x{EXPECTED_START_ADDRESS:08X}\u3002"
        )
    if start_address < FLASH_START_ADDRESS or end_address > FLASH_END_ADDRESS:
        raise FirmwareValidationError(
            f"\u56fa\u4ef6\u5730\u5740\u8303\u56f4\u4e3a 0x{start_address:08X}-0x{end_address:08X}\uff0c"
            f"\u8d85\u51fa\u5141\u8bb8\u8303\u56f4 0x{FLASH_START_ADDRESS:08X}-0x{FLASH_END_ADDRESS:08X}\u3002"
        )
    return start_address, end_address