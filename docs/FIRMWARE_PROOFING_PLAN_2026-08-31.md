# Firmware ATS Proofing Plan — 2026-08-31

> Status: PLAN ONLY — no firmware flashed or edited. Recall: old `PROMINI.ino` weekly `Sunday 18:00` drifted to `11:11` `2026-08-30` → `EMERGENCY_GENSET` latch `68:C6:3A:D7:60:47` `SERVERv5/v5/hubgatev5.db` despite `PLN 220V` ; `genset 55V < BATAS 200V` 5× retry.

## Objective
Harden `PROMINI` (Pro Mini ATS FSM) + `fixed_wemos_mqtt_raspi` (WEMOS bridge) for 1GB VPS / 3s poll fleet: no WDT boot-loop, no weekly drift, no false warmup, no heap crash, single emergency policy with manual `RST` release, relay-safe boot, voltage hysteresis.

## Scope
- `firmware/PROMINI/PROMINI.ino:1-897`
- `firmware/fsm_w_serial/fsm_w_serial.ino:1-660` (reference, will be aligned to PROMINI weekly)
- `firmware/fixed_wemos_mqtt_raspi/fixed_wemos_mqtt_raspi.ino:1-~360`
- `firmware/WEMOS_ATS/WEMOS_ATS.ino` shim (keep)
- `firmware/common/secrets.h.example`
- Out of scope: `WEMOS_TS` `WEMOS_AC` OLED, `HARDWARE_OLED_TEST`

## Audit — Top Gaps (P1 = must, P2 = should)

| # | Area | PROMINI | fsm_w_serial | WEMOS | Gap | Risk |
|---|------|---------|--------------|-------|-----|------|
| 1 | WDT boot | `155 WDTO_2S` no `MCUSR=0` | `88 MCUSR=0;wdt_disable() 140 WDTO_8S` | ESP SDK | 2s fires during `delay 1000` `212` + `rtc/EEPROM` after WDT reset | boot-loop |
| 2 | WDT hang | `383` only top `wdt_reset()` | `267` | — | `do_lcd 288 lcd.clear()` I2C `0x27` hang >2s | freeze |
| 3 | RTC sync | `181-194 lostPower→adjust(__DATE__)` | `105-121` | — | compile-time stale, no `<T,unixtime>` resync | drift 5h |
| 4 | EEPROM bounds | `882-897 >1700000000` only | `126 >now+8d` | — | future `0xFFFFFFFE` → never warmup | silent failure |
| 5 | Relay glitch | `4/5` `pinMode` then `HIGH` | `2/3` same | — | `OUTPUT` before `HIGH` momentary `LOW` crank | starter pulse |
| 6 | Voltage | `822 checkVolt <batas` single `500` sens | `616` | — | no hysteresis `210/190` single sample noise | chatter `WAIT` |
| 7 | Voting | `SIZE10 LONG20` `cariModus` tie→false | same | — | 5s/10s too short, tie false | false `WAIT_GENSET` |
| 8 | Emergency | `MAX 5` `596` state `EMERGENCY_GENSET` vs `3` `fsm:11` | `473` no state | `58` display | fleet 5 vs 3 divergence | confusion |
| 9 | RST guard | `261 any <RST,*>` clears | `248 <RST,rst>` exact | — | accidental clear | latch bypass |
|10 | Serial heap | `86 char[65] strchr` ok | `String(buf)` heap | `String` heap | AVR/ESP fragmentation | crash long uptime |
|11 | SGM guard | `274 only gensetOnState` not `autoMode` | `238 autoMode==false` but direct `relay2` | `105` | `SGM on` in `AUTO` | unsafe |
|12 | Warmup freq | `WARMUP_DAY 0 18:00` weekly `869` | `86400` daily `38` | — | weekly vs daily fleet | wrong cadence |
|13 | Warmup persist | `isWarmup` RAM only `59` `682` put at end | same | — | brownout mid-5min → immediate retrigger | wear |
|14 | WEMOS block | — | — | `81 setup_wifi block 10s delay` | blocks `client.loop` | ESP WDT |

Full 23-row audit in task `ses_faaa00a96ffeRPzmOBa0qU5K1f`.

## Proposal — Grouped Fixes (no flash until approved)

### A. WDT + Power (P1)
- PROMINI: first line `MCUSR=0; wdt_disable();` last `wdt_enable(WDTO_8S)` align `fsm:88-140`, `wdt_reset()` before/after `delay 1000` `212` and inside `do_lcd` after `Wire` ops; `WDTO_2S→8S`.
- Relay: `digitalWrite(relay,HIGH)` before `pinMode(OUTPUT)` both relays `4/5` (`fsm` `2/3` standardize via `pins.h` header `relay1=4 relay2=5`), external pull-up already, add `BOOT_GUARD_MS 500` no crank after reset.
- Verify: `avrdude` flash, power-cycle 3×, `WDT` timeout test via `while(1)` 9s, scope relay `HIGH` at boot 10ms.

