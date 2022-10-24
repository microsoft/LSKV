from dateutil.parser import parse, ParserError
from datetime import datetime, timedelta

out_file = "workspace/sandbox_0/out"

with open(out_file, "r", encoding="utf-8") as f:
    lines = f.readlines()
    last_us = 0
    last = ""
    violations = 0
    for i, line in enumerate(lines):
        parts = line.split()
        if not parts:
            continue
        time = parts[0]
        try:
            time = parse(time)
        except ParserError:
            continue
        time = time.replace(tzinfo=None)
        time_us = int((time - datetime(1970, 1, 1)) / timedelta(microseconds=1))
        if last_us:
            diff = time_us - last_us
            if diff > 45000:
                violations += 1
                print(f"violation at line {i} diff={diff}us last={last} now={time}")
        last = time
        last_us = time_us
    print("total violations", violations)
