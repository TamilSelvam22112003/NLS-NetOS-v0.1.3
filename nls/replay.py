"""Bounded sliding-window anti-replay primitive."""
import threading
class ReplayWindow:
    def __init__(self, width: int = 1024) -> None:
        if width < 1: raise ValueError("window width must be positive")
        self.width, self.highest, self.bitmap = width, -1, 0
        self._lock = threading.Lock()
    def accept(self, sequence: int) -> bool:
        if sequence < 0: return False
        with self._lock:
            if self.highest == -1:
                self.highest, self.bitmap = sequence, 1
                return True
            if sequence > self.highest:
                shift = sequence - self.highest
                self.bitmap = 0 if shift >= self.width else (self.bitmap << shift) & ((1 << self.width) - 1)
                self.bitmap |= 1
                self.highest = sequence
                return True
            offset = self.highest - sequence
            if offset >= self.width: return False
            mask = 1 << offset
            if self.bitmap & mask: return False
            self.bitmap |= mask
            return True
