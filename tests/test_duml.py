from __future__ import annotations

import unittest
from pathlib import Path

from dji_mic import duml

FIXTURES = Path(__file__).parent / "fixtures"


def load(name: str) -> bytes:
    return bytes.fromhex((FIXTURES / name).read_text(encoding="utf-8"))


def h(text: str) -> bytes:
    return bytes.fromhex(text.replace("\n", " ").replace(" ", ""))


class FramingTests(unittest.TestCase):
    def test_crc8_matches_known_header(self):
        self.assertEqual(duml.crc8(bytes([0x55, 0x16, 0x04])), 0xFC)

    def test_stereo_frame_matches_capture(self):
        frame = duml.set_param_frame(0xF936, duml.SETTING_CHANNEL_MODE, duml.CHANNEL_STEREO)
        self.assertEqual(
            frame,
            h("55 16 04 fc 02 5a 36 f9 40 5b 01 02 00 00 00 00 08 00 01 02 58 2b"),
        )

    def test_gain_frames_match_capture(self):
        self.assertEqual(
            duml.set_param_frame(0x0100, duml.SETTING_RECEIVER_GAIN, 6),
            h("55 16 04 fc 02 5a 00 01 40 5b 01 02 00 00 00 00 39 00 01 06 db 27"),
        )
        self.assertEqual(
            duml.set_param_frame(0x0101, duml.SETTING_RECEIVER_GAIN, -12),
            h("55 16 04 fc 02 5a 01 01 40 5b 01 02 00 00 00 00 39 00 01 f4 ac 8d"),
        )

    def test_decode_roundtrip(self):
        raw = load("5b_03_023.hex")
        frame = duml.Frame.decode(raw)
        self.assertIsNotNone(frame)
        self.assertEqual(frame.sender, duml.ADDRESS_RECEIVER)
        self.assertEqual(frame.receiver, duml.ADDRESS_APP)
        self.assertEqual(frame.command_set, 0x5B)
        self.assertEqual(frame.command_id, 0x03)
        self.assertEqual(frame.encode(), raw)

    def test_stream_parser_skips_iap2_noise_and_splits(self):
        parser = duml.StreamParser()
        raw = h("ff 55 02 00 ee 10 ff 55 02 00 ee 10") + load("5b_03_023.hex")
        frames = parser.feed(raw[:37]) + parser.feed(raw[37:])
        self.assertEqual([f.command_id for f in frames], [0x03])


class StatusTests(unittest.TestCase):
    def test_one_transmitter_live_frame(self):
        status = duml.MicStatus()
        self.assertTrue(duml.apply_frame(duml.Frame.decode(load("5b_03_086.hex")), status))
        rx = status.receiver
        self.assertEqual(rx.gain_db, 6)
        self.assertTrue(rx.noise_cancelling)
        self.assertEqual(rx.noise_level, 1)
        self.assertTrue(rx.auto_power_off)
        self.assertEqual(rx.channel_raw, duml.CHANNEL_MONO)
        self.assertEqual(rx.channel_name, "单声道")
        self.assertEqual(rx.connected, {1})
        self.assertTrue(rx.attached_over_usb)
        tx = status.transmitters[1]
        self.assertEqual(tx.battery_level, 1)
        self.assertFalse(tx.is_charging)
        self.assertTrue(tx.noise_cancelling)

    def test_two_transmitter_frame(self):
        frame = duml.Frame.decode(load("5b_03_086.hex"))
        payload = bytearray(frame.payload)
        payload[1:3] = (0x66).to_bytes(2, "little")
        # RX record starts at payload[3]; connected mask is record[0x1e].
        rx_record = 3
        payload[rx_record + 0x1E] = 0x03
        tx_record = bytes(payload[3 + 6 + 0x20 : 3 + 6 + 0x20 + 0x20])
        tx2 = bytearray(tx_record)
        tx2[1] = 0x02
        payload += tx2
        frame.payload = bytes(payload)
        status = duml.MicStatus()
        self.assertTrue(duml.apply_frame(duml.Frame.decode(frame.encode()), status))
        self.assertEqual(status.receiver.connected, {1, 2})
        self.assertIn(2, status.transmitters)

    def test_identity_and_level(self):
        status = duml.MicStatus()
        duml.apply_frame(duml.Frame.decode(load("5b_03_126.hex")), status)
        rx = status.receiver
        self.assertEqual(rx.identity.product_name, "DJI Mic Mini 2")
        self.assertEqual(rx.identity.firmware, "02.03.17.00")
        self.assertEqual(rx.identity.serial_number, "X" * 14)
        self.assertEqual(rx.identity.bluetooth_id, "XXXXXX")
        tx1 = status.transmitters[1]
        self.assertEqual(tx1.identity.product_name, "DJI Mic Mini")
        self.assertEqual(tx1.identity.firmware, "02.03.17.00")
        self.assertEqual(tx1.identity.serial_number, "X" * 14)
        self.assertEqual(tx1.identity.bluetooth_id, "XXXXXX")
        duml.apply_frame(duml.Frame.decode(load("5b_03_023.hex")), status)
        self.assertEqual(status.transmitters[1].meter_level, 0x00)

    def test_capability_parse(self):
        payload = h(
            "71 00 00 00 00 00 31 00 0d 00 01 01 06 00 0c f4 ff ff ff 0c 00 "
            "00 00 06 00 00 00 09 00 0c f4 ff ff ff 0c 00 00 00 01 00 00 00 "
            "11 00 08 c8 00 00 00 00 00 00 00 05 00 01 07 01 00 00 00 17 00 "
            "02 00 08 42 49 0b 00 00 00 00 00 03 00 01 03 04 00 01 05 12 00 "
            "01 01 02 00 00 00 17 00 02 00 08 42 49 0b 00 00 00 00 00 03 00 "
            "01 03 04 00 01 05 12 00 01 01"
        )
        caps = duml.parse_capabilities(payload)
        self.assertEqual(duml.capability_range(caps[0][6]), (-12, 12, 6))
        self.assertEqual(caps[0][5], b"\x07")


if __name__ == "__main__":
    unittest.main()
