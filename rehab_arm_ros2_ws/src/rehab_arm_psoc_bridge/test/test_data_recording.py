from __future__ import annotations

import io
import json
import sys
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from rehab_arm_psoc_bridge.data_recording import (
    make_joint_state_payload,
    make_jsonl_record,
    make_payload_record,
    make_session_metadata,
    parse_message_payload,
    session_log_path,
    write_jsonl_record,
)


class DataRecordingTests(unittest.TestCase):
    def test_parse_json_payload(self) -> None:
        payload = parse_message_payload('{"state":"limited","motion_allowed":false}')

        self.assertEqual(payload['state'], 'limited')
        self.assertIs(payload['motion_allowed'], False)

    def test_parse_plain_text_payload_as_raw(self) -> None:
        payload = parse_message_payload('not-json')

        self.assertEqual(payload, {'raw': 'not-json'})

    def test_make_jsonl_record(self) -> None:
        record = make_jsonl_record('/rehab_arm/safety_state', '{"state":"ok"}', now=123.5)

        self.assertEqual(record['record_type'], 'topic_message')
        self.assertEqual(record['ts_unix'], 123.5)
        self.assertEqual(record['topic'], '/rehab_arm/safety_state')
        self.assertEqual(record['payload'], {'state': 'ok'})

    def test_make_payload_record(self) -> None:
        record = make_payload_record('/joint_states', {'name': ['j0']}, now=124.5)

        self.assertEqual(record['record_type'], 'topic_message')
        self.assertEqual(record['ts_unix'], 124.5)
        self.assertEqual(record['topic'], '/joint_states')
        self.assertEqual(record['payload'], {'name': ['j0']})

    def test_make_joint_state_payload(self) -> None:
        payload = make_joint_state_payload(
            names=['shoulder_lift_joint'],
            positions=[0.1],
            velocities=[0.2],
            efforts=[0.3],
            stamp_sec=12,
            stamp_nanosec=34,
        )

        self.assertEqual(payload['stamp'], {'sec': 12, 'nanosec': 34})
        self.assertEqual(payload['name'], ['shoulder_lift_joint'])
        self.assertEqual(payload['position'], [0.1])
        self.assertEqual(payload['velocity'], [0.2])
        self.assertEqual(payload['effort'], [0.3])

    def test_make_session_metadata(self) -> None:
        record = make_session_metadata(
            session_id='s1',
            device_id='nanopi-m5',
            robot_id='rehab-arm-alpha',
            software_version='abc123',
            mode='logging_only',
            now=10.0,
        )

        self.assertEqual(record['record_type'], 'session_metadata')
        self.assertEqual(record['ts_unix'], 10.0)
        self.assertEqual(record['session_id'], 's1')
        self.assertEqual(record['device_id'], 'nanopi-m5')
        self.assertEqual(record['robot_id'], 'rehab-arm-alpha')
        self.assertEqual(record['software_version'], 'abc123')
        self.assertEqual(record['mode'], 'logging_only')
        self.assertIn('/joint_states', record['topics'])
        self.assertIn('/rehab_arm/safety_state', record['topics'])
        self.assertIs(record['motion_allowed_expected'], False)

    def test_write_jsonl_record(self) -> None:
        handle = io.StringIO()
        write_jsonl_record(handle, {'ts_unix': 1.0, 'topic': '/x', 'payload': {'a': 1}})

        lines = handle.getvalue().splitlines()
        self.assertEqual(len(lines), 1)
        self.assertEqual(json.loads(lines[0])['payload'], {'a': 1})

    def test_session_log_path_sanitizes_session_id(self) -> None:
        path = session_log_path('logs', 'session 1/unsafe')

        self.assertEqual(path.as_posix(), 'logs/session_1_unsafe.jsonl')


if __name__ == '__main__':
    unittest.main()
