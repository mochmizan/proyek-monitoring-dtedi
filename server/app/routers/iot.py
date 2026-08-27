# app/routers/iot.py
import logging
import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from databasev5 import get_db
from modelsv5 import hub_table, dev_table, data_table, temperature_data, ats_data
from schemasv5 import IotPayload, UnapprovedDeviceAlert, TSData, ATSData
from app.dependencies import verify_hub_identity
from app.core.rate_limit import limiter
from app.services.alert_engine import evaluate_device_thresholds
from app.services.presence import resolve_offline_on_telemetry

router = APIRouter(tags=["iot"])


@router.post("/api/iot/unapproved")
@limiter.limit("60/minute")
def receive_unapproved_alert(
    request: Request,
    payload: UnapprovedDeviceAlert,
    hub: hub_table = Depends(verify_hub_identity),
    db: Session = Depends(get_db),
):
    try:
        exist = db.get(dev_table, payload.DEV_ID)
        now_utc = datetime.now(UTC)
        if exist is None:
            new_pending_device = dev_table(
                dev_id=payload.DEV_ID,
                dev_name=payload.DEV_NAME,
                dev_type=payload.DEV_TYPE,
                hub_id=hub.hub_id,
                is_active=False,
                created_at=now_utc,
            )
            db.add(new_pending_device)
            db.commit()
            return {"status": "registered_as_pending"}
        else:
            if not exist.is_active and exist.room_id is None:
                exist.created_at = now_utc
                db.commit()
            return {"status": "already_exists"}
    except Exception as e:
        logging.exception("Exception in receive_unapproved_alert")
        db.rollback()
        raise HTTPException(status_code=500, detail="Internal Server Error")


@router.post("/api/iot")
@limiter.limit("120/minute")
def receive_iot(
    request: Request,
    device: IotPayload,
    hub: hub_table = Depends(verify_hub_identity),
    db: Session = Depends(get_db),
):
    try:
        registered_device = db.get(dev_table, device.DEV_ID)
        if not registered_device or not registered_device.is_active:
            raise HTTPException(status_code=403, detail="Device not authorized")

        now_utc = datetime.now(UTC)
        resolve_offline_on_telemetry(db, registered_device, now_utc)

        if isinstance(device, TSData):
            new_data = temperature_data(
                data_id=str(uuid.uuid4()),
                dev_id=device.DEV_ID,
                timestamp=now_utc,
                temp=device.TEMP,
                humid=device.HUMID,
            )
            db.add(new_data)
        elif isinstance(device, ATSData):
            new_data = ats_data(
                data_id=str(uuid.uuid4()),
                dev_id=device.DEV_ID,
                timestamp=now_utc,
                state=device.STATE,
                pln=device.PLN,
                genset=device.GENSET,
                aki=device.AKI,
                rem_hour=device.REM_HOUR,
                rem_min=device.REM_MIN,
                rem_sec=device.REM_SEC,
                auto_mode=device.AUTO_MODE,
                emergency=device.EMERGENCY,
            )
            db.add(new_data)
        else:
            new_data = data_table(
                data_id=str(uuid.uuid4()),
                dev_id=device.DEV_ID,
                dev_name=device.DEV_NAME,
                timestamp=now_utc,
                payload=device.model_dump(mode="json"),
            )
            db.add(new_data)

            payload_dict = device.model_dump(mode="json")
            if "TEMP" in payload_dict and payload_dict["TEMP"] is not None:
                temp_val = float(payload_dict["TEMP"])
                humid_val = float(payload_dict["HUMID"]) if "HUMID" in payload_dict and payload_dict["HUMID"] is not None else None
                temp_record = temperature_data(
                    data_id=str(uuid.uuid4()),
                    dev_id=device.DEV_ID,
                    timestamp=now_utc,
                    temp=temp_val,
                    humid=humid_val,
                )
                db.add(temp_record)

        payload_dict = device.model_dump(mode="json")
        evaluate_device_thresholds(db=db, dev=registered_device, payload=payload_dict, timestamp=now_utc)

        db.commit()
        return {"status": "received"}

    except HTTPException:
        raise
    except Exception as e:
        logging.exception("Exception in receive_iot")
        db.rollback()
        raise HTTPException(status_code=500, detail="Failed to record data")
