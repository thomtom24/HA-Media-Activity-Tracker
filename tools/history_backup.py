"""Offline, explicitly confirmed backup/restore of a single tracker's HA history.

Stop Home Assistant before restoring. No network requests are made.
"""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import re
import tempfile

spec=importlib.util.spec_from_file_location("history_schema",Path(__file__).resolve().parents[1]/"custom_components/media_activity_tracker/history_schema.py")
schema=importlib.util.module_from_spec(spec)
spec.loader.exec_module(schema)

def read(path, key):
    data=json.loads(path.read_text(encoding="utf-8"))
    if data.get("key")!=key or data.get("version")!=1:
        raise ValueError("Backup does not match this tracker or supported HA storage version")
    schema.validate(data["data"])
    return data

def write(path,data,replace=False):
    if path.exists() and not replace:
        raise FileExistsError(path)
    with tempfile.NamedTemporaryFile(mode="w",encoding="utf-8",dir=path.parent,delete=False) as f:
        temp=Path(f.name)
        try:
            os.chmod(temp,0o600)
            json.dump(data,f,allow_nan=False)
            f.flush()
            os.fsync(f.fileno())
        except BaseException:
            temp.unlink(missing_ok=True)
            raise
    try:
        os.replace(temp,path)
    finally:
        temp.unlink(missing_ok=True)

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("action",choices=("export","restore"))
    p.add_argument("config",type=Path)
    p.add_argument("entry_id")
    p.add_argument("file",type=Path)
    p.add_argument("--confirm-stopped",action="store_true")
    args=p.parse_args()
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,128}",args.entry_id):
        p.error("Invalid entry ID")
    key="media_activity_tracker."+args.entry_id
    target=args.config/".storage"/key
    if args.action=="export":
        write(args.file,read(target,key))
    else:
        if not args.confirm_stopped:
            p.error("Stop Home Assistant and supply --confirm-stopped")
        candidate=read(args.file,key)
        if target.exists():
            # Preserve the original bytes even if invalid.
            recovery=target.with_name(target.name+".before-restore")
            if recovery.exists():
                p.error("Move the existing .before-restore file before restoring again")
            with recovery.open("xb") as f:
                os.chmod(recovery,0o600)
                f.write(target.read_bytes())
        write(target,candidate,replace=True)
    print("Completed",args.action)

if __name__=="__main__":
    main()
