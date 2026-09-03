import sys
import os
import uuid

# Add server to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "server")))

from databasev5 import SessionLocal
from modelsv5 import rooms, dev_table, device_threshold_config, hub_table, User, temperature_data, ats_data
from datetime import datetime, UTC

def seed():
    db = SessionLocal()
    try:
        # 1. Ensure Hub
        hub = db.query(hub_table).filter(hub_table.hub_id == 'hs109rs-hub-01').first()
        if not hub:
            hub_key = os.getenv("HUB_KEY")
            if not hub_key:
                raise SystemExit("HUB_KEY env required for seeding (no hardcoded live secret).")
            hub = hub_table(
                hub_id='hs109rs-hub-01',
                hub_name='HS109 Edge Hub',
                hub_key=hub_key,
                is_active=True
            )
            db.add(hub)
            db.flush()

        # 2. Rooms
        rooms_data = [
            ("room-server", "Server Room"),
            ("room-network", "Network Closet"),
            ("room-battery", "Battery Room"),
        ]
        
        for r_id, r_name in rooms_data:
            r = db.query(rooms).filter(rooms.id == r_id).first()
            if not r:
                r = rooms(id=r_id, name=r_name, hub_id=hub.hub_id)
                db.add(r)
                db.flush()
                print(f"Created room: {r_name}")

        # 3. Devices
        devices_data = [
            ("AA:BB:CC:11:22:01", "Server Room Temp", "TS", "room-server", 35.0, 45.0, 24.5, 55.0),
            ("AA:BB:CC:11:22:02", "Server Room ATS", "ATS", "room-server", 65.0, 75.0, None, None),
            ("AA:BB:CC:11:22:03", "Network Temp", "TS", "room-network", 50.0, 50.0, 26.8, 60.0),
            ("AA:BB:CC:11:22:04", "Battery Temp", "TS", "room-battery", 40.0, 60.0, 23.1, 52.0),
        ]

        for mac, name, dtype, rid, mx, my, temp, hum in devices_data:
            dev = db.query(dev_table).filter(dev_table.dev_id == mac).first()
            if not dev:
                dev = dev_table(
                    dev_id=mac,
                    dev_name=name,
                    dev_type=dtype,
                    hub_id=hub.hub_id,
                    room_id=rid,
                    marker_x=mx,
                    marker_y=my,
                    is_active=True
                )
                db.add(dev)
                db.flush()

                # Thresholds
                is_ats = dtype == "ATS"
                thresh = device_threshold_config(
                    dev_id=mac,
                    warning=11.8 if is_ats else 28.0,
                    critical=11.2 if is_ats else 32.0,
                    hysteresis=0.2 if is_ats else 0.5,
                    debounce_seconds=60
                )
                db.add(thresh)

                # Seed initial telemetry
                now = datetime.now(UTC)
                if dtype == "TS":
                    tdata = temperature_data(
                        data_id=uuid.uuid4().hex,
                        dev_id=mac,
                        timestamp=now,
                        temp=temp,
                        humid=hum
                    )
                    db.add(tdata)
                elif dtype == "ATS":
                    adata = ats_data(
                        data_id=uuid.uuid4().hex,
                        dev_id=mac,
                        timestamp=now,
                        state="PLN",
                        pln=220.5,
                        genset=0.0,
                        aki=13.2,
                        rem_hour=0.0,
                        rem_min=0.0,
                        rem_sec=0.0,
                        auto_mode=True,
                        emergency=False
                    )
                    db.add(adata)
                print(f"Created device: {name} ({mac})")

        # 4. Pending Unpaired Device for testing pairing workflow
        pending_mac = "AA:BB:CC:99:99:99"
        pdev = db.query(dev_table).filter(dev_table.dev_id == pending_mac).first()
        if not pdev:
            pdev = dev_table(
                dev_id=pending_mac,
                dev_name="Discovered SHT30 Node",
                dev_type="TS",
                hub_id=hub.hub_id,
                room_id=None,
                is_active=False
            )
            db.add(pdev)
            print(f"Created pending discovery device: {pending_mac}")

        db.commit()
        print("Demo seed completed successfully!")
    except Exception as e:
        db.rollback()
        print(f"Error seeding demo data: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    seed()
