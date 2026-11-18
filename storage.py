"""Thread-safe atomic JSON storage. Write to .tmp, then os.replace() over the target."""

import json
import os
import threading


class AtomicJSONStore:
    def __init__(self, path, default=None):
        self.path = path
        self._lock = threading.RLock()
        self._default = default if default is not None else {}
        if not os.path.exists(self.path):
            self.write(self._default)

    def read(self):
        with self._lock:
            try:
                with open(self.path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except (FileNotFoundError, json.JSONDecodeError):
                return json.loads(json.dumps(self._default))

    def write(self, data):
        with self._lock:
            tmp_path = self.path + ".tmp"
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            os.replace(tmp_path, self.path)

    def update(self, mutator):
        """mutator(data) -> data; read-modify-write under the same lock."""
        with self._lock:
            data = self.read()
            data = mutator(data)
            self.write(data)
            return data
