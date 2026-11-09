"""DJI DUML framing and status decoding for the Mic Series Mobile Receiver.

The receiver exposes a vendor interface (MI_06) with Bulk OUT 0x06 / Bulk IN 0x86.
Frames use DJI's DUML v1 framing::

    0      0x55
    1-2    length (10 bits, whole frame incl. CRC16) | version 1 << 10
    3      CRC8 of bytes 0-2
    4      sender   (0x02 = host/app)
    5      receiver (0x5a = receiver)
    6-7    sequence (little endian)
    8      command type (0x00 push, 0x40 request with ack, bit 7 = response)
    9      command set
    10     command id
    11..   payload
    n-2..  CRC16 of everything before it (little endian)

Protocol notes were derived from the public community documentation listed in
docs/CREDITS.md. This module is an independent implementation.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable

MAGIC = 0x55
ADDRESS_APP = 0x02
ADDRESS_RECEIVER = 0x5A
HEADER_LENGTH = 11
MIN_FRAME_LENGTH = 13
MAX_FRAME_LENGTH = 1024

COMMAND_SET_WIRELESS_MIC = 0x5B
COMMAND_STATUS_PUSH = 0x03
COMMAND_SET_PARAMS = 0x01
COMMAND_GET_CAPABILITY = 0x12

# set_wireless_mic_params setting IDs (verified on the Mobile RX)
SETTING_CHANNEL_MODE = 0x0008
SETTING_RECEIVER_GAIN = 0x0039
SETTING_AUTO_POWER_OFF = 0x0010
SETTING_TRANSMITTER_MUTE = 0x0009

# Capability IDs
CAPABILITY_ALL = 0
CAPABILITY_CHANNEL_MODES = 5
CAPABILITY_GAIN = 6

CHANNEL_MONO = 0
CHANNEL_STEREO = 2

# 3-bit battery gauge: 1 = full, 7 = about to shut down.
GAUGE_PERCENT = {0: None, 1: 100, 2: 85, 3: 70, 4: 55, 5: 40, 6: 20, 7: 5}


def crc8(data: bytes) -> int:
    """CRC-8 used for the 3-byte DUML header (poly 0x31 reflected, init 0x77)."""
    crc = 0x77
    for byte in data:
        crc ^= byte
        for _ in range(8):
            crc = ((crc >> 1) ^ 0x8C) if (crc & 1) else (crc >> 1)
    return crc & 0xFF


def crc16(data: bytes) -> int:
    """CRC-16/IBM-SDLC (poly 0x8408 reflected, init 0x3692)."""
    crc = 0x3692
    for byte in data:
        crc ^= byte
        for _ in range(8):
            crc = ((crc >> 1) ^ 0x8408) if (crc & 1) else (crc >> 1)
    return crc & 0xFFFF


def _u32_le(data: bytes, offset: int) -> int:
    value = 0
    for i in range(4):
        if offset + i < len(data):
            value |= data[offset + i] << (8 * i)
    return value


def _ascii(data: bytes) -> str:
    return "".join(chr(b) for b in data if 0x20 <= b < 0x7F)


@dataclass
class Frame:
    sender: int
    receiver: int
    sequence: int
    command_type: int
    command_set: int
    command_id: int
    payload: bytes = b""

    @property
    def is_response(self) -> bool:
        return bool(self.command_type & 0x80)

    def encode(self) -> bytes:
        length = MIN_FRAME_LENGTH + len(self.payload)
        header = bytes(
            [MAGIC, length & 0xFF, ((length >> 8) & 0x03) | 0x04]
        )
        body = bytearray(header)
        body.append(crc8(header))
        body += bytes(
            [
                self.sender & 0xFF,
                self.receiver & 0xFF,
                self.sequence & 0xFF,
                (self.sequence >> 8) & 0xFF,
                self.command_type & 0xFF,
                self.command_set & 0xFF,
                self.command_id & 0xFF,
            ]
        )
        body += self.payload
        crc = crc16(bytes(body))
        body += bytes([crc & 0xFF, (crc >> 8) & 0xFF])
        return bytes(body)

    @classmethod
    def decode(cls, data: bytes) -> "Frame | None":
        if len(data) < MIN_FRAME_LENGTH or data[0] != MAGIC:
            return None
        if crc8(data[:3]) != data[3]:
            return None
        length = data[1] | ((data[2] & 0x03) << 8)
        if length != len(data) or length < MIN_FRAME_LENGTH:
            return None
        expected = data[length - 2] | (data[length - 1] << 8)
        if crc16(data[: length - 2]) != expected:
            return None
        return cls(
            sender=data[4],
            receiver=data[5],
            sequence=data[6] | (data[7] << 8),
            command_type=data[8],
            command_set=data[9],
            command_id=data[10],
            payload=bytes(data[HEADER_LENGTH : length - 2]),
        )


@dataclass
class StreamParser:
    """Reassembles DUML frames from a stream that may contain iAP2 noise."""

    buffer: bytearray = field(default_factory=bytearray)
    rejected: int = 0

    def feed(self, data: bytes) -> list[Frame]:
        self.buffer.extend(data)
        frames: list[Frame] = []
        while True:
            start = self.buffer.find(MAGIC)
            if start < 0:
                self.buffer.clear()
                break
            if start:
                del self.buffer[:start]
            if len(self.buffer) < 4:
                break
            length = self.buffer[1] | ((self.buffer[2] & 0x03) << 8)
            if (
                crc8(bytes(self.buffer[:3])) != self.buffer[3]
                or length < MIN_FRAME_LENGTH
                or length > MAX_FRAME_LENGTH
            ):
                del self.buffer[0]
                continue
            if len(self.buffer) < length:
                break
            frame = Frame.decode(bytes(self.buffer[:length]))
            if frame is None:
                self.rejected += 1
                del self.buffer[0]
            else:
                frames.append(frame)
                del self.buffer[:length]
        if len(self.buffer) > 4096:
            del self.buffer[:-4096]
        return frames


def tlv_payload(setting: int, value: int) -> bytes:
    """Body of `set_wireless_mic_params` (V2): index 0 = receiver, TLV id, value."""
    return bytes(
        [
            0x02,
            0x00,
            0x00,
            0x00,
            0x00,
            setting & 0xFF,
            (setting >> 8) & 0xFF,
            0x01,
            value & 0xFF,
        ]
    )


def set_param_frame(sequence: int, setting: int, value: int) -> bytes:
    return Frame(
        sender=ADDRESS_APP,
        receiver=ADDRESS_RECEIVER,
        sequence=sequence,
        command_type=0x40,
        command_set=COMMAND_SET_WIRELESS_MIC,
        command_id=COMMAND_SET_PARAMS,
        payload=tlv_payload(setting, value),
    ).encode()


def get_capability_frame(sequence: int, capability: int = 0) -> bytes:
    return Frame(
        sender=ADDRESS_APP,
        receiver=ADDRESS_RECEIVER,
        sequence=sequence,
        command_type=0x40,
        command_set=COMMAND_SET_WIRELESS_MIC,
        command_id=COMMAND_GET_CAPABILITY,
        payload=bytes(
            [0, 0, 0, 0, capability & 0xFF, (capability >> 8) & 0xFF]
        ),
    ).encode()


# ---------------------------------------------------------------------------
# Status model
# ---------------------------------------------------------------------------


@dataclass
class Identity:
    product_name: str | None = None
    firmware: str | None = None
    serial_number: str | None = None
    bluetooth_id: str | None = None


@dataclass
class ReceiverStatus:
    identity: Identity = field(default_factory=Identity)
    channel_raw: int | None = None
    gain_db: int | None = None
    noise_cancelling: bool | None = None
    noise_level: int | None = None
    auto_power_off: bool | None = None
    battery_level: int | None = None
    attached_over_usb: bool | None = None
    connected: set[int] = field(default_factory=set)

    @property
    def channel_name(self) -> str:
        if self.channel_raw == CHANNEL_MONO:
            return "单声道"
        if self.channel_raw == CHANNEL_STEREO:
            return "立体声"
        if self.channel_raw is None:
            return "—"
        return f"模式 {self.channel_raw}"

    @property
    def battery_percent(self) -> int | None:
        return GAUGE_PERCENT.get(self.battery_level or 0)


@dataclass
class TransmitterStatus:
    index: int
    identity: Identity = field(default_factory=Identity)
    battery_level: int | None = None
    is_charging: bool | None = None
    noise_cancelling: bool | None = None
    noise_level: int | None = None
    gain_db: int | None = None
    signal_level: int | None = None
    meter_level: int | None = None
    raw_flags: int | None = None

    @property
    def battery_percent(self) -> int | None:
        return GAUGE_PERCENT.get(self.battery_level or 0)


@dataclass
class MicStatus:
    receiver: ReceiverStatus = field(default_factory=ReceiverStatus)
    transmitters: dict[int, TransmitterStatus] = field(default_factory=dict)

    def transmitter(self, index: int) -> TransmitterStatus:
        return self.transmitters.setdefault(index, TransmitterStatus(index))

    def connected_transmitters(self) -> list[TransmitterStatus]:
        return [
            self.transmitters.get(i, TransmitterStatus(i))
            for i in sorted(self.receiver.connected)
        ]


def _signed_byte(value: int) -> int:
    return value - 256 if value > 127 else value


def apply_frame(frame: Frame, status: MicStatus) -> bool:
    """Apply one status push to `status`. Returns True if it was a status push."""
    if (
        frame.command_set != COMMAND_SET_WIRELESS_MIC
        or frame.command_id != COMMAND_STATUS_PUSH
        or frame.is_response
    ):
        return False
    payload = frame.payload
    if len(payload) < 3 or payload[0] != 0x03:
        return False

    declared = payload[1] | (payload[2] << 8)
    total = min(len(payload), declared + 3)
    offset = 3
    while offset + 6 <= total:
        kind = payload[offset]
        index = _u32_le(payload, offset + 1)
        length = payload[offset + 5]
        end = min(len(payload), offset + 6 + length)
        record = payload[offset:end]
        value = record[6:]
        _apply_record(kind, index, record, value, status)
        offset += 6 + length
    return True


def _apply_record(
    kind: int,
    index: int,
    record: bytes,
    value: bytes,
    status: MicStatus,
) -> None:
    if kind == 0x01:  # identity: firmware + serial
        if len(value) < 4:
            return
        firmware = ".".join(f"{b:02d}" for b in reversed(value[:4]))
        identity = (
            status.receiver.identity if index == 0 else status.transmitter(index).identity
        )
        identity.firmware = firmware
        identity.serial_number = _ascii(value[4:])
    elif kind == 0x04:  # Bluetooth id suffix
        identity = (
            status.receiver.identity if index == 0 else status.transmitter(index).identity
        )
        identity.bluetooth_id = _ascii(value)
    elif kind == 0x06:  # product name
        identity = (
            status.receiver.identity if index == 0 else status.transmitter(index).identity
        )
        identity.product_name = _ascii(value)
    elif kind == 0x05:  # live level
        if index > 0 and value:
            status.transmitter(index).meter_level = value[0]
    elif kind == 0x02:  # transmitter status
        if index <= 0 or len(record) < 10:
            return
        word = _u32_le(record, 6)
        tx = status.transmitter(index)
        tx.raw_flags = word
        tx.battery_level = (word >> 10) & 0x07
        tx.is_charging = bool((word >> 9) & 1)
        tx.noise_cancelling = bool((word >> 8) & 1)
        tx.noise_level = (word >> 5) & 0x03
        if len(record) > 0x0C:
            tx.signal_level = record[0x0C] >> 4
        if len(record) > 0x0D:
            tx.gain_db = _signed_byte(record[0x0D])
    elif kind == 0x03:  # receiver status
        if len(record) < 8:
            return
        word = record[6] | (record[7] << 8)
        rx = status.receiver
        rx.noise_cancelling = bool((word >> 5) & 1)
        rx.noise_level = (word >> 3) & 0x03
        rx.auto_power_off = bool((word >> 8) & 1)
        rx.channel_raw = (word >> 9) & 0x07
        rx.battery_level = (word >> 13) & 0x07
        if len(record) > 0x08:
            rx.gain_db = _signed_byte(record[0x08])
        if len(record) > 0x1E:
            mask = record[0x1E]
            rx.connected = {bit + 1 for bit in range(8) if (mask >> bit) & 1}
        if len(record) > 0x22:
            rx.attached_over_usb = bool((record[0x22] >> 3) & 1)


def parse_capabilities(payload: bytes) -> dict:
    """Parse a 0x5B/0x12 reply into {device_index: {capability_id: bytes}}."""
    result: dict = {}
    if len(payload) < 2:
        return result
    i = 2
    while i + 6 <= len(payload):
        index = _u32_le(payload, i)
        length = payload[i + 4] | (payload[i + 5] << 8)
        end = min(len(payload), i + 6 + length)
        items: dict = {}
        j = i + 6
        while j + 3 <= end:
            cap_id = payload[j] | (payload[j + 1] << 8)
            cap_len = payload[j + 2]
            items[cap_id] = payload[j + 3 : min(end, j + 3 + cap_len)]
            j += 3 + cap_len
        result[index] = items
        i = end
    return result


def capability_range(value: bytes) -> tuple[int, int, int] | None:
    """(minimum, maximum, step) from a range capability, if present."""
    if len(value) < 8:
        return None
    lo = int.from_bytes(value[0:4], "little", signed=True)
    hi = int.from_bytes(value[4:8], "little", signed=True)
    step = int.from_bytes(value[8:12], "little", signed=True) if len(value) >= 12 else 1
    if lo > hi:
        return None
    return lo, hi, step
