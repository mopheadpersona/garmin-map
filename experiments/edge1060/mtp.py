"""Files on an MTP device (Garmin Edge 1050/1060) through OpenMTP's own kalam library.

OpenMTP itself must be closed: only one program can hold the device.

usage: mtp.py info
       mtp.py ls <path> [<path> ...]
       mtp.py get <local dir> <device path> [<device path> ...]
       mtp.py put <device dir> <local file> [<local file> ...]
       mtp.py rm <device path> [<device path> ...]
"""
import ctypes
import json
import sys

BIN = "/Applications/OpenMTP.app/Contents/Resources/bin/arm64"
CB = ctypes.CFUNCTYPE(None, ctypes.c_char_p)


def load():
    try:
        ctypes.CDLL(BIN + "/libusb-seg5.dylib", mode=ctypes.RTLD_GLOBAL)
    except OSError:
        pass
    return ctypes.CDLL(BIN + "/kalam-seg5.dylib")


def call(lib, name, payload=None):
    box = {}

    def on_done(raw):
        box["r"] = json.loads(raw.decode("utf-8", "replace")) if raw else None

    cb = CB(on_done)
    fn = getattr(lib, name)
    fn.restype = None
    if payload is None:
        fn.argtypes = [CB]
        fn(cb)
    else:
        fn.argtypes = [ctypes.c_char_p, CB]
        fn(json.dumps(payload).encode("utf-8"), cb)
    return box.get("r")


def main():
    lib = load()
    r = call(lib, "Initialize")
    print("Initialize:", json.dumps(r, ensure_ascii=False)[:600])
    if not r or r.get("error"):
        return 1
    try:
        st = call(lib, "FetchStorages")
        print("Storages:", json.dumps(st, ensure_ascii=False))
        storages = (st or {}).get("data") or []
        if sys.argv[1] == "info":
            print("DeviceInfo:", json.dumps(call(lib, "FetchDeviceInfo"), ensure_ascii=False)[:1500])
            return 0
        sid = int(storages[0].get("Sid", storages[0].get("sid", 0))) if storages else 0
        if sys.argv[1] == "rm":
            print("Delete:", json.dumps(call(lib, "DeleteFile", {"storageId": sid, "files": sys.argv[2:]}),
                                        ensure_ascii=False)[:300])
            return 0
        if sys.argv[1] == "put":
            last = {}

            def on_any(raw):
                pass

            def on_done(raw):
                last["d"] = json.loads(raw.decode("utf-8", "replace")) if raw else None

            a, b, c = CB(on_any), CB(on_any), CB(on_done)
            fn = lib.UploadFiles
            fn.restype = None
            fn.argtypes = [ctypes.c_char_p, CB, CB, CB]
            fn(json.dumps({"storageId": sid, "sources": sys.argv[3:], "destination": sys.argv[2],
                           "preprocessFiles": False}).encode("utf-8"), a, b, c)
            print("Upload:", json.dumps(last.get("d"), ensure_ascii=False)[:500])
            return 0
        if sys.argv[1] == "get":
            last = {}

            def on_pre(raw):
                pass

            def on_prog(raw):
                last["p"] = raw

            def on_done(raw):
                last["d"] = json.loads(raw.decode("utf-8", "replace")) if raw else None

            a, b, c = CB(on_pre), CB(on_prog), CB(on_done)
            fn = lib.DownloadFiles
            fn.restype = None
            fn.argtypes = [ctypes.c_char_p, CB, CB, CB]
            fn(json.dumps({"storageId": sid, "sources": sys.argv[3:], "destination": sys.argv[2],
                           "preprocessFiles": False}).encode("utf-8"), a, b, c)
            print("Download:", json.dumps(last.get("d"), ensure_ascii=False)[:500])
            return 0
        for path in sys.argv[2:]:
            w = call(lib, "Walk", {
                "storageId": sid, "fullPath": path, "recursive": False,
                "skipDisallowedFiles": False, "skipHiddenFiles": False,
            })
            print(f"--- {path}")
            if not w or w.get("error"):
                print("   error:", json.dumps(w, ensure_ascii=False)[:500])
                continue
            for f in sorted(w.get("data") or [], key=lambda x: (not x.get("isDir"), x.get("name", "").lower())):
                kind = "d" if f.get("isDir") else "-"
                print(f"   {kind} {f.get('size', 0):>12}  {f.get('modTime', '')!s:<22} {f.get('name')}")
    finally:
        print("Dispose:", json.dumps(call(lib, "Dispose"), ensure_ascii=False)[:200])
    return 0


if __name__ == "__main__":
    sys.exit(main())
