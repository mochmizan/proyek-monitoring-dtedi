# backfillv5.py
# Script untuk memigrasikan data telemetri TS dan ATS lama dari data_table ke tabel temperature_data dan ats_data.

import logging
from databasev5 import SessionLocal
from modelsv5 import data_table, temperature_data, ats_data

# Konfigurasi logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s"
)

def backfill(session_factory=None):
    Session = session_factory or SessionLocal
    db = Session()
    try:
        logging.info("Memulai proses backfill data...")
        
        # Ambil semua data telemetri lama
        telemetry_rows = db.query(data_table).all()
        logging.info(f"Ditemukan {len(telemetry_rows)} baris telemetri di data_table.")
        
        ts_count = 0
        ats_count = 0
        ts_inserted = 0
        ats_inserted = 0
        
        for row in telemetry_rows:
            payload = row.payload
            if not payload:
                continue
            
            dev_type = payload.get("DEV_TYPE")
            if dev_type == "TS":
                ts_count += 1
                # Cek apakah sudah ada di temperature_data
                exists = db.query(temperature_data).filter(temperature_data.data_id == row.data_id).first()
                if not exists:
                    temp = payload.get("TEMP")
                    humid = payload.get("HUMID")
                    
                    if temp is not None and humid is not None:
                        new_ts = temperature_data(
                            data_id=row.data_id,
                            dev_id=row.dev_id,
                            timestamp=row.timestamp,
                            temp=float(temp),
                            humid=float(humid)
                        )
                        db.add(new_ts)
                        ts_inserted += 1
            
            elif dev_type == "ATS":
                ats_count += 1
                # Cek apakah sudah ada di ats_data
                exists = db.query(ats_data).filter(ats_data.data_id == row.data_id).first()
                if not exists:
                    state = payload.get("STATE")
                    pln = payload.get("PLN")
                    genset = payload.get("GENSET")
                    aki = payload.get("AKI")
                    rem_hour = payload.get("REM_HOUR")
                    rem_min = payload.get("REM_MIN")
                    rem_sec = payload.get("REM_SEC")
                    auto_mode = payload.get("AUTO_MODE")
                    emergency = payload.get("EMERGENCY")
                    
                    # Fallback jika field missing
                    if emergency is None:
                        emergency = False
                    
                    if None not in (state, pln, genset, aki, rem_hour, rem_min, rem_sec, auto_mode):
                        new_ats = ats_data(
                            data_id=row.data_id,
                            dev_id=row.dev_id,
                            timestamp=row.timestamp,
                            state=str(state),
                            pln=float(pln),
                            genset=float(genset),
                            aki=float(aki),
                            rem_hour=float(rem_hour),
                            rem_min=float(rem_min),
                            rem_sec=float(rem_sec),
                            auto_mode=bool(auto_mode),
                            emergency=bool(emergency)
                        )
                        db.add(new_ats)
                        ats_inserted += 1
        
        # Commit semua data baru
        db.commit()
        
        logging.info("Proses backfill SELESAI.")
        logging.info(f"TS: Total di data_table = {ts_count}, Berhasil dimasukkan = {ts_inserted}")
        logging.info(f"ATS: Total di data_table = {ats_count}, Berhasil dimasukkan = {ats_inserted}")
        
        # Validasi hitungan akhir
        total_ts_in_db = db.query(temperature_data).count()
        total_ats_in_db = db.query(ats_data).count()
        logging.info(f"Verifikasi Database: Total rows temperature_data = {total_ts_in_db}")
        logging.info(f"Verifikasi Database: Total rows ats_data = {total_ats_in_db}")
        
    except Exception as e:
        db.rollback()
        logging.error(f"Gagal melakukan backfill: {e}")
        raise
    finally:
        db.close()

if __name__ == "__main__":
    backfill()
