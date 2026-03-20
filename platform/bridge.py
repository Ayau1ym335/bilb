"""
║  Запуск:                                                        ║
║    Windows:  python bridge.py --port COM3                       ║                                                          ║
║  Опции:                                                         ║
║    --port   PORT     Serial-порт (обязательно)                  ║
║    --baud   BAUD     Скорость, default=115200                   ║
║    --output FILE     Выходной CSV, default=raw_data.csv         ║
║    --timeout SEC     Таймаут порта, default=2                   
"""

import serial
import json
import csv
import argparse
import sys
import os
import time
from datetime import datetime

CSV_HEADERS = [
    # Мета
    "pc_timestamp",          # Метка времени ПК (ISO 8601)
    "timestamp_ms",          # millis() с ESP32
    "scan_id",               # Номер скана
    "building_id",           # ID объекта
    "status",                # OK / WARNING / CRITICAL (от правил ESP32)
    "score",                 # Оценка деградации 0–100

    # Экологические
    "temperature_c",         # Температура, °C
    "humidity_pct",          # Влажность, %
    "pressure_hpa",          # Давление, hPa
    "light_lux",             # Освещённость, Lux

    # Структурные
    "tilt_deg",              # Наклон, градусы
    "accel_x",               # Ускорение X, м/с²
    "accel_y",               # Ускорение Y
    "accel_z",               # Ускорение Z
    "vibration",             # Вибрация: 0 или 1

    # Пространственные (дистанции HC-SR04)
    "dist_front_cm",         # Перед, см
    "dist_back_cm",          # Сзади
    "dist_left_cm",          # Слева
    "dist_right_cm",         # Справа
    "edge_detected",         # Край: 0 или 1

    # Список проблем (как строка)
    "issues",                # "HIGH_HUMIDITY,VIBRATION_DETECTED"

    # Колонка для разметки (День 2 — заполняется вручную или auto_label.py)
    "label",                 # 0=OK, 1=WARNING, 2=CRITICAL — ЗАПОЛНИТЬ ВРУЧНУЮ
]


def extract_row(data: dict) -> dict:
    env    = data.get("environmental", {})
    struct = data.get("structural",    {})
    spat   = data.get("spatial",       {})
    issues = data.get("issues", [])

    if isinstance(issues, list):
        issues_str = ",".join(str(i) for i in issues)
    else:
        issues_str = str(issues)

    return {
        "pc_timestamp":   datetime.now().isoformat(timespec="seconds"),
        "timestamp_ms":   data.get("timestamp_ms",  0),
        "scan_id":        data.get("scan_id",        0),
        "building_id":    data.get("building_id",    "BILB_001"),
        "status":         data.get("status",         "UNKNOWN"),
        "score":          data.get("score",          0.0),

        "temperature_c":  env.get("temperature_c",  0.0),
        "humidity_pct":   env.get("humidity_pct",   0.0),
        "pressure_hpa":   env.get("pressure_hpa",   0.0),
        "light_lux":      env.get("light_lux",       0.0),

        "tilt_deg":       struct.get("tilt_deg",    0.0),
        "accel_x":        struct.get("accel_x",     0.0),
        "accel_y":        struct.get("accel_y",     0.0),
        "accel_z":        struct.get("accel_z",     0.0),
        "vibration":      1 if struct.get("vibration", False) else 0,

        "dist_front_cm":  spat.get("front_cm",      999.0),
        "dist_back_cm":   spat.get("back_cm",        999.0),
        "dist_left_cm":   spat.get("left_cm",        999.0),
        "dist_right_cm":  spat.get("right_cm",       999.0),
        "edge_detected":  1 if spat.get("edge", False) else 0,

        "issues":         issues_str,
        "label":          "",   # Заполняется вручную на Дне 2
    }


def open_csv(filepath: str):
    is_new = not os.path.exists(filepath) or os.path.getsize(filepath) == 0
    fh = open(filepath, "a", newline="", encoding="utf-8")
    writer = csv.DictWriter(fh, fieldnames=CSV_HEADERS, extrasaction="ignore")
    if is_new:
        writer.writeheader()
        fh.flush()
        print(f"[BRIDGE] Created new file: {filepath}")
    else:
        print(f"[BRIDGE] Appending to existing file: {filepath}")
    return fh, writer


