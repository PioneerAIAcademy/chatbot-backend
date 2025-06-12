import json
import os
import sys
from typing import Any

from loguru import _Logger, logger

# 1) Remove Loguru's default handler
logger.remove()


# 2) Custom sink writes directly to stdout
def _custom_sink(msg: Any) -> None:
    record = msg.record

    if os.environ.get("AWS_LAMBDA_FUNCTION_NAME"):
        # AWS Lambda → emit a single JSON object per line
        log_entry = {
            "timestamp": record["time"].isoformat(),
            "level": record["level"].name,
            "logger": record["name"],
            "message": record["message"],
            **record["extra"],  # merge any extra fields at top level
        }
        sys.stdout.write(json.dumps(log_entry) + "\n")
    else:
        # Local → human-readable
        t = record["time"].strftime("%Y-%m-%d %H:%M:%S")
        lvl = record["level"].name.ljust(5)
        nm = record["name"].ljust(30)
        text = record["message"]
        extra = record["extra"]

        if extra:
            try:
                extra_json = json.dumps(extra)
            except (TypeError, ValueError):
                extra_json = str(extra)
            text = f"{text} | {extra_json}"

        sys.stdout.write(f"{t} | {lvl} | {nm} | {text}\n")


# 3) Add our sink, with only {message} ever parsed by Loguru itself
log_level = os.getenv("LOG_LEVEL", "INFO").upper()
logger.add(
    _custom_sink,
    level=log_level,
    format="{message}",  # just this one placeholder
    colorize=False,  # ANSI off—parsing of {…} still skipped because format is static
)


def get_logger() -> _Logger:
    """
    Return the customized Loguru logger
    """
    return logger
