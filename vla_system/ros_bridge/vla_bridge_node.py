from __future__ import annotations

import json
from typing import Any

from vla_system.services.vla_bridge_service import VLABridgeService

try:
    import rclpy
    from rclpy.node import Node
    from std_msgs.msg import String
except ImportError:  # pragma: no cover - ROS is optional in local tests.
    rclpy = None
    Node = object
    String = None


class VLABridgeNode:
    input_topics = {
        "objects": "/scene/objects",
        "regions": "/scene/regions",
        "relations": "/scene/relations",
        "task_text": "/speech/text",
    }
    output_topic = "/task/resolved"

    def __init__(self, bridge_service: VLABridgeService | None = None) -> None:
        self.bridge_service = bridge_service or VLABridgeService()

    def resolve_payload(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self.bridge_service.resolve(payload).to_dict()

    def resolve_json(self, payload_json: str) -> str:
        payload = json.loads(payload_json)
        resolved = self.resolve_payload(payload)
        return json.dumps(resolved, ensure_ascii=False)


if rclpy is not None and String is not None:  # pragma: no cover - ROS is optional in local tests.
    class RclpyVLABridgeNode(Node):
        def __init__(self) -> None:
            super().__init__("vla_bridge_node")
            self.bridge_service = VLABridgeService()
            self.scene_cache: dict[str, Any] = {
                "objects": [],
                "regions": [],
                "relations": [],
                "robot_state": {},
                "execution_history": [],
            }
            self.publisher = self.create_publisher(String, "/task/resolved", 10)
            self.create_subscription(String, "/scene/objects", self._objects_callback, 10)
            self.create_subscription(String, "/scene/regions", self._regions_callback, 10)
            self.create_subscription(String, "/scene/relations", self._relations_callback, 10)
            self.create_subscription(String, "/speech/text", self._task_callback, 10)

        def _objects_callback(self, msg: String) -> None:
            self.scene_cache["objects"] = json.loads(msg.data)

        def _regions_callback(self, msg: String) -> None:
            self.scene_cache["regions"] = json.loads(msg.data)

        def _relations_callback(self, msg: String) -> None:
            self.scene_cache["relations"] = json.loads(msg.data)

        def _task_callback(self, msg: String) -> None:
            payload = dict(self.scene_cache)
            payload["text"] = msg.data
            resolved = self.bridge_service.resolve(payload).to_dict()
            output = String()
            output.data = json.dumps(resolved, ensure_ascii=False)
            self.publisher.publish(output)
