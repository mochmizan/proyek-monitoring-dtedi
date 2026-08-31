---
type: workstream
governed_by: AGENTS.md
links: [wiki/entity-ats-firmware-chain.md, wiki/workstream-ats-emergency-2026-08.md, wiki/workstream-flexible-scheduling.md]
sources: [docs/FIRMWARE_PROOFING_PLAN_2026-08-31.md, firmware/PROMINI/PROMINI.ino, firmware/WEMOS_ATS/WEMOS_ATS.ino, commit:dcfeb84, commit:7bf3098]
updated: 2026-08-31
---

# Firmware proofing workstream

**Status: committed (dcfeb84 / 7bf3098); bench soak + fleet flash pending.**

A 14-gap audit (docs/FIRMWARE_PROOFING_PLAN_2026-08-31.md, P0/P1) of the ATS pair produced the proofed sketches. PROMINI gained: WDT 8S with MCUSR capture, I2C probe before LCD use, relay pins initialized HIGH, PLN hysteresis 210/190V with median voting (window SIZE 20, LONG 60, tie→hasilWait), genset start attempts MAX 5→3, `<SGM>` guarded by autoMode, bounded `char[65]` serial, `<T,unixtime>` + `RTC_OK`, EEPROM sanity guard (>1.7e9 and < now+8d), and autonomous WARMUP removed entirely. WEMOS_ATS (canonical after absorbing `fixed_wemos_mqtt_raspi` in 7bf3098) gained non-blocking WiFi retry, publish-only-while-connected with 500/2000ms throttle, snprintf-built clientIds, and bounded parsing.

Fleet status 2026-08-31: field unit 68:C6:3A:D7:60:47 (HS109SR-ATS) still runs pre-proof firmware; `WEMOS_ATS` dir is canonical on disk but not yet flashed anywhere. Plan is a 24h bench soak, then fleet flash via avrdude (Pro Mini) + esptool (ESP8266), after which the emergency workstream's root cause is gone.