### B. RTC + Warmup Canonical (P1)
- Choose weekly `Sunday 18:00 Asia/Jakarta` canonical (existing `PROMINI:66-67`), backport to `fsm` (remove `86400` daily `38`), keep `EEPROM nextWarmup` `0` slot `>1700000000 && <now+8d` `fsm:128` both.
- Add `<T,unixtime>` command: WEMOS `NTP → rtc.adjust(DateTime(unixtime))` `processCommand` `fsm:248` style, `PROMINI` add `else if typeLen=1 && T` `EEPROM.put` `lastWarmup`. Gate `lostPower` behind `hour() 6-19` sanity?
- Degraded flag: `<C,GET>` add `RTC_OK 0/1` `EMERGENCY 1/0` `fsm:217` already, bridge forward `doc["RTC_OK"]` `fixed_wemos:344` → `alert_engine` `event_log metric=rtc_offline` hysteresis.
- Warmup persist at start: `nextWarmup = getNextWarmup(now)` `save` at `isWarmup=true` `330` not end `682`, revert on failure.

### C. Voltage + Voting Hardening (P1)
- `checkVolt` hysteresis: `on >210V off<190V` `BATAS_VAC 200` `822` add `190/210`, `AKI 12 → 11.5/12.5`.
- `readVAC` median 3 samples `10ms` `ZMPT.getRmsVoltage()` average `readVDC` same, `SENSITIVITAS 500` per-unit cal comment.
- `SIZE 10→20 (10s) LONG_SIZE 20→60 (30s)` `109` tie → keep `hasilWait` previous, not `false`.

### D. Emergency Policy Unified (P1)
- Unify `EMERGENCY_RETRY_LIMIT 3` both (`5→3` less wear), keep `EMERGENCY_GENSET` state (fsm lacks it, add back) for LCD `GENSET FAILURE! 377` + LED `pin2`; fsm add `pin2` `emergencyGensetPin`.
- Tighten `PROMINI:261` to `dataLen==3 && strncmp "rst"` exact (like `fsm:248`), add optional auto-recovery `isGensetOn true && emergencyNotified 1h` → `WAIT` (log `RESET_OK auto`).
- LCD alternates `EMERGENCY` / state `1s` blink, keep `BTN 7/8` nav `288`.

### E. Serial + Manual Safety (P1)
- Port `fsm`+WEMOS `String` → `char[65] strchr/strncmp` `PROMINI:86-419` bounded, overflow `len=0` + `<ERR,overflow>` counter `56-58` `emergency` style; WEMOS guard `payload.length>=200` `233` keep.
- WEMOS `setup_wifi` non-blocking: return immediate, retry in `loop` with `millis` backoff `3000→30000` `165`, gate `<C,GET>` `227` behind `client.connected()` throttle 2s.
- `SGM` both require `!autoMode` early return `704` `autoMode` check; `fsm` replace direct `digitalWrite(relay2)` `240` with full `GENSET_ON/OFF` FSM `PROMINI:722-762` + `THREE_SECONDS` sequencing.

### F. LCD/I2C Resilience (P2)
- `Wire.beginTransmission(0x27) endTransmission()==0` probe like WEMOS OLED `206`, `lcdAvailable` flag skip `do_lcd` if fail, `lcd.clear()` only on `state change` not every `500ms`, `sprintf "%02ld"` cap `sisaJam>99 → 99`.

### G. EEPROM Wear (P3)
- `EEPROM.put` only if `savedTime != nextWarmup` dirty check, add magic `0xA5` + `CRC8` header at `0:4` bytes.

## Non-Goals
- No TLS change (campus LAN `smsb-iot 192.168.72.242` private per `AGENTS.md` Secrets)
- No server cron change (already `APScheduler Asia/Jakarta` `schedules` authoritative, firmware weekly is fallback)
- No `WEMOS_TS/AC` changes
- No `WEMOS_ATS` shim removal (keep `#warning` shim `12` lines)

## Verification
- `just firmware-check` `arduino-cli compile --fqbn arduino:avr:pro PROMINI` + `esp8266:esp8266:generic WEMOS` 0 errors
- `pytest tests/test_verify_*.py` still `107`
- Bench: brownout 3× `VIN 5V→3V` relay stays `HIGH`, WDT 9s reset → `WAIT`, `RTC` unplug → `RTC_OK 0` MQTT, warmup `nextWarmup` Monday `18:00` not Sunday `11:11`, emergency 3× `genset 55V` → `EMERGENCY` `pln 220V` stays until `RST,rst` → `PLN`, manual `M,manual + SGM,on` blocked in `autoMode`

## Rollout
1. PR `firmware/ats-proofing` with diffs `PROMINI.ino` + `fsm_w_serial.ino` align + `fixed_wemos...ino` bridge
2. Flash bench Pro Mini via `avrdude` + WEMOS via `esptool` on spare hub, soak 24h log `<EMERGENCY/` `<STATE/` every `500ms`
3. Field flash one hub `68:C6:3A:D7:60:47` first (current `EMERGENCY`), `RST` then warmup soak Sunday `18:00` → confirm `GENSET 5min → PLN` no latch if `genset>210V`
4. Fleet flash remainder, `just deploy` no server change

## Alternatives Considered
- Daily vs weekly: keep weekly per `FIRMWARE_ALIGNMENT_REPORT:321` `WARMUP_DAY 0` hardware-team v2
- Auto-recovery emergency after 1h: rejected for now (safety latch until human), keep manual `RST` only
- `String` keep: rejected heap fragmentation AVR long uptime
