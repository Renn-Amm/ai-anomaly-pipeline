"""Unit tests — Pydantic model validation."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.models.schemas import TelemetryBatch, TelemetryPoint


class TestTelemetryPointValidation:
    def test_valid_point_accepted(self):
        p = TelemetryPoint(metric_name="cpu_usage", value=42.0, source="srv")
        assert p.value == 42.0

    def test_metric_name_with_special_chars_rejected(self):
        with pytest.raises(ValidationError):
            TelemetryPoint(metric_name="bad name!", value=1.0, source="s")

    def test_metric_name_too_long_rejected(self):
        with pytest.raises(ValidationError):
            TelemetryPoint(metric_name="a" * 200, value=1.0, source="s")

    def test_too_many_tags_rejected(self):
        with pytest.raises(ValidationError):
            TelemetryPoint(
                metric_name="cpu",
                value=1.0,
                source="s",
                tags={f"k{i}": "v" for i in range(25)},
            )

    def test_extra_fields_rejected(self):
        with pytest.raises(ValidationError):
            TelemetryPoint(metric_name="cpu", value=1.0, source="s", unknown_field="bad")


class TestTelemetryBatchValidation:
    def _point(self) -> dict:
        return {"metric_name": "cpu", "value": 1.0, "source": "s"}

    def test_valid_batch_accepted(self):
        assert len(TelemetryBatch(points=[self._point()]).points) == 1

    def test_empty_batch_rejected(self):
        with pytest.raises(ValidationError):
            TelemetryBatch(points=[])

    def test_batch_too_large_rejected(self):
        with pytest.raises(ValidationError):
            TelemetryBatch(points=[self._point()] * 10_001)

    def test_extra_fields_on_batch_rejected(self):
        with pytest.raises(ValidationError):
            TelemetryBatch(points=[self._point()], evil="payload")