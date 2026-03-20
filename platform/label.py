"""
║  ВАЖНО: auto_label — это СТАРТОВАЯ ТОЧКА, не замена экспертной ║
║  разметке! После запуска открой labeled_data.csv и проверь     ║
║  каждую строку визуально. Правь label вручную там, где         ║
║  алгоритм ошибся (ложные срабатывания вибрации и т.п.).        ║
║  Запуск:                                                        ║
║    python auto_label.py                          # с дефолтами  ║
║    python auto_label.py --input raw_data.csv    # явно          ║
║    python auto_label.py --inspect               # показать стат ║
╚══════════════════════════════════════════════════════════════════╝
"""

import argparse
import sys
import os

class Thresholds:
    HUMIDITY_CRITICAL   = 70.0    # %
    HUMIDITY_WARNING    = 55.0
    TEMP_CRITICAL       = 40.0    # °C
    TEMP_WARNING        = 30.0
    TILT_CRITICAL       = 15.0    # градусы
    TILT_WARNING        =  5.0
    LIGHT_LOW           = 100.0   # Lux
    SCORE_WARNING       = 30.0    # порог оценки → WARNING
    SCORE_CRITICAL      = 60.0    # порог оценки → CRITICAL


def compute_label(row) -> tuple:
    score   = 0.0
    reasons = []
    status  = 0   # 0=OK, 1=WARNING, 2=CRITICAL

    hum  = float(row.get("humidity_pct",  0))
    temp = float(row.get("temperature_c", 0))
    tilt = abs(float(row.get("tilt_deg",  0)))
    vib  = int(row.get("vibration", 0))
    lux  = float(row.get("light_lux", 999))

    # ── Влажность 
    if hum >= Thresholds.HUMIDITY_CRITICAL:
        score += 40
        reasons.append(f"humidity={hum:.1f}%≥70")
        status = max(status, 2)  # CRITICAL
    elif hum >= Thresholds.HUMIDITY_WARNING:
        score += 20
        reasons.append(f"humidity={hum:.1f}%≥55")
        status = max(status, 1)

    # ── Вибрация 
    if vib == 1:
        score += 25
        reasons.append("vibration=YES")
        status = max(status, 1)

        if hum >= Thresholds.HUMIDITY_CRITICAL:
            score += 15
            reasons.append("COMBO:hum+vib→CRITICAL")
            status = 2

    # ── Температура 
    if temp >= Thresholds.TEMP_CRITICAL:
        score += 20
        reasons.append(f"temp={temp:.1f}°C≥40")
        status = max(status, 1)
    elif temp >= Thresholds.TEMP_WARNING:
        score += 8
        reasons.append(f"temp={temp:.1f}°C≥30")

    # ── Наклон 
    if tilt >= Thresholds.TILT_CRITICAL:
        score += 35
        reasons.append(f"tilt={tilt:.1f}°≥15")
        status = 2
    elif tilt >= Thresholds.TILT_WARNING:
        score += 10
        reasons.append(f"tilt={tilt:.1f}°≥5")
        status = max(status, 1)

    # ── Освещённость 
    if 0 < lux < Thresholds.LIGHT_LOW:
        score += 5
        reasons.append(f"light={lux:.0f}lux<100")

    # ── Score-based (если явные правила не дотянули) 
    if score >= Thresholds.SCORE_CRITICAL and status < 2:
        status = 2
        reasons.append(f"score={score:.0f}≥60")
    elif score >= Thresholds.SCORE_WARNING and status < 1:
        status = 1
        reasons.append(f"score={score:.0f}≥30")

    reason_str = "; ".join(reasons) if reasons else "all_normal"
    return status, reason_str


def label_csv(input_path: str, output_path: str) -> dict:
    try:
        import pandas as pd
    except ImportError:
        print("[ERROR] pandas not installed. Run: pip install pandas")
        sys.exit(1)

    if not os.path.exists(input_path):
        print(f"[ERROR] Input file not found: {input_path}")
        print("[TIP]   Run bridge.py first to collect data.")
        sys.exit(1)

    df = pd.read_csv(input_path, dtype=str)

    required = ["humidity_pct", "temperature_c", "vibration", "tilt_deg"]
    missing  = [c for c in required if c not in df.columns]
    if missing:
        print(f"[ERROR] Missing columns in CSV: {missing}")
        sys.exit(1)

    print(f"\n[LABEL] Input:  {input_path}  ({len(df)} rows)")

    labels  = []
    reasons = []
    conflicts = 0  # Случаи, когда auto-label не совпадает с колонкой status

    for _, row in df.iterrows():
        lbl, reason = compute_label(row)
        labels.append(lbl)
        reasons.append(reason)

        esp_status = str(row.get("status", "")).strip().upper()
        label_to_status = {0: "OK", 1: "WARNING", 2: "CRITICAL"}
        if esp_status and esp_status != "UNKNOWN":
            if label_to_status[lbl] != esp_status:
                conflicts += 1

    df["label"]        = labels
    df["label_reason"] = reasons  
    df.to_csv(output_path, index=False)
    counts = {0: labels.count(0), 1: labels.count(1), 2: labels.count(2)}
    total  = len(labels)

    stats = {
        "total":     total,
        "ok":        counts[0],
        "warning":   counts[1],
        "critical":  counts[2],
        "conflicts": conflicts,
        "output":    output_path,
    }
    return stats


