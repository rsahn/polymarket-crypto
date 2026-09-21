import struct
from collections import OrderedDict
from app.d5.store import Store

class CachedStore(Store):
    def __init__(self, *args, **kwargs):
        self.depth_cache = OrderedDict()
        self.cache_hits = 0
        self.cache_misses = 0
        super().__init__(*args, **kwargs)

    def pack(self, value):
        if type(value) is not list or len(value) > 20:
            return super().pack(value)
        flat = []
        for level in value:
            if type(level) not in (tuple, list) or len(level) != 2:
                return super().pack(value)
            if type(level[0]) is not float or type(level[1]) is not float:
                return super().pack(value)
            flat.extend(level)
        key = struct.pack('<' + 'd' * len(flat), *flat)
        if key in self.depth_cache:
            self.cache_hits += 1
            self.depth_cache.move_to_end(key)
            return self.depth_cache[key]
        self.cache_misses += 1
        packed = super().pack(value)
        self.depth_cache[key] = packed
        if len(self.depth_cache) > 1024:
            self.depth_cache.popitem(last=False)
        return packed
