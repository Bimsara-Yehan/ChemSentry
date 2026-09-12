"""Unit normaliser for extracted SDS values (M1, Lab 07).

Converts extracted values to a consistent internal representation so that
comparison is possible even when different SDS documents use different units:
    - Temperature: everything normalised to °C
    - Exposure limits: normalised to mg/m³ (with molecular weight if available)

Why is this needed?
    One SDS might say "store below 77 °F" and another "store below 25 °C"
    for the same chemical.  Without normalisation, the conflict detector
    (M3) would see two different numbers and flag a false conflict.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class NormalisedValue:
    """A value normalised to standard units."""

    original_value: float
    original_unit: str
    normalised_value: float
    normalised_unit: str
    conversion_applied: str  # human-readable description of the conversion


def fahrenheit_to_celsius(f: float) -> float:
    """Convert Fahrenheit to Celsius.

    Formula: C = (F - 32) × 5/9.

    Args:
        f: Temperature in Fahrenheit.

    Returns:
        Temperature in Celsius, rounded to 1 decimal.
    """
    return round((f - 32) * 5 / 9, 1)


def celsius_to_fahrenheit(c: float) -> float:
    """Convert Celsius to Fahrenheit.

    Args:
        c: Temperature in Celsius.

    Returns:
        Temperature in Fahrenheit, rounded to 1 decimal.
    """
    return round(c * 9 / 5 + 32, 1)


def normalise_temperature(value: float, unit: str) -> NormalisedValue:
    """Normalise a temperature value to °C.

    Args:
        value: Numeric temperature value.
        unit: Unit string — must contain 'F' or 'C'.

    Returns:
        NormalisedValue in °C.

    Example:
        >>> normalise_temperature(77.0, "°F")
        NormalisedValue(original_value=77.0, ..., normalised_value=25.0, normalised_unit='°C')
    """
    unit_upper = unit.upper().replace("°", "").strip()

    if "F" in unit_upper:
        normalised = fahrenheit_to_celsius(value)
        return NormalisedValue(
            original_value=value,
            original_unit=unit,
            normalised_value=normalised,
            normalised_unit="°C",
            conversion_applied=f"{value}°F → {normalised}°C",
        )
    else:
        # Already in °C (or assumed °C).
        return NormalisedValue(
            original_value=value,
            original_unit=unit,
            normalised_value=value,
            normalised_unit="°C",
            conversion_applied="no conversion (already °C)",
        )


def ppm_to_mg_m3(
    ppm: float, molecular_weight: Optional[float] = None
) -> NormalisedValue:
    """Convert ppm (parts per million) to mg/m³.

    Uses the standard conversion at 25°C and 1 atm:
        mg/m³ = ppm × (molecular_weight / 24.45)

    If molecular weight is not available, returns the original value
    with a note — we don't guess molecular weights.

    Args:
        ppm: Concentration in ppm.
        molecular_weight: Molecular weight in g/mol (optional).

    Returns:
        NormalisedValue in mg/m³, or original ppm if MW is unknown.
    """
    if molecular_weight is not None and molecular_weight > 0:
        mg_m3 = round(ppm * molecular_weight / 24.45, 2)
        return NormalisedValue(
            original_value=ppm,
            original_unit="ppm",
            normalised_value=mg_m3,
            normalised_unit="mg/m³",
            conversion_applied=f"{ppm} ppm × ({molecular_weight}/24.45) = {mg_m3} mg/m³",
        )
    else:
        return NormalisedValue(
            original_value=ppm,
            original_unit="ppm",
            normalised_value=ppm,
            normalised_unit="ppm",
            conversion_applied="no conversion (molecular weight unavailable)",
        )


def normalise_value(
    value: float,
    unit: str,
    molecular_weight: Optional[float] = None,
) -> NormalisedValue:
    """Normalise any extracted value to its standard unit.

    Routes to the appropriate converter based on the unit string.

    Args:
        value: Numeric value to normalise.
        unit: Original unit string (e.g. '°F', 'ppm', 'mg/m³', '%').
        molecular_weight: MW in g/mol (only needed for ppm→mg/m³).

    Returns:
        NormalisedValue with the conversion applied (or identity).
    """
    unit_clean = unit.strip().lower()

    # Temperature
    if "f" in unit_clean and ("°" in unit_clean or "deg" in unit_clean):
        return normalise_temperature(value, unit)
    if "c" in unit_clean and ("°" in unit_clean or "deg" in unit_clean):
        return normalise_temperature(value, unit)

    # Concentration
    if unit_clean == "ppm":
        return ppm_to_mg_m3(value, molecular_weight)

    # Already in target unit or no conversion available.
    return NormalisedValue(
        original_value=value,
        original_unit=unit,
        normalised_value=value,
        normalised_unit=unit,
        conversion_applied="no conversion applied",
    )