def print_live_row(row: dict, total: int):
    status_colors = {
        "OK":       "\033[92m",   # Зелёный
        "WARNING":  "\033[93m",   # Жёлтый
        "CRITICAL": "\033[91m",   # Красный
        "UNKNOWN":  "\033[90m",   # Серый
    }
    RESET = "\033[0m"
    color = status_colors.get(row["status"], "\033[90m")

    line = (
        f"  #{total:04d} | "
        f"scan={row['scan_id']:>3} | "
        f"{color}{row['status']:>8}{RESET} | "
        f"score={row['score']:>5.1f} | "
        f"T={row['temperature_c']:>5.1f}°C | "
        f"H={row['humidity_pct']:>5.1f}% | "
        f"vib={'Y' if row['vibration'] else 'N'} | "
        f"F={row['dist_front_cm']:>5.1f}cm | "
        f"issues={row['issues'] or 'NONE'}"
    )
    try:
        term_w = os.get_terminal_size().columns
        line = line[:term_w - 1]
    except OSError:
        pass
    print(line)


def run_bridge(port: str, baud: int, output: str, timeout: int):
    total_rows    = 0
    parse_errors  = 0
    last_status   = {}

    print(f"\n{'='*60}")
    print(f"  BILB Serial Bridge  |  port={port}  baud={baud}")
    print(f"  Output: {output}")
    print(f"  Press Ctrl+C to stop and save.")
    print(f"{'='*60}\n")

    fh, writer = open_csv(output)
    ser = None
    while ser is None:
        try:
            ser = serial.Serial(
                port=port,
                baudrate=baud,
                timeout=timeout,
                bytesize=serial.EIGHTBITS,
                parity=serial.PARITY_NONE,
                stopbits=serial.STOPBITS_ONE,
            )
            print(f"[BRIDGE] Connected to {port} at {baud} baud.\n")
        except serial.SerialException as e:
            print(f"[BRIDGE] Cannot open port: {e}")
            print(f"[BRIDGE] Retrying in 3 seconds... (Ctrl+C to abort)")
            try:
                time.sleep(3)
            except KeyboardInterrupt:
                print("\n[BRIDGE] Aborted.")
                fh.close()
                sys.exit(0)

    try:
        while True:
            try:
                raw_line = ser.readline()
            except serial.SerialException as e:
                print(f"\n[BRIDGE] Serial read error: {e}")
                print("[BRIDGE] Reconnecting in 3 seconds...")
                ser.close()
                time.sleep(3)
                ser = serial.Serial(port=port, baudrate=baud, timeout=timeout)
                continue

            if not raw_line:
                continue

            try:
                line = raw_line.decode("utf-8", errors="replace").strip()
            except Exception:
                continue
            if not line.startswith("[JSON]"):
                if line.startswith("["):
                    print(f"  \033[90mESP32: {line}\033[0m")
                continue

            json_str = line[len("[JSON]"):].strip()
            try:
                data = json.loads(json_str)
            except json.JSONDecodeError as e:
                parse_errors += 1
                print(f"\n[BRIDGE] JSON parse error #{parse_errors}: {e}")
                print(f"  Raw: {json_str[:120]}")
                continue

            row = extract_row(data)
            writer.writerow(row)
            fh.flush()

            total_rows += 1
            last_status = row
            print_live_row(row, total_rows)

    except KeyboardInterrupt:
        pass

    print(f"\n\n{'='*60}")
    print(f"  BILB Bridge stopped.")
    print(f"  Total rows saved : {total_rows}")
    print(f"  Parse errors     : {parse_errors}")
    if last_status:
        print(f"  Last status      : {last_status.get('status', '?')}")
        print(f"  Last score       : {last_status.get('score', '?')}")
    print(f"  File             : {os.path.abspath(output)}")
    print(f"{'='*60}\n")

    fh.close()
    if ser and ser.is_open:
        ser.close()

def main():
    parser = argparse.ArgumentParser(
        description="BILB Serial Bridge — ESP32 JSON → CSV",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--port", required=True,
        help="Serial port (e.g. COM3 or /dev/ttyUSB0)"
    )
    parser.add_argument(
        "--baud", type=int, default=115200,
        help="Baud rate"
    )
    parser.add_argument(
        "--output", default="raw_data.csv",
        help="Output CSV file path"
    )
    parser.add_argument(
        "--timeout", type=int, default=2,
        help="Serial read timeout, seconds"
    )

    args = parser.parse_args()

    try:
        import serial  # noqa: F401
    except ImportError:
        print("[ERROR] pyserial not installed")
        sys.exit(1)

    run_bridge(
        port=args.port,
        baud=args.baud,
        output=args.output,
        timeout=args.timeout,
    )


if __name__ == "__main__":
    main()