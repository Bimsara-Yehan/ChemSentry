// Display helpers only. Nothing here is a safety value, a preset reading or
// zone metadata: zones, their inventories and every limit come from the API.

export const ROLE_LABELS = { viewer: 'Viewer', analyst: 'Analyst', admin: 'Admin' };

// Bounds of the simulator slider. These mirror the API's own validation for
// a DHT22 reading (api/models.py SensorReading: -40..80 C, 0..100 %), so the
// UI can never send a value the backend would reject.
export const SENSOR_RANGE = {
  temperature: { min: -40, max: 80 },
  humidity: { min: 0, max: 100 },
};

export function zoneName(zoneId) {
  return zoneId.replace(/_/g, ' ');
}

// A zone is described by what it actually stores (from the database-backed
// inventory), not by a label typed into the UI.
export function zoneSummary(chemicals = []) {
  if (chemicals.length === 0) return 'No chemicals assigned';
  if (chemicals.length <= 2) return chemicals.join(', ');
  return `${chemicals.slice(0, 2).join(', ')} +${chemicals.length - 2} more`;
}
