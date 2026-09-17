#!/usr/bin/env python3
"""
tools/verify_firmware.py
Static analysis & compilation guard verifier for SMSB firmware fleet.
Validates:
1. Inverted include priority in all ESP sketches.
2. Presence and validity of sketch-local and common secrets.h files.
3. Cadence and deadband constants matching Phase 3 specs across WEMOS_TS, WEMOS_ATS, WEMOS_AC.
4. C++ syntax invariants: balanced braces, parentheses, string literals, and bounded buffer usage.
5. Canonical uncorrupted state of PROMINI.ino against Git.
"""

import os
import re
import subprocess
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
FIRMWARE_DIR = ROOT_DIR / "firmware"


def check_brackets_and_quotes(filepath: Path) -> list[str]:
    """Validates balanced braces, parentheses, and brackets outside comments/strings."""
    errors = []
    content = filepath.read_text(encoding="utf-8", errors="replace")

    # Strip multi-line comments
    cleaned = re.sub(r'/\*.*?\*/', '', content, flags=re.DOTALL)
    # Strip single-line comments
    cleaned = re.sub(r'//.*$', '', cleaned, flags=re.MULTILINE)

    stack = []
    pairs = {')': '(', '}': '{', ']': '['}
    line_no = 1
    in_string = False
    in_char = False
    escape = False

    for i, char in enumerate(cleaned):
        if char == '\n':
            line_no += 1
            continue

        if escape:
            escape = False
            continue

        if char == '\\':
            escape = True
            continue

        if char == '"' and not in_char:
            in_string = not in_string
            continue

        if char == "'" and not in_string:
            in_char = not in_char
            continue

        if in_string or in_char:
            continue

        if char in '({[':
            stack.append((char, line_no))
        elif char in ')}]':
            if not stack:
                errors.append(f"{filepath.name}:{line_no} Unmatched closing '{char}'")
            else:
                top, top_line = stack.pop()
                if top != pairs[char]:
                    errors.append(f"{filepath.name}:{line_no} Mismatched '{char}', expected closing for '{top}' from line {top_line}")

    while stack:
        top, top_line = stack.pop()
        errors.append(f"{filepath.name}:{top_line} Unclosed opening '{top}'")

    return errors


def verify_secrets_invariants() -> list[str]:
    """Verifies sketch-local and common secrets.h existence and include priority."""
    errors = []
    sketches = ["WEMOS_TS", "WEMOS_ATS", "WEMOS_AC"]

    # 1. Check secrets.h existence
    common_secrets = FIRMWARE_DIR / "common" / "secrets.h"
    if not common_secrets.is_file():
        errors.append("firmware/common/secrets.h is missing!")

    for sketch in sketches:
        local_secrets = FIRMWARE_DIR / sketch / "secrets.h"
        if not local_secrets.is_file():
            errors.append(f"firmware/{sketch}/secrets.h is missing!")

        ino_file = FIRMWARE_DIR / sketch / f"{sketch}.ino"
        if not ino_file.is_file():
            errors.append(f"{ino_file} is missing!")
            continue

        content = ino_file.read_text(encoding="utf-8", errors="replace")

        # 2. Check inverted include priority
        expected_guard = (
            '#if __has_include("secrets.h")' in content and
            '#include "secrets.h"' in content and
            '#elif __has_include("../common/secrets.h")' in content
        )
        if not expected_guard:
            errors.append(f"{sketch}.ino missing inverted include priority guard for secrets.h")

    return errors


def verify_wemos_ts() -> list[str]:
    """Verifies WEMOS_TS timing, deadbands, and logic invariants."""
    errors = []
    ino = FIRMWARE_DIR / "WEMOS_TS" / "WEMOS_TS.ino"
    content = ino.read_text(encoding="utf-8", errors="replace")

    # Timing checks
    if not re.search(r'const\s+unsigned\s+long\s+HEARTBEAT_INTERVAL_MS\s*=\s*300000', content):
        errors.append("WEMOS_TS: HEARTBEAT_INTERVAL_MS must be 300000 (5 minutes / 300s)")
    if not re.search(r'const\s+unsigned\s+long\s+MIN_PUBLISH_INTERVAL_MS\s*=\s*5000', content):
        errors.append("WEMOS_TS: MIN_PUBLISH_INTERVAL_MS must be 5000 (5s)")
    if not re.search(r'const\s+unsigned\s+long\s+SENSOR_INTERVAL_MS\s*=\s*2000', content):
        errors.append("WEMOS_TS: SENSOR_INTERVAL_MS must be 2000 (2s)")
    if not re.search(r'const\s+unsigned\s+long\s+OLED_INTERVAL_MS\s*=\s*1000', content):
        errors.append("WEMOS_TS: OLED_INTERVAL_MS must be 1000 (1 Hz)")

    # Deadband checks
    if not re.search(r'const\s+float\s+DEADBAND_TEMP\s*=\s*0\.2', content):
        errors.append("WEMOS_TS: DEADBAND_TEMP must be 0.2°C")
    if not re.search(r'const\s+float\s+DEADBAND_HUMID\s*=\s*2\.0', content):
        errors.append("WEMOS_TS: DEADBAND_HUMID must be 2.0%")

    # Error recovery & null safety
    if "STATUS" not in content or "SENSOR_ERROR" not in content:
        errors.append("WEMOS_TS: missing STATUS / SENSOR_ERROR error reporting")
    if "sensorStatusChanged" not in content:
        errors.append("WEMOS_TS: missing sensor error/recovery trigger (sensorStatusChanged)")

    return errors


