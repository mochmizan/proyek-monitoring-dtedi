import sys
import os
import uuid
import math
import random
from datetime import datetime, UTC, timedelta

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "server", "v5")))

from databasev5 import SessionLocal
from modelsv5 import temperature_data, ats_data, dev_table

def seed_complete_30d_history():
    db = SessionLocal()
    try:
        now = datetime.now(UTC)
        
        # Clear existing telemetry for seeded devices so we have a clean realistic distribution
        db.query(temperature_data).delete()
        db.query(ats_data).delete()
        db.commit()

        ts_devices = [
            ("AA:BB:CC:11:22:01", 24.5, 55.0), # Server Room Temp
            ("AA:BB:CC:11:22:03", 26.8, 60.0), # Network Temp
            ("AA:BB:CC:11:22:04", 23.2, 52.0), # Battery Temp
        ]

        # 1. Generate points across 30 days:
        # - Past 30d to 7d: 1 point every 2 hours
        # - Past 7d to 24h: 1 point every 30 mins
        # - Past 24h to 0: 1 point every 10 mins
        
        timestamps = []
        # Days 30 to 7 (every 2 hours)
        for h in range(30 * 24, 7 * 24, -2):
            timestamps.append(now - timedelta(hours=h))
        # Days 7 to 1 (every 30 mins)
        for m in range(7 * 24 * 60, 24 * 60, -30):
            timestamps.append(now - timedelta(minutes=m))
        # Last 24 hours (every 10 mins)
        for m in range(24 * 60, -1, -10):
            timestamps.append(now - timedelta(minutes=m))

        print(f"Generating {len(timestamps)} time-series points per device across 30 days...")

        for dev_id, base_temp, base_hum in ts_devices:
            trows = []
            for idx, ts in enumerate(timestamps):
                # Daily sinusoidal temperature cycle (peaks at 14:00, coolest at 04:00)
                hour_of_day = ts.hour + ts.minute / 60.0
                daily_cycle = 2.0 * math.sin((hour_of_day - 8) * math.pi / 12.0)
                noise = random.uniform(-0.3, 0.3)
                temp = round(base_temp + daily_cycle + noise, 1)
                
                # Inverse humidity cycle
                hum_cycle = -4.0 * math.sin((hour_of_day - 8) * math.pi / 12.0)
                humid = round(max(30.0, min(95.0, base_hum + hum_cycle + random.uniform(-1.0, 1.0))), 1)

                trows.append(
                    temperature_data(
                        data_id=uuid.uuid4().hex,
                        dev_id=dev_id,
                        timestamp=ts,
                        temp=temp,
                        humid=humid
                    )
                )
            db.bulk_save_objects(trows)

        # ATS Device history
        ats_dev_id = "AA:BB:CC:11:22:02"
        arows = []
        for idx, ts in enumerate(timestamps):
            # Normal grid PLN 220V with minor fluctuations
            pln_val = 220.0 + random.uniform(-3.0, 3.5)
            genset_val = 0.0
            aki_val = 13.2 + random.uniform(-0.15, 0.15)
            state_val = "PLN"

            # Occasional simulated outage event 3 days ago
            if 68 <= (now - ts).total_seconds() / 3600 <= 72:
                pln_val = 0.0
                genset_val = 221.5 + random.uniform(-2.0, 2.0)
                state_val = "GENSET"

            arows.append(
                ats_data(
                    data_id=uuid.uuid4().hex,
                    dev_id=ats_dev_id,
                    timestamp=ts,
                    state=state_val,
                    pln=round(pln_val, 1),
                    genset=round(genset_val, 1),
                    aki=round(aki_val, 1),
                    rem_hour=0.0,
                    rem_min=0.0,
                    rem_sec=0.0,
                    auto_mode=True,
                    emergency=False
                )
            )
        db.bulk_save_objects(arows)

        db.commit()
        print(f"Successfully seeded complete 30-day history ({len(timestamps)} points per device)!")
    except Exception as e:
        db.rollback()
        print("Error seeding 30d history:", e)
    finally:
        db.close()

if __name__ == "__main__":
    seed_complete_30d_history()
