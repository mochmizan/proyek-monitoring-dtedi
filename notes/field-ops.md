Field ops quick facts (unsynthesized; promote to wiki when stable)

- VPS: ssh genset@100.108.98.30 (key auth works from this machine). sudoers allows ONLY `systemctl restart smsb-api` — no root shell.
- Normalized smsb-api unit points to WorkingDirectory=/opt/smsb/server; legacy /opt/smsb/SERVERv5/v5 archived and hook rsync compat block removed (2026-09-03). Root required for unit install/daemon-reload; unprivileged genset deploy user restarts service via sudoers.
- Prod login admin/admin123 (Tier 2 weak; rotate before any public exposure).
- Hub Pi: eth0 10.33.102.10, AP 192.168.72.242 (smsb-iot), NTP 10.33.102.172. Real hub id hs109rs-hub-01 (3 devices incl ATS 68:C6:3A:D7:60:47).
- Genset physically NOT wired to the ATS as of 31/8 (reads ~55V floating). RST re-latch on old firmware confirmed live — see wiki workstream-ats-emergency-2026-08.
- Reflash of proofed PROMINI + WEMOS_ATS pending physical access (avrdude / esptool). WEMOS_ATS dir is canonical since 7bf3098 — don't look for fixed_wemos_mqtt_raspi.
- Dummy hub RASPI_HUB_01 deleted 31/8 via new DELETE /api/hubs/{id}.