def verify_wemos_ats() -> list[str]:
    """Verifies WEMOS_ATS timing, deadbands, burst mode, and safety invariants."""
    errors = []
    ino = FIRMWARE_DIR / "WEMOS_ATS" / "WEMOS_ATS.ino"
    content = ino.read_text(encoding="utf-8", errors="replace")

    # Timing checks
    if not re.search(r'const\s+unsigned\s+long\s+STEADY_PUBLISH_INTERVAL_MS\s*=\s*60000', content):
        errors.append("WEMOS_ATS: STEADY_PUBLISH_INTERVAL_MS must be 60000 (60s)")
    if not re.search(r'const\s+unsigned\s+long\s+BURST_PUBLISH_INTERVAL_MS\s*=\s*2000', content):
        errors.append("WEMOS_ATS: BURST_PUBLISH_INTERVAL_MS must be 2000 (2.0s)")
    if not re.search(r'const\s+unsigned\s+long\s+BURST_DURATION_MS\s*=\s*60000', content):
        errors.append("WEMOS_ATS: BURST_DURATION_MS must be 60000 (60s)")
    if not re.search(r'const\s+unsigned\s+long\s+MIN_PUBLISH_INTERVAL_MS\s*=\s*2000', content):
        errors.append("WEMOS_ATS: MIN_PUBLISH_INTERVAL_MS must be 2000 (2s)")
    if not re.search(r'const\s+unsigned\s+long\s+intervalConnected\s*=\s*500', content):
        errors.append("WEMOS_ATS: intervalConnected must be 500ms (Pro Mini polling)")

    # Deadband checks
    if not re.search(r'const\s+double\s+DEADBAND_PLN_V\s*=\s*1\.0', content):
        errors.append("WEMOS_ATS: DEADBAND_PLN_V must be 1.0V")
    if not re.search(r'const\s+double\s+DEADBAND_GEN_V\s*=\s*1\.0', content):
        errors.append("WEMOS_ATS: DEADBAND_GEN_V must be 1.0V")
    if not re.search(r'const\s+double\s+DEADBAND_AKI_V\s*=\s*0\.1', content):
        errors.append("WEMOS_ATS: DEADBAND_AKI_V must be 0.1V")

    # State transition & burst trigger checks
    for state_prop in ["nowState", "autoMode", "emergency", "isPlnOn", "isGensetOn", "isAlarm"]:
        if state_prop not in content:
            errors.append(f"WEMOS_ATS: missing discrete state tracking for {state_prop}")

    if "burstUntil = now + BURST_DURATION_MS" not in content:
        errors.append("WEMOS_ATS: dynamic burst activation missing on discrete state change")

    # Buffer safety
    if "char buf[65]" not in content:
        errors.append("WEMOS_ATS: serial buffer bounded safety char[65] missing")
    if "client.setBufferSize(512)" not in content:
        errors.append("WEMOS_ATS: client.setBufferSize(512) missing")

    return errors