def inspect_csv(path: str):
    try:
        import pandas as pd
    except ImportError:
        print("[ERROR] pip install pandas"); sys.exit(1)

    if not os.path.exists(path):
        print(f"[ERROR] File not found: {path}"); sys.exit(1)

    df = pd.read_csv(path)
    print(f"\n{'='*60}")
    print(f"  BILB Dataset Inspector: {path}")
    print(f"{'='*60}")
    print(f"  Total rows : {len(df)}")
    print(f"  Columns    : {list(df.columns)}\n")

    if "label" in df.columns:
        lbl = df["label"].value_counts().sort_index()
        label_names = {0: "OK (0)", 1: "WARNING (1)", 2: "CRITICAL (2)"}
        print("  Label distribution:")
        for k, v in lbl.items():
            pct = v / len(df) * 100
            bar = "█" * int(pct / 2)
            name = label_names.get(int(k), str(k))
            print(f"    {name:15s}: {v:4d} ({pct:5.1f}%)  {bar}")
        print()

    numeric_cols = [
        "temperature_c", "humidity_pct", "light_lux",
        "tilt_deg", "dist_front_cm", "score"
    ]
    available = [c for c in numeric_cols if c in df.columns]
    if available:
        print("  Sensor ranges (min → mean → max):")
        for col in available:
            series = pd.to_numeric(df[col], errors="coerce").dropna()
            if len(series) == 0:
                continue
            print(f"    {col:20s}: {series.min():8.2f} → {series.mean():8.2f} → {series.max():8.2f}")
        print()

    # Вибрация
    if "vibration" in df.columns:
        vib = pd.to_numeric(df["vibration"], errors="coerce")
        n_vib = int(vib.sum())
        print(f"  Vibration events : {n_vib} / {len(df)} ({n_vib/len(df)*100:.1f}%)")

    print(f"\n  [TIP] Open {path} in Excel/LibreOffice to review and fix labels.")
    print(f"{'='*60}\n")


def main():
    parser = argparse.ArgumentParser(
        description="BILB Day 2 — Auto-label raw_data.csv",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--input",   default="raw_data.csv",     help="Входной CSV")
    parser.add_argument("--output",  default="labeled_data.csv", help="Выходной CSV")
    parser.add_argument("--inspect", action="store_true",         help="Показать статистику файла и выйти")
    parser.add_argument("--inspect-file", default=None,           help="Файл для --inspect (по умолчанию --output)")
    args = parser.parse_args()

    if args.inspect:
        target = args.inspect_file or args.output
        # Если labeled ещё нет — смотрим на raw
        if not os.path.exists(target):
            target = args.input
        inspect_csv(target)
        return

    # ── Автоматическая разметка 
    stats = label_csv(args.input, args.output)

    total = stats["total"]
    print(f"\n{'='*60}")
    print(f"  BILB Auto-Labeler — Done!")
    print(f"{'='*60}")
    print(f"  Rows processed: {total}")
    print(f"  OK       (0)  : {stats['ok']:4d}  ({stats['ok']/total*100:.1f}%)")
    print(f"  WARNING  (1)  : {stats['warning']:4d}  ({stats['warning']/total*100:.1f}%)")
    print(f"  CRITICAL (2)  : {stats['critical']:4d}  ({stats['critical']/total*100:.1f}%)")
    if stats["conflicts"] > 0:
        print(f"\n  [!] Conflicts with ESP32 status: {stats['conflicts']} rows")
        print(f"      Review these rows manually in {args.output}")
    print(f"\n  Output: {os.path.abspath(args.output)}")
    print(f"\n  NEXT STEP: Open {args.output} in Excel/LibreOffice.")
    print(f"  Check 'label' and 'label_reason' columns.")
    print(f"  Fix any misclassified rows, then run day3_train.py.")
    print(f"{'='*60}\n")

    inspect_csv(args.output)


if __name__ == "__main__":
    main()