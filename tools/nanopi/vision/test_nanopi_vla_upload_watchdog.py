import importlib.util
from pathlib import Path


MODULE_PATH = Path(__file__).with_name("nanopi-vla-cpp-upload-loop.py")


def load_module():
    spec = importlib.util.spec_from_file_location("nanopi_vla_upload_loop_watchdog", MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class PendingFuture:
    def done(self):
        return False


class CompletedFuture:
    def done(self):
        return True


def test_upload_watchdog_only_trips_for_overdue_pending_future():
    module = load_module()

    assert not module.upload_future_stalled(None, None, now_monotonic=20.0, timeout_s=12.0)
    assert not module.upload_future_stalled(CompletedFuture(), 1.0, now_monotonic=20.0, timeout_s=12.0)
    assert not module.upload_future_stalled(PendingFuture(), 10.0, now_monotonic=20.0, timeout_s=12.0)
    assert module.upload_future_stalled(PendingFuture(), 5.0, now_monotonic=20.0, timeout_s=12.0)
