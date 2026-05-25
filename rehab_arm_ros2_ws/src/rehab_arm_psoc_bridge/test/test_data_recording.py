from __future__ import annotations

import io
import json
import sys
import tempfile
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from rehab_arm_psoc_bridge.data_recording import (
    make_joint_state_payload,
    make_motor_state_payload,
    make_camera_keyframe_payload,
    make_default_session_id,
    make_jsonl_record,
    make_payload_record,
    make_session_metadata,
    load_jsonl_records,
    parse_message_payload,
    session_log_path,
    validate_jsonl_records,
    write_jsonl_record,
    sanitize_identifier,
    build_recording_manifest,
    build_sync_dry_run_plan,
    file_sha256,
    summarize_jsonl_records,
)


class DataRecordingTests(unittest.TestCase):
    def test_parse_json_payload(self) -> None:
        payload = parse_message_payload('{"state":"limited","motion_allowed":false}')

        self.assertEqual(payload['state'], 'limited')
        self.assertIs(payload['motion_allowed'], False)

    def test_parse_plain_text_payload_as_raw(self) -> None:
        payload = parse_message_payload('not-json')

        self.assertEqual(payload, {'raw': 'not-json'})

    def test_sanitize_identifier(self) -> None:
        self.assertEqual(sanitize_identifier(' rehab arm/alpha '), 'rehab_arm_alpha')
        self.assertEqual(sanitize_identifier(''), 'unknown')

    def test_make_default_session_id(self) -> None:
        session_id = make_default_session_id('rehab arm', 'nanopi/m5', now=0)

        self.assertEqual(session_id, 'rehab_arm__nanopi_m5__19700101T000000Z')

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
        self.assertEqual(record['schema_version'], 'rehab_arm_jsonl_v1')
        self.assertEqual(record['ts_unix'], 10.0)
        self.assertEqual(record['session_id'], 's1')
        self.assertEqual(record['device_id'], 'nanopi-m5')
        self.assertEqual(record['robot_id'], 'rehab-arm-alpha')
        self.assertEqual(record['software_version'], 'abc123')
        self.assertEqual(record['mode'], 'logging_only')
        self.assertEqual(record['source'], 'nanopi_ros_recorder')
        self.assertEqual(record['sync_status'], 'local_only')
        self.assertIn('/joint_states', record['topics'])
        self.assertIn('/rehab_arm/safety_state', record['topics'])
        self.assertIn('/rehab_arm/motor_state', record['optional_topics'])
        self.assertIn('/rehab_arm/camera_keyframe', record['optional_topics'])
        self.assertIs(record['motion_allowed_expected'], False)

    def test_make_motor_state_payload(self) -> None:
        payload = make_motor_state_payload(
            motors=[
                {
                    'motor_id': 4,
                    'joint_name': 'shoulder_lift_joint',
                    'protocol': 'private_mit',
                    'position': 0.1,
                    'velocity': 0.2,
                    'current': 0.3,
                    'temperature': 35.0,
                    'fault': False,
                },
            ],
            robot_id='rehab-arm-alpha',
            device_id='nanopi-m5',
            now=12.5,
        )

        self.assertEqual(payload['schema_version'], 'rehab_arm_motor_state_v1')
        self.assertEqual(payload['ts_unix'], 12.5)
        self.assertEqual(payload['motors'][0]['motor_id'], 4)
        self.assertEqual(payload['control_boundary'], 'telemetry_only_not_motor_command')

    def test_make_camera_keyframe_payload(self) -> None:
        payload = make_camera_keyframe_payload(
            camera_id='front_rgb',
            image_path='/home/pi/frames/f1.jpg',
            sha256='abc123',
            robot_id='rehab-arm-alpha',
            device_id='nanopi-m5',
            width=640,
            height=480,
            now=13.5,
            scene_summary='cup visible',
            detection_summary={'objects': ['cup']},
        )

        self.assertEqual(payload['schema_version'], 'rehab_arm_camera_keyframe_v1')
        self.assertEqual(payload['camera_id'], 'front_rgb')
        self.assertEqual(payload['width'], 640)
        self.assertEqual(payload['detection_summary'], {'objects': ['cup']})
        self.assertEqual(payload['control_boundary'], 'perception_data_only_not_motor_command')

    def test_write_jsonl_record(self) -> None:
        handle = io.StringIO()
        write_jsonl_record(handle, {'ts_unix': 1.0, 'topic': '/x', 'payload': {'a': 1}})

        lines = handle.getvalue().splitlines()
        self.assertEqual(len(lines), 1)
        self.assertEqual(json.loads(lines[0])['payload'], {'a': 1})

    def test_load_jsonl_records(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / 'session.jsonl'
            path.write_text('{"record_type":"session_metadata"}\n{"record_type":"topic_message"}\n')

            records = load_jsonl_records(path)

        self.assertEqual(len(records), 2)
        self.assertEqual(records[0]['record_type'], 'session_metadata')

    def test_validate_jsonl_records_ok(self) -> None:
        records = [
            make_session_metadata('s1', 'nanopi', 'arm', 'dev', 'logging_only', now=1.0),
            make_payload_record('/joint_states', {}, now=2.0),
            make_payload_record('/rehab_arm/safety_state', {}, now=3.0),
            make_payload_record('/rehab_arm/sensor_state', {}, now=4.0),
        ]

        summary = validate_jsonl_records(records)

        self.assertIs(summary['ok'], True)
        self.assertEqual(summary['metadata_count'], 1)
        self.assertEqual(summary['missing_topics'], [])

    def test_validate_jsonl_records_reports_missing_topic(self) -> None:
        records = [
            make_session_metadata('s1', 'nanopi', 'arm', 'dev', 'logging_only', now=1.0),
            make_payload_record('/joint_states', {}, now=2.0),
        ]

        summary = validate_jsonl_records(records)

        self.assertIs(summary['ok'], False)
        self.assertIn('/rehab_arm/safety_state', summary['missing_topics'])

    def test_build_recording_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / 's1.jsonl'
            records = [
                make_session_metadata('s1', 'nanopi', 'arm', 'dev', 'logging_only', now=1.0),
                make_payload_record('/joint_states', {}, now=2.0),
                make_payload_record('/rehab_arm/safety_state', {}, now=3.0),
                make_payload_record('/rehab_arm/sensor_state', {}, now=4.0),
            ]
            with path.open('w', encoding='utf-8') as handle:
                for record in records:
                    write_jsonl_record(handle, record)

            manifest = build_recording_manifest(tmpdir)

        self.assertEqual(manifest['schema_version'], 'rehab_arm_manifest_v1')
        self.assertEqual(manifest['session_count'], 1)
        session = manifest['sessions'][0]
        self.assertIs(session['ok'], True)
        self.assertEqual(session['session_id'], 's1')
        self.assertEqual(session['sync_status'], 'local_only')
        self.assertIn('/joint_states', session['topics'])
        self.assertNotIn('summary', session)

    def test_build_recording_manifest_can_include_summary(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / 's1.jsonl'
            records = [
                make_session_metadata('s1', 'nanopi', 'arm', 'dev', 'simulation_data_collection', now=1.0),
                make_payload_record(
                    '/joint_states',
                    make_joint_state_payload(['j0'], [0.0], [0.0], [0.0], 1, 0),
                    now=2.0,
                ),
                make_payload_record(
                    '/joint_states',
                    make_joint_state_payload(['j0'], [0.5], [0.0], [0.0], 2, 0),
                    now=3.0,
                ),
                make_payload_record('/rehab_arm/safety_state', {'state': 'ok'}, now=4.0),
                make_payload_record('/rehab_arm/sensor_state', {'source': 'sim'}, now=5.0),
            ]
            with path.open('w', encoding='utf-8') as handle:
                for record in records:
                    write_jsonl_record(handle, record)

            manifest = build_recording_manifest(tmpdir, include_summary=True)

        session = manifest['sessions'][0]
        self.assertIn('summary', session)
        self.assertEqual(session['summary']['schema_version'], 'rehab_arm_recording_summary_v1')
        self.assertEqual(session['summary']['moving_joint_count'], 1)
        self.assertEqual(session['summary']['topic_counts']['/joint_states'], 2)

    def test_summarize_jsonl_records(self) -> None:
        records = [
            make_session_metadata('s1', 'nanopi', 'arm', 'dev', 'simulation_data_collection', now=1.0),
            make_payload_record(
                '/joint_states',
                make_joint_state_payload(['j0'], [0.0], [0.0], [0.0], 1, 0),
                now=2.0,
            ),
            make_payload_record(
                '/joint_states',
                make_joint_state_payload(['j0'], [0.5], [0.0], [0.0], 2, 0),
                now=3.0,
            ),
            make_payload_record(
                '/rehab_arm/motor_state',
                make_motor_state_payload(
                    [{'joint_name': 'j0', 'position': 0.5}],
                    robot_id='arm',
                    device_id='nanopi',
                    now=3.0,
                ),
                now=3.0,
            ),
            make_payload_record('/rehab_arm/safety_state', {'state': 'ok', 'motion_allowed': False}, now=4.0),
            make_payload_record('/rehab_arm/sensor_state', {'source': 'sim'}, now=5.0),
        ]

        summary = summarize_jsonl_records(records)

        self.assertEqual(summary['schema_version'], 'rehab_arm_recording_summary_v1')
        self.assertEqual(summary['topic_counts']['/joint_states'], 2)
        self.assertEqual(summary['joint_position_ranges']['j0']['min'], 0.0)
        self.assertEqual(summary['joint_position_ranges']['j0']['max'], 0.5)
        self.assertEqual(summary['moving_joint_count'], 1)
        self.assertEqual(summary['motor_entry_count_min'], 1)
        self.assertEqual(summary['motor_entry_count_max'], 1)
        self.assertEqual(summary['safety_states']['ok'], 1)
        self.assertEqual(summary['motion_allowed_counts']['false'], 1)

    def test_file_sha256(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / 'payload.txt'
            path.write_bytes(b'rehab-arm\n')

            digest = file_sha256(path)

        self.assertEqual(
            digest,
            'a7ec0bad4217df635954642dea88bb1b7df2ba42c6a93607a2c95290986c8be6',
        )

    def test_build_sync_dry_run_plan(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / 's1.jsonl'
            path.write_text('{"record_type":"session_metadata"}\n', encoding='utf-8')
            manifest = {
                'schema_version': 'rehab_arm_manifest_v1',
                'sessions': [
                    {
                        'ok': True,
                        'path': str(path),
                        'file_name': 's1.jsonl',
                        'session_id': 's1',
                        'device_id': 'nanopi-m5',
                        'robot_id': 'rehab-arm-alpha',
                        'software_version': 'dev',
                        'record_count': 1,
                    },
                ],
            }

            plan = build_sync_dry_run_plan(manifest, 'http://server.local/api/')

        self.assertEqual(plan['schema_version'], 'rehab_arm_sync_dry_run_v1')
        self.assertEqual(plan['base_url'], 'http://server.local/api')
        self.assertEqual(plan['request_count'], 4)
        urls = [request['url'] for request in plan['requests']]
        self.assertIn('http://server.local/api/devices/register', urls)
        self.assertIn('http://server.local/api/sessions/manifest', urls)
        self.assertIn('http://server.local/api/sessions/s1/files', urls)
        self.assertIn('http://server.local/api/sessions/s1/sync-status', urls)

    def test_build_sync_dry_run_plan_skips_incomplete_sessions(self) -> None:
        manifest = {
            'schema_version': 'rehab_arm_manifest_v1',
            'sessions': [
                {
                    'ok': False,
                    'file_name': 'bad.jsonl',
                    'session_id': 'bad',
                    'errors': ['missing session_metadata'],
                },
            ],
        }

        plan = build_sync_dry_run_plan(manifest, 'http://server.local/api')

        self.assertEqual(plan['request_count'], 1)
        self.assertEqual(plan['requests'][0]['url'], 'http://server.local/api/sessions/manifest')
        self.assertEqual(plan['skipped_sessions'][0]['file_name'], 'bad.jsonl')

    def test_session_log_path_sanitizes_session_id(self) -> None:
        path = session_log_path('logs', 'session 1/unsafe')

        self.assertEqual(path.as_posix(), 'logs/session_1_unsafe.jsonl')


if __name__ == '__main__':
    unittest.main()
