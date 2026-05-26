from __future__ import annotations

import io
import json
import subprocess
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
    required_topics_for_profile,
    write_jsonl_record,
    sanitize_identifier,
    build_recording_manifest,
    build_recording_quality_report,
    build_annotation_queue,
    make_annotation_template_rows,
    validate_annotation_rows,
    build_replay_plan,
    build_dataset_index,
    build_sync_dry_run_plan,
    file_sha256,
    summarize_jsonl_records,
    make_joint_state_csv_rows,
    make_motor_state_csv_rows,
    write_csv_rows,
    JOINT_STATE_CSV_FIELDS,
)
from rehab_arm_psoc_bridge.jsonl_replay_node import parse_topic_list, payload_to_json_text


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

    def test_required_topics_for_profile_returns_robotics_contract_presets(self) -> None:
        self.assertEqual(
            required_topics_for_profile('simulation_minimum'),
            ['/joint_states', '/rehab_arm/safety_state', '/rehab_arm/sensor_state'],
        )
        self.assertEqual(
            required_topics_for_profile('hardware_telemetry'),
            ['/joint_states', '/rehab_arm/safety_state', '/rehab_arm/sensor_state', '/rehab_arm/motor_state'],
        )
        self.assertEqual(
            required_topics_for_profile('perception_vla'),
            ['/joint_states', '/rehab_arm/safety_state', '/rehab_arm/sensor_state', '/rehab_arm/camera_keyframe'],
        )

    def test_required_topics_for_profile_rejects_unknown_profile(self) -> None:
        with self.assertRaises(ValueError):
            required_topics_for_profile('unknown')

    def test_check_recording_cli_topic_profile_reports_missing_motor_state(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / 's1.jsonl'
            records = [
                make_session_metadata('s1', 'nanopi', 'arm', 'dev', 'simulation_data_collection', now=1.0),
                make_payload_record('/joint_states', {}, now=2.0),
                make_payload_record('/rehab_arm/safety_state', {'motion_allowed': False}, now=3.0),
                make_payload_record('/rehab_arm/sensor_state', {}, now=4.0),
            ]
            with path.open('w', encoding='utf-8') as handle:
                for record in records:
                    write_jsonl_record(handle, record)

            result = subprocess.run(
                [
                    sys.executable,
                    str(Path(__file__).resolve().parents[1] / 'rehab_arm_psoc_bridge' / 'check_recording.py'),
                    str(path),
                    '--topic-profile',
                    'hardware_telemetry',
                ],
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )

        self.assertEqual(result.returncode, 1)
        payload = json.loads(result.stdout)
        self.assertEqual(payload['topic_profile'], 'hardware_telemetry')
        self.assertIn('/rehab_arm/motor_state', payload['missing_topics'])

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

    def test_build_recording_manifest_can_include_quality_report(self) -> None:
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
            with path.open('w', encoding='utf-8') as handle:
                for record in records:
                    write_jsonl_record(handle, record)

            manifest = build_recording_manifest(
                tmpdir,
                include_quality_report=True,
                min_joint_messages=2,
                min_moving_joints=1,
                require_motor_state=True,
                min_motor_entry_count=1,
            )

        session = manifest['sessions'][0]
        self.assertIn('quality_report', session)
        self.assertEqual(session['quality_report']['schema_version'], 'rehab_arm_recording_quality_v1')
        self.assertIs(session['quality_report']['ok'], True)
        self.assertEqual(session['quality_report']['criteria']['min_moving_joints'], 1)
        self.assertEqual(session['quality_report']['summary']['moving_joint_count'], 1)

    def test_build_recording_manifest_quality_report_accepts_topic_profile(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / 's1.jsonl'
            records = [
                make_session_metadata('s1', 'nanopi', 'arm', 'dev', 'simulation_data_collection', now=1.0),
                make_payload_record('/joint_states', {}, now=2.0),
                make_payload_record('/rehab_arm/safety_state', {'motion_allowed': False}, now=3.0),
                make_payload_record('/rehab_arm/sensor_state', {}, now=4.0),
            ]
            with path.open('w', encoding='utf-8') as handle:
                for record in records:
                    write_jsonl_record(handle, record)

            manifest = build_recording_manifest(
                tmpdir,
                include_quality_report=True,
                topic_profile='hardware_telemetry',
            )

        report = manifest['sessions'][0]['quality_report']
        self.assertIs(report['ok'], False)
        self.assertEqual(report['topic_profile'], 'hardware_telemetry')
        self.assertIn('/rehab_arm/motor_state', report['schema_check']['missing_topics'])

    def test_build_manifest_cli_quality_report_accepts_topic_profile(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / 's1.jsonl'
            records = [
                make_session_metadata('s1', 'nanopi', 'arm', 'dev', 'simulation_data_collection', now=1.0),
                make_payload_record('/joint_states', {}, now=2.0),
                make_payload_record('/rehab_arm/safety_state', {'motion_allowed': False}, now=3.0),
                make_payload_record('/rehab_arm/sensor_state', {}, now=4.0),
            ]
            with path.open('w', encoding='utf-8') as handle:
                for record in records:
                    write_jsonl_record(handle, record)

            result = subprocess.run(
                [
                    sys.executable,
                    str(Path(__file__).resolve().parents[1] / 'rehab_arm_psoc_bridge' / 'build_manifest.py'),
                    tmpdir,
                    '--include-quality-report',
                    '--topic-profile',
                    'hardware_telemetry',
                ],
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )

        self.assertEqual(result.returncode, 0)
        manifest = json.loads(result.stdout)
        report = manifest['sessions'][0]['quality_report']
        self.assertEqual(report['topic_profile'], 'hardware_telemetry')
        self.assertIn('/rehab_arm/motor_state', report['schema_check']['missing_topics'])

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

    def test_build_replay_plan_orders_topic_messages_by_record_time(self) -> None:
        records = [
            make_session_metadata('s1', 'nanopi', 'arm', 'dev', 'simulation_data_collection', now=1.0),
            make_payload_record('/rehab_arm/safety_state', {'state': 'ok'}, now=12.0),
            make_payload_record('/joint_states', {'name': ['j0'], 'position': [0.1]}, now=10.0),
            make_payload_record('/rehab_arm/motor_state', {'motors': []}, now=11.5),
        ]

        plan = build_replay_plan(records)

        self.assertEqual(plan['schema_version'], 'rehab_arm_replay_plan_v1')
        self.assertEqual(plan['event_count'], 3)
        self.assertEqual(plan['duration_sec'], 2.0)
        self.assertEqual(
            [event['topic'] for event in plan['events']],
            ['/joint_states', '/rehab_arm/motor_state', '/rehab_arm/safety_state'],
        )
        self.assertEqual(plan['events'][0]['relative_time_sec'], 0.0)
        self.assertEqual(plan['events'][1]['relative_time_sec'], 1.5)
        self.assertEqual(plan['events'][2]['sequence_index'], 2)
        self.assertEqual(plan['topic_counts']['/joint_states'], 1)
        self.assertEqual(plan['control_boundary'], 'replay_plan_only_not_motion_permission')

    def test_build_replay_plan_can_filter_topics_and_omit_payloads(self) -> None:
        records = [
            make_payload_record('/joint_states', {'name': ['j0']}, now=10.0),
            make_payload_record('/rehab_arm/motor_state', {'motors': []}, now=11.0),
        ]

        plan = build_replay_plan(records, topics=['/joint_states'], include_payload=False)

        self.assertEqual(plan['event_count'], 1)
        self.assertEqual(plan['topics'], ['/joint_states'])
        self.assertNotIn('payload', plan['events'][0])

    def test_build_replay_plan_cli_writes_filtered_plan(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / 'session.jsonl'
            output = Path(tmpdir) / 'replay_plan.json'
            records = [
                make_session_metadata('s1', 'nanopi', 'arm', 'dev', 'simulation_data_collection', now=1.0),
                make_payload_record('/joint_states', {'name': ['j0']}, now=10.0),
                make_payload_record('/rehab_arm/safety_state', {'state': 'ok'}, now=11.0),
            ]
            with path.open('w', encoding='utf-8') as handle:
                for record in records:
                    write_jsonl_record(handle, record)

            result = subprocess.run(
                [
                    sys.executable,
                    str(Path(__file__).resolve().parents[1] / 'rehab_arm_psoc_bridge' / 'build_replay_plan.py'),
                    str(path),
                    '--topic',
                    '/joint_states',
                    '--no-payload',
                    '--output',
                    str(output),
                ],
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )
            saved = json.loads(output.read_text(encoding='utf-8'))

        self.assertEqual(result.returncode, 0)
        payload = json.loads(result.stdout)
        self.assertEqual(payload['schema_version'], 'rehab_arm_replay_plan_v1')
        self.assertEqual(payload['event_count'], 1)
        self.assertEqual(saved['events'][0]['topic'], '/joint_states')
        self.assertNotIn('payload', saved['events'][0])

    def test_jsonl_replay_helpers_parse_topics_and_payload_text(self) -> None:
        self.assertIn('/joint_states', parse_topic_list(''))
        self.assertEqual(parse_topic_list('/joint_states, /rehab_arm/motor_state'), [
            '/joint_states',
            '/rehab_arm/motor_state',
        ])
        self.assertEqual(payload_to_json_text('already-json'), 'already-json')
        self.assertEqual(payload_to_json_text({'state': 'ok'}), '{"state":"ok"}')

    def test_build_recording_quality_report_passes_dynamic_session(self) -> None:
        records = [
            make_session_metadata('s1', 'nanopi', 'arm', 'dev', 'simulation_data_collection', now=1.0),
            make_payload_record(
                '/joint_states',
                make_joint_state_payload(['j0', 'j1'], [0.0, 0.0], [0.0, 0.0], [0.0, 0.0], 1, 0),
                now=2.0,
            ),
            make_payload_record(
                '/joint_states',
                make_joint_state_payload(['j0', 'j1'], [0.5, 0.2], [0.0, 0.0], [0.0, 0.0], 2, 0),
                now=3.0,
            ),
            make_payload_record(
                '/rehab_arm/motor_state',
                make_motor_state_payload(
                    [
                        {'joint_name': 'j0', 'position': 0.5},
                        {'joint_name': 'j1', 'position': 0.2},
                    ],
                    robot_id='arm',
                    device_id='nanopi',
                    now=3.0,
                ),
                now=3.0,
            ),
            make_payload_record('/rehab_arm/safety_state', {'state': 'ok', 'motion_allowed': False}, now=4.0),
            make_payload_record('/rehab_arm/sensor_state', {'source': 'sim'}, now=5.0),
        ]

        report = build_recording_quality_report(
            records,
            min_joint_messages=2,
            min_moving_joints=2,
            require_motor_state=True,
            min_motor_entry_count=2,
        )

        self.assertIs(report['ok'], True)
        self.assertEqual(report['schema_version'], 'rehab_arm_recording_quality_v1')
        self.assertEqual(report['summary']['moving_joint_count'], 2)
        self.assertEqual(report['summary']['motor_entry_count_min'], 2)

    def test_build_recording_quality_report_fails_strict_thresholds(self) -> None:
        records = [
            make_session_metadata('s1', 'nanopi', 'arm', 'dev', 'logging_only', now=1.0),
            make_payload_record(
                '/joint_states',
                make_joint_state_payload(['j0'], [0.0], [0.0], [0.0], 1, 0),
                now=2.0,
            ),
            make_payload_record('/rehab_arm/safety_state', {'state': 'ok', 'motion_allowed': True}, now=3.0),
            make_payload_record('/rehab_arm/sensor_state', {'source': 'sim'}, now=4.0),
        ]

        report = build_recording_quality_report(
            records,
            min_joint_messages=2,
            min_moving_joints=1,
            require_motor_state=True,
            min_motor_entry_count=1,
        )

        self.assertIs(report['ok'], False)
        joined_errors = '\n'.join(report['errors'])
        self.assertIn('joint state message count 1 below required 2', joined_errors)
        self.assertIn('moving joint count 0 below required 1', joined_errors)
        self.assertIn('missing required /rehab_arm/motor_state messages', joined_errors)
        self.assertIn('motion_allowed true appeared 1 times', joined_errors)

    def test_build_recording_quality_report_applies_topic_profile(self) -> None:
        records = [
            make_session_metadata('s1', 'nanopi', 'arm', 'dev', 'simulation_data_collection', now=1.0),
            make_payload_record(
                '/joint_states',
                make_joint_state_payload(['j0'], [0.0], [0.0], [0.0], 1, 0),
                now=2.0,
            ),
            make_payload_record('/rehab_arm/safety_state', {'state': 'ok', 'motion_allowed': False}, now=3.0),
            make_payload_record('/rehab_arm/sensor_state', {'source': 'sim'}, now=4.0),
        ]

        report = build_recording_quality_report(
            records,
            topic_profile='hardware_telemetry',
        )

        self.assertIs(report['ok'], False)
        self.assertEqual(report['topic_profile'], 'hardware_telemetry')
        self.assertIn('/rehab_arm/motor_state', report['required_topics'])
        self.assertIn('/rehab_arm/motor_state', report['schema_check']['missing_topics'])

    def test_build_recording_quality_report_checks_camera_keyframe_count(self) -> None:
        records = [
            make_session_metadata('s1', 'nanopi', 'arm', 'dev', 'perception_data_collection', now=1.0),
            make_payload_record('/joint_states', {}, now=2.0),
            make_payload_record('/rehab_arm/safety_state', {'state': 'ok', 'motion_allowed': False}, now=3.0),
            make_payload_record('/rehab_arm/sensor_state', {'source': 'sim'}, now=4.0),
            make_payload_record(
                '/rehab_arm/camera_keyframe',
                make_camera_keyframe_payload(
                    camera_id='front_rgb',
                    image_path='/tmp/frame_001.jpg',
                    sha256='abc123',
                    robot_id='arm',
                    device_id='nanopi',
                    now=5.0,
                ),
                now=5.0,
            ),
        ]

        report = build_recording_quality_report(
            records,
            topic_profile='perception_vla',
            min_camera_keyframes=2,
        )

        self.assertIs(report['ok'], False)
        self.assertEqual(report['criteria']['min_camera_keyframes'], 2)
        self.assertIn('camera keyframe count 1 below required 2', '\n'.join(report['errors']))

    def test_build_recording_quality_report_checks_camera_files_when_required(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            image_path = Path(tmpdir) / 'frame_001.jpg'
            image_path.write_bytes(b'valid-frame\n')
            missing_path = Path(tmpdir) / 'missing.jpg'
            records = [
                make_session_metadata('s1', 'nanopi', 'arm', 'dev', 'perception_data_collection', now=1.0),
                make_payload_record('/joint_states', {}, now=2.0),
                make_payload_record('/rehab_arm/safety_state', {'state': 'ok', 'motion_allowed': False}, now=3.0),
                make_payload_record('/rehab_arm/sensor_state', {'source': 'sim'}, now=4.0),
                make_payload_record(
                    '/rehab_arm/camera_keyframe',
                    make_camera_keyframe_payload(
                        camera_id='front_rgb',
                        image_path=str(image_path),
                        sha256=file_sha256(image_path),
                        robot_id='arm',
                        device_id='nanopi',
                        now=5.0,
                    ),
                    now=5.0,
                ),
                make_payload_record(
                    '/rehab_arm/camera_keyframe',
                    make_camera_keyframe_payload(
                        camera_id='front_rgb',
                        image_path=str(missing_path),
                        sha256='not-present',
                        robot_id='arm',
                        device_id='nanopi',
                        now=6.0,
                    ),
                    now=6.0,
                ),
                make_payload_record(
                    '/rehab_arm/camera_keyframe',
                    make_camera_keyframe_payload(
                        camera_id='front_rgb',
                        image_path=str(image_path),
                        sha256='wrong-sha',
                        robot_id='arm',
                        device_id='nanopi',
                        now=7.0,
                    ),
                    now=7.0,
                ),
            ]

            report = build_recording_quality_report(
                records,
                topic_profile='perception_vla',
                require_camera_files=True,
            )

        self.assertIs(report['ok'], False)
        self.assertEqual(report['criteria']['require_camera_files'], True)
        self.assertEqual(report['camera_file_check']['checked_count'], 3)
        self.assertEqual(report['camera_file_check']['ok_count'], 1)
        self.assertEqual(report['camera_file_check']['missing_count'], 1)
        self.assertEqual(report['camera_file_check']['hash_mismatch_count'], 1)

    def test_validate_recording_quality_cli_topic_profile_reports_missing_motor_state(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / 's1.jsonl'
            records = [
                make_session_metadata('s1', 'nanopi', 'arm', 'dev', 'simulation_data_collection', now=1.0),
                make_payload_record(
                    '/joint_states',
                    make_joint_state_payload(['j0'], [0.0], [0.0], [0.0], 1, 0),
                    now=2.0,
                ),
                make_payload_record('/rehab_arm/safety_state', {'state': 'ok', 'motion_allowed': False}, now=3.0),
                make_payload_record('/rehab_arm/sensor_state', {'source': 'sim'}, now=4.0),
            ]
            with path.open('w', encoding='utf-8') as handle:
                for record in records:
                    write_jsonl_record(handle, record)

            result = subprocess.run(
                [
                    sys.executable,
                    str(Path(__file__).resolve().parents[1] / 'rehab_arm_psoc_bridge' / 'validate_recording_quality.py'),
                    str(path),
                    '--topic-profile',
                    'hardware_telemetry',
                ],
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )

        self.assertEqual(result.returncode, 1)
        payload = json.loads(result.stdout)
        self.assertEqual(payload['topic_profile'], 'hardware_telemetry')
        self.assertIn('/rehab_arm/motor_state', payload['schema_check']['missing_topics'])

    def test_validate_recording_quality_cli_checks_camera_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            image_path = Path(tmpdir) / 'frame_001.jpg'
            image_path.write_bytes(b'frame\n')
            path = Path(tmpdir) / 's1.jsonl'
            records = [
                make_session_metadata('s1', 'nanopi', 'arm', 'dev', 'perception_data_collection', now=1.0),
                make_payload_record('/joint_states', {}, now=2.0),
                make_payload_record('/rehab_arm/safety_state', {'state': 'ok', 'motion_allowed': False}, now=3.0),
                make_payload_record('/rehab_arm/sensor_state', {'source': 'sim'}, now=4.0),
                make_payload_record(
                    '/rehab_arm/camera_keyframe',
                    make_camera_keyframe_payload(
                        camera_id='front_rgb',
                        image_path='frame_001.jpg',
                        sha256=file_sha256(image_path),
                        robot_id='arm',
                        device_id='nanopi',
                        now=5.0,
                    ),
                    now=5.0,
                ),
            ]
            with path.open('w', encoding='utf-8') as handle:
                for record in records:
                    write_jsonl_record(handle, record)

            result = subprocess.run(
                [
                    sys.executable,
                    str(Path(__file__).resolve().parents[1] / 'rehab_arm_psoc_bridge' / 'validate_recording_quality.py'),
                    str(path),
                    '--topic-profile',
                    'perception_vla',
                    '--min-camera-keyframes',
                    '1',
                    '--require-camera-files',
                ],
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )

        self.assertEqual(result.returncode, 0)
        payload = json.loads(result.stdout)
        self.assertEqual(payload['camera_file_check']['checked_count'], 1)
        self.assertEqual(payload['camera_file_check']['ok_count'], 1)

    def test_make_csv_rows_for_joint_and_motor_states(self) -> None:
        records = [
            make_payload_record(
                '/joint_states',
                make_joint_state_payload(['j0'], [0.5], [0.1], [0.2], 2, 3),
                now=10.0,
            ),
            make_payload_record(
                '/rehab_arm/motor_state',
                make_motor_state_payload(
                    [{'joint_name': 'j0', 'motor_id': 4, 'protocol': 'sim', 'position': 0.5}],
                    robot_id='arm',
                    device_id='nanopi',
                    now=10.0,
                    source='sim_bridge',
                ),
                now=10.0,
            ),
        ]

        joint_rows = make_joint_state_csv_rows(records)
        motor_rows = make_motor_state_csv_rows(records)

        self.assertEqual(joint_rows[0]['joint_name'], 'j0')
        self.assertEqual(joint_rows[0]['position'], 0.5)
        self.assertEqual(joint_rows[0]['stamp_sec'], 2)
        self.assertEqual(motor_rows[0]['joint_name'], 'j0')
        self.assertEqual(motor_rows[0]['motor_id'], 4)
        self.assertEqual(motor_rows[0]['source'], 'sim_bridge')

    def test_write_csv_rows(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / 'joint_states.csv'
            write_csv_rows(
                path,
                [{'ts_unix': 1.0, 'joint_name': 'j0', 'position': 0.5}],
                JOINT_STATE_CSV_FIELDS,
            )

            text = path.read_text(encoding='utf-8')

        self.assertIn('ts_unix,stamp_sec,stamp_nanosec,joint_name,position,velocity,effort', text)
        self.assertIn('1.0,,,j0,0.5,,', text)

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

    def test_build_sync_dry_run_plan_preserves_manifest_summary(self) -> None:
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
                        'summary': {
                            'schema_version': 'rehab_arm_recording_summary_v1',
                            'moving_joint_count': 5,
                        },
                    },
                ],
            }

            plan = build_sync_dry_run_plan(manifest, 'http://server.local/api')

        manifest_request = next(
            request for request in plan['requests']
            if request['url'] == 'http://server.local/api/sessions/manifest'
        )
        posted_manifest = manifest_request['json']['manifest']
        self.assertEqual(
            posted_manifest['sessions'][0]['summary']['schema_version'],
            'rehab_arm_recording_summary_v1',
        )
        self.assertEqual(posted_manifest['sessions'][0]['summary']['moving_joint_count'], 5)

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

    def test_build_annotation_queue_keeps_only_quality_ready_sessions(self) -> None:
        manifest = {
            'schema_version': 'rehab_arm_manifest_v1',
            'sessions': [
                {
                    'ok': True,
                    'path': '/logs/good.jsonl',
                    'file_name': 'good.jsonl',
                    'session_id': 'good',
                    'device_id': 'nanopi',
                    'robot_id': 'arm',
                    'topics': ['/joint_states', '/rehab_arm/camera_keyframe'],
                    'quality_report': {
                        'ok': True,
                        'topic_profile': 'perception_vla',
                        'summary': {'topic_counts': {'/rehab_arm/camera_keyframe': 12}},
                    },
                },
                {
                    'ok': True,
                    'file_name': 'bad_quality.jsonl',
                    'session_id': 'bad_quality',
                    'quality_report': {
                        'ok': False,
                        'errors': ['camera keyframe count 1 below required 10'],
                    },
                },
                {
                    'ok': False,
                    'file_name': 'bad_schema.jsonl',
                    'session_id': 'bad_schema',
                    'errors': ['missing session_metadata'],
                },
            ],
        }

        queue = build_annotation_queue(manifest)

        self.assertEqual(queue['schema_version'], 'rehab_arm_annotation_queue_v1')
        self.assertEqual(queue['ready_count'], 1)
        self.assertEqual(queue['skipped_count'], 2)
        self.assertEqual(queue['items'][0]['session_id'], 'good')
        self.assertEqual(queue['items'][0]['topic_profile'], 'perception_vla')
        self.assertEqual(queue['items'][0]['recommended_labels'], ['task_phase', 'object_state', 'assistance_quality'])
        self.assertEqual(queue['skipped_sessions'][0]['session_id'], 'bad_quality')
        self.assertIn('quality_report.ok is false', queue['skipped_sessions'][0]['reasons'])

    def test_build_annotation_queue_cli_outputs_ready_sessions(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            manifest_path = Path(tmpdir) / 'manifest_with_quality.json'
            manifest_path.write_text(json.dumps({
                'schema_version': 'rehab_arm_manifest_v1',
                'sessions': [
                    {
                        'ok': True,
                        'file_name': 'good.jsonl',
                        'session_id': 'good',
                        'device_id': 'nanopi',
                        'robot_id': 'arm',
                        'quality_report': {'ok': True, 'topic_profile': 'hardware_telemetry'},
                    },
                    {
                        'ok': True,
                        'file_name': 'bad.jsonl',
                        'session_id': 'bad',
                        'quality_report': {'ok': False, 'errors': ['missing motor_state']},
                    },
                ],
            }), encoding='utf-8')

            result = subprocess.run(
                [
                    sys.executable,
                    str(Path(__file__).resolve().parents[1] / 'rehab_arm_psoc_bridge' / 'build_annotation_queue.py'),
                    str(manifest_path),
                    '--label',
                    'reach_phase',
                ],
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )

        self.assertEqual(result.returncode, 0)
        queue = json.loads(result.stdout)
        self.assertEqual(queue['ready_count'], 1)
        self.assertEqual(queue['skipped_count'], 1)
        self.assertEqual(queue['items'][0]['recommended_labels'], ['reach_phase'])

    def test_make_annotation_template_rows_from_queue(self) -> None:
        queue = {
            'schema_version': 'rehab_arm_annotation_queue_v1',
            'items': [
                {
                    'session_id': 's1',
                    'file_name': 's1.jsonl',
                    'path': '/logs/s1.jsonl',
                    'device_id': 'nanopi',
                    'robot_id': 'arm',
                    'topic_profile': 'perception_vla',
                    'recommended_labels': ['reach_phase', 'object_state'],
                },
            ],
        }

        rows, fields = make_annotation_template_rows(queue)

        self.assertEqual(fields[:7], [
            'session_id',
            'file_name',
            'path',
            'device_id',
            'robot_id',
            'topic_profile',
            'annotation_status',
        ])
        self.assertIn('reach_phase', fields)
        self.assertIn('object_state', fields)
        self.assertEqual(rows[0]['session_id'], 's1')
        self.assertEqual(rows[0]['annotation_status'], 'pending')
        self.assertEqual(rows[0]['reach_phase'], '')

    def test_export_annotation_template_cli_writes_csv(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            queue_path = Path(tmpdir) / 'annotation_queue.json'
            csv_path = Path(tmpdir) / 'annotation_template.csv'
            queue_path.write_text(json.dumps({
                'schema_version': 'rehab_arm_annotation_queue_v1',
                'items': [
                    {
                        'session_id': 's1',
                        'file_name': 's1.jsonl',
                        'path': '/logs/s1.jsonl',
                        'device_id': 'nanopi',
                        'robot_id': 'arm',
                        'topic_profile': 'perception_vla',
                        'recommended_labels': ['reach_phase'],
                    },
                ],
            }), encoding='utf-8')

            result = subprocess.run(
                [
                    sys.executable,
                    str(Path(__file__).resolve().parents[1] / 'rehab_arm_psoc_bridge' / 'export_annotation_template.py'),
                    str(queue_path),
                    '--output',
                    str(csv_path),
                ],
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )
            csv_text = csv_path.read_text(encoding='utf-8')

        self.assertEqual(result.returncode, 0)
        payload = json.loads(result.stdout)
        self.assertEqual(payload['schema_version'], 'rehab_arm_annotation_template_export_v1')
        self.assertEqual(payload['row_count'], 1)
        self.assertIn('session_id,file_name,path,device_id,robot_id,topic_profile,annotation_status', csv_text)
        self.assertIn('s1,s1.jsonl,/logs/s1.jsonl,nanopi,arm,perception_vla,pending', csv_text)

    def test_validate_annotation_rows_requires_approved_status_and_labels(self) -> None:
        queue = {
            'schema_version': 'rehab_arm_annotation_queue_v1',
            'items': [
                {'session_id': 's1', 'recommended_labels': ['reach_phase', 'object_state']},
                {'session_id': 's2', 'recommended_labels': ['reach_phase']},
            ],
        }
        rows = [
            {
                'session_id': 's1',
                'annotation_status': 'approved',
                'reach_phase': 'reach',
                'object_state': 'cup_visible',
            },
            {
                'session_id': 's2',
                'annotation_status': 'pending',
                'reach_phase': '',
            },
            {
                'session_id': 'ghost',
                'annotation_status': 'approved',
                'reach_phase': 'reach',
            },
        ]

        report = validate_annotation_rows(rows, queue)

        self.assertIs(report['ok'], False)
        self.assertEqual(report['approved_count'], 1)
        self.assertEqual(report['error_count'], 3)
        joined_errors = '\n'.join(report['errors'])
        self.assertIn('row 2 session s2 annotation_status pending is not approved', joined_errors)
        self.assertIn('row 2 session s2 missing required label reach_phase', joined_errors)
        self.assertIn('row 3 session ghost is not in annotation queue', joined_errors)

    def test_validate_annotations_cli_reports_failed_rows(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            queue_path = Path(tmpdir) / 'annotation_queue.json'
            csv_path = Path(tmpdir) / 'annotations.csv'
            queue_path.write_text(json.dumps({
                'schema_version': 'rehab_arm_annotation_queue_v1',
                'items': [
                    {'session_id': 's1', 'recommended_labels': ['reach_phase']},
                ],
            }), encoding='utf-8')
            write_csv_rows(
                csv_path,
                [{'session_id': 's1', 'annotation_status': 'pending', 'reach_phase': ''}],
                ['session_id', 'annotation_status', 'reach_phase'],
            )

            result = subprocess.run(
                [
                    sys.executable,
                    str(Path(__file__).resolve().parents[1] / 'rehab_arm_psoc_bridge' / 'validate_annotations.py'),
                    str(queue_path),
                    str(csv_path),
                ],
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )

        self.assertEqual(result.returncode, 1)
        payload = json.loads(result.stdout)
        self.assertIs(payload['ok'], False)
        self.assertEqual(payload['error_count'], 2)

    def test_build_dataset_index_keeps_quality_ready_sessions(self) -> None:
        manifest = {
            'schema_version': 'rehab_arm_manifest_v1',
            'sessions': [
                {
                    'ok': True,
                    'path': '/logs/good.jsonl',
                    'file_name': 'good.jsonl',
                    'session_id': 'good',
                    'device_id': 'nanopi',
                    'robot_id': 'arm',
                    'mode': 'simulation_data_collection',
                    'record_count': 42,
                    'topics': ['/joint_states', '/rehab_arm/motor_state'],
                    'quality_report': {
                        'ok': True,
                        'topic_profile': 'hardware_telemetry',
                        'summary': {'moving_joint_count': 5},
                    },
                },
                {
                    'ok': True,
                    'file_name': 'bad.jsonl',
                    'session_id': 'bad',
                    'quality_report': {
                        'ok': False,
                        'errors': ['missing motor_state'],
                    },
                },
            ],
        }

        index = build_dataset_index(manifest, dataset_id=' rehab arm/demo ', purpose='replay_review')

        self.assertEqual(index['schema_version'], 'rehab_arm_dataset_index_v1')
        self.assertEqual(index['dataset_id'], 'rehab_arm_demo')
        self.assertEqual(index['purpose'], 'replay_review')
        self.assertEqual(index['ready_count'], 1)
        self.assertEqual(index['skipped_count'], 1)
        self.assertEqual(index['items'][0]['session_id'], 'good')
        self.assertEqual(index['items'][0]['jsonl_path'], '/logs/good.jsonl')
        self.assertEqual(index['items'][0]['topic_profile'], 'hardware_telemetry')
        self.assertEqual(index['items'][0]['summary']['moving_joint_count'], 5)
        self.assertEqual(index['items'][0]['control_boundary'], 'dataset_index_only_not_motion_permission')
        self.assertIn('quality_report.ok is false', index['skipped_sessions'][0]['reasons'])

    def test_build_dataset_index_cli_writes_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            manifest_path = Path(tmpdir) / 'manifest_with_quality.json'
            output_path = Path(tmpdir) / 'dataset_index.json'
            manifest_path.write_text(json.dumps({
                'schema_version': 'rehab_arm_manifest_v1',
                'sessions': [
                    {
                        'ok': True,
                        'path': '/logs/good.jsonl',
                        'file_name': 'good.jsonl',
                        'session_id': 'good',
                        'quality_report': {'ok': True, 'topic_profile': 'hardware_telemetry'},
                    },
                ],
            }), encoding='utf-8')

            result = subprocess.run(
                [
                    sys.executable,
                    str(Path(__file__).resolve().parents[1] / 'rehab_arm_psoc_bridge' / 'build_dataset_index.py'),
                    str(manifest_path),
                    '--dataset-id',
                    'dataset-1',
                    '--output',
                    str(output_path),
                ],
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )
            payload = json.loads(output_path.read_text(encoding='utf-8'))

        self.assertEqual(result.returncode, 0)
        self.assertEqual(payload['schema_version'], 'rehab_arm_dataset_index_v1')
        self.assertEqual(payload['dataset_id'], 'dataset-1')
        self.assertEqual(payload['ready_count'], 1)

    def test_session_log_path_sanitizes_session_id(self) -> None:
        path = session_log_path('logs', 'session 1/unsafe')

        self.assertEqual(path.as_posix(), 'logs/session_1_unsafe.jsonl')


if __name__ == '__main__':
    unittest.main()
