from typing import Any, Dict, List

import mysql.connector

from app.core.analyze_settings import analyze_settings


def get_conn():
    return mysql.connector.connect(
        host=analyze_settings.MYSQL_HOST,
        port=analyze_settings.MYSQL_PORT,
        user=analyze_settings.MYSQL_USER,
        password=analyze_settings.MYSQL_PASSWORD,
        database=analyze_settings.MYSQL_DB,
        charset=analyze_settings.MYSQL_CHARSET,
    )


def upsert_analyze_with_detections(payload: Dict[str, Any]) -> int:
    conn = get_conn()
    try:
        conn.start_transaction()
        cur = conn.cursor()

        # Ensure unique key on (cctv_id, analyzed_date) exists in DB schema
        sql_analyze = (
            "INSERT INTO analyzes (cctv_id, analyzed_date, message, detection_count, severity_score, image_data) "
            "VALUES (%s, %s, %s, %s, %s, FROM_BASE64(%s)) "
            "ON DUPLICATE KEY UPDATE message=VALUES(message), detection_count=VALUES(detection_count), "
            "severity_score=VALUES(severity_score), image_data=VALUES(image_data)"
        )
        cur.execute(
            sql_analyze,
            (
                payload["cctv_id"],
                payload["analyzed_date"],
                payload.get("message"),
                payload["detection_count"],
                payload.get("severity_score"),
                payload["image_base64"].decode("ascii"),
            ),
        )

        # Get analyze_id (inserted or existing)
        if cur.lastrowid:
            analyze_id = cur.lastrowid
        else:
            # select id
            cur2 = conn.cursor()
            cur2.execute(
                "SELECT id FROM analyzes WHERE cctv_id=%s AND analyzed_date=%s",
                (payload["cctv_id"], payload["analyzed_date"]),
            )
            row = cur2.fetchone()
            analyze_id = int(row[0]) if row else 0
            cur2.close()

        # Replace detections for this analyze_id
        cur.execute("DELETE FROM detections WHERE analyze_id=%s", (analyze_id,))
        sql_det = (
            "INSERT INTO detections (analyze_id, class_id, damage_type, confidence, bbox, severity, area, severity_score) "
            "VALUES (%s, %s, %s, %s, CAST(%s AS JSON), %s, %s, %s)"
        )
        det_rows: List[tuple] = []
        for d in payload["detections"]:
            det_rows.append(
                (
                    analyze_id,
                    d["class_id"],
                    d["damage_type"],
                    d["confidence"],
                    str(d["bbox"]).replace("'", '"'),
                    d["severity"],
                    d.get("area"),
                    d.get("severity_score"),
                )
            )
        if det_rows:
            cur.executemany(sql_det, det_rows)

        conn.commit()
        return analyze_id
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
