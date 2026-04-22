from __future__ import annotations

import shutil
from datetime import datetime
from pathlib import Path
from typing import Any

import joblib

import prediction_service
from model.train_model import train


BACKEND_DIR = Path(__file__).resolve().parent
MODEL_DIR = BACKEND_DIR / "model"

MODEL_ARTIFACTS = [
    "attendance_model.pkl",
    "feature_columns.pkl",
    "training_meta.pkl",
    "historical_daily.pkl",
]


def _artifact_path(name: str) -> Path:
    return MODEL_DIR / name


def _prev_path(name: str) -> Path:
    return MODEL_DIR / f"{name}.prev.pkl"


def backup_artifacts() -> None:
    """Copy each artifact to <name>.prev.pkl in backend/model/."""
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    for name in MODEL_ARTIFACTS:
        src = _artifact_path(name)
        if not src.exists():
            raise FileNotFoundError(f"Missing model artifact: {src}")
        shutil.copy2(src, _prev_path(name))


def restore_artifacts() -> None:
    """
    Swap .prev.pkl files back into place.
    Raise FileNotFoundError if any .prev.pkl is missing.
    """
    for name in MODEL_ARTIFACTS:
        prev = _prev_path(name)
        if not prev.exists():
            raise FileNotFoundError(f"Missing previous artifact: {prev}")
    for name in MODEL_ARTIFACTS:
        shutil.copy2(_prev_path(name), _artifact_path(name))


def _load_metrics() -> dict[str, float]:
    meta_path = _artifact_path("training_meta.pkl")
    if not meta_path.exists():
        return {}
    meta = joblib.load(meta_path)
    metrics = meta.get("metrics", {}) if isinstance(meta, dict) else {}
    out: dict[str, float] = {}
    for k in ("mae", "mdape", "wmape", "r2"):
        if k in metrics:
            try:
                out[k] = float(metrics[k])
            except Exception:
                pass
    return out


def retrain_with_safety_net() -> dict[str, Any]:
    """
    1. Load current metrics from training_meta.pkl (old_metrics)
    2. Call backup_artifacts()
    3. Try: call train() from train_model. On ANY exception, call
       restore_artifacts() and re-raise
    4. Compare new vs old MdAPE:
       - If new MdAPE > old MdAPE * 1.20:
           call restore_artifacts()
           return {"status": "reverted", "reverted_reason": "..."}
       - Else: return {"status": "success"}
    5. After success: call prediction_service.reload_artifacts()
    6. Return status, old_metrics, new_metrics, improvement deltas,
       trained_at ISO timestamp
    """
    old_metrics = _load_metrics()
    backup_artifacts()

    trained_at = datetime.utcnow().isoformat() + "Z"
    try:
        train()
    except Exception:
        # Ensure we never leave the system without a working model
        restore_artifacts()
        raise

    new_metrics = _load_metrics()

    # Safety threshold: revert if MdAPE degrades by >20%
    old_mdape = float(old_metrics.get("mdape", 0.0) or 0.0)
    new_mdape = float(new_metrics.get("mdape", 0.0) or 0.0)
    if old_mdape > 0 and new_mdape > old_mdape * 1.20:
        restore_artifacts()
        prediction_service.reload_artifacts()
        return {
            "status": "reverted",
            "reverted_reason": "New model MdAPE degraded by more than 20% vs previous model.",
            "old_metrics": old_metrics,
            "new_metrics": new_metrics,
            "improvement": {
                "mdape_delta": new_mdape - old_mdape,
                "wmape_delta": float(new_metrics.get("wmape", 0.0) or 0.0)
                - float(old_metrics.get("wmape", 0.0) or 0.0),
                "r2_delta": float(new_metrics.get("r2", 0.0) or 0.0)
                - float(old_metrics.get("r2", 0.0) or 0.0),
            },
            "trained_at": trained_at,
        }

    prediction_service.reload_artifacts()
    return {
        "status": "success",
        "old_metrics": old_metrics,
        "new_metrics": new_metrics,
        "improvement": {
            "mdape_delta": new_mdape - old_mdape,
            "wmape_delta": float(new_metrics.get("wmape", 0.0) or 0.0)
            - float(old_metrics.get("wmape", 0.0) or 0.0),
            "r2_delta": float(new_metrics.get("r2", 0.0) or 0.0)
            - float(old_metrics.get("r2", 0.0) or 0.0),
        },
        "trained_at": trained_at,
    }

