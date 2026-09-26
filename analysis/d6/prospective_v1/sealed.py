"""Sealed files and one-shot economic loaders; no collection or automatic access."""
import json
from pathlib import Path
from .journal import validate
from .core import AccessGate, PartitionPlan, digest, file_hash, write_once, safety
SPLITS=("TRAIN","VALIDATION","OOS")

class SealedDataset:
    def __init__(self,directory,source_root,seal,manifest_hash,*,synthetic=False):
        safety()
        self.directory=Path(directory); self.source_root=Path(source_root)
        self.seal=seal; self.manifest_hash=manifest_hash; self.synthetic=synthetic
        self.gate=AccessGate(self.directory,self.source_root,seal,manifest_hash)
        self.verify()
        # Real collection binding is intentionally unavailable until its missing
        # passive V1 observation contract has been resolved and audited.
        if not synthetic: raise ValueError("REAL_V1_BINDING_NOT_QUALIFIED")
    def verify(self):
        self.seal.verify(self.source_root)
        p=self.directory/"manifest.json"
        if file_hash(p)!=self.manifest_hash: raise ValueError("DATASET_MANIFEST_MISMATCH")
        m=json.loads(p.read_text(encoding="utf-8"))
        if m.get("seal_hash")!=self.seal.hash: raise ValueError("DEPENDENCY_SEAL_MISMATCH")
        if m.get("duration_hours")!=[72,48,48] or m.get("embargo_ms")!=60000:
            raise ValueError("PRESPECIFIED_BOUNDARIES_CHANGED")
        if self.synthetic and m.get("synthetic") is not True: raise ValueError("REAL_DATA_FORBIDDEN_IN_FIXTURE")
        self.manifest=m
        return m
    def _path(self,split,suffix):
        if split not in SPLITS: raise ValueError("INVALID_SPLIT")
        return self.directory/(split+suffix)
    def seal_partition(self,split,now_ms):
        safety(); m=self.verify()
        index=SPLITS.index(split)
        end=m["start"]+sum(m["duration_hours"][:index+1])*3600000
        if now_ms<end: raise ValueError("PARTITION_NOT_CLOSED")
        p=self._path(split,".jsonl")
        write_once(self._path(split,".SEALED.json"),{
            "split":split,"file_hash":file_hash(p),"manifest_hash":self.manifest_hash,
            "seal_hash":self.seal.hash,"closed_at":now_ms,"end":end})
    def _closed(self,split):
        p=self._path(split,".SEALED.json")
        if not p.exists(): raise ValueError("PARTITION_NOT_SEALED")
        closed=json.loads(p.read_text())
        if closed["manifest_hash"]!=self.manifest_hash or closed["seal_hash"]!=self.seal.hash:
            raise ValueError("PARTITION_SEAL_MISMATCH")
        if closed["file_hash"]!=file_hash(self._path(split,".jsonl")):
            raise ValueError("DATASET_HASH_MISMATCH")
        return closed
    def _upstream(self,split):
        hashes={}
        for prev in SPLITS[:SPLITS.index(split)]:
            result=self.gate._read(prev+"_RESULT.json")
            marker=self.gate._read(prev+"_FIRST_ACCESS.json")
            if result.get("verdict")!="PASS" or result.get("marker_hash")!=digest(marker):
                raise ValueError("UPSTREAM_NOT_PASS")
            if marker["dataset_hash"]!=self.manifest_hash or marker["seal_hash"]!=self.seal.hash:
                raise ValueError("UPSTREAM_HASH_MISMATCH")
            self._closed(prev)
            hashes[prev]=digest(result)
        return hashes
    def freeze(self,split):
        safety(); self.verify()
        if split not in ("VALIDATION","OOS"): raise ValueError("INVALID_FREEZE")
        upstream=self._upstream(split)
        payload={"kind":"PRE_"+split+"_FREEZE","split":split,
            "upstream":upstream,"manifest_hash":self.manifest_hash,"seal_hash":self.seal.hash,
            "selection":"NONE","sizing":"FIXED25"}
        write_once(self._path(split,"_FREEZE.json"),payload)
        return payload
    def load(self,split):
        safety(); self.verify()
        marker=self._path(split,"_FIRST_ACCESS.json")
        if marker.exists(): raise FileExistsError(split+"_CONSUMED")
        closed=self._closed(split); upstream=self._upstream(split); freeze={}
        if split!="TRAIN":
            p=self._path(split,"_FREEZE.json")
            if not p.exists(): raise ValueError("PRE_"+split+"_FREEZE_MISSING")
            freeze=json.loads(p.read_text())
            expected={"kind":"PRE_"+split+"_FREEZE","split":split,"upstream":upstream,
                "manifest_hash":self.manifest_hash,"seal_hash":self.seal.hash,
                "selection":"NONE","sizing":"FIXED25"}
            if freeze!=expected: raise ValueError("FREEZE_INVALID_OR_CHANGED")
        self.gate.open(split,self.manifest_hash,freeze)
        # From this point on EVERY failure consumes access, including parse crash.
        p=self._path(split,".jsonl")
        data=p.read_bytes()
        import hashlib
        if hashlib.sha256(data).hexdigest()!=closed["file_hash"]: raise ValueError("DATASET_CHANGED_DURING_READ")
        rows=[json.loads(line) for line in data.splitlines()]
        ids=set(); previous="0"*64; last=-1
        for sequence,row in enumerate(rows):
            identity={"partition":split,"dataset_session_id":self.manifest["session"],
                      "strategy_hash":self.manifest.get("strategy_hash"),
                      "runner_hash":self.manifest.get("runner_hash")}
            validate(row,identity,sequence,previous,ids,last)
            ids.add(row["event_id"]); previous=row["event_hash"]; last=row["event_ts"]
            if row.get("partition")!=split or self.manifest["markets"].get(row.get("market_id"))!=split:
                raise ValueError("MARKET_PARTITION_MISMATCH")
        return rows

def planned_boundaries(now_ms,other_gates_pass):
    if not other_gates_pass: raise ValueError("BLOCKED_BEFORE_T0")
    start=((now_ms+600000+299999)//300000)*300000
    return {"T0":start,"TRAIN_END":start+72*3600000,
        "VALIDATION_START":start+72*3600000,"VALIDATION_END":start+120*3600000,
        "OOS_START":start+120*3600000,"OOS_END":start+168*3600000,
        "embargo_ms":60000}
