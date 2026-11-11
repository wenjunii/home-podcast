"""Build a NEW 5090 native revision from the receiver rig and approved show.

Uses the installed Derivative offline expand/collapse tools, never TD/model
startup. Both renderer subtrees, renderer callbacks, audio device and Spout
senders come byte-for-byte from the receiver. Every pre-existing TOE is held.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import struct
import subprocess

PREFIX = "project1/podcast_visualizer"
EDITION = "work/storytelling-real-december/continuous-image-hold-136-3080-2026-10-30"
RECEIVER_HASH = "073bac312a21ceb09bab75f9c8c279c947556b20bca734df7e56cb21d47929e3"
SENDER_HASH = "6b411b5386c368f734327820d8460a94521bb70beecd85569d7e52390763018b"


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def protected(name):
    if not name.startswith(PREFIX + "/"):
        return False
    head = name[len(PREFIX) + 1:].split("/")[0].split(".")[0]
    return head.startswith("StreamDiffusionTD") or head in {"audio_out", "syphonspoutout1", "syphonspoutout2"}


def own(name):
    return (name.startswith(PREFIX + "/") or name.startswith(PREFIX + ".")) and not protected(name)


def decode_dat(data):
    if len(data) < 27 or data[:3] != b"2\n*" or struct.unpack(">I", data[23:27])[0] != len(data) - 27:
        raise ValueError("Unsupported Text DAT serialization; do not patch arbitrary binary data")
    return data[27:].decode("utf-8")


def encode_dat(original, text):
    decode_dat(original)
    payload = text.encode("utf-8")
    return original[:23] + struct.pack(">I", len(payload)) + payload


def replace_root(text, old, new):
    mapping = {old: str(new), old.replace("\\", "/"): str(new).replace("\\", "/"),
               old.replace("\\", "\\\\"): str(new).replace("\\", "\\\\")}
    pattern = re.compile("|".join(re.escape(k) for k in sorted(mapping, key=len, reverse=True)))
    return pattern.sub(lambda m: mapping[m[0]], text)


def set_parameter(text, name, value, flags="67108928"):
    line = f"{name} {flags} {value}"
    pattern = re.compile(r"(?m)^" + re.escape(name) + r" .*$")
    if pattern.search(text):
        return pattern.sub(lambda m: line, text)
    return text.rstrip() + "\n" + line + "\n"


def checked_expand(binary, source):
    result = subprocess.run([str(binary), str(source)], capture_output=True, text=True)
    tree = Path(str(source) + ".dir")
    toc = Path(str(source) + ".toc")
    if not tree.is_dir() or not toc.is_file():
        raise RuntimeError("Offline expansion did not create a complete tree")
    names = toc.read_text(encoding="utf-8").splitlines()
    if not names or any(not (tree / n).is_file() for n in names):
        raise RuntimeError("Incomplete offline expansion; preserve scratch and stop")
    return tree, names


def build(root, receiver, sender, output, scratch, td_bin):
    root, receiver, sender, output, scratch = map(lambda p: Path(p).resolve(), (root, receiver, sender, output, scratch))
    if receiver.name != "podcast.5090.24.toe" or output != root / "podcast.5090.25.toe":
        raise ValueError("Only the approved .24 -> new .25 migration is supported")
    if output.exists() or scratch.exists():
        raise FileExistsError("Output/scratch already exists; never overwrite a native project")
    if sha(receiver) != RECEIVER_HASH or sha(sender) != SENDER_HASH:
        raise ValueError("Native input differs from the approved review")
    playlist = json.loads((root / EDITION / "playlist.json").read_text(encoding="utf-8"))
    if playlist["story_count"] != 136 or len(playlist["stories"]) != 136:
        raise ValueError("Wrong approved data edition")
    scratch.mkdir(parents=True)
    base = scratch / "receiver.toe"; reference = scratch / "reference.toe"
    shutil.copy2(receiver, base); shutil.copy2(sender, reference)
    receiver_tree, receiver_names = checked_expand(td_bin / "toeexpand.exe", base)
    sender_tree, sender_names = checked_expand(td_bin / "toeexpand.exe", reference)
    candidate = scratch / "candidate.toe"
    candidate_tree = Path(str(candidate) + ".dir")
    shutil.copytree(receiver_tree, candidate_tree)
    protected_before = {n: sha(receiver_tree / n) for n in receiver_names if protected(n)}
    parm = (sender_tree / (PREFIX + ".parm")).read_text(encoding="utf-8")
    saved = re.search(r"(?m)^Playlistmanifest \d+ (.+)$", parm)[1].strip().replace("\\\\", "\\")
    suffix = "\\" + EDITION.replace("/", "\\") + "\\playlist.json"
    if not saved.endswith(suffix):
        raise ValueError("Unexpected sender root; do not guess a rebind")
    old_root = saved[:-len(suffix)]
    transferred = []
    for name in sender_names:
        if not own(name):
            continue
        source, target = sender_tree / name, candidate_tree / name
        target.parent.mkdir(parents=True, exist_ok=True)
        data = source.read_bytes()
        if source.suffix == ".text":
            text = decode_dat(data)
            if name.endswith("show_control/playlist_callbacks.text"):
                text = (root / "touchdesigner/playlist_5090_callbacks.py").read_text(encoding="utf-8")
            elif name.endswith("show_control/control_callbacks.text"):
                text = (root / "touchdesigner/canonical_5090_callbacks.py").read_text(encoding="utf-8")
            else:
                text = replace_root(text, old_root, root)
            data = encode_dat(data, text)
        elif source.suffix in {".parm", ".cparm", ".n"}:
            data = replace_root(data.decode("utf-8"), old_root, root).encode("utf-8")
        target.write_bytes(data); transferred.append(name)
    # Keep shared data and immutable sender receipts unchanged; receiver runtime
    # state has a dedicated local path and cannot activate the sender's worker.
    connector_file = candidate_tree / (PREFIX + ".parm")
    text = connector_file.read_text(encoding="utf-8")
    for name, filename in (("Livecontroljson", "control.json"), ("Livestatusjson", "status.json"), ("Livecurrentjson", "current.json")):
        value = str(root / "work/5090-136/runtime" / filename).replace("\\", "\\\\")
        text = set_parameter(text, name, value)
    text = set_parameter(text, "Runtimeprofile", "3080_safe")
    connector_file.write_bytes(text.encode("utf-8"))
    control_file = candidate_tree / (PREFIX + "/show_control.parm")
    text = control_file.read_text(encoding="utf-8")
    for name, value in (("Runtimeprofile", "3080_safe"), ("Livevariations", "off"), ("Play", "off")):
        text = set_parameter(text, name, value)
    # Retain receiver's selected color/audio-enable settings, and adopt the
    # approved edition's new three-second scene/story presentation controls.
    baseline = (receiver_tree / (PREFIX + "/show_control.parm")).read_text(encoding="utf-8")
    for line in baseline.splitlines():
        bits = line.split(" ", 2)
        if len(bits) == 3 and bits[0] in {"Audioenabled", "Randomseeds", "Colorenabled", "Brightness", "Contrast", "Gamma", "Blacklevel", "Opacity", "Hue", "Saturation", "Value"}:
            text = set_parameter(text, bits[0], bits[2], bits[1])
    control_file.write_bytes(text.encode("utf-8"))
    time_file = candidate_tree / "local/time.parm"
    text = time_file.read_text(encoding="utf-8")
    import math
    end = math.ceil(playlist["duration_ms"] / 1000 * 60) + 1
    for name, value in (("play", "0"), ("end", str(end)), ("rangeend", str(end))):
        text = set_parameter(text, name, value, "0")
    time_file.write_bytes(text.encode("utf-8"))
    # Native project.name comes from the saved TOENAME variable, not merely
    # the filesystem name. Both numbered names have identical UTF-8 lengths,
    # so the serialized table's cell lengths are retained exactly.
    variable_file = candidate_tree / "local/set_variables.table"
    data = variable_file.read_bytes()
    old_name, new_name = receiver.name.encode(), output.name.encode()
    if len(old_name) != len(new_name) or data.count(old_name) != 1:
        raise ValueError("Unexpected saved TOENAME table")
    variable_file.write_bytes(data.replace(old_name, new_name))
    names = list(receiver_names)
    names.extend(n for n in sender_names if own(n) and n not in names)
    # Derivative's Windows collapse tool treats a CR as part of the filename.
    # Its expanded TOC uses LF even on Windows; do not use text-mode translation.
    Path(str(candidate) + ".toc").write_bytes(("\n".join(names) + "\n").encode("utf-8"))
    if any(sha(candidate_tree / n) != digest for n, digest in protected_before.items()):
        raise RuntimeError("Receiver renderer/audio/Spout serialization changed")
    for name in names:
        if own(name) and name.endswith(".text"):
            compile(decode_dat((candidate_tree / name).read_bytes()), name, "exec")
    subprocess.run([str(td_bin / "toecollapse.exe"), str(candidate)], check=True, capture_output=True, text=True)
    # A second expansion verifies the native roundtrip and preservation before
    # the final new filename is published using exclusive creation.
    roundtrip_file = scratch / "roundtrip.toe"
    shutil.copy2(candidate, roundtrip_file)
    roundtrip, expanded_names = checked_expand(td_bin / "toeexpand.exe", roundtrip_file)
    if len(expanded_names) != len(names) or any(sha(roundtrip / n) != digest for n, digest in protected_before.items()):
        raise RuntimeError("Collapsed project failed preservation verification")
    with output.open("xb") as target, candidate.open("rb") as source:
        shutil.copyfileobj(source, target)
    if sha(output) != sha(candidate):
        raise RuntimeError("New native copy failed hashing")
    report = dict(project=output.name,receiver_sha256=sha(receiver),reference_sha256=sha(sender),new_sha256=sha(output),
                  protected_files=len(protected_before),protected_files_unchanged=True,connector_files_transferred=len(transferred),
                  live_generation=False,servers_started=False,preexisting_native_overwrites=0)
    (scratch / "build-report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return report


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for name in ("root", "receiver", "sender", "output", "scratch", "td-bin"):
        p.add_argument("--" + name, type=Path, required=True)
    a = p.parse_args()
    print(json.dumps(build(a.root, a.receiver, a.sender, a.output, a.scratch, a.td_bin), indent=2))


if __name__ == "__main__":
    main()