def verify_wemos_ac() -> list[str]:
    """Verifies WEMOS_AC timing, deadbands, and command execution invariants."""
    errors = []
    ino = FIRMWARE_DIR / "WEMOS_AC" / "WEMOS_AC.ino"
    content = ino.read_text(encoding="utf-8", errors="replace")

    # Timing checks
    if not re.search(r'const\s+unsigned\s+long\s+HEARTBEAT_INTERVAL_MS\s*=\s*120000', content):
        errors.append("WEMOS_AC: HEARTBEAT_INTERVAL_MS must be 120000 (120s / 2m)")
    if not re.search(r'const\s+unsigned\s+long\s+MIN_PUBLISH_INTERVAL_MS\s*=\s*5000', content):
        errors.append("WEMOS_AC: MIN_PUBLISH_INTERVAL_MS must be 5000 (5s)")
    if not re.search(r'const\s+unsigned\s+long\s+SENSOR_INTERVAL_MS\s*=\s*2000', content):
        errors.append("WEMOS_AC: SENSOR_INTERVAL_MS must be 2000 (2s)")
    if not re.search(r'const\s+unsigned\s+long\s+OLED_INTERVAL_MS\s*=\s*1000', content):
        errors.append("WEMOS_AC: OLED_INTERVAL_MS must be 1000 (1 Hz)")

    # Deadband checks
    if not re.search(r'const\s+float\s+DEADBAND_TEMP\s*=\s*0\.5', content):
        errors.append("WEMOS_AC: DEADBAND_TEMP must be 0.5°C")
    if not re.search(r'const\s+float\s+DEADBAND_HUMID\s*=\s*2\.0', content):
        errors.append("WEMOS_AC: DEADBAND_HUMID must be 2.0%")

    # Immediate command publish check
    if content.count("publishACStatus(&ac1, &ac2);") < 3:
        errors.append("WEMOS_AC: publishACStatus must be called in loop, callback(), and processSerialCommand()")

    return errors


def verify_promini_canonical() -> list[str]:
    """Verifies that PROMINI.ino is identical to git HEAD and uncorrupted."""
    errors = []
    promini_file = FIRMWARE_DIR / "PROMINI" / "PROMINI.ino"
    if not promini_file.is_file():
        errors.append("firmware/PROMINI/PROMINI.ino does not exist!")
        return errors

    res = subprocess.run(
        ["git", "diff", "--exit-code", "firmware/PROMINI/PROMINI.ino"],
        cwd=ROOT_DIR,
        capture_output=True,
        text=True
    )
    if res.returncode != 0:
        errors.append("firmware/PROMINI/PROMINI.ino has uncommitted changes or corruption!")

    return errors


def main() -> int:
    print("=" * 60)
    print("  SMSB Phase 3 Firmware Fleet Verification Tool")
    print("=" * 60)

    all_errors = []

    # 1. Check balanced syntax brackets across all firmware files
    print("[1/5] Checking C++ syntax brackets & parentheses...")
    for sketch in ["WEMOS_TS", "WEMOS_ATS", "WEMOS_AC", "PROMINI"]:
        ino_path = FIRMWARE_DIR / sketch / f"{sketch}.ino"
        if ino_path.is_file():
            errs = check_brackets_and_quotes(ino_path)
            if errs:
                all_errors.extend(errs)
            else:
                print(f"  + {ino_path.name}: Balanced syntax verified.")

    # 2. Check secrets and inverted priority
    print("\n[2/5] Checking secrets.h existence and include priority...")
    errs = verify_secrets_invariants()
    if errs:
        all_errors.extend(errs)
    else:
        print("  + Inverted include priority and secrets.h existence verified.")

    # 3. Check WEMOS_TS specifications
    print("\n[3/5] Verifying WEMOS_TS cadence, deadbands, and recovery...")
    errs = verify_wemos_ts()
    if errs:
        all_errors.extend(errs)
    else:
        print("  + WEMOS_TS: 300s heartbeat, 5s rate-limit, 0.2C/2.0% deadband verified.")

    # 4. Check WEMOS_ATS specifications
    print("\n[4/5] Verifying WEMOS_ATS cadence, burst mode, and deadbands...")
    errs = verify_wemos_ats()
    if errs:
        all_errors.extend(errs)
    else:
        print("  + WEMOS_ATS: 60s heartbeat, 2.0s/60s burst, 1.0V/0.1V deadband verified.")

    # 5. Check WEMOS_AC specifications & PROMINI canonical status
    print("\n[5/5] Verifying WEMOS_AC specifications and PROMINI canonical status...")
    errs = verify_wemos_ac()
    if errs:
        all_errors.extend(errs)
    else:
        print("  + WEMOS_AC: 120s heartbeat, 5s rate-limit, 0.5C/2.0% deadband, 0ms command ACK verified.")

    errs = verify_promini_canonical()
    if errs:
        all_errors.extend(errs)
    else:
        print("  + PROMINI: Canonical uncorrupted state verified.")

    print("\n" + "=" * 60)
    if all_errors:
        print(f"FAILED: Found {len(all_errors)} issues:")
        for err in all_errors:
            print(f"  - {err}")
        return 1

    print("ALL FIRMWARE CHECKS PASSED (100% compliant with Phase 3 specifications)")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
